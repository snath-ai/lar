"""
Fractal Compliance Agent — BatchNode + AdaptiveNode + Recursion
================================================================
Demonstrates a Lár agent that combines:

  1. BatchNode       — three parallel analysis branches running simultaneously
  2. AdaptiveNode    — each branch composes its own validated subgraph at runtime
  3. ReduceNode      — consolidates parallel outputs into a single assessment
  4. Full compliance backbone — all 12 primitives from 22_eu_ai_act_finance_showcase.py

Scenario: Multi-dimensional pharmaceutical clinical trial assessment (PHARMA domain).
A new compound (ZX-412) must be assessed across three independent dimensions simultaneously:
  - Safety:     adverse event profile and patient risk
  - Efficacy:   primary endpoint analysis and confidence interval
  - Regulatory: GCP / ICH / EMA compliance status

Each dimension is handled by an AdaptiveNode that composes a domain-specific subgraph
at runtime. TopologyValidator enforces an allowlist — only LLMNode and FunctionalNode
allowed inside each dynamic subgraph. AdaptiveNode is excluded from the inner allowlist,
controlling recursion depth to one level.

Compliance notes:
  - ComplianceManifestGenerator flags AdaptiveNode as HIGH (Art. 3(23) substantial
    modification candidate) — expected and correct.
  - RuntimeStateVersioner detects schema drift as dynamic subgraphs add new keys.
  - TopologyValidator validates every generated GraphSpec before injection.
  - BiasFilterNode scans the consolidated output.
  - HumanJuryNode fires because PHARMA = PRE_EXECUTION oversight.
  - All PII keys stripped before HMAC signing.
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

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
DOMAIN      = "PHARMA"
HMAC_SECRET = os.getenv("HMAC_SECRET", "change-me-in-prod")
OUTPUT_DIR  = "enterprise_audit"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PII_KEYS = ["subject_id", "dob", "name", "trial_id", "site_id"]

# Clinical trial case — compound ZX-412 Phase III trial
TRIAL_CASE = {
    "subject_id":     "ZX412-EU-0047",    # PII — redacted
    "trial_id":       "NCT-2026-ZX412",   # PII — redacted
    "site_id":        "SITE-IRL-03",      # PII — redacted
    "dob":            "1978-11-22",       # PII — redacted
    "name":           "Trial Subject",    # PII — redacted
    "compound":       "ZX-412",
    "phase":          "Phase III",
    "indication":     "Non-small cell lung cancer (NSCLC)",
    "safety_summary": (
        "Grade 4 hepatotoxicity (n=4, 2 requiring ICU), Grade 4 neutropenia (n=5). "
        "3 confirmed treatment-related deaths. DSMB voted 5-0 to suspend trial. "
        "Protocol halted pending emergency safety review. AE incidence: 78%. Discontinuation: 41%."
    ),
    "efficacy_summary": (
        "Primary endpoint (PFS): 8.4 months vs 5.1 months control (HR 0.61, 95% CI 0.48-0.78, p<0.001). "
        "ORR: 47% vs 24%. OS data immature at interim analysis."
    ),
    "regulatory_summary": (
        "GCP audit completed Q1 2026. Two protocol deviations noted: "
        "1 informed consent form version mismatch, 1 late SAE reporting (48h delay). "
        "No critical findings. IMPD submitted to EMA June 2026."
    ),
    "action_type": "trial_assessment",
}

# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE INFRASTRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

vault = CredentialVault()
vault.register_credential("PHARMA_API_KEY", os.getenv("PHARMA_API_KEY", "mock-jit-token-pharma"))

redactor  = PIIRedactionEngine(sensitive_keys=PII_KEYS)
authority_ledger = AuthorityLedger(hmac_secret=HMAC_SECRET)
audit_logger = AuditLogger(log_dir=OUTPUT_DIR, hmac_secret=HMAC_SECRET, pii_redactor=redactor)

registry = PolicyRegistry()
registry.clear()
registry.register("trial_assessment", ActionPolicy(
    domain=DOMAIN,
    process="analysis",
    decision_type="trial_assessment",
    risk_tier="HIGH",
    reversibility=False,
    oversight_level="PRE_EXECUTION",
    regulatory_tags=["EU_AI_ACT", "GDPR", "FDA_21CFR11", "ICH_GCP", "EMA"],
    affected_parties="THIRD_PARTY",
))

trifecta_guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("safety_summary") is not None,
    sensitive_data_fn=lambda s: any(s.get(k) for k in PII_KEYS),
    autonomous_action_fn=lambda s: True,
    human_approval_state_key="jury_decision",
    block_on_violation=True,
)

transparency = TransparencyEngine()

versioner = RuntimeStateVersioner(conformity_baseline_id="CA-PH-2026")
baseline = versioner.snapshot(
    tool_catalogue=["safety_adaptive", "efficacy_adaptive", "regulatory_adaptive",
                    "reduce", "bias_filter", "external_write"],
    state_schema_keys=list(TRIAL_CASE.keys()) + ["consolidated_assessment", "jury_decision"],
    policy_bindings={"trial_assessment": "PRE_EXECUTION"},
)

# ─────────────────────────────────────────────────────────────────────────────
# TOPOLOGY VALIDATOR — inner allowlist (no nested AdaptiveNode)
# ─────────────────────────────────────────────────────────────────────────────
# AdaptiveNode is intentionally excluded to prevent unbounded recursion.
# Depth-1 fractal: manager (BatchNode) → workers (AdaptiveNode) → leaf subgraphs (LLMNode only)

inner_validator = TopologyValidator(allowed_tools=[])

# ─────────────────────────────────────────────────────────────────────────────
# ADAPTIVE NODE PROMPTS — tight structured prompts for phi4
# ─────────────────────────────────────────────────────────────────────────────

SAFETY_PROMPT = """You are a pharmacovigilance AI. Analyze this safety data and return a risk assessment.

Safety data: {safety_summary}
Compound: {compound}
Phase: {phase}

Design a single-node graph that analyzes this data. Return ONLY this JSON (fill in the prompt):
{
  "nodes": [
    {
      "id": "safety_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a drug safety expert. Assess: {safety_summary} for compound {compound}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "safety_analysis",
      "next": null
    }
  ],
  "entry_point": "safety_analysis_node"
}"""

EFFICACY_PROMPT = """You are a biostatistics AI. Analyze this efficacy data and return an assessment.

Efficacy data: {efficacy_summary}
Compound: {compound}
Indication: {indication}

Design a single-node graph that analyzes this data. Return ONLY this JSON (fill in the prompt):
{
  "nodes": [
    {
      "id": "efficacy_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a clinical biostatistician. Assess: {efficacy_summary} for {compound} in {indication}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "efficacy_analysis",
      "next": null
    }
  ],
  "entry_point": "efficacy_analysis_node"
}"""

REGULATORY_PROMPT = """You are a GCP compliance AI. Analyze this regulatory status and return an assessment.

Regulatory data: {regulatory_summary}
Trial: {indication}

Design a single-node graph that analyzes this data. Return ONLY this JSON (fill in the prompt):
{
  "nodes": [
    {
      "id": "regulatory_analysis_node",
      "type": "LLMNode",
      "prompt": "You are a GCP compliance expert. Assess: {regulatory_summary} for trial on {indication}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence), confidence (0.0-1.0). No prose.",
      "output_key": "regulatory_analysis",
      "next": null
    }
  ],
  "entry_point": "regulatory_analysis_node"
}"""

# ─────────────────────────────────────────────────────────────────────────────
# GRAPH NODES
# ─────────────────────────────────────────────────────────────────────────────

# Node A: Credential fetch
def fetch_credentials(state: GraphState):
    token = vault.get("pharma_gateway", "read:trials", "PHARMA_API_KEY")
    state.set("jit_token_present", token is not None)

node_creds = FunctionalNode(func=fetch_credentials, next_node=None)

# Nodes B1/B2/B3: AdaptiveNode workers (one per dimension)
node_safety = AdaptiveNode(
    llm_model=MODEL,
    prompt_template=SAFETY_PROMPT,
    validator=inner_validator,
    context_keys=["safety_summary", "compound", "phase"],
    next_node=None,
)

node_efficacy = AdaptiveNode(
    llm_model=MODEL,
    prompt_template=EFFICACY_PROMPT,
    validator=inner_validator,
    context_keys=["efficacy_summary", "compound", "indication"],
    next_node=None,
)

node_regulatory = AdaptiveNode(
    llm_model=MODEL,
    prompt_template=REGULATORY_PROMPT,
    validator=inner_validator,
    context_keys=["regulatory_summary", "indication"],
    next_node=None,
)

# Node C: BatchNode — runs all three AdaptiveNodes in parallel
node_batch = BatchNode(
    nodes=[node_safety, node_efficacy, node_regulatory],
    next_node=None,
)

# Node C2: BranchTriageNode — engine primitive (lar.compliance.BranchTriageNode)
# Parses all three AdaptiveNode outputs, builds branch_findings_summary for jury context,
# and sets branch_critical=True if any dimension breaches the threshold.
node_triage = BranchTriageNode(
    branch_output_keys=["safety_analysis", "efficacy_analysis", "regulatory_analysis"],
    critical_threshold="CRITICAL",
    next_node=None,  # → node_branch_router (wired after all nodes exist)
)

# Node D: ReduceNode — consolidates three parallel outputs into one assessment
node_reduce = ReduceNode(
    model_name=MODEL,
    input_keys=["safety_analysis", "efficacy_analysis", "regulatory_analysis"],
    output_key="consolidated_assessment",
    prompt_template=(
        "You are a senior medical reviewer. Consolidate these three assessments "
        "into a single overall trial risk assessment.\n\n"
        "Safety analysis: {safety_analysis}\n"
        "Efficacy analysis: {efficacy_analysis}\n"
        "Regulatory analysis: {regulatory_analysis}\n\n"
        "Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
        "recommendation (max 2 sentences), confidence (0.0-1.0). No prose."
    ),
    next_node=None,
)

# Node E: Parse consolidated output
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
    state.set("action_type",      "trial_assessment")

node_parse = FunctionalNode(func=parse_consolidated, next_node=None)

# Node F: Bias filter
node_bias = BiasFilterNode(
    input_key="recommendation",
    sensitive_terms=["race", "gender", "age", "ethnicity", "nationality", "disability"],
    next_node=None,
    jury_node=None,  # wired below
)

# Node G: Risk scorer
node_risk = RiskScorerNode(
    next_node=None,
    jury_node=None,  # wired below
    confidence_key="model_confidence",
    action_type_key="action_type",
)

# Node H-early: Human jury — fires BEFORE ReduceNode if any branch returns CRITICAL.
# The PI sees the raw per-dimension findings and decides whether to proceed at all.
node_jury_early = HumanJuryNode(
    prompt=(
        f"[{DOMAIN}] CRITICAL risk detected in one or more analysis branches.\n"
        "Review the individual dimension findings before consolidation proceeds."
    ),
    choices=["approve", "reject"],
    output_key="jury_early_decision",
    context_keys=["branch_findings_summary"],
    next_node=None,  # → node_reduce (wired below)
    authority_ledger=authority_ledger,
    stakeholder_id=os.getenv("REVIEWER_EMAIL", "pi@clinical-site.org"),
    stakeholder_role="Principal Investigator",
    action_description=f"{DOMAIN} CRITICAL branch — pre-consolidation safety gate",
    risk_score_key=None,
)

# Node H-final: Human jury — fires after consolidation for PRE_EXECUTION sign-off.
# Context includes branch_findings_summary so the PI sees dimension detail alongside
# the consolidated recommendation. Satisfies Art. 14 meaningful human oversight.
node_jury = HumanJuryNode(
    prompt=f"[{DOMAIN}] Multi-dimensional trial assessment ready. Do you approve?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    context_keys=["risk_level", "recommendation", "model_confidence", "branch_findings_summary"],
    next_node=None,
    authority_ledger=authority_ledger,
    stakeholder_id=os.getenv("REVIEWER_EMAIL", "pi@clinical-site.org"),
    stakeholder_role="Principal Investigator",
    action_description=f"{DOMAIN} multi-dimensional trial assessment — regulatory submission pending",
    risk_score_key="model_confidence",
)

node_bias.jury_node = node_jury
node_risk.jury_node = node_jury

# Node I: Compliance checks
def compliance_checks(state: GraphState):
    trifecta_guard.check(state, action_label="regulatory_submission")
    transparency.flag(
        action_type="trial_assessment",
        tool_name="regulatory_submission",
        affected_description=f"Trial subjects and regulatory body in {DOMAIN} workflow",
        run_id=state.get("run_id", "unknown"),
    )
    snap = versioner.snapshot(
        tool_catalogue=["safety_adaptive", "efficacy_adaptive", "regulatory_adaptive",
                        "reduce", "bias_filter", "external_write"],
        state_schema_keys=list(state._state.keys()),
        policy_bindings={"trial_assessment": "PRE_EXECUTION"},
    )
    state.set("drift_report", snap.get("drift_report", {"drift_detected": False}))

node_checks = FunctionalNode(func=compliance_checks, next_node=None)
node_checks.compliance_metadata = {
    "action_type":      "external_write",
    "affected_parties": "THIRD_PARTY",
    "external_action":  True,
    "description":      "Post-approval regulatory submission — affects trial subjects and EMA.",
}

# Node J: Prohibited practice guard
node_prohibited = ProhibitedPracticeGuard(
    input_key="recommendation",
    next_node=None,
    block_on_violation=True,
)

# Node K: Synthetic marker
node_marker = SyntheticMarkerNode(
    input_key="recommendation",
    output_key="final_output",
    marker_type="VISIBLE",
    next_node=None,
)

# Node C3: Router — created here so all target nodes (jury_early, reduce) already exist
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
node_jury_early.next_node = node_reduce    # after early approval, still consolidate
node_reduce.next_node     = node_parse
node_parse.next_node      = node_bias
node_bias.next_node       = node_risk
node_risk.next_node       = node_checks    # LOW/MEDIUM path (no jury needed)
node_jury.next_node       = node_checks    # PRE_EXECUTION post-approval path
node_checks.next_node     = node_prohibited
node_prohibited.next_node = node_marker

# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE MANIFEST (pre-execution static inventory)
# ─────────────────────────────────────────────────────────────────────────────

manifest = ComplianceManifestGenerator(
    start_node=node_creds,
    system_name="AI Fractal Clinical Trial Assessment Agent",
)
manifest_path = f"{OUTPUT_DIR}/compliance_manifest_fractal.json"
manifest.save(manifest_path)

# ─────────────────────────────────────────────────────────────────────────────
# EXECUTE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import builtins

    print("\n" + "="*65)
    print("  Lár Fractal Compliance Agent")
    print("  BatchNode + AdaptiveNode + Recursion + Full EU AI Act Backbone")
    print(f"  Domain  : {DOMAIN}")
    print(f"  Compound: {TRIAL_CASE['compound']} — {TRIAL_CASE['indication']}")
    print("="*65 + "\n")

    # Mock inputs for non-interactive run
    mock_inputs = [
        # Early jury (fires only if any branch returns CRITICAL)
        "approve",
        "DSMB notified. Grade 4 events are within pre-specified stopping rules. Proceeding to full consolidation with enhanced monitoring protocol.",
        # Final jury (fires always for PRE_EXECUTION domains after consolidation)
        "approve",
        "Reviewed consolidated assessment and all branch findings. Risk accepted with mandatory protocol amendment and DSMB oversight.",
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
        executor = GraphExecutor(
            log_dir=OUTPUT_DIR,
            hmac_secret=HMAC_SECRET,
            logger=audit_logger,
            versioner=versioner,
        )

        initial_state = {**TRIAL_CASE}

        for step in executor.run_step_by_step(node_creds, initial_state):
            node_name = step.get("node", "?")
            added = list(step.get("state_diff", {}).get("added", {}).keys())
            print(f"    ✓ {node_name:<35} → {added}")

        authority_ledger.save(f"{OUTPUT_DIR}/authority_ledger_fractal.json")

    finally:
        builtins.input = _orig

    # ── Verify artefacts ────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("  Artefact Verification")
    print("="*65)

    import glob
    runs = sorted(glob.glob(f"{OUTPUT_DIR}/run_*.json"), key=os.path.getmtime, reverse=True)
    if runs:
        with open(runs[0]) as f:
            trace = json.load(f)

        steps      = trace.get("steps", [])
        step0      = steps[0] if steps else {}
        sig        = trace.get("signature", "")

        # PII check
        pii_clean = all(
            step0.get("state_before", {}).get(k) == "[REDACTED]"
            for k in PII_KEYS
            if k in step0.get("state_before", {})
        )

        # BiasFilterNode check
        bias_step = next((s for s in steps if s.get("node") == "BiasFilterNode"), None)

        # BatchNode check
        batch_step = next((s for s in steps if s.get("node") == "BatchNode"), None)

        # AdaptiveNode detection: AdaptiveNode runs inside BatchNode threads and is not
        # logged as a top-level trace step. Detect via BatchNode's state_diff:
        #   - __graph_spec_json__ added → AdaptiveNode composed at least one validated spec
        #   - _batch_conflicts present  → multiple AdaptiveNode branches competed for the key
        batch_added   = batch_step.get("state_diff", {}).get("added", {}) if batch_step else {}
        batch_updated = batch_step.get("state_diff", {}).get("updated", {}) if batch_step else {}
        adaptive_spec_present = "__graph_spec_json__" in batch_added or "__graph_spec_json__" in batch_updated
        adaptive_outputs = [k for k in batch_added if k in ("safety_analysis", "efficacy_analysis", "regulatory_analysis")]
        adaptive_ok = adaptive_spec_present and len(adaptive_outputs) == 3

        # Early-exit HITL check: HumanJuryNode should have fired before ReduceNode
        # if any branch returned CRITICAL (output key = jury_early_decision).
        # BranchTriageNode is logged as "BranchTriageNode" in the causal trace.
        triage_step      = next((s for s in steps if s.get("node") == "BranchTriageNode"), None)
        early_jury_step  = next((s for s in steps if s.get("node") == "HumanJuryNode"
                                 and "jury_early_decision" in s.get("state_diff", {}).get("added", {})
                                 ), None)
        # Check that branch_findings_summary reached the final jury's context
        final_jury_step  = next((s for s in steps if s.get("node") == "HumanJuryNode"
                                 and "jury_decision" in s.get("state_diff", {}).get("added", {})), None)
        branch_critical_val = None
        if triage_step:
            branch_critical_val = triage_step.get("state_diff", {}).get("added", {}).get("branch_critical")
        findings_in_state = any(
            "branch_findings_summary" in s.get("state_before", {})
            for s in steps if s.get("node") == "HumanJuryNode"
        )

        print(f"\n✓ Causal Trace           : {runs[0].split('/')[-1]}")
        print(f"  Steps recorded         : {len(steps)}")
        print(f"  PII redacted           : {'✅ YES' if pii_clean else '❌ NO — check pii_keys'}")
        print(f"  HMAC signature         : {'✅ ' + sig[:16] + '...' if sig else '❌ MISSING'}")
        print(f"  BatchNode fired        : {'✅ YES' if batch_step else '❌ NO'}")
        print(f"  AdaptiveNode instances : {'✅ 3 branches inferred (spec+outputs in BatchNode diff)' if adaptive_ok else '❌ NONE — check BatchNode state_diff'}")
        print(f"  BiasFilterNode fired   : {'✅ YES' if bias_step else '❌ NO'}")
        crit_label = "CRITICAL detected" if branch_critical_val else "no CRITICAL branch"
        print(f"  Branch triage          : {'✅ ' + crit_label if triage_step else '❌ triage node missing'}")
        print(f"  Early-exit jury        : {'✅ FIRED (pre-consolidation safety gate)' if early_jury_step else ('⏭  skipped (no CRITICAL branch)' if triage_step else '❌ MISSING')}")
        print(f"  Branch findings in jury: {'✅ YES (PI saw dimension breakdown)' if findings_in_state else '❌ NO — jury context missing branch summary'}")

    with open(f"{OUTPUT_DIR}/authority_ledger_fractal.json") as f:
        ledger = json.load(f)
    records = ledger.get("records", [])
    if records:
        r = records[0]
        print(f"\n✓ Authority Ledger")
        print(f"  Stakeholder  : {r.get('stakeholder_id')} ({r.get('stakeholder_role')})")
        print(f"  Decision     : {r.get('decision')}")
        print(f"  Rationale    : {r.get('rationale', '')[:80]}")
        print(f"  Signature    : {ledger.get('signature', '')[:16]}...")

    with open(manifest_path) as f:
        mf = json.load(f)
    s = mf.get("summary", {})
    print(f"\n✓ Compliance Manifest")
    print(f"  Nodes inventoried      : {s.get('total_nodes_inventoried')}")
    print(f"  External actions       : {s.get('total_external_actions')}")
    print(f"  Unvaulted tools        : {s.get('tools_without_credential_vault')}")
    for flag in mf.get("risk_flags", []):
        print(f"  [{flag['severity']}] {flag.get('article','')}: {flag['message'][:80]}")

    print("\nAll primitives executed. Fractal compliance agent run complete.")
    print(f"Artefacts in: {OUTPUT_DIR}/")
