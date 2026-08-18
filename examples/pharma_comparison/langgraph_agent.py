"""
LangGraph implementation of the same Adverse Event Triage Agent, built with
LangGraph's own real primitives: StateGraph, conditional edges, interrupt()
for human-in-the-loop, and a MemorySaver checkpointer for pause/resume.
Same model, same scenario, same attacks as lar_agent.py.
"""
import json
import hashlib
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama

from scenario import CLASSIFY_SYSTEM, hard_severity_check, MODEL_NAME_LANGCHAIN
from actions import file_routine_note, notify_regulatory_contact

try:
    from langgraph.types import interrupt
except ImportError:
    from langgraph.errors import GraphInterrupt as interrupt  # fallback for older versions

SIGNING_SECRET = "pharmacovigilance_hmac_key"


def _sign(case_id: str, note: str) -> str:
    return hashlib.sha256(f"{case_id}:{note}:{SIGNING_SECRET}".encode()).hexdigest()


class TriageState(TypedDict):
    case_id: str
    note: str
    llm_classification: Optional[str]
    hard_severity_flag: Optional[bool]
    final_classification: Optional[str]
    approval_signature: Optional[str]
    approved_note_snapshot: Optional[str]
    outcome: Optional[str]
    result: Optional[str]


llm = ChatOllama(model=MODEL_NAME_LANGCHAIN, temperature=0)


def classify_node(state: TriageState) -> dict:
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user", "content": f"Clinical note:\n{state['note']}"},
    ]
    resp = llm.invoke(messages)
    raw = resp.content.strip()
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1].replace("json", "", 1).strip() if len(parts) >= 2 else raw
    try:
        parsed = json.loads(raw)
        llm_class = str(parsed.get("classification", "ROUTINE")).upper()
    except Exception:
        llm_class = "ROUTINE"

    # Same deterministic backstop as the Lár side -- independent of the LLM.
    hard_flag = hard_severity_check(state["note"])
    final_class = "SEVERE" if (llm_class == "SEVERE" or hard_flag) else "ROUTINE"
    print(f"    [LangGraph] LLM said: {llm_class} | hard backstop: {hard_flag} | final: {final_class}")
    return {"llm_classification": llm_class, "hard_severity_flag": hard_flag, "final_classification": final_class}


def route_on_classification(state: TriageState) -> str:
    return "approval" if state["final_classification"] == "SEVERE" else "execute_routine"


def approval_node(state: TriageState) -> dict:
    # LangGraph's real HITL primitive -- pauses the graph here, resumed via
    # Command(resume=...) against the same thread_id / checkpoint.
    decision = interrupt({"case_id": state["case_id"], "note": state["note"], "ask": "Approve escalation?"})
    sig = _sign(state["case_id"], state["note"])
    print(f"    [LangGraph] Officer approves via interrupt() for {state['case_id']}. Signing: {sig[:8]}...")
    return {"approval_signature": sig}


def execute_severe_node(state: TriageState) -> dict:
    case_id = state["case_id"]
    note = state["note"]  # whatever is CURRENT in state when this node runs
    stored_sig = state.get("approval_signature")
    expected_sig = _sign(case_id, note)
    if not stored_sig:
        return {"outcome": "blocked_no_approval"}
    if stored_sig != expected_sig:
        print("    [LangGraph] STALE AUTHORITY DETECTED: signature no longer matches current case content.")
        print(f"       stored={stored_sig[:8]}...  expected={expected_sig[:8]}...")
        return {"outcome": "blocked_stale_authority"}
    result = notify_regulatory_contact(case_id, note)
    return {"outcome": "executed", "result": result}


def execute_routine_node(state: TriageState) -> dict:
    result = file_routine_note(state["case_id"], state["note"])
    return {"outcome": "executed_routine", "result": result}


builder = StateGraph(TriageState)
builder.add_node("classify", classify_node)
builder.add_node("approval", approval_node)
builder.add_node("execute_severe", execute_severe_node)
builder.add_node("execute_routine", execute_routine_node)
builder.set_entry_point("classify")
builder.add_conditional_edges(
    "classify", route_on_classification, {"approval": "approval", "execute_routine": "execute_routine"}
)
builder.add_edge("approval", "execute_severe")
builder.add_edge("execute_severe", END)
builder.add_edge("execute_routine", END)

checkpointer = MemorySaver()
app = builder.compile(checkpointer=checkpointer)


def run_case(case_id: str, note: str, thread_id: str = None, verbose: bool = True):
    config = {"configurable": {"thread_id": thread_id or case_id}}
    result = app.invoke({"case_id": case_id, "note": note}, config=config)
    if "__interrupt__" in result:
        if verbose:
            print("    [LangGraph] Interrupted for human approval — resuming with 'approve'")
        result = app.invoke(Command(resume="approve"), config=config)
    return result


# --- Minimal approval->execute graph for Attack 2, isolating LangGraph's own
#     interrupt/checkpoint/resume mechanism from the classifier stage ---
approval_builder = StateGraph(TriageState)
approval_builder.add_node("approval", approval_node)
approval_builder.add_node("execute_severe", execute_severe_node)
approval_builder.set_entry_point("approval")
approval_builder.add_edge("approval", "execute_severe")
approval_builder.add_edge("execute_severe", END)
approval_checkpointer = MemorySaver()
approval_app = approval_builder.compile(checkpointer=approval_checkpointer)


def run_attack_2_stale_authority():
    from scenario import ATTACK_2_CASE_A, ATTACK_2_CASE_B_DRIFT

    case_id = ATTACK_2_CASE_A["case_id"]
    config = {"configurable": {"thread_id": f"attack2-{case_id}"}}

    print(f"    [LangGraph] Phase 1: submitting Case A ({case_id}) for approval")
    approval_app.invoke({"case_id": case_id, "note": ATTACK_2_CASE_A["note"]}, config=config)

    print("    [LangGraph] Phase 2: case content DRIFTS via checkpoint update_state()")
    approval_app.update_state(config, {"note": ATTACK_2_CASE_B_DRIFT["note"]})

    result = approval_app.invoke(Command(resume="approve"), config=config)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# HARDENED VARIANT — same interrupt()/checkpointer primitives, but structured
# per LangGraph's own documented guidance: a node containing interrupt() re-runs
# ENTIRELY on resume, so anything computed in that same node (like _sign() on
# state["note"]) gets recomputed from whatever is CURRENT at resume time, not
# what was true when the pause happened. That's what made the naive version
# above vulnerable -- not a LangGraph ceiling, a node that mixed "pause" and
# "compute a security-critical value" in one function body.
#
# Fix: commit a snapshot to the checkpoint in its OWN node BEFORE the interrupt
# node runs, so the snapshot is safe from anything that mutates state["note"]
# afterward.
# ─────────────────────────────────────────────────────────────────────────────

def snapshot_node(state: TriageState) -> dict:
    """Runs and commits BEFORE the interrupt -- this write is safely
    checkpointed prior to any pause, so a later update_state() on 'note'
    cannot touch it."""
    print(f"    [LangGraph] Snapshotting note at approval time (pre-interrupt, committed).")
    return {"approved_note_snapshot": state["note"]}


def interrupt_only_node(state: TriageState) -> dict:
    """ONLY calls interrupt() -- no security-critical computation in here,
    since this function body re-runs on resume."""
    interrupt({"case_id": state["case_id"], "note": state["approved_note_snapshot"], "ask": "Approve escalation?"})
    sig = _sign(state["case_id"], state["approved_note_snapshot"])
    print(f"    [LangGraph] Officer approves via interrupt() for {state['case_id']}. Signing (from snapshot): {sig[:8]}...")
    return {"approval_signature": sig}


def execute_severe_hardened_node(state: TriageState) -> dict:
    case_id = state["case_id"]
    current_note = state["note"]  # possibly drifted
    stored_sig = state.get("approval_signature")
    expected_sig_for_current = _sign(case_id, current_note)
    if not stored_sig:
        return {"outcome": "blocked_no_approval"}
    if stored_sig != expected_sig_for_current:
        print("    [LangGraph] STALE AUTHORITY DETECTED (hardened): signature was bound to the")
        print(f"       snapshot taken at approval time, not the current (possibly drifted) note.")
        return {"outcome": "blocked_stale_authority"}
    result = notify_regulatory_contact(case_id, current_note)
    return {"outcome": "executed", "result": result}


hardened_builder = StateGraph(TriageState)
hardened_builder.add_node("snapshot", snapshot_node)
hardened_builder.add_node("interrupt_only", interrupt_only_node)
hardened_builder.add_node("execute_severe", execute_severe_hardened_node)
hardened_builder.set_entry_point("snapshot")
hardened_builder.add_edge("snapshot", "interrupt_only")
hardened_builder.add_edge("interrupt_only", "execute_severe")
hardened_builder.add_edge("execute_severe", END)
hardened_checkpointer = MemorySaver()
hardened_app = hardened_builder.compile(checkpointer=hardened_checkpointer)


def run_attack_2_hardened():
    from scenario import ATTACK_2_CASE_A, ATTACK_2_CASE_B_DRIFT

    case_id = ATTACK_2_CASE_A["case_id"]
    config = {"configurable": {"thread_id": f"attack2-hardened-{case_id}"}}

    print(f"    [LangGraph] Phase 1: submitting Case A ({case_id}) for approval (hardened graph)")
    hardened_app.invoke({"case_id": case_id, "note": ATTACK_2_CASE_A["note"]}, config=config)

    print("    [LangGraph] Phase 2: case content DRIFTS via checkpoint update_state()")
    hardened_app.update_state(config, {"note": ATTACK_2_CASE_B_DRIFT["note"]})

    result = hardened_app.invoke(Command(resume="approve"), config=config)
    return result
