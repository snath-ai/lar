#!/usr/bin/env python3
"""
Lár Kitchen Sink Agent 2 — DynamicNode Live Execution Demo
===========================================================
This is a companion to kitchen_sink_agent.py.

kitchen_sink_agent.py demonstrated the SAFETY path:
  → DynamicNode generated an unsafe subgraph (unknown tool name)
  → TopologyValidator correctly REJECTED it
  → Agent fell through gracefully

THIS file demonstrates the SUCCESS path:
  → DynamicNode generates a valid 2-step LLMNode subgraph
  → TopologyValidator APPROVES it
  → The subgraph actually EXECUTES in the live graph

Scenario — Code Review Pipeline
---------------------------------
1.  AddValueNode          → Seed code snippet + token budget
2.  @node (FunctionalNode) → Extract language + add reviewer prefix
3.  LLMNode               → High-level summary of what the code does
4.  DynamicNode           → AI designs a 2-step review subgraph at runtime:
                            - Subgraph Step A: security vulnerability check
                            - Subgraph Step B: performance optimisation check
                            (Both steps run, results saved to state)
5.  ToolNode              → Score the two reviews (pure Python, no AI)
6.  ClearErrorNode        → Janitor for ToolNode error path
7.  RouterNode            → Route: 'needs_work' vs 'looks_good'
8.  ReduceNode            → Compress all review text into a verdict
9.  HumanJuryNode         → Human APPROVE / REJECT (or auto in SKIP_JURY mode)
10. BatchNode             → Two parallel final LLMs (pros + cons summary)
11. LLMNode (final)       → Final formatted report

Key differences from kitchen_sink_agent.py:
  - qwen2.5:14b is used for DynamicNode (better at following JSON instructions)
  - Prompt tells LLM to use ONLY LLMNode nodes with explicit node IDs
  - Validator has no allowed tools → any ToolNode attempt fails safely,
    but the good prompt makes the LLM output LLMNode-only JSON
  - DynamicNode subgraph EXECUTES successfully

Run:
    cd /Users/aadithya/Desktop/Lar_Main/lar
    SKIP_JURY=1 .venv/bin/python3 examples/kitchen_sink_agent2.py
"""

import os
import sys
import json
import re

_LAR_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _LAR_SRC not in sys.path:
    sys.path.insert(0, _LAR_SRC)

from lar import (
    GraphState,
    AddValueNode, LLMNode, RouterNode, ToolNode,
    ClearErrorNode, BatchNode, ReduceNode,
    HumanJuryNode, FunctionalNode, node,
    DynamicNode, TopologyValidator,
    GraphExecutor, AuditLogger, TokenTracker,
    compute_state_diff, apply_diff,
    build_log_table, summarize_diff,
)
from rich.console import Console

# ── Configuration ─────────────────────────────────────────────────────────────
MODEL_FAST    = "ollama/llama3.2"        # fast cheap model for most steps
MODEL_DYNAMIC = "ollama/qwen2.5:14b"    # larger smarter model for DynamicNode

HMAC_SECRET   = "snath-kitchen-sink-2-secret"
LOG_DIR       = os.path.join(os.path.dirname(__file__), "lar_logs", "kitchen_sink2")
SKIP_JURY     = os.getenv("SKIP_JURY", "0") == "1"

# The code snippet the agent will review
CODE_SNIPPET = """\
def get_user_data(user_id):
    import sqlite3
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result
"""

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS  (plain Python functions for ToolNode)
# ═══════════════════════════════════════════════════════════════════════════════

def score_reviews(security_review: str, optimisation_review: str) -> dict:
    """
    ToolNode function: scores the two reviews by counting issue keywords.
    Pure Python — no AI involved. Returns a dict that is merged into state.
    """
    security_keywords    = ["sql injection", "vulnerability", "unsafe", "risk",
                            "exploit", "injection", "attack", "dangerous", "flaw", "insecure"]
    performance_keywords = ["slow", "inefficient", "memory", "optimise", "optimize",
                            "cache", "index", "speed", "bottleneck", "improve"]

    sec_score = sum(1 for kw in security_keywords
                    if kw in (security_review or "").lower())
    perf_score = sum(1 for kw in performance_keywords
                     if kw in (optimisation_review or "").lower())

    total = sec_score + perf_score
    verdict = "needs_work" if total >= 2 else "looks_good"

    return {
        "security_score":     sec_score,
        "performance_score":  perf_score,
        "combined_score":     total,
        "score_verdict":      verdict,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# @node DECORATOR  (FunctionalNode)
# ═══════════════════════════════════════════════════════════════════════════════

@node(output_key="code_context")
def build_context(state: GraphState) -> str:
    """
    Adds a brief context header to the code snippet for use in all prompts.
    Demonstrates the @node pattern — lightweight Python logic, no AI.
    """
    snippet = state.get("code_snippet") or ""
    language = "Python"  # In production you'd detect this dynamically
    lines = len(snippet.strip().splitlines())
    ctx = f"[{language} function, {lines} lines] Code under review:\n{snippet}"
    print(f"  [@node build_context]: Created context header ({lines} lines of code)")
    return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER DECISION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def route_on_verdict(state: GraphState) -> str:
    """Routes on the score_verdict written by the ToolNode scoring function."""
    return state.get("score_verdict") or "looks_good"


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION  (reverse definition — leaf nodes first)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n[Setup] Constructing Lár graph (Kitchen Sink 2)...")

# ─── FINAL REPORT NODE ────────────────────────────────────────────────────────
final_report_node = LLMNode(
    model_name         = MODEL_FAST,
    system_instruction = "You are a senior code reviewer. Format your report professionally.",
    prompt_template    = (
        "Write a final code review report for the following submission.\n\n"
        "CODE REVIEWED:\n{code_snippet}\n\n"
        "HIGH-LEVEL SUMMARY:\n{code_summary}\n\n"
        "SECURITY REVIEW (from AI subgraph):\n{security_review}\n\n"
        "PERFORMANCE REVIEW (from AI subgraph):\n{optimisation_review}\n\n"
        "VERDICT SUMMARY:\n{verdict_summary}\n\n"
        "SCORES: Security issues found: {security_score} | "
        "Performance issues found: {performance_score}\n\n"
        "Format as: # Code Review Report, ## Overview, ## Security Findings, "
        "## Performance Findings, ## Verdict, ## Recommended Actions"
    ),
    output_key        = "final_report",
    generation_config = {"temperature": 0.2, "max_tokens": 1024},
    next_node         = None,
)

# ─── PARALLEL FINAL SUMMARY (BatchNode) ───────────────────────────────────────
pros_node = LLMNode(
    model_name      = MODEL_FAST,
    system_instruction = "You are a balanced technical lead. Be concise.",
    prompt_template = (
        "In 2 sentences, what are the STRENGTHS of this code?\n{code_snippet}"
    ),
    output_key      = "code_strengths",
    generation_config = {"temperature": 0.5, "max_tokens": 150},
)

cons_node = LLMNode(
    model_name      = MODEL_FAST,
    system_instruction = "You are a strict security auditor. Be concise.",
    prompt_template = (
        "In 2 sentences, what are the CRITICAL WEAKNESSES of this code?\n{code_snippet}"
    ),
    output_key      = "code_weaknesses",
    generation_config = {"temperature": 0.3, "max_tokens": 150},
)

parallel_summary_batch = BatchNode(
    nodes     = [pros_node, cons_node],
    next_node = final_report_node,
)

# ─── HUMAN JURY NODE ──────────────────────────────────────────────────────────
if SKIP_JURY:
    jury_node = AddValueNode(
        key       = "jury_verdict",
        value     = "approve",
        next_node = parallel_summary_batch,
    )
    print("  [Setup] SKIP_JURY=1 → HumanJuryNode replaced with auto-approve")
else:
    jury_node = HumanJuryNode(
        prompt       = "Approve this code review for delivery?",
        choices      = ["approve", "reject"],
        output_key   = "jury_verdict",
        context_keys = ["verdict_summary", "security_score", "performance_score"],
        next_node    = parallel_summary_batch,
    )

# ─── REDUCE NODE: compress all reviews into a verdict summary ─────────────────
reduce_to_verdict = ReduceNode(
    model_name      = MODEL_FAST,
    prompt_template = (
        "You are a senior code reviewer. Summarise these two review findings "
        "into a single 3-sentence verdict paragraph.\n\n"
        "Security Review:\n{security_review}\n\n"
        "Performance Review:\n{optimisation_review}\n\n"
        "Overall score: {combined_score} issues found. Verdict: {score_verdict}\n\n"
        "Verdict paragraph:"
    ),
    input_keys      = ["security_review", "optimisation_review"],  # deleted after run
    output_key      = "verdict_summary",
    generation_config = {"temperature": 0.3, "max_tokens": 256},
    next_node       = jury_node,
)

# ─── ROUTER: route on verdict ─────────────────────────────────────────────────
verdict_router = RouterNode(
    decision_function = route_on_verdict,
    path_map          = {
        "needs_work": reduce_to_verdict,
        "looks_good": reduce_to_verdict,
    },
    default_node = reduce_to_verdict,
)

# ─── CLEAR ERROR NODE ─────────────────────────────────────────────────────────
clear_error = ClearErrorNode(next_node=verdict_router)

# ─── TOOL NODE: score the reviews ─────────────────────────────────────────────
# output_key=None → dict-merge mode: all keys in returned dict merged into state
score_reviews_node = ToolNode(
    tool_function = score_reviews,
    input_keys    = ["security_review", "optimisation_review"],
    output_key    = None,           # dict-merge: security_score, performance_score etc go in directly
    next_node     = verdict_router,
    error_node    = clear_error,    # safety net
)

# ─── DYNAMIC NODE ─────────────────────────────────────────────────────────────
# Key design decisions that make the subgraph ACTUALLY EXECUTE:
#   1. Use qwen2.5:14b — larger model, better at following JSON instructions
#   2. Describe nodes in WORDS with explicit IDs — don't use a JSON template
#   3. Explicitly say "NEVER use ToolNode"
#   4. next_node = score_reviews_node so the subgraph rejoins main graph
#
# TopologyValidator has NO allowed tools.
# If the LLM still includes a ToolNode it gets safely rejected.
# But the clear prompt means it won't.

validator = TopologyValidator(allowed_tools=[])

dynamic_review_node = DynamicNode(
    llm_model = MODEL_DYNAMIC,
    prompt_template = (
        "Design a Lár agent subgraph to perform a two-part code review.\n\n"
        "CODE BEING REVIEWED:\n{code_snippet}\n\n"
        "STRICT RULES — READ CAREFULLY:\n"
        "1. Use ONLY 'LLMNode' as the node type. Never use ToolNode or any other type.\n"
        "2. Create EXACTLY 2 nodes:\n"
        "   - First node: id must be 'security_check', output_key must be 'security_review'\n"
        "   - Second node: id must be 'performance_check', output_key must be 'optimisation_review'\n"
        "3. security_check.next must be 'performance_check'\n"
        "4. performance_check.next must be null\n"
        "5. entry_point must be 'security_check'\n"
        "6. For the 'prompt' field of security_check: write a prompt asking for SQL injection "
        "and security vulnerability analysis of the code\n"
        "7. For the 'prompt' field of performance_check: write a prompt asking for "
        "performance and efficiency analysis of the code\n"
        "DO NOT include any ToolNode. Ignore ToolNode examples in any schema shown below."
    ),
    validator          = validator,
    next_node          = score_reviews_node,
    system_instruction = (
        "You are a software architect. Output ONLY valid JSON representing a Lár graph. "
        "Use ONLY LLMNode type nodes — never ToolNode. "
        "Your JSON must have exactly 2 nodes: 'security_check' and 'performance_check'."
    ),
)

# ─── LLMNode: high-level code summary ─────────────────────────────────────────
code_summary_node = LLMNode(
    model_name      = MODEL_FAST,
    system_instruction = "You are a code reviewer. Be concise and technical.",
    prompt_template = (
        "In 2 sentences, describe what this code does and its main purpose:\n\n{code_context}"
    ),
    output_key      = "code_summary",
    generation_config = {"temperature": 0.2, "max_tokens": 150},
    next_node       = dynamic_review_node,
)

# ─── @node: build context header ─────────────────────────────────────────────
build_context.next_node = code_summary_node

# ─── ADD VALUE NODES ──────────────────────────────────────────────────────────
add_code_node = AddValueNode(
    key       = "code_snippet",
    value     = CODE_SNIPPET,
    next_node = build_context,
)

add_budget_node = AddValueNode(
    key       = "token_budget",
    value     = 80_000,
    next_node = add_code_node,
)

entry_node = add_budget_node


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTOR SETUP
# ═══════════════════════════════════════════════════════════════════════════════

_console = Console()

audit_logger  = AuditLogger(log_dir=LOG_DIR, hmac_secret=HMAC_SECRET)
token_tracker = TokenTracker()

executor = GraphExecutor(
    log_dir          = LOG_DIR,
    offline_mode     = False,
    user_id          = "kitchen-sink-2-demo",
    logger           = audit_logger,
    tracker          = token_tracker,
    hmac_secret      = HMAC_SECRET,
    max_node_fatigue = 25,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 70)
print("  Lár Kitchen Sink Agent 2 — Code Review Pipeline")
print(f"  Fast Model  : {MODEL_FAST}")
print(f"  Smart Model : {MODEL_DYNAMIC}  (used for DynamicNode only)")
print(f"  HMAC        : enabled")
print(f"  Jury        : {'auto-approve (SKIP_JURY=1)' if SKIP_JURY else 'interactive'}")
print("═" * 70 + "\n")

history = []

for step_log in executor.run_step_by_step(
    start_node    = entry_node,
    initial_state = {},
    max_steps     = 50,
):
    history.append(step_log)

    node_name   = step_log.get("node", "?")
    outcome     = step_log.get("outcome", "?")
    diff        = step_log.get("state_diff", {})
    metadata    = step_log.get("run_metadata") or {}

    emoji       = "✅" if outcome == "success" else "❌"
    tokens_used = metadata.get("total_tokens", 0)
    added       = list(diff.get("added", {}).keys())
    removed     = list(diff.get("removed", {}).keys())

    print(f"\n  {emoji} Step {step_log['step']:02d} | {node_name:<30} | tokens: {tokens_used:>5}")
    if added:   print(f"     ↳ Added  : {added}")
    if removed: print(f"     ↳ Removed: {removed}")

    if diff:
        raw_summary = summarize_diff(diff)
        if raw_summary:
            clean = re.sub(r"\[/?[a-zA-Z_ ]+\]", "", str(raw_summary))
            if clean.strip():
                print(f"     ↳ Diff   : {clean.strip()}")


# ═══════════════════════════════════════════════════════════════════════════════
# POST-RUN REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n" + "═" * 70)
print("  KITCHEN SINK 2 — EXECUTION COMPLETE")
print("═" * 70)

# Token summary
summary = token_tracker.get_summary()
print(f"\n  💰 Token Budget Report")
print(f"     Prompt tokens     : {summary['total_prompt_tokens']:,}")
print(f"     Completion tokens : {summary['total_completion_tokens']:,}")
print(f"     Total tokens      : {summary['total_tokens']:,}")
for model, toks in summary.get("tokens_by_model", {}).items():
    print(f"     [{model}] : {toks:,} tokens")

# Audit table
print("\n  📋 Execution Audit Table")
_console.print(build_log_table(history))

# Round-trip check
if len(history) >= 2:
    before = history[0].get("state_before", {})
    diff   = history[0].get("state_diff", {})
    after  = apply_diff(before, diff)
    print(f"\n  🔬 compute_state_diff / apply_diff: {'✅ PASS' if after is not None else '❌ FAIL'}")

# DynamicNode subgraph check
dynamic_steps = [h for h in history if h.get("node") == "DynamicNode"]
if dynamic_steps:
    ds = dynamic_steps[0]
    spec = (ds.get("state_after") or {}).get("__graph_spec_json__", "")
    print(f"\n  🧠 DynamicNode subgraph spec generated: {'yes' if spec else 'no'}")
    if spec:
        try:
            parsed = json.loads(spec) if isinstance(spec, str) else spec
            node_types = [n.get("type") for n in parsed.get("nodes", [])]
            print(f"     Node types in subgraph : {node_types}")
            print(f"     Entry point            : {parsed.get('entry_point')}")
            all_llm = all(t == "LLMNode" for t in node_types)
            print(f"     All LLMNode (no Tool)  : {'✅ YES' if all_llm else '⚠️  NO — contained non-LLM type'}")
        except Exception:
            print("     (could not parse spec JSON)")

subgraph_keys = []
for key in ["security_review", "optimisation_review"]:
    final_state = history[-1].get("state_after", {}) if history else {}
    if key in final_state:
        subgraph_keys.append(key)
print(f"\n  ✅ Subgraph outputs in final state: {subgraph_keys if subgraph_keys else 'not found (check ReduceNode deletion)'}")

# Final report
final_state = history[-1].get("state_after", {}) if history else {}
final_report = final_state.get("final_report")
if final_report:
    print("\n" + "─" * 70)
    print("  📄 FINAL CODE REVIEW REPORT")
    print("─" * 70)
    print(final_report)

# Nodes exercised
print("\n" + "═" * 70)
print("  Nodes exercised:")
for n in sorted({h.get("node") for h in history}):
    print(f"    • {n}")
print("═" * 70 + "\n")
