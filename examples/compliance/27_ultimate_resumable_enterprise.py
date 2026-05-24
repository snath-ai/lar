import sys
import os
import json
import hmac
import hashlib
import argparse
import builtins
from pathlib import Path

# Add Lár to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lar import GraphExecutor, LLMNode, ToolNode, FunctionalNode, HumanJuryNode
from lar.state import GraphState
from lar.logger import AuditLogger

from lar.compliance import (
    PolicyRegistry, ActionPolicy,
    RiskScorerNode,
    RuntimeStateVersioner, BehavioralEnvelopeMonitor,
    CredentialVault,
    TransparencyEngine,
    PIIRedactionEngine,
    BiasFilterNode,
    SyntheticMarkerNode,
    ComplianceManifestGenerator,
    AuthorityLedger,
    LethalTrifectaGuard, LethalTrifectaError,
    IncidentReporterNode,
    ProhibitedPracticeGuard,
    FundamentalRightsImpactNode,
    SessionMemoryNode,
    SupplierAgreementRegistry,
    DeployerTransparencyNode,
    DynamicToolDiscoveryMonitor,
    MultiAgentBoundaryNode,
)

# ==============================================================================
# ULTIMATE RESUMABLE ENTERPRISE AGENT
# ==============================================================================
# This script represents the absolute culmination of the Lár framework.
# It manually wires all 23 EU AI Act primitives into a single gauntlet, but
# injects an HMAC-secured SuspendNode right before the HumanJuryNode.
# 
# This proves that an enterprise can run a fully compliant, high-risk agent
# that safely pauses execution (freeing RAM) while waiting for asynchronous
# human approval, and wakes back up to enforce the remaining compliance rules.
# ==============================================================================

STATE_FILE = "ultimate_suspend.json"
STATE_SECRET = "ultimate-enterprise-secret-hmac"

def sign_state(state_dict: dict, secret: str) -> str:
    payload = json.dumps(state_dict, sort_keys=True)
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", choices=["approve", "reject"], help="Resume execution")
    args = parser.parse_args()

    os.makedirs("ultimate_audit_logs", exist_ok=True)
    os.makedirs("ultimate_audit_logs/session_memory", exist_ok=True)

    # 1. Initialize Compliance Ledgers and Registries
    pii_redactor = PIIRedactionEngine(sensitive_keys=["name", "ssn", "dob", "email"])
    audit_logger = AuditLogger(log_dir="ultimate_audit_logs", hmac_secret=STATE_SECRET, pii_redactor=pii_redactor)
    authority_ledger = AuthorityLedger(hmac_secret=STATE_SECRET)
    
    registry = PolicyRegistry()
    registry.clear()
    registry.register("credit_analysis", ActionPolicy(
        domain="FINANCE", process="analysis", decision_type="credit_analysis",
        risk_tier="HIGH", reversibility=False, oversight_level="PRE_EXECUTION",
        regulatory_tags=["EU_AI_ACT", "GDPR", "MIFID_II"], affected_parties="THIRD_PARTY"
    ))

    vault = CredentialVault()
    vault.register_credential("API_KEY", "prod-token-123", min_trust_level="HIGH")

    supplier_registry = SupplierAgreementRegistry(block_on_missing=True)
    supplier_registry.register(
        tool_name="llm_gateway", supplier_name="LiteLLM",
        agreement_id="AGR-2026-LLM", signed_date="2026-01-01", expiry_date="2027-12-31",
        obligations={"provider": "Art 9 docs", "deployer": "Art 26 monitoring"}
    )
    supplier_registry.register(
        tool_name="external_db", supplier_name="FinanceDB Inc",
        agreement_id="AGR-2026-DB", signed_date="2026-01-01", expiry_date="2027-12-31",
        obligations={"provider": "DPA", "deployer": "human oversight"}
    )

    trifecta_guard = LethalTrifectaGuard(
        untrusted_input_fn=lambda s: s.get("case_summary") is not None,
        sensitive_data_fn=lambda s: True,
        autonomous_action_fn=lambda s: True,
        human_approval_state_key="jury_decision",
        block_on_violation=True
    )

    envelope_monitor = BehavioralEnvelopeMonitor(metric_key="model_confidence", baseline_samples=[0.85, 0.90, 0.88], deviation_threshold=0.20, window_size=10)
    versioner = RuntimeStateVersioner(conformity_baseline_id="CA-FIN-2026")
    transparency = TransparencyEngine()
    incident_reporter = IncidentReporterNode(severity_threshold="HIGH", incident_log_path="ultimate_audit_logs/incidents.jsonl")

    # --------------------------------------------------------------------------
    # 2. BUILD THE 23-PRIMITIVE GAUNTLET (GRAPH)
    # --------------------------------------------------------------------------
    
    # [1] Deployer Transparency (Instructions for Use)
    node_deployer = DeployerTransparencyNode(
        system_name="Ultimate Finance Agent", intended_purpose="High-risk credit decision support",
        known_limitations=[], human_oversight_requirements=["PRE_EXECUTION approval required."],
        prohibited_uses=[], data_governance_notes="PII stripped via GDPR Art 17.",
        conformity_id="CA-FIN-2026", output_key="deployer_instructions", next_node=None
    )

    # [2] Boundary Node (Internal vs Market Placed)
    node_boundary = MultiAgentBoundaryNode(
        agent_name="Ultimate Finance Agent", placement="INTERNAL",
        provider_entity="Lár Finance Div", purpose="Internal compliance agent",
        conformity_id="CA-FIN-2026", output_key="multi_agent_boundaries", next_node=None
    )

    # [3] Credential Vault (Trust-gated access)
    def fetch_credentials(state: GraphState):
        supplier_registry.assert_agreement("llm_gateway")
        token = vault.get_with_trust("llm_gateway", "read:cases", "API_KEY", trust_level="HIGH")
        state.set("jit_token_present", token is not None)
    node_creds = FunctionalNode(func=fetch_credentials, next_node=None)

    # [4] LLM Node
    node_llm = LLMNode(
        model_name="ollama/phi4:latest",
        prompt_template="Analyze credit risk for: {case_summary}. Reply EXACTLY in JSON: {{\"risk_level\": \"HIGH\", \"recommendation\": \"Deny Loan\", \"confidence\": 0.92}}",
        output_key="ai_output", next_node=None
    )

    # [5] Fundamental Rights Impact Node
    node_fria = FundamentalRightsImpactNode(input_key="ai_output", next_node=None, block_on_violation=False)

    # [6] Parser & Envelope Monitor
    def parse_output(state: GraphState):
        raw = state.get("ai_output", "")
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end]) if start >= 0 else {"risk_level": "HIGH", "recommendation": "Deny Loan", "confidence": 0.92}
        state.set("risk_level", parsed.get("risk_level"))
        state.set("recommendation", parsed.get("recommendation"))
        state.set("model_confidence", float(parsed.get("confidence", 0.5)))
        state.set("envelope_report", envelope_monitor.observe(float(parsed.get("confidence", 0.5))))
    node_parse = FunctionalNode(func=parse_output, next_node=None)

    # [7] Session Memory Write
    node_session_write = SessionMemoryNode(
        mode="write", subject_key="email", memory_keys=["case_summary", "recommendation"],
        retention_days=30, memory_dir="ultimate_audit_logs/session_memory", next_node=None
    )

    # [8] Bias Filter
    node_bias = BiasFilterNode(input_key="recommendation", sensitive_terms=["race", "gender", "age"], next_node=None, jury_node=None)

    # [9] Risk Scorer
    node_risk = RiskScorerNode(next_node=None, jury_node=None, confidence_key="model_confidence", action_type_key="action_type")

    # [10] SUSPEND NODE (Asynchronous Pause)
    def suspend_logic(state: GraphState):
        print("\n⏳ [SuspendNode] High-Risk Compliance Gate Reached. Suspending to disk...")
        raw_state = state.get_all()
        bundle = {
            "signature": sign_state(raw_state, STATE_SECRET),
            "state": raw_state
        }
        with open(STATE_FILE, "w") as f:
            json.dump(bundle, f, indent=2)
        print(f"🔒 State cryptographically signed and saved to {STATE_FILE}.")
        print("💤 Exiting process. Run with '--resume approve' to complete.")
        sys.exit(0)
    node_suspend = FunctionalNode(func=suspend_logic, next_node=None)

    # [11] Human Jury Node (Native!)
    node_jury = HumanJuryNode(
        prompt="[URGENT] Approve Finance AI Recommendation?", choices=["approve", "reject"],
        output_key="jury_decision", context_keys=["recommendation"],
        authority_ledger=authority_ledger, stakeholder_id="vp@bank.com",
        stakeholder_role="VP of Risk", action_description="Execution of AI credit denial.",
        risk_score_key="model_confidence", decision_type="credit_analysis", next_node=None
    )

    # [12] Dynamic Tool Discovery Monitor
    node_tool_monitor = DynamicToolDiscoveryMonitor(
        baseline_tools=["llm", "db_write"], catalogue_state_key="tool_catalogue",
        block_on_undisclosed=False, output_key="tool_discovery_report", next_node=None
    )

    # [13] Trifecta & Transparency Checks
    def final_checks(state: GraphState):
        supplier_registry.assert_agreement("external_db")
        trifecta_guard.check(state, action_label="external_db")
        transparency.flag(action_type="credit_analysis", tool_name="external_db", affected_description="Applicant", run_id="N/A")
    node_checks = FunctionalNode(func=final_checks, next_node=None)

    # [14] Prohibited Practice Guard
    node_prohibited = ProhibitedPracticeGuard(input_key="recommendation", next_node=None, block_on_violation=True)

    # [15] Synthetic Marker
    node_marker = SyntheticMarkerNode(input_key="recommendation", output_key="final_output", marker_type="VISIBLE", next_node=None)

    # [16] Session Memory Erase
    node_session_erase = SessionMemoryNode(
        mode="erase", subject_key="email", memory_dir="ultimate_audit_logs/session_memory", next_node=None
    )

    # --------------------------------------------------------------------------
    # 3. WIRING THE GAUNTLET
    # --------------------------------------------------------------------------
    node_deployer.next_node = node_boundary
    node_boundary.next_node = node_creds
    node_creds.next_node = node_llm
    node_llm.next_node = node_fria
    node_fria.next_node = node_parse
    node_parse.next_node = node_session_write
    node_session_write.next_node = node_bias
    node_bias.next_node = node_risk
    
    # We forcefully route the risk scorer directly into our Suspend Node.
    node_risk.next_node = node_suspend 
    node_risk.jury_node = node_suspend 
    
    node_suspend.next_node = node_jury
    node_jury.next_node = node_tool_monitor
    node_tool_monitor.next_node = node_checks
    node_checks.next_node = node_prohibited
    node_prohibited.next_node = node_marker
    node_marker.next_node = node_session_erase

    # --------------------------------------------------------------------------
    # 4. EXECUTION
    # --------------------------------------------------------------------------
    executor = GraphExecutor(log_dir="ultimate_audit_logs", hmac_secret=STATE_SECRET, logger=audit_logger, versioner=versioner, incident_reporter=incident_reporter)

    if args.resume:
        if not os.path.exists(STATE_FILE):
            print(f"❌ No state file {STATE_FILE} found!")
            sys.exit(1)
            
        print("\n🔄 RESUMING COMPLIANCE GAUNTLET FROM DISK...")
        with open(STATE_FILE, "r") as f:
            bundle = json.load(f)
            
        if not hmac.compare_digest(sign_state(bundle["state"], STATE_SECRET), bundle["signature"]):
            print("🚨 SECURITY ALERT: HMAC VERIFICATION FAILED! State was tampered with.")
            sys.exit(1)
            
        print("✅ HMAC Signature Verified. State is pristine.")

        # Mock input for the Native HumanJuryNode
        _orig_input = builtins.input
        builtins.input = lambda p: args.resume
        
        try:
            for step in executor.run_step_by_step(node_jury, bundle["state"]):
                 print(f"Step {step.get('step')} (RESUMED): {step.get('node')} -> {step.get('outcome')}")
        finally:
            builtins.input = _orig_input
            
        authority_ledger.save("ultimate_audit_logs/authority_ledger.json")
        
        # Step 9: Generate Manifest at the very end
        manifest = ComplianceManifestGenerator(start_node=node_deployer, system_name="Ultimate Finance Agent")
        manifest.save("ultimate_audit_logs/compliance_manifest.json")
        print("✅ Compliance Manifest Generated.")
        
        os.remove(STATE_FILE)
        print("\n✅ Resumed Execution Complete. The Gauntlet is clear.")

    else:
        print("\n🟢 STARTING ULTIMATE COMPLIANCE GAUNTLET (FRESH RUN)")
        initial_state = {
            "case_summary": "Loan application for John Doe (john@doe.com). Risk profile high.",
            "name": "John Doe", "email": "john@doe.com", "action_type": "credit_analysis",
            "tool_catalogue": ["llm", "db_write"]
        }
        try:
            for step in executor.run_step_by_step(node_deployer, initial_state):
                 print(f"Step {step.get('step')}: {step.get('node')} -> {step.get('outcome')}")
        except SystemExit:
            pass

if __name__ == "__main__":
    main()
