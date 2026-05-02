"""
Example 21: Closing the Final Gaps — Authority Records & Lethal Trifecta Guard
==============================================================================

Gap 1 — AEPD "Rule of 2" / Lethal Trifecta (paper Section 7.2):
  An agent must NOT simultaneously combine (1) untrusted input + (2) sensitive data +
  (3) autonomous action affecting individuals — without human oversight.
  LethalTrifectaGuard enforces this at runtime as a GDPR-grounded constraint.

Gap 2 — The "Fourth Tier" Authority Record (paper Section 9, Finding 10):
  "A fourth tier is absent: infrastructure maintaining an immutable oversight record."
  AuthorityLedger + HumanJuryNode now produce a cryptographically-signable evidence
  chain from action proposal → risk score → human determination → execution outcome.

This example demonstrates both primitives working together in a healthcare scenario:
a clinical agent that analyses patient notes and suggests a diagnosis before
any action affecting the patient is taken.
"""

import os
import sys

# Non-interactive mode: simulate inputs for automated verification
# Input sequence: "approve" then rationale text
SIMULATED_INPUTS = ["approve", "Reviewed patient record. Diagnosis aligns with clinical notes."]
_input_idx = 0

def mock_input(prompt=""):
    global _input_idx
    val = SIMULATED_INPUTS[_input_idx % len(SIMULATED_INPUTS)]
    _input_idx += 1
    print(f"{prompt}{val}")  # echo to stdout so test output is readable
    return val

# Patch input for non-interactive testing
import builtins
builtins.input = mock_input

from lar import GraphState, LLMNode, ToolNode, RouterNode
from lar.compliance import (
    AuthorityLedger,
    LethalTrifectaGuard,
    LethalTrifectaError,
    CredentialVault,
)
from lar import HumanJuryNode

print("\n" + "="*70)
print("  COMPLIANCE VERIFICATION: Authority Records + Lethal Trifecta Guard")
print("="*70 + "\n")

# -----------------------------------------------------------------------
# PART 1: Lethal Trifecta Guard
# -----------------------------------------------------------------------
print("--- PART 1: LethalTrifectaGuard (AEPD Rule of 2) ---\n")

state = GraphState({
    "user_query": "What medication should I take?",  # Leg 1: untrusted input
    "patient_health_data": {"condition": "hypertension"},  # Leg 2: sensitive data
})

guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("user_query") is not None,
    sensitive_data_fn=lambda s: s.get("patient_health_data") is not None,
    autonomous_action_fn=lambda s: True,  # This tool always writes to external system
    human_approval_state_key="jury_decision",
    block_on_violation=True,
)

# Test 1a: Should RAISE — all 3 legs active, no prior human approval
print("Test 1a: All 3 legs active, no human approval (expect violation):")
try:
    guard.check(state, action_label="update_patient_record")
    print("  FAIL: Should have raised LethalTrifectaError")
    sys.exit(1)
except LethalTrifectaError:
    print("  ✅ PASS: LethalTrifectaError raised correctly\n")

# Test 1b: Should PASS — human approval on record
state.set("jury_decision", "approve")
print("Test 1b: All 3 legs active but human approval recorded (expect pass):")
result = guard.check(state, action_label="update_patient_record")
assert result["violation"] == False, "Should not flag violation"
print("  ✅ PASS: Guard cleared with human approval on record\n")

# Test 1c: Should PASS — only 2 legs active (no sensitive data)
state2 = GraphState({"user_query": "What is the weather?"})
print("Test 1c: Only 1 trifecta leg active (expect safe):")
result2 = guard.check(state2, action_label="fetch_weather")
assert result2["all_three_active"] == False
print("  ✅ PASS: 1/3 legs active — no violation\n")


# -----------------------------------------------------------------------
# PART 2: Authority Ledger + Upgraded HumanJuryNode
# -----------------------------------------------------------------------
print("--- PART 2: AuthorityLedger + HumanJuryNode (Fourth Tier Governance) ---\n")

ledger = AuthorityLedger(hmac_secret="test-hmac-secret-for-healthcare")

jury_node = HumanJuryNode(
    prompt="AI has proposed a diagnosis of hypertension. Do you approve?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    context_keys=["ai_diagnosis", "patient_id"],
    next_node=None,
    # --- Fourth Tier fields ---
    authority_ledger=ledger,
    stakeholder_id="dr.smith@hospital.org",
    stakeholder_role="Attending Physician",
    action_description="AI-proposed diagnosis: Hypertension — update patient record",
    risk_score_key="risk_score",
)

review_state = GraphState({
    "patient_id": "PT-00123",
    "ai_diagnosis": "Hypertension (Stage 2)",
    "risk_score": 0.87,
    "patient_health_data": {"bp": "160/100"},
})

print("Simulating physician review via HumanJuryNode...")
jury_node.execute(review_state)

# Verify the authority record was written
records = ledger.get_records()
assert len(records) == 1, f"Expected 1 record, got {len(records)}"
rec = records[0]
assert rec["stakeholder_id"] == "dr.smith@hospital.org"
assert rec["stakeholder_role"] == "Attending Physician"
assert rec["decision"] == "approve"
assert rec["risk_score_at_decision"] == 0.87
assert rec["record_type"] == "AUTHORITY_EXERCISE"
assert "timestamp" in rec
print(f"\n  ✅ PASS: Authority record created:")
print(f"     Stakeholder: {rec['stakeholder_id']} ({rec['stakeholder_role']})")
print(f"     Decision:    {rec['decision']}")
print(f"     Risk Score:  {rec['risk_score_at_decision']}")
print(f"     Timestamp:   {rec['timestamp']}")
print(f"     Rationale:   {rec['rationale']}\n")

# Save the ledger
output_path = "authority_ledger_test.json"
ledger.save(output_path)

# Verify the file was written and has a signature
import json
with open(output_path) as f:
    saved = json.load(f)
assert "signature" in saved, "HMAC signature must be present"
assert saved["total_records"] == 1
print(f"  ✅ PASS: Ledger saved to '{output_path}' with HMAC-SHA256 signature")
print(f"     Signature: {saved['signature'][:32]}...\n")

# Cleanup
os.remove(output_path)

print("="*70)
print("  ALL COMPLIANCE VERIFICATION TESTS PASSED")
print("  Gap 1 (Lethal Trifecta Guard) — ✅ CLOSED")
print("  Gap 2 (Authority Record / Fourth Tier) — ✅ CLOSED")
print("="*70 + "\n")
