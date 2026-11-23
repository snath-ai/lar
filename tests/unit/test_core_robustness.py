"""Regression tests for problems found by reading node.py (token budget, batch timeout, fallbacks)."""
import io, json, time, threading, contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
import importlib
lar_node = importlib.import_module("lar.node")   # `lar.node` the module, not the @node decorator
from lar import LLMNode, BatchNode, FunctionalNode, GraphState


class _Msg:
    def __init__(self, c): self.content = c; self.reasoning_content = None
class _Choice:
    def __init__(self, c): self.message = _Msg(c)
class _Resp:
    def __init__(self, text, usage=None): self.choices = [_Choice(text)]; self.usage = usage


def _run(node, state):
    with contextlib.redirect_stdout(io.StringIO()):
        return node.execute(state)


def test_token_budget_is_enforced_even_when_provider_omits_usage(monkeypatch):
    monkeypatch.setattr(lar_node, "completion", lambda **kw: _Resp("a" * 400, usage=None))
    llm = LLMNode(model_name="x/y", prompt_template="b" * 400, output_key="out")
    s = GraphState({"token_budget": 1000})
    _run(llm, s)
    assert s.get("token_budget") < 1000                       # estimated spend was charged
    assert s.get("__last_run_metadata")["usage_estimated"] is True


def test_missing_usage_cannot_loop_forever_on_a_budget(monkeypatch):
    monkeypatch.setattr(lar_node, "completion", lambda **kw: _Resp("a" * 4000, usage=None))
    llm = LLMNode(model_name="x/y", prompt_template="b" * 4000, output_key="out")
    s = GraphState({"token_budget": 1500})
    for _ in range(3):
        _run(llm, s)
    assert s.get("token_budget") <= 0
    _run(llm, s)
    assert "budget" in (s.get("last_error") or "").lower()


def test_think_tags_removed_even_without_usage(monkeypatch):
    monkeypatch.setattr(lar_node, "completion", lambda **kw: _Resp("<think>secret plan</think>final answer", usage=None))
    llm = LLMNode(model_name="x/y", prompt_template="hi", output_key="out")
    s = GraphState({})
    _run(llm, s)
    assert s.get("out") == "final answer"


def _slow(seconds, key):
    def f(state):
        time.sleep(seconds)
        state.set(key, True)
    return FunctionalNode(f)


def test_batch_timeout_skips_slow_branch_without_blocking_or_raising():
    fast = FunctionalNode(lambda s: s.set("fast_done", True))
    slow = _slow(3.0, "slow_done")
    batch = BatchNode([fast, slow], branch_timeout=0.3)
    s = GraphState({})
    t0 = time.time()
    _run(batch, s)
    assert time.time() - t0 < 1.5                              # did not wait for the 3 s branch
    assert s.get("fast_done") is True
    assert s.get("slow_done") is None                          # its result was not merged
    assert s.get("_batch_timeouts")
    assert "timed out" in (s.get("last_error") or "")


def test_batch_without_timeout_still_merges_everything():
    batch = BatchNode([FunctionalNode(lambda s: s.set("a", 1)), FunctionalNode(lambda s: s.set("b", 2))])
    s = GraphState({})
    _run(batch, s)
    assert s.get("a") == 1 and s.get("b") == 2


class _Provider(BaseHTTPRequestHandler):
    seen = []
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Provider.seen.append(body["model"])
        if body["model"] == "primary":
            self.send_response(500); self.end_headers()
            self.wfile.write(b'{"error":{"message":"boom","type":"server_error"}}')
            return
        out = {"id": "x", "object": "chat.completion", "created": 1, "model": body["model"],
               "choices": [{"index": 0, "message": {"role": "assistant", "content": "from-" + body["model"]},
                            "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())


@pytest.fixture
def provider(monkeypatch):
    # Other tests replace lar.node.completion with a fake and do not restore it; use the real one here.
    import litellm
    monkeypatch.setattr(lar_node, "completion", litellm.completion)
    srv = HTTPServer(("127.0.0.1", 0), _Provider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Provider.seen = []
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _llm(base, fallbacks):
    return LLMNode(model_name="openai/primary", prompt_template="hi", output_key="out", max_retries=1,
                   fallbacks=fallbacks, generation_config={"api_base": base, "api_key": "x", "num_retries": 0})


def test_fallback_model_is_really_used_when_primary_fails(provider):
    s = GraphState({})
    _run(_llm(provider, ["openai/backup"]), s)
    assert s.get("out") == "from-backup"
    assert _Provider.seen == ["primary", "backup"]


def test_without_fallbacks_the_primary_failure_is_raised(provider):
    with pytest.raises(Exception):
        _run(_llm(provider, None), GraphState({}))
