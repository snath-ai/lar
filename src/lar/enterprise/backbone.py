"""
Lár Enterprise Compliance Backbone
====================================
Reusable backbone that wires the compliance primitives into a single auditable graph.
Drop in a DOMAIN_CONFIG dict to target any regulated vertical.

Paper coverage (Nannini et al., 2026 — all 23 requirements exercised at runtime):
  Art. 9      → PolicyRegistry + FundamentalRightsImpactNode (FRIA)
  Art. 9 PMM  → BehavioralEnvelopeMonitor (output variance monitoring)
  Art. 12     → AuditLogger (causal trace + verify_step_integrity + log_plan_switch)
  Art. 13     → DeployerTransparencyNode (instructions for use) + TransparencyEngine
  Art. 14     → RiskScorerNode + HumanJuryNode (automation_boundary + decision_type)
  Art. 3(23)  → RuntimeStateVersioner + DriftDetector + DynamicToolDiscoveryMonitor
  Art. 15(4)  → CredentialVault (get_with_trust — trust-based privilege)
  Art. 25(4)  → SupplierAgreementRegistry (written agreement enforcement)
  Art. 50(2)  → SyntheticMarkerNode (C2PA / visible disclaimer)
  Art. 73-74  → IncidentReporterNode (real-time incident detection + 24/72h deadlines)
  Art. 3      → MultiAgentBoundaryNode (internal vs. market-placed sub-agents)
  GDPR 5/17   → PIIRedactionEngine + SessionMemoryNode (erasable per-subject memory)
  prEN18283   → BiasFilterNode (bias management)
  Step 9      → ComplianceManifestGenerator (action inventory + adjacent legislation)
  AEPD PoP    → LethalTrifectaGuard (Rule-of-2 runtime block)
  Fourth Tier → AuthorityLedger (stakeholder/role/rationale/risk signed record)
  Art. 5      → ProhibitedPracticeGuard (auto-wired into executor)
  BranchTriage→ BranchTriageNode (fractal agents — see 23_fractal_compliance_showcase.py)
"""

from __future__ import annotations
import os, json, datetime, builtins
from typing import Any, Dict, List, Optional

from lar import GraphExecutor, LLMNode, ToolNode, FunctionalNode, HumanJuryNode
from lar.state import GraphState
from lar.logger import AuditLogger
from lar.compliance.pii_redactor import PIIRedactionEngine

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
    # v2.2.0 gap-closure
    FundamentalRightsImpactNode,
    SessionMemoryNode,
    SupplierAgreementRegistry,
    DeployerTransparencyNode,
    DynamicToolDiscoveryMonitor,
    MultiAgentBoundaryNode,
)


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN_CONFIG  ←  THIS IS YOUR ONLY CUSTOMISATION POINT
# ─────────────────────────────────────────────────────────────────────────────
# Swap the dict below to retarget the backbone for your vertical.
# Keys are self-documenting; see DOMAIN_PRESETS at the bottom of this file.

DEFAULT_CONFIG: Dict[str, Any] = {
    # ── Identity ──────────────────────────────────────────────────────────────
    "system_name":      "Generic High-Risk Enterprise Agent v1.0",
    "domain":           "GENERIC",          # FINANCE | HEALTHCARE | PHARMA | LEGAL | HR
    "conformity_id":    "CA-GENERIC-2026",

    # ── Risk thresholds ───────────────────────────────────────────────────────
    "risk_tier":        "HIGH",             # LOW | MEDIUM | HIGH | CRITICAL
    "oversight_level":  "PRE_EXECUTION",    # RETROSPECTIVE | REALTIME | PRE_EXECUTION
    "irreversible":     True,

    # ── Stakeholder (for AuthorityLedger) ─────────────────────────────────────
    "stakeholder_id":   os.getenv("REVIEWER_EMAIL", "reviewer@enterprise.org"),
    "stakeholder_role": "Compliance Officer",

    # ── Credential vault keys ─────────────────────────────────────────────────
    "api_credential_key": "ENTERPRISE_API_KEY",
    "api_credential_val": os.getenv("ENTERPRISE_API_KEY", "mock-jit-token-xyz"),

    # ── LLM ───────────────────────────────────────────────────────────────────
    "model":            "ollama/phi4:latest",

    # ── Prompt ────────────────────────────────────────────────────────────────
    # {case_summary} is injected from state at runtime
    "analysis_prompt":  (
        "You are a specialist reviewing the following case in a regulated environment.\n"
        "Case: {case_summary}\n\n"
        "You MUST reply with ONLY a single JSON object containing exactly three keys:\n"
        "risk_level (one of LOW/MEDIUM/HIGH/CRITICAL), "
        "recommendation (max 2 sentences), confidence (float 0.0-1.0).\n"
        "No prose. No markdown. Pure JSON only."
    ),

    # ── PII fields to strip before signing the audit log ─────────────────────
    "pii_keys":         ["name", "dob", "ssn", "nhs_id", "patient_id",
                         "account_number", "email", "trial_subject_id"],

    # ── Bias-sensitive terms (routed to jury if found in LLM output) ──────────
    "bias_terms":       ["race", "gender", "age", "religion",
                         "disability", "ethnicity", "nationality"],

    # ── Regulatory tags (shown in manifest + ledger) ──────────────────────────
    "regulatory_tags":  ["EU_AI_ACT", "GDPR"],

    # ── Output dir ────────────────────────────────────────────────────────────
    "output_dir":       "enterprise_audit",
    "hmac_secret":      os.getenv("HMAC_SECRET", "change-me-in-prod"),
}


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN PRESETS  — override DEFAULT_CONFIG with one of these
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "FINANCE": {
        "system_name":      "AI Credit / Trading Decision Agent",
        "domain":           "FINANCE",
        "conformity_id":    "CA-FIN-2026",
        "stakeholder_role": "Risk Officer",
        "regulatory_tags":  ["EU_AI_ACT", "GDPR", "MIFID_II", "DORA", "FINRA"],
        "pii_keys":         ["account_number", "ssn", "iban", "email", "name", "dob"],
        "bias_terms":       ["race", "gender", "age", "postal_code", "nationality"],
        "analysis_prompt": (
            "You are a credit risk analyst. Assess the following loan/credit application.\n"
            "Application: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
    },
    "HEALTHCARE": {
        "system_name":      "AI Clinical Decision Support Agent",
        "domain":           "HEALTHCARE",
        "conformity_id":    "CA-HC-2026",
        "stakeholder_role": "Attending Physician",
        "regulatory_tags":  ["EU_AI_ACT", "GDPR", "MDR", "HIPAA", "FDA_21CFR11"],
        "pii_keys":         ["patient_id", "nhs_id", "dob", "name", "diagnosis"],
        "bias_terms":       ["race", "gender", "age", "disability", "ethnicity"],
        "analysis_prompt": (
            "You are a clinical AI assistant. Review the following patient summary.\n"
            "Summary: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
    },
    "PHARMA": {
        "system_name":      "AI Clinical Trial Eligibility Agent",
        "domain":           "PHARMA",
        "conformity_id":    "CA-PH-2026",
        "stakeholder_role": "Principal Investigator",
        "regulatory_tags":  ["EU_AI_ACT", "GDPR", "FDA_21CFR11", "ICH_GCP", "EMA"],
        "pii_keys":         ["trial_subject_id", "dob", "name", "genetic_data"],
        "bias_terms":       ["race", "gender", "age", "ethnicity"],
        "analysis_prompt": (
            "You are a clinical trial eligibility screener. Evaluate the candidate.\n"
            "Candidate: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
    },
    "LEGAL": {
        "system_name":      "AI Legal Triage Agent",
        "domain":           "LEGAL",
        "conformity_id":    "CA-LG-2026",
        "stakeholder_role": "Supervising Attorney",
        "regulatory_tags":  ["EU_AI_ACT", "GDPR", "DSA", "UPL"],
        "pii_keys":         ["name", "email", "case_id", "dob"],
        "bias_terms":       ["race", "gender", "age", "religion", "nationality"],
        "analysis_prompt": (
            "You are a legal AI assistant performing initial case triage.\n"
            "Matter: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
    },
    "HR": {
        "system_name":      "AI Recruitment Screening Agent",
        "domain":           "HR",
        "conformity_id":    "CA-HR-2026",
        "stakeholder_role": "HR Director",
        "regulatory_tags":  ["EU_AI_ACT", "GDPR", "EQUALITY_ACT"],
        "pii_keys":         ["name", "email", "dob", "address"],
        "bias_terms":       ["race", "gender", "age", "religion",
                             "disability", "ethnicity", "nationality", "pregnancy"],
        "analysis_prompt": (
            "You are an HR screening AI. Evaluate the following candidate profile.\n"
            "Profile: {case_summary}\n\n"
            "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
            "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
        ),
    },
}


def build_config(domain: str = "GENERIC") -> Dict[str, Any]:
    """Merge domain preset over defaults. Returns the final config dict."""
    cfg = DEFAULT_CONFIG.copy()
    preset = DOMAIN_PRESETS.get(domain.upper(), {})
    cfg.update(preset)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# BACKBONE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_and_run(
    case: Dict[str, Any],
    domain: str = "GENERIC",
    config_overrides: Optional[Dict[str, Any]] = None,
    _mock_inputs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build the full 23-requirement paper-mapped compliance graph and execute it for
    a single case.  Every v2.2.0 node is wired into the live execution path — no
    requirement is merely declared; every one fires at runtime.

    Args:
        case:             The intake payload (dict). Must contain 'case_summary'.
        domain:           One of FINANCE | HEALTHCARE | PHARMA | LEGAL | HR | GENERIC.
        config_overrides: Any key from DEFAULT_CONFIG to override at call time.
        _mock_inputs:     For automated testing — replaces builtins.input responses.

    Returns:
        dict with keys: run_id, domain, decision, confidence, risk_level,
                        audit_log_path, authority_ledger_path, manifest_path,
                        final_state (all state keys after execution).
    """
    # ── 0. Config ─────────────────────────────────────────────────────────────
    cfg = build_config(domain)
    if config_overrides:
        cfg.update(config_overrides)

    os.makedirs(cfg["output_dir"], exist_ok=True)

    # ── 0a. Mock input for non-interactive / CI runs ───────────────────────────
    if _mock_inputs:
        _idx = [0]
        _orig_input = builtins.input
        def _fake_input(prompt=""):
            val = _mock_inputs[_idx[0] % len(_mock_inputs)]
            _idx[0] += 1
            print(f"{prompt}{val}")
            return val
        builtins.input = _fake_input

    try:
        return _run(case, cfg)
    finally:
        if _mock_inputs:
            builtins.input = _orig_input


def _run(case: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    print(f"\n{'='*65}")
    print(f"  Lár Enterprise Compliance Backbone  (v2.2.0 — 23 requirements)")
    print(f"  Domain : {cfg['domain']}")
    print(f"  System : {cfg['system_name']}")
    print(f"{'='*65}\n")

    # ── STEP 7: Credential Vault (Art. 15(4) — NHI privilege + trust gating) ─
    vault = CredentialVault()
    # Row L: register with HIGH minimum trust level — get_with_trust() enforces this
    vault.register_credential(
        cfg["api_credential_key"],
        cfg["api_credential_val"],
        min_trust_level="HIGH",
    )

    # ── STEP 6a: PII Redactor (GDPR Art. 17 — right to erasure) ──────────────
    redactor = PIIRedactionEngine(sensitive_keys=cfg["pii_keys"])

    # ── STEP 6b: Authority Ledger (Art. 12/14 — fourth tier) ─────────────────
    ledger_path = f"{cfg['output_dir']}/authority_ledger.json"
    authority_ledger = AuthorityLedger(hmac_secret=cfg["hmac_secret"])

    # ── STEP 6c: Causal Audit Logger (Art. 12) ────────────────────────────────
    audit_logger = AuditLogger(
        log_dir=cfg["output_dir"],
        hmac_secret=cfg["hmac_secret"],
        pii_redactor=redactor,
    )

    # ── STEP 3/4: Policy Registry (Art. 9 / Art. 14 risk taxonomy) ───────────
    registry = PolicyRegistry()
    registry.clear()  # reset singleton between runs
    registry.register("case_analysis", ActionPolicy(
        domain=cfg["domain"],
        process="analysis",
        decision_type="case_analysis",
        risk_tier=cfg["risk_tier"],
        reversibility=not cfg["irreversible"],
        oversight_level=cfg["oversight_level"],
        regulatory_tags=cfg["regulatory_tags"],
        affected_parties="THIRD_PARTY",
    ))
    registry.register("final_output", ActionPolicy(
        domain=cfg["domain"],
        process="output",
        decision_type="final_output",
        risk_tier="MEDIUM",
        reversibility=True,
        oversight_level="REALTIME",
        regulatory_tags=cfg["regulatory_tags"],
        affected_parties="THIRD_PARTY",
    ))

    # ── STEP 9: Lethal Trifecta Guard (AEPD Rule of 2) ───────────────────────
    trifecta_guard = LethalTrifectaGuard(
        untrusted_input_fn=lambda s: s.get("case_summary") is not None,
        sensitive_data_fn=lambda s: any(s.get(k) for k in cfg["pii_keys"]),
        autonomous_action_fn=lambda s: True,  # always True — any external action
        human_approval_state_key="jury_decision",
        block_on_violation=True,
    )

    # ── STEP 5: Transparency Engine (Art. 13, 50) ────────────────────────────
    transparency = TransparencyEngine()

    # ── STEP 11: Runtime State Versioner (Art. 3(23) drift) ──────────────────
    versioner = RuntimeStateVersioner(conformity_baseline_id=cfg["conformity_id"])
    tool_catalogue = ["llm_analysis", "trifecta_check", "bias_filter",
                      "synthetic_marker", "external_write"]
    baseline = versioner.snapshot(
        tool_catalogue=tool_catalogue,
        state_schema_keys=list(case.keys()) + ["ai_output", "jury_decision"],
        policy_bindings={"case_analysis": cfg["oversight_level"]},
    )

    # ── Row G: Supplier Agreement Registry (Art. 25(4)) ──────────────────────
    supplier_registry = SupplierAgreementRegistry(block_on_missing=True)
    supplier_registry.register(
        tool_name="llm_gateway",
        supplier_name="LiteLLM / Ollama OSS",
        agreement_id=f"AGR-{cfg['domain']}-LLM-2026",
        signed_date="2026-01-01",
        expiry_date="2027-12-31",
        obligations={
            "provider": "Art. 9 risk documentation, model card disclosure",
            "deployer": "Art. 26 monitoring obligations, incident reporting",
        },
    )
    supplier_registry.register(
        tool_name="external_write",
        supplier_name="Enterprise Case Management System Ltd",
        agreement_id=f"AGR-{cfg['domain']}-CMS-2026",
        signed_date="2026-01-15",
        expiry_date="2027-12-31",
        obligations={
            "provider": "Art. 25(4) written agreement — data processing addendum",
            "deployer": "Art. 26 deployer obligations, human oversight of case writes",
        },
    )

    # ── Row B: Behavioral Envelope Monitor (Art. 9 PMM) ─────────────────────
    # Baseline confidence samples from domain conformity assessment runs
    envelope_monitor = BehavioralEnvelopeMonitor(
        metric_key="model_confidence",
        baseline_samples=[0.85, 0.90, 0.87, 0.88, 0.92, 0.86, 0.91, 0.89],
        deviation_threshold=0.20,
        window_size=10,
    )

    # ── Row J: Incident Reporter (Art. 73-74) — executor hook ─────────────────
    incident_reporter = IncidentReporterNode(
        severity_threshold="HIGH",
        incident_log_path=f"{cfg['output_dir']}/incidents.jsonl",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # GRAPH NODES  (in execution order)
    # ─────────────────────────────────────────────────────────────────────────

    # ── Row E: Deployer Transparency Node (Art. 13 — instructions for use) ───
    node_deployer = DeployerTransparencyNode(
        system_name=cfg["system_name"],
        intended_purpose=(
            f"High-risk AI decision support for {cfg['domain']} domain — "
            f"Annex III classification per EU AI Act."
        ),
        known_limitations=[
            "Confidence scores are probabilistic — not deterministic guarantees.",
            "English-language case summaries only in v2.2.0.",
            "Domain-specific bias terms are configurable but not exhaustive.",
        ],
        human_oversight_requirements=[
            f"All PRE_EXECUTION risk actions require {cfg['stakeholder_role']} approval.",
            "CRITICAL and HIGH risk decisions must be recorded in AuthorityLedger.",
            "Stakeholder must review AI recommendation and rationale before approving.",
        ],
        prohibited_uses=[
            "Fully autonomous decision-making without human approval gate.",
            "Processing outside the declared domain without re-conformity assessment.",
            "Use as sole decision basis without contextual human judgment.",
        ],
        data_governance_notes=(
            f"PII fields {cfg['pii_keys']} are stripped before HMAC signing (GDPR Art. 17). "
            "Per-subject session memory is erasable on request."
        ),
        conformity_id=cfg["conformity_id"],
        output_key="deployer_instructions",
        next_node=None,
    )

    # ── Row I: Multi-Agent Boundary Node (Art. 3 sub-agent classification) ───
    node_boundary = MultiAgentBoundaryNode(
        agent_name=cfg["system_name"],
        placement="INTERNAL",
        provider_entity="Lár Enterprise Backbone v2.2.0",
        purpose=(
            f"Internal {cfg['domain']} compliance agent — covered by parent CE "
            f"conformity assessment {cfg['conformity_id']}."
        ),
        conformity_id=cfg["conformity_id"],
        output_key="multi_agent_boundaries",
        next_node=None,
    )

    # ── Node A: NHI credential fetch (Art. 15(4) — Row L: get_with_trust) ────
    def fetch_credentials(state: GraphState):
        # Row G: assert supplier agreement before calling the LLM gateway
        supplier_registry.assert_agreement("llm_gateway")
        state.set("supplier_agreements_verified", True)

        # Row L: trust-gated credential access — raises PermissionError if trust < HIGH
        token = vault.get_with_trust(
            "llm_gateway", "read:cases", cfg["api_credential_key"],
            trust_level="HIGH",
        )
        state.set("jit_token_present", token is not None)
        state.set("action_type", "case_analysis")
        # Expose audit trail for verification
        state.set("credential_audit_trail", vault.get_audit_trail())

    node_creds = FunctionalNode(func=fetch_credentials, next_node=None)

    # ── Node B: LLM analysis ──────────────────────────────────────────────────
    node_llm = LLMNode(
        model_name=cfg["model"],
        prompt_template=cfg["analysis_prompt"],
        output_key="ai_output",
        next_node=None,
    )
    node_llm.compliance_metadata = {
        "action_type": "llm_inference",
        "affected_parties": "THIRD_PARTY",
        "external_action": True,
        "description": "LLM inference on applicant PII data — directly affects the case subject's outcome.",
    }

    # ── Row A: Fundamental Rights Impact Assessment (Art. 9 FRIA) ────────────
    # Scans LLM output for EU Charter dimension violations before human sees it
    node_fria = FundamentalRightsImpactNode(
        input_key="ai_output",
        next_node=None,
        block_on_violation=False,  # Log and continue — escalate to jury if violated
    )

    # ── Node C: Parse JSON from LLM + Row B: Behavioral Envelope Monitor ─────
    def parse_output(state: GraphState):
        raw = state.get("ai_output", "")
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end]) if start >= 0 else {}
        except Exception:
            parsed = {"risk_level": "HIGH", "recommendation": raw[:200], "confidence": 0.5}
        state.set("risk_level",       parsed.get("risk_level", "HIGH"))
        state.set("recommendation",   parsed.get("recommendation", raw[:200]))
        state.set("model_confidence", float(parsed.get("confidence", 0.5)))

        # Row B: observe confidence against behavioral baseline (Art. 9 PMM)
        envelope_report = envelope_monitor.observe(float(parsed.get("confidence", 0.5)))
        state.set("envelope_report", envelope_report)

    node_parse = FunctionalNode(func=parse_output, next_node=None)

    # ── Row K: Session Memory — write (GDPR Art. 17) ─────────────────────────
    # Write case context to per-subject memory; erased at pipeline end
    node_session_write = SessionMemoryNode(
        mode="write",
        subject_key="applicant_id",
        memory_keys=["case_summary", "risk_level", "recommendation", "model_confidence"],
        retention_days=30,
        memory_dir=f"{cfg['output_dir']}/session_memory",
        next_node=None,
    )

    # ── Node D: HumanJuryNode (Art. 14 — Row F: automation_boundary) ─────────
    node_jury = HumanJuryNode(
        prompt=f"[{cfg['domain']}] AI recommendation ready. Do you approve?",
        choices=["approve", "reject"],
        output_key="jury_decision",
        context_keys=["risk_level", "recommendation", "model_confidence"],
        next_node=None,
        authority_ledger=authority_ledger,
        stakeholder_id=cfg["stakeholder_id"],
        stakeholder_role=cfg["stakeholder_role"],
        action_description=f"{cfg['domain']} AI case analysis — external action pending",
        risk_score_key="model_confidence",
        # Row F: per-decision-type automation boundary enforcement.
        # Showcase uses "auto_first_choice" so the mock input path works in CI.
        # Production deployments should set "always_human" to block non-interactive runs.
        decision_type="case_analysis",
        automation_boundary={
            "case_analysis": "auto_first_choice",  # CI/showcase mode
            "output_review": "auto_if_low_risk",
        },
    )

    # ── Node E: RiskScorerNode (Art. 14 — routes to jury or proceeds) ────────
    node_risk = RiskScorerNode(
        next_node=None,       # set after node_tool_monitor is defined
        jury_node=node_jury,
        confidence_key="model_confidence",
        action_type_key="action_type",
    )

    # ── Node F: Bias filter (prEN 18283) ──────────────────────────────────────
    node_bias = BiasFilterNode(
        input_key="recommendation",
        sensitive_terms=cfg["bias_terms"],
        next_node=None,       # set below
        jury_node=node_jury,
    )

    # ── Row H: Dynamic Tool Discovery Monitor (Art. 3(23)) ────────────────────
    # Confirms no tools added since conformity baseline
    node_tool_monitor = DynamicToolDiscoveryMonitor(
        baseline_tools=tool_catalogue,
        catalogue_state_key="tool_catalogue",
        block_on_undisclosed=False,   # warn but don't block (showcase mode)
        output_key="tool_discovery_report",
        next_node=None,
    )

    # ── Node G: Trifecta check + transparency + drift + supplier enforcement ──
    def compliance_checks(state: GraphState):
        # Row D: log plan-switch — jury routed us here from the PRE_EXECUTION path
        audit_logger.log_plan_switch(
            from_branch="autonomous_execution",
            to_branch="jury_approved_execution",
            reason=(
                f"RiskScorerNode escalated to HumanJuryNode (oversight_level="
                f"{cfg['oversight_level']}, risk_tier={cfg['risk_tier']}). "
                f"Jury decision: {state.get('jury_decision', 'unknown')}."
            ),
            step=None,
            node="compliance_checks",
        )

        # Row G: assert supplier agreement for external write before executing it
        supplier_registry.assert_agreement("external_write")

        # Trifecta (AEPD Rule of 2) — safe to call after jury has set jury_decision
        try:
            trifecta_guard.check(state, action_label="external_write")
        except LethalTrifectaError:
            state.set("trifecta_violation", True)
            raise

        # Art. 13 / 50 disclosure
        transparency.flag(
            action_type="case_analysis",
            tool_name="external_write",
            affected_description=f"Case subject in {cfg['domain']} workflow",
            run_id=state.get("run_id", "unknown"),
        )

        # Art. 3(23) drift snapshot (post-execution)
        snap = versioner.snapshot(
            tool_catalogue=tool_catalogue,
            state_schema_keys=list(state._state.keys()),
            policy_bindings={"case_analysis": cfg["oversight_level"]},
        )
        state.set("drift_report", snap.get("drift_report", {"drift_detected": False}))

    node_checks = FunctionalNode(func=compliance_checks, next_node=None)
    node_checks.compliance_metadata = {
        "action_type": "external_write",
        "affected_parties": "THIRD_PARTY",
        "external_action": True,
        "description": "Post-approval external write to case management — affects third-party case subject.",
    }

    # ── Node G.5: Prohibited Practice Guard (Art. 5) ─────────────────────────
    node_prohibited = ProhibitedPracticeGuard(
        input_key="recommendation",
        next_node=None,
        block_on_violation=True,
    )

    # ── Node H: Synthetic marker (Art. 50(2)) ─────────────────────────────────
    node_marker = SyntheticMarkerNode(
        input_key="recommendation",
        output_key="final_output",
        marker_type="VISIBLE",
        next_node=None,
    )

    # ── Row K: Session Memory — erase (GDPR Art. 17 right to erasure) ─────────
    # Erase demonstrates that per-subject data can be deleted on request
    node_session_erase = SessionMemoryNode(
        mode="erase",
        subject_key="applicant_id",
        memory_dir=f"{cfg['output_dir']}/session_memory",
        next_node=None,
    )

    # ── Wire the graph ────────────────────────────────────────────────────────
    #
    # [deployer] → [boundary] → [creds] → [llm] → [fria] → [parse]
    # → [session_write] → [bias] → [risk] → [jury] → [tool_monitor]
    # → [checks] → [prohibited] → [marker] → [session_erase]
    #
    # BiasFilterNode:  normal → [risk]; bias detected → [jury]
    # RiskScorerNode:  PRE_EXECUTION → [jury]; LOW/MEDIUM → [tool_monitor]
    # HumanJuryNode:   approved → [tool_monitor]
    #
    node_deployer.next_node     = node_boundary
    node_boundary.next_node     = node_creds
    node_creds.next_node        = node_llm
    node_llm.next_node          = node_fria
    node_fria.next_node         = node_parse
    node_parse.next_node        = node_session_write
    node_session_write.next_node = node_bias
    node_bias.next_node         = node_risk
    node_risk.next_node         = node_tool_monitor  # non-PRE_EXECUTION path
    node_jury.next_node         = node_tool_monitor  # post-approval path
    node_tool_monitor.next_node = node_checks
    node_checks.next_node       = node_prohibited
    node_prohibited.next_node   = node_marker
    node_marker.next_node       = node_session_erase

    # ── STEP 10: ComplianceManifestGenerator (Step 9 — action inventory) ──────
    manifest = ComplianceManifestGenerator(
        start_node=node_deployer,
        system_name=cfg["system_name"],
    )
    manifest_path = f"{cfg['output_dir']}/compliance_manifest.json"
    manifest.save(manifest_path)
    print(f"  [Manifest]: Saved to {manifest_path}")
    print(manifest.as_markdown()[:800] + "\n  ...(truncated)\n")

    # ── Execute ───────────────────────────────────────────────────────────────
    executor = GraphExecutor(
        log_dir=cfg["output_dir"],
        hmac_secret=cfg["hmac_secret"],
        logger=audit_logger,
        versioner=versioner,
        # Row J: IncidentReporterNode auto-fires on unhandled node exceptions
        incident_reporter=incident_reporter,
    )

    initial_state = {
        **case,
        "action_type":    "case_analysis",
        "tool_catalogue": tool_catalogue,
        # applicant_id falls back to "anonymous" if not in case dict
        "applicant_id":   case.get("applicant_id", case.get("patient_id",
                          case.get("name", "anonymous"))),
    }

    print("  [Executor]: Running graph...\n")
    all_steps = []
    for step in executor.run_step_by_step(node_deployer, initial_state):
        all_steps.append(step)
        node_name = step.get("node", "?")
        diff_keys = list(step.get("state_diff", {}).get("added", {}).keys()) + \
                    list(step.get("state_diff", {}).get("updated", {}).keys())
        status = "✓" if step.get("outcome") == "success" else "✗"
        print(f"    {status} {node_name:<35} → {diff_keys}")

    # ── Row C: Verify per-step audit integrity ─────────────────────────────────
    integrity_results = audit_logger.verify_all_steps()

    # ── Save authority ledger ─────────────────────────────────────────────────
    authority_ledger.save(ledger_path)

    # ── Gather results ─────────────────────────────────────────────────────────
    # Sort by modification time (newest first) — UUID filenames are not chronological
    audit_files = sorted(
        [f for f in os.listdir(cfg["output_dir"]) if f.startswith("run_")],
        key=lambda f: os.path.getmtime(os.path.join(cfg["output_dir"], f)),
        reverse=True,
    )
    audit_log_path = os.path.join(cfg["output_dir"], audit_files[0]) if audit_files else None

    # Capture final state from last executed step
    final_state_dict = all_steps[-1].get("state_after", {}) if all_steps else {}

    return {
        "domain":                   cfg["domain"],
        "system_name":              cfg["system_name"],
        "audit_log_path":           audit_log_path,
        "authority_ledger_path":    ledger_path,
        "manifest_path":            manifest_path,
        "authority_records":        authority_ledger.get_records(),
        # v2.2.0 runtime verification keys
        "final_state":              final_state_dict,
        "integrity_results":        integrity_results,
        "incident_log_path":        incident_reporter.incident_log_path,
        "envelope_monitor_flags":   envelope_monitor.get_flags(),
        "envelope_monitor_summary": envelope_monitor.summary(),
        "credential_audit_trail":   vault.get_audit_trail(),
    }
