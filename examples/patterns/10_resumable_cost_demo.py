"""
Resumable Graphs: The Cost-Saving Killer Feature
=================================================

THE PROBLEM with every other framework:
    A 5-step LLM pipeline crashes on Step 4.
    When you retry, they replay Steps 0-3 from scratch —
    sending the same prompt + history to the LLM AGAIN.
    In a 10-step pipeline with 500 tokens per step, that's
    4,500 wasted tokens. At scale, that's real money.

THE LAR SOLUTION:
    Lár runs step-by-step via a Python generator.
    You can serialize the GraphState to disk at ANY point,
    kill the process, and resume exactly where you left off —
    sending only the remaining steps to the LLM.

This demo simulates a 4-step legal document analysis pipeline:
    Step 0: Extract key clauses (LLM — expensive)
    Step 1: Identify risk factors (LLM — expensive)
    Step 2: ← SIMULATED CRASH HERE (e.g. rate limit, OOM, deploy)
    Step 3: Draft executive summary (LLM — only step on resume)

WITHOUT Lár: Steps 0+1 would be re-run on retry = wasted tokens.
WITH Lár:    Resume starts at Step 2 — zero wasted tokens.
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
        print(f"  💰 Competitor frameworks would re-send Steps 0+1 to the LLM here.\n")

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
        print(f"     Lár (resume):     ~{token_total} tokens  ← only Step 3")
        print(f"     Competitors:      ~{pre_crash + token_total} tokens  ← full pipeline re-run")
        print(f"     💰 Savings:       ~{pre_crash} tokens ({pre_crash * 0.000002:.4f} USD at $0.002/1K)")
        print(f"     At 10,000 runs/day that's ${pre_crash * 0.000002 * 10000:.2f}/day saved.\n")

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
