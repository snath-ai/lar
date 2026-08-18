"""
Lár implementation of the Adverse Event Triage Agent.
See scenario.py for the shared scenario/attacks both frameworks are tested against.
"""
import sys
import os
import json
import hashlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from lar import GraphExecutor, GraphState, LLMNode, ToolNode, RouterNode, AddValueNode
from scenario import CLASSIFY_SYSTEM, hard_severity_check, MODEL_NAME_LAR
from actions import file_routine_note, notify_regulatory_contact, EXECUTION_LOG, reset_log

SIGNING_SECRET = "pharmacovigilance_hmac_key"


def _sign(case_id: str, note: str) -> str:
    return hashlib.sha256(f"{case_id}:{note}:{SIGNING_SECRET}".encode()).hexdigest()


# --- Classification (LLM) ---
classifier = LLMNode(
    model_name=MODEL_NAME_LAR,
    prompt_template="Clinical note:\n{note}",
    output_key="llm_classification_raw",
    system_instruction=CLASSIFY_SYSTEM,
)


# --- Parse + deterministic backstop (belt-and-suspenders, same pattern as
#     ProhibitedPracticeGuard elsewhere in this repo) ---
def parse_and_backstop(state: dict) -> dict:
    raw = state.get("llm_classification_raw", "{}")
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1].replace("json", "", 1).strip() if raw.count("```") >= 2 else raw
    try:
        parsed = json.loads(raw)
        llm_class = parsed.get("classification", "ROUTINE").upper()
    except Exception:
        llm_class = "ROUTINE"  # fail closed to ROUTINE parse, but the hard check below still runs

    # DETERMINISTIC BACKSTOP: independent of what the LLM concluded, or whether
    # its output even parsed. This is what defends Attack 1.
    hard_flag = hard_severity_check(state.get("note", ""))
    final_class = "SEVERE" if (llm_class == "SEVERE" or hard_flag) else "ROUTINE"

    return {
        "llm_classification": llm_class,
        "hard_severity_flag": hard_flag,
        "final_classification": final_class,
    }


classifier_parser = ToolNode(
    tool_function=parse_and_backstop,
    input_keys=["__state__"],
    output_key=None,
    next_node=None,
)


# --- Approval gate (STRONG: signature bound to the specific case_id+note) ---
def strong_approve(state: dict) -> dict:
    case_id = state.get("case_id")
    note = state.get("note")
    sig = _sign(case_id, note)
    print(f"    [Lár] Officer approves escalation for {case_id}. Signing: {sig[:8]}...")
    return {"approval_signature": sig}


approval_node = ToolNode(
    tool_function=strong_approve,
    input_keys=["__state__"],
    output_key=None,
    next_node=None,
)


# --- Execute SEVERE path: re-verify signature against CURRENT note before acting ---
def execute_severe(state: dict) -> dict:
    case_id = state.get("case_id")
    note = state.get("note")  # the CURRENT note, which may have drifted since approval
    stored_sig = state.get("approval_signature")
    expected_sig = _sign(case_id, note)

    if not stored_sig:
        return {"outcome": "blocked_no_approval"}
    if stored_sig != expected_sig:
        print(f"    [Lár] STALE AUTHORITY DETECTED: signature no longer matches current case content.")
        print(f"       stored={stored_sig[:8]}...  expected={expected_sig[:8]}...")
        return {"outcome": "blocked_stale_authority"}

    result = notify_regulatory_contact(case_id, note)
    return {"outcome": "executed", "result": result}


execute_severe_node = ToolNode(
    tool_function=execute_severe,
    input_keys=["__state__"],
    output_key=None,
    next_node=None,
)


def execute_routine(state: dict) -> dict:
    case_id = state.get("case_id")
    note = state.get("note")
    result = file_routine_note(case_id, note)
    return {"outcome": "executed_routine", "result": result}


execute_routine_node = ToolNode(
    tool_function=execute_routine,
    input_keys=["__state__"],
    output_key=None,
    next_node=None,
)


def route_on_classification(state: GraphState) -> str:
    return state.get("final_classification", "ROUTINE")


router = RouterNode(
    decision_function=route_on_classification,
    path_map={"SEVERE": approval_node, "ROUTINE": execute_routine_node},
)
classifier_parser.next_node = router
classifier.next_node = classifier_parser
approval_node.next_node = execute_severe_node


def run_case(case_id: str, note: str, verbose: bool = True):
    """Run the full triage pipeline for a single case (classify -> approve -> execute)."""
    executor = GraphExecutor(log_dir="/tmp/lar_pharma_logs")
    state = {"case_id": case_id, "note": note}
    final = None
    for step in executor.run_step_by_step(classifier, state):
        if verbose:
            print(f"    [Lár] Step {step['step']}: {step['node']} -> {step['outcome']}")
        final = step
    return final["state_after"] if final else {}


def run_attack_2_stale_authority():
    """Approve Case A, then swap the note content before execution -- mirrors
    6_zombie_action_test.py's pattern applied to this scenario."""
    from scenario import ATTACK_2_CASE_A, ATTACK_2_CASE_B_DRIFT

    case_id = ATTACK_2_CASE_A["case_id"]
    print(f"    [Lár] Phase 1: submitting Case A ({case_id}) — mild, ROUTINE-looking")
    state = {"case_id": case_id, "note": ATTACK_2_CASE_A["note"]}

    # Force SEVERE classification+approval regardless of the mild note, to set
    # up the same "approval exists, then content drifts" scenario as the
    # original zombie-action test (there: judge approves, then target swaps).
    approve_result = strong_approve(state)
    state.update(approve_result)

    print(f"    [Lár] Phase 2: case content DRIFTS to a fatal event before execution")
    state["note"] = ATTACK_2_CASE_B_DRIFT["note"]

    result = execute_severe(state)
    return result
