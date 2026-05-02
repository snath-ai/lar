"""
Example 20: Compliance Manifest Generator
==========================================
EU AI Act Step 9 — Exhaustive External Action Inventory.

The paper (Nannini et al., 2026) states:
  "The provider's foundational compliance task is an exhaustive inventory of
   the agent's actions, data flows, connected systems, and affected persons.
   That inventory is the regulatory map."

This example builds a realistic agent graph, then calls ComplianceManifestGenerator
to statically walk the entire graph without executing it, producing:
  - A JSON file suitable for submission to a notified body / compliance officer.
  - A human-readable Markdown report with risk flags.
"""

import os
from lar import LLMNode, ToolNode, RouterNode, BatchNode
from lar.compliance import (
    ComplianceManifestGenerator,
    CredentialVault,
    TransparencyEngine,
)

# --- 1. Build a realistic agent graph (no API keys needed — never executed) ---

# A dummy external email function (affects third parties)
def send_customer_email(content: str) -> str:
    return f"Email sent: {content}"

# A dummy internal DB lookup (user-only)
def lookup_crm(customer_id: str) -> dict:
    return {"name": "Test User", "tier": "premium"}

# Compliance middleware
vault = CredentialVault()
vault.register_credential("smtp_cred", "***VAULT***")
transparency = TransparencyEngine()

# End node — sends email to customer (third-party action)
email_node = ToolNode(
    tool_function=send_customer_email,
    input_keys=["response_text"],
    output_key="email_status",
    next_node=None,
    action_type="SEND_EMAIL",
    affected_parties="THIRD_PARTY",
    transparency_engine=transparency,
    credential_vault=vault,
    credential_key="smtp_cred",
)

# LLM drafts response
draft_node = LLMNode(
    model_name="ollama/phi4",
    prompt_template="Draft a helpful customer service reply for: {crm_data}",
    output_key="response_text",
    next_node=email_node,
)

# CRM lookup — internal only, no vault needed for this example
crm_node = ToolNode(
    tool_function=lookup_crm,
    input_keys=["customer_id"],
    output_key="crm_data",
    next_node=draft_node,
    action_type="READ_CRM",
    affected_parties="USER_ONLY",
    # Note: No vault — the manifest generator will flag this
)

# Router: route high vs. standard tier customers differently
def route_by_tier(state):
    return "HIGH" if state.get("priority") == "urgent" else "STANDARD"

router = RouterNode(
    decision_function=route_by_tier,
    path_map={"HIGH": crm_node, "STANDARD": crm_node},
    default_node=crm_node,
)

# --- 2. Generate the Compliance Manifest (no execution — pure static analysis) ---
print("\n" + "="*60)
print("  COMPLIANCE MANIFEST GENERATOR")
print("  EU AI Act Step 9 — Regulatory Action Inventory")
print("="*60 + "\n")

manifest = ComplianceManifestGenerator(
    start_node=router,
    system_name="Customer Service Agent v1.0"
)

# Generate and print the Markdown report
report = manifest.as_markdown()
print(report)

# Save JSON for auditors
output_path = "compliance_manifest.json"
manifest.save(output_path)

print(f"\n✅ Full JSON manifest saved to: {output_path}")
print("   → Submit this file to your compliance officer or notified body.\n")
