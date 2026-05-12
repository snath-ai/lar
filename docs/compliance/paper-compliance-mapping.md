# Lár ↔ Nannini et al. (2026) Compliance Architecture Mapping

This page maps every compliance requirement from **"AI Agents Under EU Law: A Compliance Architecture for AI Providers"** (Nannini, Smith, Maggini et al., April 2026, arXiv:2604.04604v1) to the specific Lár primitive that implements it.

The paper proposes a 12-step compliance sequence (Section 8.1) and identifies four agent-specific challenges (Section 6). Lár's Enterprise Compliance Backbone addresses every step and every challenge.

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

## Running the Full Showcase

```bash
cd lar/
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

The showcase runs the FINANCE backbone against a credit application, validates the 12 Nannini et al. paper-mapped compliance steps (13 primitives total — see [Fractal Compliance Showcase](https://docs.snath.ai/compliance/fractal-showcase/) for `BranchTriageNode`), and produces three audit artifacts in `enterprise_audit/`:

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
