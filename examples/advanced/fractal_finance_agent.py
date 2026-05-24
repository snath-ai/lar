import os
import sys
import json
from pathlib import Path

# Ensure the core lar library is accessible from the test directory
sys.path.insert(0, str(Path(__file__).parent.parent / "lar" / "src"))

from lar import (
    GraphExecutor, LLMNode, FunctionalNode,
    HumanJuryNode, BatchNode, ReduceNode, RouterNode,
    BranchTriageNode,
)
from lar.state import GraphState
from lar.logger import AuditLogger
from lar.adaptive import AdaptiveNode, TopologyValidator
from lar.compliance import (
    PolicyRegistry, ActionPolicy,
    RiskScorerNode,
    CredentialVault,
    PIIRedactionEngine,
    BiasFilterNode,
    TransparencyEngine,
    RuntimeStateVersioner,
    ComplianceManifestGenerator,
    AuthorityLedger,
    LethalTrifectaGuard, LethalTrifectaError,
    SyntheticMarkerNode,
    ProhibitedPracticeGuard,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

MODEL       = "ollama/phi4:latest"
DOMAIN      = "FINANCE"
HMAC_SECRET = os.getenv("HMAC_SECRET", "finance-secret-key")
OUTPUT_DIR  = "enterprise_audit_finance"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PII_KEYS = ["ssn", "dob", "name", "account_number", "email", "applicant_id"]

FINANCE_CASE = {
    "applicant_id":   "APP-2026-00923",
    "ssn":            "000-00-0000",
    "dob":            "1985-04-12",
    "name":           "Jane Doe",
    "account_number": "ACT-99281-XYZ",
    "email":          "jane.doe@example.com",
    "loan_type":      "SME Loan",
    "amount":         "€500,000",
    "credit_summary": "Current debt-to-equity ratio is 4.2. Three missed payments on existing credit lines in the last 18 months.",
    "market_summary": "Industry sector (Commercial Real Estate) is experiencing a 15% downturn. Regional property values declining.",
    "kyc_aml_summary":"Applicant flagged in legacy database for late disclosures. No sanctions or PEP matches. Medium risk KYC profile.",
    "action_type":    "credit_assessment",
}

# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE INFRASTRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

vault = CredentialVault()
vault.register_credential("FINANCE_API_KEY", os.getenv("FINANCE_API_KEY", "mock-jit-token-finance"))

redactor  = PIIRedactionEngine(sensitive_keys=PII_KEYS)
authority_ledger = AuthorityLedger(hmac_secret=HMAC_SECRET)
audit_logger = AuditLogger(log_dir=OUTPUT_DIR, hmac_secret=HMAC_SECRET, pii_redactor=redactor)

registry = PolicyRegistry()
registry.clear()
registry.register("credit_assessment", ActionPolicy(
    domain=DOMAIN,
    process="analysis",
    decision_type="credit_assessment",
    risk_tier="HIGH",
    reversibility=False,
    oversight_level="PRE_EXECUTION",
    regulatory_tags=["EU_AI_ACT", "GDPR", "BASEL_III"],
    affected_parties="THIRD_PARTY",
))

trifecta_guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("credit_summary") is not None,
    sensitive_data_fn=lambda s: any(s.get(k) for k in PII_KEYS),
    autonomous_action_fn=lambda s: True,
    human_approval_state_key="jury_decision",
    block_on_violation=True,
)

transparency = TransparencyEngine()

versioner = RuntimeStateVersioner(conformity_baseline_id="CA-FIN-2026")
baseline = versioner.snapshot(
    tool_catalogue=["credit_adaptive", "market_adaptive", "kyc_adaptive",
                    "reduce", "bias_filter", "external_write"],
    state_schema_keys=list(FINANCE_CASE.keys()) + ["consolidated_assessment", "jury_decision"],
    policy_bindings={"credit_assessment": "PRE_EXECUTION"},
)

inner_validator = TopologyValidator(allowed_tools=[])

# ─────────────────────────────────────────────────────────────────────────────
# ADAPTIVE NODE PROMPTS 
# ─────────────────────────────────────────────────────────────────────────────

CREDIT_PROMPT = """You are a credit risk AI. Analyze this credit data and return a risk assessment.

Credit data: {credit_summary}
Loan: {amount} {loan_type}

Design a single-node graph that analyzes this data. Return ONLY this JSON (fill in the prompt):
{
  "nodes": [
    {
      "id": "credit_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a credit analyst. Assess: {credit_summary} for {amount} {loan_type}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "credit_analysis",
      "next": null
    }
  ],
  "entry_point": "credit_analysis_node"
}"""

MARKET_PROMPT = """You are a market risk AI. Analyze this market data and return an assessment.

Market data: {market_summary}
Loan: {amount} {loan_type}

Design a single-node graph that analyzes this data. Return ONLY this JSON:
{
  "nodes": [
    {
      "id": "market_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a market risk analyst. Assess: {market_summary} for {amount} {loan_type}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "market_analysis",
      "next": null
    }
  ],
  "entry_point": "market_analysis_node"
}"""

KYC_PROMPT = """You are a KYC/AML compliance AI. Analyze this KYC data and return an assessment.

KYC data: {kyc_aml_summary}
Loan: {amount} {loan_type}

Design a single-node graph that analyzes this data. Return ONLY this JSON:
{
  "nodes": [
    {
      "id": "kyc_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a KYC compliance officer. Assess: {kyc_aml_summary} for {amount} {loan_type}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "kyc_analysis",
      "next": null
    }
  ],
  "entry_point": "kyc_analysis_node"
}"""

# ─────────────────────────────────────────────────────────────────────────────
# GRAPH NODES
# ─────────────────────────────────────────────────────────────────────────────

def fetch_credentials(state: GraphState):
    token = vault.get("finance_gateway", "read:credit", "FINANCE_API_KEY")
    state.set("jit_token_present", token is not None)

node_creds = FunctionalNode(func=fetch_credentials, next_node=None)

node_credit = AdaptiveNode(llm_model=MODEL, prompt_template=CREDIT_PROMPT, validator=inner_validator, context_keys=["credit_summary", "amount", "loan_type"], next_node=None)
node_market = AdaptiveNode(llm_model=MODEL, prompt_template=MARKET_PROMPT, validator=inner_validator, context_keys=["market_summary", "amount", "loan_type"], next_node=None)
node_kyc = AdaptiveNode(llm_model=MODEL, prompt_template=KYC_PROMPT, validator=inner_validator, context_keys=["kyc_aml_summary", "amount", "loan_type"], next_node=None)

node_batch = BatchNode(nodes=[node_credit, node_market, node_kyc], next_node=None)

node_triage = BranchTriageNode(
    branch_output_keys=["credit_analysis", "market_analysis", "kyc_analysis"],
    critical_threshold="CRITICAL",
    next_node=None,
)

node_reduce = ReduceNode(
    model_name=MODEL,
    input_keys=["credit_analysis", "market_analysis", "kyc_analysis"],
    output_key="consolidated_assessment",
    prompt_template=(
        "You are a Senior Underwriter. Consolidate these three assessments into a single overall credit decision.\n\n"
        "Credit analysis: {credit_analysis}\n"
        "Market analysis: {market_analysis}\n"
        "KYC analysis: {kyc_analysis}\n\n"
        "Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), recommendation (max 2 sentences), confidence (0.0-1.0). No prose."
    ),
    next_node=None,
)

def parse_consolidated(state: GraphState):
    raw = state.get("consolidated_assessment", "")
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        parsed = json.loads(raw[start:end]) if start >= 0 else {}
    except Exception:
        parsed = {"risk_level": "HIGH", "recommendation": raw[:200], "confidence": 0.5}
    state.set("risk_level",       parsed.get("risk_level", "HIGH"))
    state.set("recommendation",   parsed.get("recommendation", raw[:200]))
    state.set("model_confidence", float(parsed.get("confidence", 0.5)))
    state.set("action_type",      "credit_assessment")

node_parse = FunctionalNode(func=parse_consolidated, next_node=None)

node_bias = BiasFilterNode(input_key="recommendation", sensitive_terms=["race", "gender", "age", "ethnicity", "nationality", "disability", "religion"], next_node=None, jury_node=None)

node_risk = RiskScorerNode(next_node=None, jury_node=None, confidence_key="model_confidence", action_type_key="action_type")

node_jury_early = HumanJuryNode(
    prompt=f"[{DOMAIN}] CRITICAL risk detected in one or more analysis branches.\nReview the individual dimension findings before consolidation proceeds.",
    choices=["approve", "reject"],
    output_key="jury_early_decision",
    context_keys=["branch_findings_summary"],
    next_node=None,
    authority_ledger=authority_ledger,
    stakeholder_id=os.getenv("REVIEWER_EMAIL", "risk.officer@bank.com"),
    stakeholder_role="Chief Risk Officer",
    action_description=f"{DOMAIN} CRITICAL branch — pre-consolidation safety gate",
    risk_score_key=None,
)

node_jury = HumanJuryNode(
    prompt=f"[{DOMAIN}] Multi-dimensional credit assessment ready. Do you approve?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    context_keys=["risk_level", "recommendation", "model_confidence", "branch_findings_summary"],
    next_node=None,
    authority_ledger=authority_ledger,
    stakeholder_id=os.getenv("REVIEWER_EMAIL", "risk.officer@bank.com"),
    stakeholder_role="Chief Risk Officer",
    action_description=f"{DOMAIN} multi-dimensional credit assessment — loan approval pending",
    risk_score_key="model_confidence",
)

node_bias.jury_node = node_jury
node_risk.jury_node = node_jury

def compliance_checks(state: GraphState):
    trifecta_guard.check(state, action_label="loan_approval")
    transparency.flag(action_type="credit_assessment", tool_name="loan_approval", affected_description=f"Loan applicant in {DOMAIN} workflow", run_id=state.get("run_id", "unknown"))
    snap = versioner.snapshot(
        tool_catalogue=["credit_adaptive", "market_adaptive", "kyc_adaptive", "reduce", "bias_filter", "external_write"],
        state_schema_keys=list(state._state.keys()),
        policy_bindings={"credit_assessment": "PRE_EXECUTION"},
    )
    state.set("drift_report", snap.get("drift_report", {"drift_detected": False}))

node_checks = FunctionalNode(func=compliance_checks, next_node=None)
node_checks.compliance_metadata = {
    "action_type":      "external_write",
    "affected_parties": "THIRD_PARTY",
    "external_action":  True,
    "description":      "Post-approval loan origination — affects applicant.",
}

node_prohibited = ProhibitedPracticeGuard(input_key="recommendation", next_node=None, block_on_violation=True)

node_marker = SyntheticMarkerNode(input_key="recommendation", output_key="final_output", marker_type="VISIBLE", next_node=None)

node_branch_router = RouterNode(
    decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
    path_map={
        "critical": node_jury_early,
        "ok":       node_reduce,
    },
)

# ─────────────────────────────────────────────────────────────────────────────
# WIRE THE GRAPH
# ─────────────────────────────────────────────────────────────────────────────

node_creds.next_node      = node_batch
node_batch.next_node      = node_triage
node_triage.next_node     = node_branch_router
node_jury_early.next_node = node_reduce
node_reduce.next_node     = node_parse
node_parse.next_node      = node_bias
node_bias.next_node       = node_risk
node_risk.next_node       = node_checks
node_jury.next_node       = node_checks
node_checks.next_node     = node_prohibited
node_prohibited.next_node = node_marker

manifest = ComplianceManifestGenerator(start_node=node_creds, system_name="AI Fractal Finance Assessment Agent")
manifest_path = f"{OUTPUT_DIR}/compliance_manifest_finance_fractal.json"
manifest.save(manifest_path)

if __name__ == "__main__":
    import builtins
    print("\n" + "="*65)
    print("  Lár Fractal Finance Compliance Agent")
    print("  BatchNode + AdaptiveNode + Recursion + Full EU AI Act Backbone")
    print(f"  Domain  : {DOMAIN}")
    print(f"  Applicant: {FINANCE_CASE['name']} — {FINANCE_CASE['loan_type']}")
    print("="*65 + "\n")

    mock_inputs = [
        "approve",
        "Reviewed early CRITICAL warning. Market downturn acceptable given other collateral. Proceeding to consolidation.",
        "approve",
        "Reviewed consolidated assessment. Risk accepted. Approving SME loan application.",
    ]
    _idx = [0]
    _orig = builtins.input
    def _fake(prompt=""):
        val = mock_inputs[_idx[0] % len(mock_inputs)]
        _idx[0] += 1
        print(f"{prompt}{val}")
        return val
    builtins.input = _fake

    try:
        executor = GraphExecutor(log_dir=OUTPUT_DIR, hmac_secret=HMAC_SECRET, logger=audit_logger, versioner=versioner)
        initial_state = {**FINANCE_CASE}
        for step in executor.run_step_by_step(node_creds, initial_state):
            node_name = step.get("node", "?")
            added = list(step.get("state_diff", {}).get("added", {}).keys())
            print(f"    ✓ {node_name:<35} → {added}")
        authority_ledger.save(f"{OUTPUT_DIR}/authority_ledger_finance_fractal.json")
    finally:
        builtins.input = _orig

    print("\nAll primitives executed. Fractal finance agent run complete.")
    print(f"Artefacts in: {OUTPUT_DIR}/")
