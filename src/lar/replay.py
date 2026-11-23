"""
lar.replay
==========
Turn a saved run log into a reproducible failure.

A run log stores ``state_before`` for every step, so a failing step can be re-run in isolation: same
node, same input state. Use it to reproduce a production failure, to prove a fix, and to keep the
failing case as a permanent regression test.

Limits you should know:
  * The log is redacted by the logger's PII redactor, so replaying a step restores the REDACTED values.
    A step whose behaviour depends on a redacted field may behave differently.
  * An ``LLMNode`` step will call the model again; its answer can differ. Replay is exact for the
    deterministic parts of a graph (tools, routers, functional nodes), which is where most failures are.
  * Internal ``__`` keys that the executor strips from the saved state (prompt, token metadata) are absent.
"""
import copy
import json
from typing import Any, Dict, List

from .state import GraphState


def load_run(path: str) -> Dict[str, Any]:
    """Load a saved ``run_<id>.json`` log."""
    with open(path) as f:
        return json.load(f)


def failing_steps(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Steps that ended in ``error`` or ``paused`` (the circuit-breaker marker is included)."""
    return [s for s in run.get("steps", []) if s.get("outcome") in ("error", "paused")]


def replay_step(run: Dict[str, Any], step: int, node) -> Dict[str, Any]:
    """
    Re-execute ``node`` on the exact ``state_before`` that step ``step`` saw.

    Returns ``{"error", "error_type", "next_node", "state_after"}``. ``error`` is None when the node
    finished cleanly. Nothing is written to any log.
    """
    entry = next((s for s in run.get("steps", []) if s.get("step") == step), None)
    if entry is None:
        raise KeyError(f"step {step} not found in run {run.get('run_id')!r}")
    state = GraphState(copy.deepcopy(entry["state_before"]))
    writes_before = state.set_count("last_error")
    error, error_type, next_node = None, None, None
    try:
        next_node = node.execute(state)
        if state.get("last_error") and state.set_count("last_error") > writes_before:
            error = str(state.get("last_error"))
    except Exception as e:                         # replay reports the failure; it must not raise it
        error, error_type = str(e), type(e).__name__
    return {"error": error, "error_type": error_type, "next_node": next_node, "state_after": state.get_all()}
