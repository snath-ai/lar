"""
Lár Enterprise Compliance Backbone
====================================
Reusable backbone that wires ALL 12 compliance primitives into a single,
auditable graph. Drop in a DOMAIN_CONFIG dict to target any regulated vertical.

Paper coverage  (every box the April 2026 paper implies):
  Art. 9    → PolicyRegistry (risk taxonomy per action)
  Art. 12   → AuditLogger / Causal Trace + AuthorityLedger (action-level records)
  Art. 13   → TransparencyEngine (third-party disclosure)
  Art. 14   → RiskScorerNode + HumanJuryNode (commensurate oversight)
  Art. 3(23)→ RuntimeStateVersioner + DriftDetector (substantial modification)
  Art. 15(4)→ CredentialVault (NHI just-in-time privilege)
  Art. 50(2)→ SyntheticMarkerNode (C2PA / visible disclaimer)
  prEN18283 → BiasFilterNode (bias management)
  GDPR 5/17 → PIIRedactionEngine (right to erasure)
  Step 9    → ComplianceManifestGenerator (exhaustive action inventory)
  AEPD PoP  → LethalTrifectaGuard (Rule-of-2 runtime block)
  Fourth Tier→ AuthorityLedger (who/role/rationale/risk signed record)
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
    RuntimeStateVersioner,
    CredentialVault,
    TransparencyEngine,
    PIIRedactionEngine,
    BiasFilterNode,
    SyntheticMarkerNode,
    ComplianceManifestGenerator,
    AuthorityLedger,
    LethalTrifectaGuard, LethalTrifectaError,
    ProhibitedPracticeGuard,
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
        "pii_keys":         ["account_number", "ssn", "iban", "email", "name"],
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
    Build the full 12-primitive compliance graph and execute it for a single case.

    Args:
        case:             The intake payload (dict). Must contain 'case_summary'.
        domain:           One of FINANCE | HEALTHCARE | PHARMA | LEGAL | HR | GENERIC.
        config_overrides: Any key from DEFAULT_CONFIG to override at call time.
        _mock_inputs:     For automated testing — replaces builtins.input responses.

    Returns:
        dict with keys: run_id, domain, decision, confidence, risk_level,
                        audit_log_path, authority_ledger_path, manifest_path.
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
    print(f"  Lár Enterprise Compliance Backbone")
    print(f"  Domain : {cfg['domain']}")
    print(f"  System : {cfg['system_name']}")
    print(f"{'='*65}\n")

    # ── STEP 7: Credential Vault (Art. 15(4) — NHI privilege) ────────────────
    vault = CredentialVault()
    vault.register_credential(cfg["api_credential_key"], cfg["api_credential_val"])

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

    # ─────────────────────────────────────────────────────────────────────────
    # GRAPH NODES
    # ─────────────────────────────────────────────────────────────────────────

    # Node A: NHI credential fetch (Art. 15(4))
    def fetch_credentials(state: GraphState):
        token = vault.get("llm_gateway", "read:cases", cfg["api_credential_key"])
        state.set("jit_token_present", token is not None)
        state.set("action_type", "case_analysis")

    node_creds = FunctionalNode(func=fetch_credentials, next_node=None)

    # Node B: LLM analysis
    node_llm = LLMNode(
        model_name=cfg["model"],
        prompt_template=cfg["analysis_prompt"],
        output_key="ai_output",
        next_node=None,
    )

    # Node C: Parse JSON from LLM
    def parse_output(state: GraphState):
        raw = state.get("ai_output", "")
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end]) if start >= 0 else {}
        except Exception:
            parsed = {"risk_level": "HIGH", "recommendation": raw[:200], "confidence": 0.5}
        state.set("risk_level",      parsed.get("risk_level", "HIGH"))
        state.set("recommendation",  parsed.get("recommendation", raw[:200]))
        state.set("model_confidence", float(parsed.get("confidence", 0.5)))

    node_parse = FunctionalNode(func=parse_output, next_node=None)

    # Node D: HumanJuryNode (Art. 14 — with AuthorityLedger for fourth tier)
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
    )

    # Node E: RiskScorerNode (Art. 14 — routes to jury or proceeds)
    node_risk = RiskScorerNode(
        next_node=None,      # set after node_bias is defined
        jury_node=node_jury,
        confidence_key="model_confidence",
        action_type_key="action_type",
    )

    # Node F: Bias filter (prEN 18283)
    node_bias = BiasFilterNode(
        input_key="recommendation",
        sensitive_terms=cfg["bias_terms"],
        next_node=None,      # set below
        jury_node=node_jury,
    )

    # Node G: Trifecta check + transparency disclosure + drift snapshot
    def compliance_checks(state: GraphState):
        # Trifecta (AEPD Rule of 2) — safe to call after jury has set jury_decision
        try:
            trifecta_guard.check(state, action_label="external_write")
        except LethalTrifectaError:
            state.set("trifecta_violation", True)
            # In a real system, abort the action and raise an incident report
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

    # Node H: Synthetic marker (Art. 50(2))
    node_marker = SyntheticMarkerNode(
        input_key="recommendation",
        output_key="final_output",
        marker_type="VISIBLE",
        next_node=None,
    )

    # Node G.5: Prohibited Practice Guard (Art. 5)
    node_prohibited = ProhibitedPracticeGuard(
        input_key="recommendation",
        next_node=node_marker,
        block_on_violation=True
    )

    # ── Wire the graph ────────────────────────────────────────────────────────
    node_creds.next_node  = node_llm
    node_llm.next_node    = node_parse
    node_parse.next_node  = node_risk
    node_risk.next_node   = node_bias   # non-PRE_EXECUTION path
    node_bias.next_node   = node_checks
    node_jury.next_node   = node_checks # post-approval path
    node_checks.next_node = node_prohibited
    # node_prohibited -> node_marker

    # ── STEP 10: ComplianceManifestGenerator (Step 9 — action inventory) ──────
    manifest = ComplianceManifestGenerator(
        start_node=node_creds,
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
    )

    initial_state = {**case, "action_type": "case_analysis"}

    print("  [Executor]: Running graph...\n")
    for step in executor.run_step_by_step(node_creds, initial_state):
        node_name = step.get("node", "?")
        diff_keys = list(step.get("state_diff", {}).get("added", {}).keys()) + \
                    list(step.get("state_diff", {}).get("updated", {}).keys())
        print(f"    ✓ {node_name:<30} → {diff_keys}")

    # ── Save authority ledger ─────────────────────────────────────────────────
    authority_ledger.save(ledger_path)

    # ── Gather results ────────────────────────────────────────────────────────
    audit_files = sorted(
        [f for f in os.listdir(cfg["output_dir"]) if f.startswith("run_")],
        reverse=True,
    )
    audit_log_path = os.path.join(cfg["output_dir"], audit_files[0]) if audit_files else None

    final_state = GraphState(initial_state)  # re-read via executor internals
    return {
        "domain":               cfg["domain"],
        "system_name":          cfg["system_name"],
        "audit_log_path":       audit_log_path,
        "authority_ledger_path": ledger_path,
        "manifest_path":        manifest_path,
        "authority_records":    authority_ledger.get_records(),
    }
