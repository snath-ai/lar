"""
Durable pause/resume (v2.3.0) — the fix for the gap surfaced by actually
reading executor.py, node.py, and state.py: Lár had no framework-level
pause primitive at all. HumanJuryNode blocked on input() in the same
process/thread; "resumable graphs" meant a developer hand-serializing
GraphState and hardcoding which node to resume at (see
examples/patterns/10_resumable_cost_demo.py's own correction note).

This demo proves the new primitive with a real cross-process test, not a
same-script simulation: run this file with no arguments to PAUSE (writes a
checkpoint to disk and the process EXITS — nothing kept in memory). Run it
again with a decision argument to RESUME in a completely fresh Python
process, loading only what's on disk.

    python 11_durable_checkpoint.py                  # phase 1: pauses, exits
    python 11_durable_checkpoint.py approve           # phase 2: fresh process, resumes
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from lar import (
    GraphExecutor, AddValueNode, FunctionalNode, HumanJuryNode,
    Checkpoint, FileCheckpointStore, resume_human_decision,
)
from lar.compliance import BranchTriageNode  # noqa: F401 (not used, just confirms import path)
from lar.compliance.authority_record import AuthorityLedger

CHECKPOINT_DIR = "/tmp/lar_durable_checkpoint_demo"
LEDGER_FILE = "/tmp/lar_durable_checkpoint_demo/ledger.json"

store = FileCheckpointStore(directory=CHECKPOINT_DIR)
ledger = AuthorityLedger(hmac_secret="demo-secret")


# ── Graph: intake -> jury (pauses here, durably) -> notify (only on resume) ──

def notify(state):
    print(f"  [notify] Executing approved action for case '{state.get('case_id')}': "
          f"decision={state.get('jury_decision')!r}")
    return {"executed": True}


notify_node = FunctionalNode(func=notify, output_key="notify_result", next_node=None)
notify_node._node_id = "notify_node"  # stable id required for resume lookup

jury_node = HumanJuryNode(
    prompt="Approve this case?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    context_keys=["case_id"],
    next_node=notify_node,
    authority_ledger=ledger,
    stakeholder_id="reviewer@snath.ai",
    stakeholder_role="COMPLIANCE_OFFICER",
    decision_type="case_review",
    # always_human: in a non-interactive environment (no TTY -- exactly what
    # this demo runs under), HumanJuryNode raises rather than silently
    # auto-selecting a choice. That's the real halt-and-wait-for-a-human
    # signal this demo needs to prove the checkpoint against -- not a bug.
    automation_boundary={"case_review": "always_human"},
    checkpoint_store=store,
    case_id_key="case_id",
)

intake_node = AddValueNode(key="case_id", value="CASE-4471", next_node=jury_node)

# node_registry: same live objects the checkpoint was created against —
# required because a checkpoint stores graph POSITION, not graph TOPOLOGY.
node_registry = {"notify_node": notify_node}

executor = GraphExecutor(log_dir="/tmp/lar_durable_checkpoint_demo/logs")


def phase_1_pause():
    print("=" * 70)
    print("  PHASE 1 — first process: run until the human-review pause")
    print("=" * 70)
    for step in executor.run_step_by_step(intake_node, {}):
        print(f"  step {step['step']}: {step['node']} -> {step['outcome']}")
    print(f"\n  The 'error' outcome above IS the halt: automation_boundary="
          f"'always_human' refuses to auto-decide with no TTY present, same as")
    print(f"  it would if this process's HumanJuryNode were left mid-input() and")
    print(f"  the process were then killed. The checkpoint was written BEFORE")
    print(f"  that halt, on the line before this node ever blocked or raised.")
    print(f"  Process is now exiting. Nothing is held in memory.")
    print(f"  Checkpoint on disk: {store.exists('CASE-4471')}")
    print(f"\n  -> Run again with a decision to resume in a FRESH process:")
    print(f"     python {os.path.basename(__file__)} approve\n")


def phase_2_resume(decision: str):
    print("=" * 70)
    print(f"  PHASE 2 — a DIFFERENT process: resuming with decision={decision!r}")
    print("=" * 70)
    print(f"  Checkpoint found on disk before this process touched anything: "
          f"{store.exists('CASE-4471')}")

    for step in resume_human_decision(
        checkpoint_store=store,
        case_id="CASE-4471",
        decision=decision,
        executor=executor,
        node_registry=node_registry,
        authority_ledger=ledger,
        stakeholder_id="reviewer@snath.ai",
        stakeholder_role="COMPLIANCE_OFFICER",
        rationale="Reviewed offline, approved via ticket #4471.",
    ):
        print(f"  step {step['step']}: {step['node']} -> {step['outcome']}")

    print(f"\n  Checkpoint deleted after resolution: {not store.exists('CASE-4471')}")
    print(f"  Authority ledger entries: {len(ledger._records)}")
    for rec in ledger._records:
        print(f"    - {rec['decision']} by {rec['stakeholder_id']} ({rec['stakeholder_role']}): "
              f"{rec['rationale']}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        phase_2_resume(sys.argv[1])
    else:
        phase_1_pause()
