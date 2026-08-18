"""
Resumable Graphs: Zero Wasted Tokens on Retry
==============================================

Correction: an earlier version of this docstring claimed "every other
framework" replays a crashed pipeline from scratch on retry. That isn't
accurate -- LangGraph, for one, ships a real, automatic checkpointer that
persists state after every step and resumes a failed run from the last
successful step via the same thread_id, with no manual re-run of earlier
steps required. That's a genuine, well-documented feature, not a gap.

WHAT LÁR ACTUALLY DOES HERE, verified against its own code (not a
competitor comparison): Lár runs step-by-step via a Python generator. You
can serialize the GraphState to disk at ANY point, kill the process, and
resume from that state -- but this repo's own resumability is currently
MANUAL: the developer has to know and hardcode which node to resume at
(see the comment in examples/patterns/9_resumable_graph.py: "In a real
'resumer', the serialization would include the 'next_step' pointer. Here
we manually know it's `final_step_llm`"). LangGraph's checkpointer tracks
the resume position automatically; Lár's current pattern does not.

This demo simulates a 4-step legal document analysis pipeline:
    Step 0: Extract key clauses (LLM — expensive)
    Step 1: Identify risk factors (LLM — expensive)
    Step 2: ← SIMULATED CRASH HERE (e.g. rate limit, OOM, deploy)
    Step 3: Draft executive summary (LLM — only step on resume, IF you
            correctly hardcode the resume entry point yourself)

What IS true and demonstrated below: because Lár's state is a plain,
JSON-serializable dict at every step, saving/restoring it yourself is
simple to do -- it's just not automatic the way a checkpointer is.
"""

import os, sys, json, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, LLMNode, ToolNode, GraphState

# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT FILE — the "time machine" state
# ─────────────────────────────────────────────────────────────────────────────
CHECKPOINT_FILE = "/tmp/lar_legal_checkpoint.json"

# ─────────────────────────────────────────────────────────────────────────────
# THE DOCUMENT (shared across both runs)
# ─────────────────────────────────────────────────────────────────────────────
DOCUMENT = """
MASTER SERVICE AGREEMENT — Section 4.3 (Liability Cap):
The aggregate liability of either party shall not exceed £50,000 in any 12-month period.
Consequential, indirect, or punitive damages are expressly excluded.

Section 7.1 (IP Ownership):
All work product created by the Supplier remains IP of the Supplier unless
explicitly transferred in writing signed by both parties.

Section 9.2 (Termination for Convenience):
Either party may terminate with 30 days written notice. No compensation
is owed to the Supplier on termination for convenience.
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# GRAPH DEFINITION — 4 nodes, built backwards (Lár convention)
# ─────────────────────────────────────────────────────────────────────────────

# Step 3 — Executive Summary (only runs on RESUME)
summary_node = LLMNode(
    model_name="ollama/phi4",
    prompt_template=(
        "You are a legal counsel AI.\n"
        "Clauses extracted: {clauses}\n"
        "Risk factors: {risks}\n\n"
        "Write a 3-bullet executive summary for a non-legal executive. "
        "Be concise and highlight the most important points. Reply with plain bullets, no JSON."
    ),
    output_key="executive_summary",
    next_node=None,
)

# Step 2 — Crash checkpoint (simulates a crash/OOM/rate-limit)
def crash_and_checkpoint(state):
    """Saves state then exits — simulating a crash mid-pipeline."""
    snapshot = state.get_all()
    # Write a sentinel so resume run can report pre-crash spend
    snapshot["_tokens_spent_before_crash"] = snapshot.get("_tokens_spent", 0)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"\n  💥 [Step 2] Simulated crash (rate limit / OOM / deployment restart)")
    print(f"  💾 State checkpointed → {CHECKPOINT_FILE}")
    print(f"  📊 Tokens spent so far: ~{snapshot.get('_tokens_spent', '?')} tokens")
    print(f"  🔑 Checkpointed keys: {[k for k in snapshot if not k.startswith('__')]}")

crash_node = ToolNode(
    tool_function=crash_and_checkpoint,
    input_keys=["__state__"],
    output_key=None,
    next_node=summary_node,  # skipped in run 1 due to sys.exit after checkpoint
)

# Step 1 — Risk Analysis (runs only in FIRST run)
risk_node = LLMNode(
    model_name="ollama/phi4",
    prompt_template=(
        "You are a legal risk analyst.\n"
        "Clauses: {clauses}\n\n"
        "List the top 3 legal risks in this contract. "
        "Reply with ONLY a JSON array of strings, e.g. [\"risk 1\", \"risk 2\", \"risk 3\"]. No prose."
    ),
    output_key="risks",
    next_node=crash_node,
)

# Step 0 — Clause Extraction (runs only in FIRST run)
clause_node = LLMNode(
    model_name="ollama/phi4",
    prompt_template=(
        "You are a legal AI assistant.\n"
        "Contract: {document}\n\n"
        "Extract the key legal clauses. Reply with ONLY a JSON array of strings. No prose."
    ),
    output_key="clauses",
    next_node=risk_node,
)

# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def print_banner(title, subtitle=""):
    w = 62
    print("\n" + "═" * w)
    print(f"  {title}")
    if subtitle:
        print(f"  {subtitle}")
    print("═" * w)

def run_pipeline():
    executor = GraphExecutor()
    token_total = 0

    # ── RESUME PATH ──────────────────────────────────────────────────────────
    if os.path.exists(CHECKPOINT_FILE):
        print_banner(
            "Lár Resumable Graph — RESUME MODE",
            "Picking up exactly where we left off. Zero wasted tokens."
        )

        with open(CHECKPOINT_FILE) as f:
            restored = json.load(f)

        print(f"\n  ♻️  Restored state from checkpoint:")
        for k, v in restored.items():
            if not k.startswith("__"):
                preview = str(v)[:60] + ("..." if len(str(v)) > 60 else "")
                print(f"     {k}: {preview}")

        print(f"\n  ▶  Resuming at Step 3 (executive_summary) — skipping Steps 0, 1 entirely")
        print(f"  💰 A naive retry with no persistence at all would re-send Steps 0+1 to the LLM here.")
        print(f"     (LangGraph's own checkpointer would also skip them automatically — this demo")
        print(f"      shows Lár CAN skip them too, via manual state persistence, not that others can't.)\n")

        for step in executor.run_step_by_step(summary_node, restored):
            node = step["node"]
            outcome = step["outcome"]
            meta = step.get("run_metadata") or {}
            tokens = meta.get("total_tokens", 0)
            token_total += tokens
            print(f"  ✅ Step {step['step']}: {node:<28} {tokens or '-':>4} tokens")
        last_step = step

        print_banner("RESUME COMPLETE", f"Total tokens THIS run: {token_total}")
        print(f"\n  Executive Summary (Step 3 output):")
        print(f"  {'-'*56}")
        summary = last_step.get("state_after", {}).get("executive_summary", "")
        for line in summary.split("\n"):
            print(f"  {line}")
        pre_crash = restored.get("_tokens_spent", 474)
        print(f"\n  📊 Cost comparison:")
        print(f"     Lár (resumed via saved state):  ~{token_total} tokens  ← only Step 3")
        print(f"     Naive no-persistence retry:      ~{pre_crash + token_total} tokens  ← full pipeline re-run")
        print(f"     💰 Savings vs. no persistence:   ~{pre_crash} tokens ({pre_crash * 0.000002:.4f} USD at $0.002/1K)")
        print(f"     At 10,000 runs/day that's ${pre_crash * 0.000002 * 10000:.2f}/day saved — IF you had no")
        print(f"     persistence at all. A framework with automatic checkpointing (e.g. LangGraph)")
        print(f"     would show the same savings without the manual resume-point tracking.\n")

        os.remove(CHECKPOINT_FILE)
        print(f"  🧹 Checkpoint cleaned up.\n")

    # ── FIRST RUN PATH ───────────────────────────────────────────────────────
    else:
        print_banner(
            "Lár Resumable Graph — FIRST RUN",
            "4-step legal analysis pipeline. Will crash at Step 2."
        )
        print(f"\n  📄 Document: {DOCUMENT[:80]}...\n")

        steps_run = []
        try:
            for step in executor.run_step_by_step(clause_node, {"document": DOCUMENT}):
                node = step["node"]
                outcome = step["outcome"]
                meta = step.get("run_metadata") or {}
                tokens = meta.get("total_tokens", 0)
                token_total += tokens
                steps_run.append(step["step"])
                print(f"  ✅ Step {step['step']}: {node:<28} {tokens or '-':>4} tokens")

                if node == "ToolNode" and outcome == "success":
                    break

        except SystemExit:
            pass

        # Write total spent into checkpoint so resume can report it
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE) as f:
                data = json.load(f)
            data["_tokens_spent"] = token_total
            with open(CHECKPOINT_FILE, "w") as f:
                json.dump(data, f, indent=2)

        print(f"\n  💡 Steps completed before crash: {steps_run}")
        print(f"  💾 State saved — Steps 0+1 results are preserved.")
        print(f"  🔄 Run this script again to resume from Step 3.\n")
        print(f"  → python {os.path.basename(__file__)}\n")


if __name__ == "__main__":
    run_pipeline()
