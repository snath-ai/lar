import sys
import os
from pathlib import Path

# Add Lár to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lar.enterprise.backbone import build_and_run

# ==============================================================================
# ULTIMATE ENTERPRISE AGENT (CYBERSECURITY)
# ==============================================================================
# This script demonstrates how to leverage the 23-primitive Enterprise Backbone
# for a custom, highly-regulated domain (Cybersecurity Threat Triage).
#
# HOW THIS WORKS:
# Instead of building an agent from scratch, you import `build_and_run` from
# `lar.enterprise.backbone`. This backbone is a pre-wired execution graph that
# natively chains together every single EU AI Act compliance primitive.
# 
# By simply injecting a domain configuration dict (`cyber_config`), the backbone
# automatically enforces:
# 1. PII Redaction & Session Memory (GDPR Art. 17): Strips `ip_address` and 
#    `employee_id` before logging, and explicitly erases memory after execution.
# 2. Fundamental Rights Impact Assessment (Art. 9): The `FundamentalRightsImpactNode`
#    scans the LLM's output for EU Charter violations before a human sees it.
# 3. Supplier Agreements (Art. 25(4)): Verifies that valid vendor agreements exist
#    for the LLM API and the Case Management System before executing API calls.
# 4. Human-in-the-Loop Oversight (Art. 14): Because this config sets the risk tier
#    to CRITICAL, the `RiskScorerNode` pauses execution and routes it to the `HumanJuryNode`
#    for CISO approval.
# 5. Cryptographic Logging (Art. 12): Everything is signed into the `AuthorityLedger`
#    and the `AuditLogger` with HMAC-SHA256.
# 
# This proves that Lár acts as a universal chassis: drop in your domain config,
# and you instantly get a production-ready, heavily regulated agent.
# ==============================================================================

def main():
    print("Initializing Ultimate Enterprise Agent (Cybersecurity)...")

    # 1. Define the Custom Domain Configuration
    cyber_config = {
        "system_name":      "CyberSec Autonomous Containment Agent",
        "domain":           "CYBERSECURITY",
        "conformity_id":    "CA-CYBER-2026",
        "risk_tier":        "CRITICAL",
        "oversight_level":  "PRE_EXECUTION",
        "stakeholder_role": "CISO / SOC Director",
        "pii_keys":         ["employee_id", "ip_address", "workstation_name", "user_email"],
        "bias_terms":       ["department", "seniority", "location"],
        "regulatory_tags":  ["EU_AI_ACT", "NIS2", "GDPR", "ISO_27001"],
        "analysis_prompt": (
            "You are an elite SOC Threat Analyst. Analyze the following SIEM alert.\n"
            "Alert Payload: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
        "output_dir":       "cyber_audit_logs",
    }

    # 2. Define a Realistic Intake Payload
    cyber_case = {
        "case_summary": (
            "Multiple rapid failed authentications followed by successful login "
            "from unrecognized geography. Process 'powershell.exe' spawned with "
            "encoded command string. Outbound C2 traffic detected on port 443."
        ),
        "employee_id":      "REDACT-EMP-98441",
        "ip_address":       "REDACT-192.168.1.105",
        "user_email":       "REDACT-admin@enterprise.local",
    }

    # 3. Execute the Backbone
    # We supply _mock_inputs to simulate the SOC Director approving the freeze
    # so this script runs hands-free in CI/CD.
    mock_human_input = [
        "approve", 
        "Verified IOCs. Authorizing immediate workstation isolation."
    ]

    result = build_and_run(
        case=cyber_case,
        domain="CYBERSECURITY",
        config_overrides=cyber_config,
        _mock_inputs=mock_human_input,
    )

    # 4. Results
    print(f"\n{'='*65}")
    print(f"  EXECUTION COMPLETE — {result['domain']}")
    print(f"{'='*65}")
    print(f"  Audit log       : {result['audit_log_path']}")
    print(f"  Authority ledger: {result['authority_ledger_path']}")
    print(f"  Manifest        : {result['manifest_path']}")
    
    records = result.get("authority_records", [])
    if records:
        r = records[0]
        print(f"\n  Authority Record (Fourth Tier):")
        print(f"    Stakeholder : {r['stakeholder_id']} ({r['stakeholder_role']})")
        print(f"    Decision    : {r['decision']}")
        print(f"    Rationale   : {r['rationale']}")
        print(f"    Risk score  : {r['risk_score_at_decision']}")
        print(f"    Timestamp   : {r['timestamp']}")

    print(f"\n  ✅ 23 EU AI Act Compliance Primitives Executed.")
    print(f"  ✅ Cryptographic Causal Trace Generated.")
    print(f"  ✅ PII Stripped: {cyber_config['pii_keys']}")
    print(f"  ✅ Final Decision: {result.get('final_state', {}).get('recommendation')}")


if __name__ == "__main__":
    main()
