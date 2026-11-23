"""A run must always say HOW it ended, and each failure must leave an unambiguous trace."""
import io, json, contextlib, glob
import pytest
from lar import (GraphExecutor, FunctionalNode, RouterNode, ToolNode, HumanJuryNode, ClearErrorNode, GraphState)
from lar.logger import AuditLogger
from lar.node import PausedForHuman


def fn(name, nxt=None):
    n = FunctionalNode(lambda s: s.set(name, True), next_node=nxt)
    n._node_id = name
    return n


def run(start, tmp_path, state=None, max_steps=100, **ex_kw):
    ex = GraphExecutor(logger=AuditLogger(log_dir=str(tmp_path), hmac_secret="k"), **ex_kw)
    with contextlib.redirect_stdout(io.StringIO()):
        steps = list(ex.run_step_by_step(start, state or {}, max_steps=max_steps))
    saved = json.load(open(glob.glob(str(tmp_path / "run_*[0-9a-f].json"))[0]))
    return ex, steps, saved


def test_router_unknown_key_without_default_is_a_loud_error(tmp_path):
    r = RouterNode(lambda s: "banana", {"yes": fn("yes_path")})
    r._node_id = "route"
    _, steps, saved = run(fn("start", r), tmp_path)
    assert steps[-1]["outcome"] == "error"
    assert "banana" in steps[-1]["error"]
    assert saved["summary"]["status"] == "failed"


def test_router_with_default_still_works(tmp_path):
    r = RouterNode(lambda s: "banana", {"yes": fn("yes_path")}, default_node=fn("fallback"))
    _, steps, saved = run(r, tmp_path)
    assert [s["outcome"] for s in steps] == ["success", "success"]
    assert saved["summary"]["status"] == "completed"


def test_pause_is_not_reported_as_failure(tmp_path):
    j = HumanJuryNode(prompt="ok?", choices=["approve", "reject"], output_key="d", next_node=fn("after"),
                      decision_type="X", automation_boundary={"X": "always_human"})
    j._node_id = "jury"
    _, steps, saved = run(j, tmp_path)
    assert steps[-1]["outcome"] == "paused"
    assert saved["summary"]["status"] == "paused"
    assert issubclass(PausedForHuman, RuntimeError)          # old `except RuntimeError` still works


def test_handled_error_is_not_sticky(tmp_path):
    t = ToolNode(lambda s: 1 / 0, ["__state__"], None, next_node=fn("never"), error_node=fn("handler", fn("more")))
    t._node_id = "tool"
    _, steps, saved = run(t, tmp_path)
    assert [s["outcome"] for s in steps] == ["error", "success", "success"]
    assert saved["summary"]["status"] == "completed"


def test_same_error_message_twice_is_flagged_twice(tmp_path):
    b = ToolNode(lambda s: 1 / 0, ["__state__"], None, next_node=fn("never"))
    b._node_id = "toolB"
    a = ToolNode(lambda s: 1 / 0, ["__state__"], None, next_node=fn("never2"), error_node=fn("handler", b))
    a._node_id = "toolA"
    _, steps, saved = run(a, tmp_path)
    assert [s["outcome"] for s in steps] == ["error", "success", "error"]
    assert saved["summary"]["status"] == "failed"


def test_clear_error_node_still_works(tmp_path):
    t = ToolNode(lambda s: 1 / 0, ["__state__"], None, next_node=fn("never"), error_node=ClearErrorNode(fn("more")))
    _, steps, _ = run(t, tmp_path)
    assert [s["outcome"] for s in steps] == ["error", "success", "success"]


def test_exception_type_and_traceback_are_logged(tmp_path):
    def boom(state):
        raise KeyError("missing_field")
    n = FunctionalNode(boom)
    n._node_id = "boom"
    _, steps, saved = run(n, tmp_path)
    assert steps[-1]["error_type"] == "KeyError"
    assert "boom" in steps[-1]["traceback"] and "Traceback" in steps[-1]["traceback"]
    assert saved["summary"]["status"] == "failed"
    assert saved["summary"]["ended_at_node"] == "boom"


def test_normal_run_records_completed(tmp_path):
    ex, _, saved = run(fn("a", fn("b")), tmp_path)
    assert saved["summary"]["status"] == "completed"
    assert saved["summary"]["ended_at_node"] == "b"
    assert ex.last_run["status"] == "completed"


def test_fatigue_limit_status(tmp_path):
    loop = FunctionalNode(lambda s: None)
    loop._node_id = "loop"
    loop.next_node = loop
    _, steps, saved = run(loop, tmp_path, max_node_fatigue=5)
    assert saved["summary"]["status"] == "fatigue_limit"


def test_circuit_breaker_status_and_no_false_trip_at_exact_limit(tmp_path):
    # runs that END exactly at max_steps are completed, not tripped
    chain = fn("a", fn("b", fn("c")))
    _, steps, saved = run(chain, tmp_path, max_steps=3)
    assert saved["summary"]["status"] == "completed"
    assert all(s["node"] != "CIRCUIT_BREAKER" for s in steps)

    # a run that WOULD continue is stopped and says so
    loop = FunctionalNode(lambda s: None)
    loop._node_id = "loop"
    loop.next_node = loop
    sub = tmp_path / "second"
    sub.mkdir()
    _, steps, saved = run(loop, sub, max_steps=4, max_node_fatigue=1000)
    assert steps[-1]["node"] == "CIRCUIT_BREAKER"
    assert saved["summary"]["status"] == "circuit_breaker"


def test_set_count_tracks_writes():
    s = GraphState({})
    assert s.set_count("k") == 0
    s.set("k", 1); s["k"] = 1
    assert s.set_count("k") == 2


# ---- replay a failing step from a saved log
def test_replay_reproduces_and_verifies_a_fix(tmp_path):
    from lar.replay import load_run, failing_steps, replay_step

    def calc(state):
        return 100 / state.get("divisor")
    broken = ToolNode(calc, ["__state__"], "out", next_node=None)
    broken._node_id = "calc"
    _, _, saved = run(fn("setup", broken), tmp_path, state={"divisor": 0})
    path = glob.glob(str(tmp_path / "run_*[0-9a-f].json"))[0]
    runlog = load_run(path)
    bad = failing_steps(runlog)
    assert [b["node"] for b in bad] == ["calc"]

    again = replay_step(runlog, bad[0]["step"], broken)
    assert again["error"] and "division" in again["error"]

    fixed = ToolNode(lambda s: 100 / (s.get("divisor") or 1), ["__state__"], "out", next_node=None)
    ok = replay_step(runlog, bad[0]["step"], fixed)
    assert ok["error"] is None and ok["state_after"]["out"] == 100
