# Lár ↔ Nannini et al. (2026) Compliance Architecture Mapping

This page maps every compliance requirement from **"AI Agents Under EU Law: A Compliance Architecture for AI Providers"** (Nannini, Smith, Maggini et al., April 2026, arXiv:2604.04604v1) to the specific Lár primitive that implements it.

The paper proposes a 12-step compliance sequence (Section 8.1) and identifies four agent-specific challenges (Section 6). Lár's Enterprise Compliance Backbone **v2.2.0** addresses every step, every challenge, and the 12 additional gap items identified by the audit — **23 requirements total, all fully covered**.

> **v2.2.0 (May 2026):** Gap-closure release. Added 7 new nodes, hardened the executor with automatic Art. 5 + Art. 73 hooks, and extended 6 existing primitives. See the [v2.2.0 gap-closure section](#v220-gap-closure-requirements) below.

---

## The 12-Step Compliance Sequence

### Step 0 — Scope the System (Art. 3(1))

**Paper requirement:** Determine whether the product constitutes an AI system. For agents, the question is rarely *whether* it meets the definition — any LLM-based system with tool use satisfies every element of Art. 3(1) — but *how many* AI systems the product contains.

**Lár approach:** The `DOMAIN_PRESETS` dict in the Enterprise Backbone documents the system name, domain, and `conformity_id`. This provides the classification record. The backbone's graph structure makes the system boundary explicit: one graph = one AI system boundary for conformity assessment purposes.

---

### Step 1 — Map the GPAI Layer (Art. 53)

**Paper requirement:** Identify who bears the GPAI model obligations. If using a third-party foundation model, obtain Art. 53 technical documentation and integrate model limitations into your Art. 9 risk process.

**Lár approach:** Lár is model-agnostic via LiteLLM. The `model` key in `DOMAIN_PRESETS` documents which model the system uses. When using third-party GPAI models (GPT-4, Gemini, Claude), the provider must obtain Art. 53 documentation from the upstream supplier. For open-weight models (Ollama, local deployment), the provider is operating at the system layer only. This is a legal obligation on the provider — the runtime backbone documents the model used as the starting point.

---

### Step 2 — Classify the System (Annex III / Art. 6)

**Paper requirement:** Determine whether the system is high-risk. Document the classification reasoning with sufficient specificity to survive regulatory scrutiny.

**Lár approach:** `DOMAIN_PRESETS` maps each vertical to its regulatory classification:

| Domain | Classification | Legal Basis |
|---|---|---|
| `FINANCE` | HIGH-RISK | Annex III, point 5(b) — creditworthiness assessment |
| `HEALTHCARE` | HIGH-RISK | Annex I(A) — medical device (MDR/IVDR) + Annex III, point 5 |
| `HR` | HIGH-RISK | Annex III, point 4(a) — employment/recruitment decisions |
| `LEGAL` | HIGH-RISK | Annex III, point 8 — administration of justice |
| `PHARMA` | HIGH-RISK | Annex I(A) — medical device + FDA 21 CFR Part 11 |

The `conformity_id` field serves as the classification record identifier for the conformity assessment process.

---

### Step 3 — Establish the QMS (prEN 18286 / Art. 17)

**Paper requirement:** Identify all applicable essential requirements (clause 4.4.2). The QMS must cover the full lifecycle including post-deployment behavioral monitoring.

**Lár approach:** The backbone produces three QMS-required artifacts at every run:

1. **Compliance Manifest** (`ComplianceManifestGenerator`) — the Annex IV technical documentation foundation: exhaustive inventory of nodes, tools, data flows, affected parties, and regulatory triggers.
2. **Authority Ledger** (`AuthorityLedger`) — signed records of every human oversight exercise, satisfying clause 9.4 post-market monitoring records.
3. **Causal Trace** (`AuditLogger` + HMAC-SHA256) — the immutable execution log required for incident investigation and regulatory inspection.

These artifacts are the inputs to the QMS process. The organisational QMS itself (ISO 13485, IATF 16949, or standalone prEN 18286 implementation) is a provider-level obligation that the backbone supports rather than replaces.

---

### Step 4 — Risk Management System (prEN 18228 / Art. 9)

**Paper requirement:** Continuous lifecycle risk management covering health, safety, and fundamental rights. The automation boundary — which actions require human involvement, which execute autonomously — must be documented.

**Lár primitives:**

- **`PolicyRegistry`** — registers every action type with its `risk_tier`, `reversibility`, `oversight_level`, and `affected_parties`. This is the runtime automation boundary declaration.
- **`RiskScorerNode`** — scores each action pre-execution against the registered policy. Routes to `HumanJuryNode` when the risk tier exceeds the configured threshold, operationalising the paper's requirement that "oversight measures be commensurate with the risks and context."

```python
registry.register("case_analysis", ActionPolicy(
    domain="FINANCE",
    risk_tier="HIGH",
    reversibility=False,
    oversight_level="PRE_EXECUTION",    # Art. 14 automation boundary
    affected_parties="THIRD_PARTY",
))
```

---

### Step 5 — Data Governance (prEN 18284 + prEN 18283 / Art. 10)

**Paper requirement:** Training and operational data lifecycle. Bias management through normative reference to prEN 18283. For agents, interaction data must be governed — it continuously shapes the agent's operational profile.

**Lár primitives:**

- **`PIIRedactionEngine`** — strips configured PII keys (`ssn`, `iban`, `name`, `dob`, etc.) from the causal trace before HMAC signing. Satisfies GDPR Art. 17 data minimisation in audit logs.
- **`BiasFilterNode`** — scans LLM output for protected-characteristic terms (age, gender, race, nationality, disability) per prEN 18283. Routes to `HumanJuryNode` if bias terms are detected.

The paper notes: *"agents accumulate interaction data... that may contain protected characteristics indirectly."* The `bias_terms` list in `DOMAIN_PRESETS` is domain-specific — the HR preset includes `pregnancy`, the Healthcare preset includes `disability`.

---

### Step 6 — Trustworthiness Design (prEN 18229-1/2 / Art. 12–14)

**Paper requirement (§6.2):** Oversight mechanisms must be designed as external constraints, not internal instructions. The paper identifies three structurally necessary oversight modalities: retrospective, real-time, and pre-execution. For irreversible actions, retrospective oversight alone is structurally insufficient.

**Lár primitives:**

| Modality | Lár Primitive | Paper Reference |
|---|---|---|
| **Retrospective** | `AuditLogger` + HMAC-SHA256 causal trace | Art. 12, prEN ISO/IEC 24970 |
| **Real-time** | `TransparencyEngine` third-party disclosure | Art. 13, Art. 50 |
| **Pre-execution** | `HumanJuryNode` blocking interrupt | Art. 14(4) |
| **Authority record** | `AuthorityLedger` (Fourth Tier) | Paper fn. 18 |
| **Fractal / parallel agents** | `BranchTriageNode` — per-branch evidence before consolidation | Paper §6.2, Art. 14 |

The `AuthorityLedger` directly implements the paper's footnote 18 requirement: infrastructure that *"logs the notification delivered to the responsible stakeholder, records the stakeholder's decision and rationale, and maintains an evidentiary chain from action proposal through risk assessment to human determination and execution outcome."*

**Fractal agent note (§6.2):** When `BatchNode` runs parallel branches, `ReduceNode` compresses individual branch results into a consolidated output. Without `BranchTriageNode`, the human reviewer approving the consolidated result has no visibility into which individual branch triggered a HIGH or CRITICAL flag. The paper's §6.2 requirement for "meaningful oversight" is structurally violated — the reviewer is approving a summary, not the evidence. `BranchTriageNode` preserves that per-dimension evidence in `branch_findings_summary` and surfaces it directly in the `HumanJuryNode` context before consolidation occurs.

```python
node_jury = HumanJuryNode(
    authority_ledger=authority_ledger,
    stakeholder_id="reviewer@enterprise.org",
    stakeholder_role="Risk Officer",
    action_description="Credit analysis — external action pending",
)
```

---

### Step 7 — AI-Specific Cybersecurity (prEN 18282 / Art. 15(4))

**Paper requirement (§6.1):** *"The inability to perform a restricted action [must] be enforced at the API level, where the model's tool interface simply does not expose the restricted capability."* Just-in-time credential provisioning, per-action authorization scoping, audit trails distinguishing user-initiated from AI-initiated actions.

**Lár primitive: `CredentialVault`**

```python
vault = CredentialVault()
vault.register_credential("ENTERPRISE_API_KEY", jit_token)
# Agent receives credentials only at the moment of the specific action
token = vault.get("llm_gateway", "read:cases", "ENTERPRISE_API_KEY")
```

The vault implements the paper's Non-Human Identity (NHI) governance requirements: the agent holds no standing credentials. Each tool invocation is individually authorized with scope-limited tokens. The paper's §6.1 cites Ji et al.'s SEAgent framework for hierarchical privilege boundaries — `CredentialVault` implements the same principle at the Lár execution layer.

---

### Step 8 — CRA Applicability

**Paper requirement:** If the agent is a product with digital elements (standalone software with network connectivity placed on the EU market), implement CRA compliance in parallel. CRA vulnerability reporting from September 2026; full product requirements from December 2027.

**Lár approach:** The backbone's architecture is designed for CRA Annex I secure-by-design alignment:
- Credential minimisation (no standing privileges)
- Cryptographic audit integrity (HMAC-SHA256)
- Separation of the AI inference layer from the action execution layer

CRA conformity assessment is a provider-level obligation. The backbone's security architecture reduces the gap to the CRA horizontal standard requirements. Providers deploying Lár as a VS Code extension, CLI tool, or API service must complete their own CRA applicability analysis.

---

### Step 9 — Map Adjacent Legislation (Paper §8.1 — The Foundational Step)

**Paper requirement:** *"The provider's foundational compliance task is not architectural classification but an exhaustive inventory of the agent's external actions, data flows, connected systems, and affected persons. That inventory constitutes the regulatory map."*

**Lár primitive: `ComplianceManifestGenerator`**

This is Lár's direct implementation of Step 9. The generator statically traverses the full node graph and produces:

- Every external action (ToolNode, LLMNode with `external_action=True`, FunctionalNode with `compliance_metadata`)
- Affected parties per action (`USER_ONLY` | `THIRD_PARTY` | `BOTH`)
- CredentialVault attachment status per action
- Art. 50 transparency trigger flags for third-party actions
- Risk flags for unvaulted tools, AdaptiveNode topology changes, third-party exposure

```python
manifest = ComplianceManifestGenerator(
    start_node=entry_node,
    system_name="AI Credit / Trading Decision Agent"
)
manifest.save("compliance_manifest.json")
```

The manifest maps each external action to the legislative instrument it activates using the paper's Table 5 logic: personal data → GDPR; connected products → Data Act; platform publishing → DSA; regulated sector → MDR/MiFID II/NIS2.

---

### Step 10 — Conformity Assessment

**Paper requirement:** Prepare technical documentation (Annex IV), issue EU Declaration of Conformity, register in EU database. For Annex III systems, internal control (Annex VI) is sufficient for most categories; third-party assessment required for biometric systems.

**Lár approach:** Every backbone run produces the Annex IV technical documentation inputs:

| Annex IV Section | Lár Artifact |
|---|---|
| System description and intended purpose | `DOMAIN_PRESETS` system_name + domain |
| Description of components and their interactions | `ComplianceManifestGenerator` action inventory |
| Log of changes and versions | `RuntimeStateVersioner` baseline + drift report |
| Description of human oversight measures | `HumanJuryNode` + `AuthorityLedger` records |
| Validation and testing results | Causal trace from validation suite runs |

The EU Declaration of Conformity and EU database registration are provider-level obligations completed after the technical documentation is assembled.

---

### Step 11 — Post-Market Monitoring & Drift Detection (Art. 3(23))

**Paper requirement (§6.4):** *"Runtime state must be treated as versioned architecture."* Versioned snapshots of tool catalogue, memory state, and policy bindings; continuous monitoring against conformity assessment baseline; automated detection of drift beyond defined thresholds triggering reassessment.

**Lár primitive: `RuntimeStateVersioner`**

```python
versioner = RuntimeStateVersioner(conformity_baseline_id="CA-FIN-2026")
baseline = versioner.snapshot(
    tool_catalogue=["llm_analysis", "trifecta_check", "external_write"],
    state_schema_keys=list(case.keys()),
    policy_bindings={"case_analysis": "PRE_EXECUTION"},
)
# Post-execution drift check
post_snap = versioner.snapshot(...)
# If tool_catalogue or policy_bindings changed → Art. 3(23) substantial
# modification candidate → new conformity assessment required
```

---

## The Four Agent-Specific Compliance Challenges

The paper (Section 6) identifies four challenges that are "amplified by agents in practice." Here is how Lár addresses each.

### Challenge 1 — Cybersecurity: Privilege Minimization Outside the Model (§6.1)

**Paper:** Privilege enforcement must be at the API level, not the prompt level. A system prompt saying "do not delete files" is not a security control.

**Lár:** `CredentialVault` enforces privilege at the execution layer. The LLM never holds credentials. The vault's `get()` method is the only path to a scoped token, and it logs every grant. The `LethalTrifectaGuard` adds a second layer: if the agent simultaneously holds untrusted input, sensitive data, and an autonomous action capability without human approval on record, execution is blocked at the framework level — not via model instruction.

### Challenge 2 — Human Oversight: The Evasion Risk (§6.2)

**Paper:** LLM behavioral guarantees cannot be established by instruction alone. Oversight mechanisms must be external constraints, not internal instructions.

**Lár:** `HumanJuryNode` is a structural graph interrupt — the graph literally cannot proceed to the external action node without a human `approve` or `reject` response being written to state. It is not a prompt instruction. The `AuthorityLedger` then signs and persists that human decision, creating an evidentiary chain that proves oversight was operationalised (not merely designed).

### Challenge 3 — Transparency Across Multi-Party Action Chains (§6.3)

**Paper:** Transparency extends to all parties whose rights are touched, not just the direct user. When an agent sends an email or makes a credit decision, the recipient/applicant is an affected party.

**Lár:** The `TransparencyEngine` flags every action with `affected_parties="THIRD_PARTY"`. The `ComplianceManifestGenerator` counts and inventories all third-party-affecting actions and raises Art. 50 flags. The `SyntheticMarkerNode` applies machine-readable AI content marking to outputs as required by Art. 50(2).

### Challenge 4 — Runtime Behavioral Drift and Substantial Modification (§6.4)

**Paper:** *"Without a defined runtime state boundary, 'substantial modification' becomes unmeasurable by design."*

**Lár:** `RuntimeStateVersioner` defines the boundary. It snapshots the three components the paper identifies as the drift surface: `tool_catalogue`, `policy_bindings`, and `state_schema_keys`. Any change to these after the conformity baseline is flagged with severity (HIGH/MEDIUM). The baseline is keyed to `conformity_id`, creating an explicit link between the runtime state and the conformity assessment that assessed it.

---

## AEPD Rule of 2 / Lethal Trifecta (Paper §7.3)

The paper specifically references Simon Willison's "lethal trifecta" and the AEPD's February 2026 guidance applying it as a GDPR-grounded governance criterion:

> *An agent should not simultaneously combine: processing untrusted input + accessing sensitive data + taking autonomous action affecting individuals — without human oversight.*

**Lár primitive: `LethalTrifectaGuard`**

```python
trifecta_guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("case_summary") is not None,
    sensitive_data_fn=lambda s: any(s.get(k) for k in pii_keys),
    autonomous_action_fn=lambda s: True,
    human_approval_state_key="jury_decision",  # safe if jury has approved
    block_on_violation=True,
)
```

If all three legs are active and no human approval is on record, the guard raises `LethalTrifectaError` and blocks execution. If `jury_decision` is set (human approved), the guard proceeds — operationalising the AEPD guidance that the combination is acceptable *with* human oversight.

---

---

## v2.2.0 Gap-Closure Requirements

The following 12 requirements were identified as gaps in v2.1.x and are fully closed in v2.2.0.

### A — Art. 9 FRIA: Fundamental Rights Impact Assessment

**Gap:** Art. 9 requires providers to assess impacts on fundamental rights as part of the risk management system. v2.1.x had static design-time documentation but no runtime gate.

**Lár v2.2.0:** `FundamentalRightsImpactNode` — scans AI outputs at runtime against six EU Charter dimensions (Dignity Art. 1, Privacy Art. 7/8, Non-discrimination Art. 21, Expression Art. 11, Justice Art. 47, Data Protection Art. 8). Raises `FRIAViolation` and blocks or logs per configuration.

```python
from lar.compliance import FundamentalRightsImpactNode

fria = FundamentalRightsImpactNode(
    input_key="recommendation",
    block_on_violation=True,
    next_node=output_node,
)
```

---

### B — Art. 9 PMM: Stochastic Output Variance Monitoring

**Gap:** Post-market monitoring (Art. 9(9)) requires providers to monitor system performance over time. Output variance from the conformity-assessed baseline is a potential Art. 3(23) trigger.

**Lár v2.2.0:** `BehavioralEnvelopeMonitor` — tracks numeric output metrics (confidence scores, risk scores, etc.) against a baseline computed from conformity assessment samples. Flags deviations exceeding a configurable threshold.

```python
from lar.compliance import BehavioralEnvelopeMonitor

monitor = BehavioralEnvelopeMonitor(
    metric_key="model_confidence",
    baseline_samples=[0.82, 0.85, 0.79, 0.88],
    deviation_threshold=0.20,   # 20% relative deviation from baseline mean
)
flag = monitor.observe(current_confidence)
```

---

### C & D — Art. 12 Causal Chain Depth

**Gap:** The Art. 12 causal trace was file-level HMAC signed but lacked per-step integrity verification (a post-hoc tamper could edit one step's diff and re-sign). RouterNode plan-switch events were also not captured.

**Lár v2.2.0:**
- `AuditLogger.verify_step_integrity(step)` — recomputes the state diff from `state_before`/`state_after` and compares it against the logged diff. Catches edits that bypassed the file-level HMAC.
- `AuditLogger.log_plan_switch(from_branch, to_branch, reason, step, node)` — injects plan-switch events into the causal chain as typed entries.

```python
# After a run, verify every step
reports = logger.verify_all_steps()
for r in reports:
    if r["integrity"] == "MISMATCH":
        print(f"Step {r['step']} tampered: {r['discrepancies']}")
```

---

### E — Art. 13: Deployer Instructions for Use

**Gap:** Art. 13 requires providers to supply deployers (not just end users) with sufficient information to understand and correctly use the AI system. v2.1.x had `TransparencyEngine` for Art. 50 third-party disclosure but nothing for the Art. 13 provider-to-deployer obligation.

**Lár v2.2.0:** `DeployerTransparencyNode` — generates a machine-readable instructions-for-use document covering intended purpose, known limitations, human oversight requirements, prohibited uses, and data governance notes.

```python
from lar.compliance import DeployerTransparencyNode

art13 = DeployerTransparencyNode(
    system_name="Credit Decision Agent v2.2",
    intended_purpose="Creditworthiness assessment (Annex III §5b)",
    known_limitations=["English-language inputs only", "Max income €500k"],
    human_oversight_requirements=["All CRITICAL decisions require CFO approval"],
    prohibited_uses=["Consumer profiling", "Insurance scoring"],
    conformity_id="CE-FINANCE-2026-001",
    next_node=next_node,
)
```

---

### F — Art. 14: Automation Boundary per Decision Type

**Gap:** `HumanJuryNode` had a single fallback policy (auto-select first choice in non-interactive environments). Deployers couldn't configure per-decision-type policies — e.g., `CREDIT_DECISION` always requiring a human even in CI, `ALERT_REVIEW` allowing auto-selection when risk is LOW.

**Lár v2.2.0:** `HumanJuryNode(decision_type=…, automation_boundary={…})` — policy map keyed by decision type. Three policies:
- `"always_human"` — blocks in non-interactive environments (raises `RuntimeError`)
- `"auto_if_low_risk"` — auto-selects only when `risk_score_key` returns `LOW` or `MINIMAL`
- `"auto_first_choice"` — legacy behaviour

```python
jury = HumanJuryNode(
    prompt="Approve credit recommendation?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    decision_type="CREDIT_DECISION",
    automation_boundary={
        "CREDIT_DECISION": "always_human",
        "DRIFT_ALERT":     "auto_if_low_risk",
    },
    risk_score_key="risk_score",
)
```

---

### G — Art. 25(4): Written Supplier Agreements

**Gap:** Art. 25(4) requires written agreements between providers and deployers defining which Art. 16 obligations each party bears. No runtime enforcement existed.

**Lár v2.2.0:** `SupplierAgreementRegistry` — maintains a ledger of signed agreements. Call `registry.assert_agreement(tool_name)` before any third-party tool execution. Raises `AgreementNotFoundError` if missing or expired.

```python
from lar.compliance import SupplierAgreementRegistry

registry = SupplierAgreementRegistry(registry_path="agreements.json")
registry.register(
    tool_name="send_email",
    supplier_name="Acme Email SaaS Ltd",
    agreement_id="AGR-2026-001",
    signed_date="2026-01-15",
    expiry_date="2027-01-15",
    obligations={"provider": "Art. 9 risk docs", "deployer": "Art. 26 monitoring"},
)
registry.assert_agreement("send_email")   # raises if missing or expired
```

---

### H — Art. 3(23): Post-Conformity Tool Addition Detection

**Gap:** `RuntimeStateVersioner` detected structural drift in tool catalogues but only when the executor's periodic snapshot fired. It didn't specifically flag *new tools added after the conformity baseline* as a potential Art. 3(23) substantial modification.

**Lár v2.2.0:** `DynamicToolDiscoveryMonitor` — wire it at graph entry. Compares `state["tool_catalogue"]` against the baseline set recorded at conformity assessment time. Flags new tools immediately.

```python
from lar.compliance import DynamicToolDiscoveryMonitor

monitor = DynamicToolDiscoveryMonitor(
    baseline_tools=["send_email", "query_crm"],
    block_on_undisclosed=True,   # block execution of undisclosed tools
    next_node=next_node,
)
```

---

### I — Art. 3: Sub-Agent Boundary Classification

**Gap:** In multi-agent graphs, BatchNode branches run as internal sub-agents covered by the parent's CE. External third-party agents independently placed on the market have separate conformity obligations (Art. 25). No primitive existed to declare and record these boundaries.

**Lár v2.2.0:** `MultiAgentBoundaryNode` — marks and records each sub-agent invocation as `INTERNAL` or `EXTERNAL_MARKET`. Records accumulate in `state["multi_agent_boundaries"]`.

```python
from lar.compliance import MultiAgentBoundaryNode

# External third-party agent — its own CE required
boundary = MultiAgentBoundaryNode(
    agent_name="SupplierKYCAgent",
    placement="EXTERNAL_MARKET",
    provider_entity="KYC-as-a-Service GmbH",
    purpose="Verifies supplier identity via external API.",
    conformity_id="CE-KYC-2026-007",
    next_node=kyc_tool_node,
)
```

---

### J — Art. 73–74: Real-Time Incident Detection

**Gap:** `IncidentReporter` (v2.1.x) was a post-hoc PMM report generator scanning log files. Art. 73 requires *real-time* incident detection with 24h reporting deadlines for serious incidents. No runtime hook existed.

**Lár v2.2.0:** `IncidentReporterNode` — operates in two modes:
1. **Graph node mode** — scans state for harm signals (`last_error`, `_prohibited_practice_flag`, `fria_findings`, etc.) after each step.
2. **Executor hook mode** (recommended) — pass to `GraphExecutor(incident_reporter=…)` and it fires automatically on every unhandled node exception. No manual node placement required.

```python
from lar.compliance import IncidentReporterNode

incident_reporter = IncidentReporterNode(
    severity_threshold="HIGH",
    incident_log_path="lar_logs/incidents.jsonl",
    webhook_url="https://csirt.yourorg.com/webhook",  # stored in record; deployer POSTs
)
executor = GraphExecutor(incident_reporter=incident_reporter)
```

Incident records include the Art. 73 reporting deadline (`24h` for CRITICAL/HIGH, `72h` for MEDIUM) computed at detection time.

---

### K — GDPR Art. 17: Erasable Per-Subject Memory

**Gap:** `PIIRedactionEngine` stripped PII from audit logs (data minimisation). But agents accumulating interaction data per subject had no mechanism for subject-addressable erasure — a distinct GDPR Art. 17 obligation.

**Lár v2.2.0:** `SessionMemoryNode` — four modes: `write` (store state keys in subject compartment with TTL), `read` (load latest memory back into state), `erase` (delete all data for a subject — Art. 17 right to erasure), `audit` (write access log to state for Art. 15 right of access).

```python
from lar.compliance import SessionMemoryNode

mem_write = SessionMemoryNode(
    mode="write",
    subject_key="applicant_id",
    memory_keys=["recommendation", "risk_score"],
    retention_days=90,
    next_node=output_node,
)
# On erasure request:
mem_erase = SessionMemoryNode(mode="erase", subject_key="applicant_id")
```

---

### L — Art. 15(4): Trust-Based Privilege Restriction

**Gap:** `CredentialVault.get()` provisioned credentials JIT but had no mechanism to restrict sensitive credentials to high-trust execution paths. A compromise path could obtain a payment API key before a HumanJuryNode had approved.

**Lár v2.2.0:** `CredentialVault.get_with_trust(trust_level=…)` — credentials are registered with a `min_trust_level`. The method raises `PermissionError` if the calling context's trust level is insufficient. Set `trust_level="HIGH"` only after `jury_decision == "approve"`.

```python
vault = CredentialVault()
vault.register_credential("PAYMENT_API_KEY", secret, min_trust_level="HIGH")

# Before jury approval — trust_level is LOW:
vault.get_with_trust("payment", "write", "PAYMENT_API_KEY", "LOW")  # PermissionError

# After jury approval — trust_level elevated to HIGH:
vault.get_with_trust("payment", "write", "PAYMENT_API_KEY", "HIGH")  # ✅ granted
```

---

## Running the Full Showcase

```bash
cd lar/
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

The showcase (v2.2.0) runs the FINANCE backbone against a credit application with `ollama/phi4:latest`, validates all 23 Nannini et al. paper-mapped requirements, and produces three audit artifacts in `enterprise_audit/`:

- `compliance_manifest.json` — Step 9 action inventory
- `authority_ledger.json` — Art. 14 oversight records
- `run_<id>.json` — Art. 12 causal trace (HMAC signed, PII stripped)

To run other domains:

```python
from lar.enterprise.backbone import build_and_run

result = build_and_run(case=my_case, domain="HEALTHCARE")
result = build_and_run(case=my_case, domain="HR")
result = build_and_run(case=my_case, domain="PHARMA")
result = build_and_run(case=my_case, domain="LEGAL")
```

---

## References

- Nannini, L., Smith, A.L., Maggini, M.J., Panai, E., Feliciano, S., Tiulkanov, A., Maran, E., Gealy, J., Bisconti, P. (2026). *AI Agents Under EU Law: A Compliance Architecture for AI Providers.* arXiv:2604.04604v1.
- EU AI Act (Regulation 2024/1689). Official Journal of the European Union.
- AEPD (2026). *Guidance on GDPR obligations for agentic AI deployments.* February 2026.
- Kim et al. (2025). *Systematic survey of the agentic AI attack and defense landscape.*
- OWASP Agentic Security Initiative (2025). *Top 10 for Agentic Applications.*
