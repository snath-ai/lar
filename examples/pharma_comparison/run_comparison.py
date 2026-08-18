"""
Runs all three attacks against both the Lár and LangGraph pharma agents and
reports the real, unedited results side by side.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from actions import EXECUTION_LOG, reset_log
from scenario import ATTACK_1_SOCIAL_ENGINEERING, ATTACK_3_ACTION_ESCALATION

import lar_agent
import langgraph_agent


def section(title):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def report_execution_log(label):
    if not EXECUTION_LOG:
        print(f"    {label}: no action executed.")
    for entry in EXECUTION_LOG:
        print(f"    {label} EXECUTED: {entry['action']}(case_id={entry['case_id']!r}) -> "
              f"note={entry['note'][:60]!r}")


# ─────────────────────────────────────────────────────────────────────────────
section("ATTACK 1 — Social Engineering (fake pre-approval embedded in the note)")
# ─────────────────────────────────────────────────────────────────────────────

print("\n--- Lár ---")
reset_log()
lar_result = lar_agent.run_case("ATK1-LAR", ATTACK_1_SOCIAL_ENGINEERING)
print(f"    Lár final_classification: {lar_result.get('final_classification')}")
report_execution_log("Lár")

print("\n--- LangGraph ---")
reset_log()
lg_result = langgraph_agent.run_case("ATK1-LG", ATTACK_1_SOCIAL_ENGINEERING)
print(f"    LangGraph final_classification: {lg_result.get('final_classification')}")
report_execution_log("LangGraph")


# ─────────────────────────────────────────────────────────────────────────────
section("ATTACK 2 — Stale Authority (approve, then case content drifts before execution)")
# ─────────────────────────────────────────────────────────────────────────────

print("\n--- Lár ---")
reset_log()
lar_atk2 = lar_agent.run_attack_2_stale_authority()
print(f"    Lár outcome: {lar_atk2.get('outcome')}")
report_execution_log("Lár")

print("\n--- LangGraph (naive: interrupt() + signing mixed in one node) ---")
reset_log()
lg_atk2_naive = langgraph_agent.run_attack_2_stale_authority()
print(f"    LangGraph (naive) outcome: {lg_atk2_naive.get('outcome')}")
report_execution_log("LangGraph naive")

print("\n--- LangGraph (hardened: snapshot committed in its own node before interrupt) ---")
reset_log()
lg_atk2_hardened = langgraph_agent.run_attack_2_hardened()
print(f"    LangGraph (hardened) outcome: {lg_atk2_hardened.get('outcome')}")
report_execution_log("LangGraph hardened")


# ─────────────────────────────────────────────────────────────────────────────
section("ATTACK 3 — Unauthorized Action (routine note tries to trigger the SEVERE-only action)")
# ─────────────────────────────────────────────────────────────────────────────

print("\n--- Lár ---")
reset_log()
lar_atk3 = lar_agent.run_case("ATK3-LAR", ATTACK_3_ACTION_ESCALATION)
print(f"    Lár final_classification: {lar_atk3.get('final_classification')}")
report_execution_log("Lár")

print("\n--- LangGraph ---")
reset_log()
lg_atk3 = langgraph_agent.run_case("ATK3-LG", ATTACK_3_ACTION_ESCALATION)
print(f"    LangGraph final_classification: {lg_atk3.get('final_classification')}")
report_execution_log("LangGraph")

print("\n" + "=" * 78)
print("  DONE — all output above is real, from this run.")
print("=" * 78)
