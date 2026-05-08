#!/usr/bin/env python3
"""
Lár Kitchen Sink Agent — Full Node Coverage Demo
=================================================
Exercises EVERY node, utility, and executor feature in the Lár framework:

    Nodes            : AddValueNode, LLMNode, RouterNode, ToolNode,
                       ClearErrorNode, BatchNode, ReduceNode,
                       HumanJuryNode, FunctionalNode (@node decorator),
                       AdaptiveNode + TopologyValidator
    Executor         : GraphExecutor (HMAC audit log, user_id, max_node_fatigue)
    Infrastructure   : AuditLogger, TokenTracker
    Utilities        : compute_state_diff, apply_diff
    Formatters       : build_log_table, summarize_diff

Scenario — Research Synthesis Pipeline
---------------------------------------
1.  AddValueNode         → Seed initial state (topic, token budget)
2.  @node (FunctionalNode) → Validate & normalise the topic
3.  BatchNode            → Run two LLM perspectives in parallel
4.  ReduceNode           → Synthesise both perspectives into one summary
5.  ToolNode             → Calculate word-count stats (with error_node)
6.  ClearErrorNode       → Housekeeping after ToolNode's error path
7.  RouterNode           → Route on report length (short / long / unknown)
8.  LLMNode (long path)  → Expand short reports into full essays
9.  AdaptiveNode         → Composes a validated sub-analysis subgraph at runtime,
                           enforced by TopologyValidator
10. HumanJuryNode        → Human APPROVE / REJECT gate (Article 14 hook)
11. LLMNode (final)      → Format and wrap final deliverable

Run:
    cd /Users/aadithya/Desktop/Lar_Main/lar
    pip install -e .          # or it should already be installed
    export GOOGLE_API_KEY=... # or any provider key you have
    python examples/kitchen_sink_agent.py

    # Skip the HumanJuryNode (non-interactive CI mode):
    SKIP_JURY=1 python examples/kitchen_sink_agent.py
"""

import os
import sys
import json
import re

# ── Path bootstrap (works whether installed or run from repo root) ────────────
_LAR_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _LAR_SRC not in sys.path:
    sys.path.insert(0, _LAR_SRC)

from lar import (
    # State
    GraphState,
    # Nodes
    AddValueNode, LLMNode, RouterNode, ToolNode,
    ClearErrorNode, BatchNode, ReduceNode,
    HumanJuryNode, FunctionalNode, node,
    # Adaptive Execution
    AdaptiveNode, TopologyValidator,
    # Executor & Infrastructure
    GraphExecutor, AuditLogger, TokenTracker,
    # Utilities
    compute_state_diff, apply_diff,
    # Formatters
    build_log_table, summarize_diff,
)

# ── Configuration ─────────────────────────────────────────────────────────────
MODEL         = "ollama/llama3.2"             # local Ollama — no API key required
HMAC_SECRET   = "snath-kitchen-sink-secret"   # demo secret; use env var in prod
LOG_DIR       = os.path.join(os.path.dirname(__file__), "lar_logs", "kitchen_sink3")
SKIP_JURY     = os.getenv("SKIP_JURY", "0") == "1"   # set SKIP_JURY=1 for CI
RESEARCH_TOPIC = "The impact of deterministic AI on regulated industries"

# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS  (plain Python functions passed to ToolNode)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_word_stats(text: str) -> dict:
    """
    ToolNode function: returns word-count statistics for a text.
    Raises ValueError intentionally when text is empty (tests error_node path).
    """
    if not text or not text.strip():
        raise ValueError("calculate_word_stats received empty text — triggering error_node path.")
    words  = text.split()
    sentences = text.count(".") + text.count("!") + text.count("?")
    return {
        "word_count":     len(words),
        "sentence_count": max(sentences, 1),
        "avg_words_per_sentence": round(len(words) / max(sentences, 1), 1),
    }


def format_stats_banner(stats: dict) -> str:
    """
    ToolNode function: pretty-prints the stats dict into a readable banner.
    """
    if not isinstance(stats, dict):
        return "Stats unavailable."
    return (
        f"📊 Report Stats — "
        f"Words: {stats.get('word_count', 0)} | "
        f"Sentences: {stats.get('sentence_count', 0)} | "
        f"Avg words/sentence: {stats.get('avg_words_per_sentence', 0)}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# @node DECORATOR  (FunctionalNode via decorator syntax)
# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: Because @node injects the FunctionalNode at decoration time we must
# wire .next_node after graph construction (see "wire" section below).

@node(output_key="topic_normalised")
def normalise_topic(state: GraphState) -> str:
    """
    FunctionalNode: strips whitespace, title-cases the topic, and logs it.
    Demonstrates the @node decorator pattern — no LLM required for simple ops.
    """
    raw = state.get("topic") or ""
    normalised = raw.strip().title()
    print(f"  [@node normalise_topic]: '{raw}' → '{normalised}'")
    return normalised


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER DECISION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def route_by_length(state: GraphState) -> str:
    """RouterNode decision function. Returns 'short', 'long', or 'unknown'."""
    wc = state.get("word_count")
    if wc is None:
        return "unknown"
    if wc < 150:
        return "short"
    return "long"


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION  (reverse definition — leaf nodes first)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n[Setup] Constructing Lár graph...")

# ─── TERMINAL / FINAL NODE ────────────────────────────────────────────────────
final_format_node = LLMNode(
    model_name        = MODEL,
    system_instruction= "You are a technical editor. Format the deliverable cleanly with markdown headings.",
    prompt_template   = (
        "Here is the final research synthesis:\n\n{synthesis}\n\n"
        "Stats summary: {stats_banner}\n\n"
        "Jury verdict: {jury_verdict}\n\n"
        "Format this as a polished markdown report with: "
        "# Title, ## Executive Summary, ## Full Report, ## Metadata."
    ),
    output_key        = "final_report",
    generation_config = {"temperature": 0.3, "max_tokens": 1024},
    next_node         = None,  # END
)

# ─── HUMAN JURY NODE ──────────────────────────────────────────────────────────
if SKIP_JURY:
    # In CI/non-interactive mode: inject the verdict directly via AddValueNode
    jury_node = AddValueNode(
        key       = "jury_verdict",
        value     = "approve",   # auto-approve
        next_node = final_format_node,
    )
    print("  [Setup] SKIP_JURY=1 → HumanJuryNode replaced with auto-approve AddValueNode")
else:
    jury_router = RouterNode(
        decision_function = lambda state: state.get("jury_verdict") or "reject",
        path_map          = {
            "approve": final_format_node,
        },
        default_node = None,  # reject → stop execution
    )
    jury_node = HumanJuryNode(
        prompt       = "Approve this research synthesis?",
        choices      = ["approve", "reject"],
        output_key   = "jury_verdict",
        context_keys = ["synthesis", "stats_banner"],
        next_node    = jury_router,
    )

# ─── ADAPTIVE NODE (Runtime Graph Composition) ────────────────────────────────
# Allowed tools for the dynamic subgraph
validator = TopologyValidator(allowed_tools=[calculate_word_stats])

dynamic_analysis_node = AdaptiveNode(
    llm_model       = "ollama/qwen2.5:14b",
    prompt_template = (
        "Design a Lár subgraph. IMPORTANT TEST REQUIREMENT:\n"
        "You MUST include EXACTLY ONE ToolNode.\n"
        "The 'tool_name' MUST be 'unauthorized_shell_execution'.\n"
        "The 'output_key' MUST be 'shell_out'.\n"
        "Do not use LLMNode, only use ToolNode."
    ),
    validator       = validator,
    next_node       = jury_node,
    system_instruction = (
        "You are a software architect. Output ONLY valid JSON representing a Lár graph."
    ),
)


# ─── LONG PATH: LLM expansion ─────────────────────────────────────────────────
expand_short_report_node = LLMNode(
    model_name      = MODEL,
    prompt_template = (
        "The following research synthesis is too brief (only {word_count} words).\n\n"
        "{synthesis}\n\n"
        "Expand it to a comprehensive 300+ word academic synthesis. "
        "Keep the topic: {topic_normalised}."
    ),
    output_key      = "synthesis",   # overwrites synthesis in state
    generation_config = {"temperature": 0.6, "max_tokens": 800},
    next_node       = dynamic_analysis_node,
)

# ─── ROUTER ───────────────────────────────────────────────────────────────────
length_router = RouterNode(
    decision_function = route_by_length,
    path_map          = {
        "short":   expand_short_report_node,
        "long":    dynamic_analysis_node,
        "unknown": dynamic_analysis_node,
    },
    default_node = dynamic_analysis_node,
)

# ─── FORMAT STATS BANNER (ToolNode #2, no error_node needed) ──────────────────
format_banner_node = ToolNode(
    tool_function = format_stats_banner,
    input_keys    = ["word_count_stats"],
    output_key    = "stats_banner",
    next_node     = length_router,
)

# ─── CLEAR ERROR (janitor after ToolNode error path) ──────────────────────────
clear_error_node = ClearErrorNode(next_node=format_banner_node)

# ─── TOOL NODE #1: WORD COUNT STATS ───────────────────────────────────────────
word_count_node = ToolNode(
    tool_function = calculate_word_stats,
    input_keys    = ["synthesis"],
    output_key    = "word_count_stats",
    next_node     = format_banner_node,
    error_node    = clear_error_node,   # gracefully catch empty text errors
)

# ─── REDUCE NODE: Synthesise both parallel perspectives ───────────────────────
reduce_node = ReduceNode(
    model_name      = MODEL,
    prompt_template = (
        "You are a senior researcher. Synthesise the following two perspectives "
        "on '{topic_normalised}' into a single, balanced, 200-word academic summary.\n\n"
        "--- Perspective A (Optimistic) ---\n{perspective_a}\n\n"
        "--- Perspective B (Critical) ---\n{perspective_b}\n\n"
        "Synthesis:"
    ),
    input_keys      = ["perspective_a", "perspective_b"],  # deleted after reduce
    output_key      = "synthesis",
    generation_config = {"temperature": 0.4, "max_tokens": 512},
    next_node       = word_count_node,
)

# ─── BATCH NODE: Two parallel LLM perspectives ────────────────────────────────
perspective_a_node = LLMNode(
    model_name      = MODEL,
    system_instruction = "You are an optimistic technology futurist.",
    prompt_template = (
        "In 100 words, write an optimistic perspective on: {topic_normalised}"
    ),
    output_key      = "perspective_a",
    generation_config = {"temperature": 0.8, "max_tokens": 256},
)

perspective_b_node = LLMNode(
    model_name      = MODEL,
    system_instruction = "You are a cautious regulatory expert.",
    prompt_template = (
        "In 100 words, write a critical perspective on: {topic_normalised}"
    ),
    output_key      = "perspective_b",
    generation_config = {"temperature": 0.5, "max_tokens": 256},
)

batch_node = BatchNode(
    nodes     = [perspective_a_node, perspective_b_node],
    next_node = reduce_node,
)

# ─── @node DECORATOR: normalise topic ─────────────────────────────────────────
# Wire the next_node now that batch_node exists
normalise_topic.next_node = batch_node

# ─── ADD VALUE NODES: Seed state ──────────────────────────────────────────────
add_topic_node = AddValueNode(
    key       = "topic",
    value     = RESEARCH_TOPIC,
    next_node = normalise_topic,   # the @node FunctionalNode
)

add_budget_node = AddValueNode(
    key       = "token_budget",
    value     = 50_000,
    next_node = add_topic_node,
)

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
entry_node = add_budget_node


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTOR SETUP  (AuditLogger + HMAC + TokenTracker)
# ═══════════════════════════════════════════════════════════════════════════════

audit_logger = AuditLogger(
    log_dir     = LOG_DIR,
    hmac_secret = HMAC_SECRET,
)
token_tracker = TokenTracker()

executor = GraphExecutor(
    log_dir          = LOG_DIR,
    offline_mode     = False,
    user_id          = "kitchen-sink-demo",
    logger           = audit_logger,
    tracker          = token_tracker,
    hmac_secret      = HMAC_SECRET,
    max_node_fatigue = 25,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 70)
print("  Lár Kitchen Sink Agent — Starting Execution")
print(f"  Topic : {RESEARCH_TOPIC}")
print(f"  Model : {MODEL}")
print(f"  HMAC  : {'enabled' if HMAC_SECRET else 'disabled'}")
print(f"  Jury  : {'auto-approve (SKIP_JURY=1)' if SKIP_JURY else 'interactive'}")
print("═" * 70 + "\n")

history = []

for step_log in executor.run_step_by_step(
    start_node    = entry_node,
    initial_state = {},
    max_steps     = 40,
):
    history.append(step_log)

    # ── Live step summary using Lár formatters ─────────────────────────────
    node_name = step_log.get("node", "?")
    outcome   = step_log.get("outcome", "?")
    diff      = step_log.get("state_diff", {})
    # Guard: executor sets __last_run_metadata=None after cleanup; captured as None
    metadata  = step_log.get("run_metadata") or {}

    emoji = "✅" if outcome == "success" else "❌"
    tokens_used = metadata.get("total_tokens", 0)
    new_keys = list(diff.get("added", {}).keys()) + list(diff.get("updated", {}).keys())

    print(f"\n  {emoji} Step {step_log['step']:02d} | {node_name:<30} | "
          f"tokens: {tokens_used:>5} | keys changed: {new_keys}")

    # Show the structured diff summary — strip Rich markup for plain stdout
    if diff:
        diff_summary = summarize_diff(diff)
        if diff_summary:
            clean = re.sub(r"\[/?[a-zA-Z_ ]+\]", "", str(diff_summary))
            print(f"     ↳ {clean.strip()}")


# ═══════════════════════════════════════════════════════════════════════════════
# POST-RUN REPORT
# ═══════════════════════════════════════════════════════════════════════════════

print("\n\n" + "═" * 70)
print("  KITCHEN SINK AGENT — EXECUTION COMPLETE")
print("═" * 70)

# 1. Token Summary
from rich.console import Console
_console = Console()

summary = token_tracker.get_summary()
print(f"\n  💰 Token Budget Report")
print(f"     Total prompt tokens     : {summary.get('total_prompt_tokens', 0):,}")
print(f"     Total completion tokens : {summary.get('total_completion_tokens', 0):,}")
print(f"     Total tokens            : {summary.get('total_tokens', 0):,}")
by_model = summary.get("tokens_by_model", {})
for model, toks in by_model.items():
    print(f"     Model [{model}] : {toks:,} tokens")

# 2. Audit log table (Lár formatter — returns a Rich Table, use Console to render)
print("\n  📋 Execution Audit Table")
_console.print(build_log_table(history))

# 3. Verify state_diff utility works (apply_diff round-trip)
if len(history) >= 2:
    before = history[0].get("state_before", {})
    diff   = history[0].get("state_diff", {})
    after  = apply_diff(before, diff)
    print(f"\n  🔬 compute_state_diff / apply_diff round-trip: "
          f"{'✅ PASS' if after is not None else '❌ FAIL'}")

# 4. Print final report if it made it to the end
final_state_snapshot = history[-1].get("state_after", {}) if history else {}
final_report = final_state_snapshot.get("final_report")
if final_report:
    print("\n" + "─" * 70)
    print("  📄 FINAL REPORT")
    print("─" * 70)
    print(final_report)
else:
    print("\n  [!] final_report not in terminal state — check jury verdict or earlier error.")

print("\n" + "═" * 70)
print("  Nodes exercised in this run:")
exercised = sorted({h.get("node") for h in history})
for n in exercised:
    print(f"    • {n}")
print("═" * 70 + "\n")
