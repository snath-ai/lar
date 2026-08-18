# Enterprise Reference Implementation

> **v2.2.0** — The canonical, working reference that ticks all **23 compliance boxes** from the April 2026 EU AI Act research paper. Validated live with `ollama/phi4:latest` — no API key required.

**Files:**

- [`src/lar/enterprise/backbone.py`](../../src/lar/enterprise/backbone.py) — domain-agnostic engine
- [`src/lar/enterprise/run.py`](../../src/lar/enterprise/run.py) — domain-selecting runner

!!! warning "Legal Disclaimer"
    Lár is open-source software infrastructure, not legal or compliance advice. Using Lár does not automatically guarantee compliance with the EU AI Act, GDPR, HIPAA, or any other regulation. Organizations are solely responsible for ensuring their AI systems undergo proper legal review and conformity assessments.

---

## The Blueprint: EU AI Act Finance Showcase

If you need to prove compliance to an auditor or understand how the compliance primitives fit together, run our definitive showcase script. This single script acts as the blueprint for high-risk EU AI Act deployments, executing a simulated SME loan application through the full compliance pipeline.

```bash
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

It explicitly validates all 23 requirements from Nannini et al. (2026):

**Original 12 steps:**
1. **Art. 15(4)**: JIT + trust-based privilege (`CredentialVault.get_with_trust()`)
2. **GDPR Art. 17**: PII redaction + erasable per-subject memory (`SessionMemoryNode`)
3. **Art. 12**: Causal audit logging + per-step integrity (`verify_step_integrity()`)
4. **Art. 9 & 14**: PolicyRegistry + RiskScorerNode
5. **Art. 14**: Human-in-the-Loop with automation boundary (`HumanJuryNode(automation_boundary=…)`)
6. **AEPD Rule of 2**: LethalTrifectaGuard
7. **Art. 13 & 50**: DeployerTransparencyNode + TransparencyEngine
8. **Art. 3(23)**: RuntimeStateVersioner + DynamicToolDiscoveryMonitor
9. **Step 9**: ComplianceManifestGenerator (auto-detects adjacent legislation)
10. **prEN 18283**: BiasFilterNode

**v2.2.0 gap-closure (A–L):**
11. **Art. 9 FRIA**: FundamentalRightsImpactNode (6 EU Charter dimensions)
12. **Art. 9 PMM**: BehavioralEnvelopeMonitor (output variance vs. baseline)
13. **Art. 12 depth**: `log_plan_switch()` for RouterNode branch-switch events
14. **Art. 13 deployer**: DeployerTransparencyNode (instructions for use)
15. **Art. 14 boundary**: `automation_boundary` + `decision_type` on HumanJuryNode
16. **Art. 25(4)**: SupplierAgreementRegistry (written agreement enforcement)
17. **Art. 3(23) tools**: DynamicToolDiscoveryMonitor (post-conformity additions)
18. **Art. 3 boundary**: MultiAgentBoundaryNode (INTERNAL vs. EXTERNAL_MARKET)
19. **Art. 73–74**: IncidentReporterNode (executor hook — auto-fires on exceptions)
20. **GDPR Art. 17 memory**: SessionMemoryNode (write/read/erase/audit modes)
21. **Art. 15(4) trust**: `get_with_trust()` — trust-level-gated credential access
22. **Art. 5 auto**: ProhibitedPracticeGuard executor hook (fires on every LLM output)
23. **Art. 50(2)**: SyntheticMarkerNode (AI content marking)

---

## Quick Start

```bash
# Healthcare (MDR + EU AI Act + GDPR + FDA 21 CFR 11)
python src/lar/enterprise/run.py HEALTHCARE

# Finance (MiFID II + DORA + FINRA + EU AI Act)
python src/lar/enterprise/run.py FINANCE

# Pharma (ICH GCP + EMA + FDA 21 CFR 11)
python src/lar/enterprise/run.py PHARMA

# Legal (DSA + UPL + EU AI Act)
python src/lar/enterprise/run.py LEGAL

# HR/Recruitment (Equality Act + EU AI Act + GDPR)
python src/lar/enterprise/run.py HR
```

Three audit artefacts are produced on every run, all HMAC-SHA256 signed:

| File | Contains | Regulatory Basis |
|:---|:---|:---|
| `enterprise_audit/run_<uuid>.json` | Full causal trace — every node, state diff, reasoning | Art. 12 |
| `enterprise_audit/authority_ledger.json` | Who approved, their role, rationale, risk score, timestamp | Art. 12, 14 |
| `enterprise_audit/compliance_manifest.json` | Static graph inventory — every tool, LLM, router catalogued | Step 9 |

---

## Using It in Your Own Code

```python
from lar.enterprise.backbone import build_and_run

result = build_and_run(
    case={
        "case_summary": "Patient BP 178/110, eGFR 38, HbA1c 9.2%...",
        "patient_id": "PT-00923",   # auto-redacted before log signing
    },
    domain="HEALTHCARE",
)

# result["audit_log_path"]        → signed causal trace
# result["authority_ledger_path"] → signed authority record
# result["manifest_path"]         → regulatory action inventory
# result["authority_records"]     → list of AuthorityRecord dicts
```

### Targeting a New Domain

Every domain is a single dict override. Add yours to `DOMAIN_PRESETS` in `backbone.py`:

```python
DOMAIN_PRESETS["INSURANCE"] = {
    "system_name":      "AI Claims Assessment Agent",
    "domain":           "INSURANCE",
    "conformity_id":    "CA-INS-2026",
    "stakeholder_role": "Senior Claims Adjuster",
    "regulatory_tags":  ["EU_AI_ACT", "GDPR", "SOLVENCY_II"],
    "pii_keys":         ["policy_number", "name", "dob", "nhs_id"],
    "bias_terms":       ["race", "gender", "age", "disability", "postcode"],
    "analysis_prompt": (
        "You are an insurance claims AI assistant. Assess the following claim.\n"
        "Claim: {case_summary}\n\n"
        "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
        "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
    ),
}
```

Then: `python run.py INSURANCE`

---

## How the Backbone Solves Each Paper Problem

The April 2026 research paper (*Nannini et al.*) identified **10 distinct compliance failures** in current agentic frameworks. The backbone addresses every one.

### Problem 1 — Art. 12: No Causal Audit Trail

> *"None produce audit trails that meet Article 12's requirement... logging must capture the causal relationships between steps: why did the agent select this tool rather than that one?"*

**How the backbone solves it:**

The `GraphExecutor` computes an exact `state_diff` (added/updated/deleted keys) after **every single node** executes — not an LLM-reported summary of what happened, but a mathematical fact. The `AuditLogger` binds the reasoning trace to this diff and signs the whole log with HMAC-SHA256.

```
enterprise_audit/run_<uuid>.json  →  immutable, tamper-evident causal trace
```

The `PIIRedactionEngine` strips all configured PII keys **before** the HMAC signature is computed, so the log satisfies both Art. 12 (integrity) and GDPR Art. 17 (right to erasure) simultaneously.

---

### Problem 2 — Art. 15(4): Static Credentials = Catastrophic Attack Surface

> *"Systems must enforce the principle of least privilege. Providing an agent with static, high-level API keys creates a catastrophic attack surface for prompt injection or autonomous drift."*

**How the backbone solves it:**

`CredentialVault` is the first node executed. It provisions a time-scoped, scope-restricted JIT token bound strictly to the immediate action (`read:cases`). No static global API key is held in the agent's state at any point. Every credential access is logged as an `NHI_CREDENTIAL_ACCESS` event.

---

### Problem 3 — Art. 14: No Infrastructure to Safely Pause and Resume

> *"Article 14 requires the ability to override or reverse outputs. Current architectures lack infrastructure to safely pause, await human review, and selectively resume without breaking the session."*

**How the backbone solves it:**

The `RiskScorerNode` evaluates the `PolicyRegistry` against the live confidence score. For `PRE_EXECUTION` risk (the default for all HIGH/CRITICAL domains), it **physically routes to `HumanJuryNode`** before any external action. The graph halts. The human reviews the exact context the LLM used. The graph only resumes on explicit approval.

---

### Problem 4 — Art. 12/14: The "Fourth Tier" Governance Gap

> *"A fourth tier is absent: infrastructure maintaining an immutable oversight record. This is not only a market gap — it is a compliance gap."*

**How the backbone solves it:**

Every `HumanJuryNode` in the backbone is wired to an `AuthorityLedger`. On each decision it captures:

- **Who:** `stakeholder_id` (e.g., `dr.smith@hospital.org`)
- **Role:** `stakeholder_role` (e.g., `Attending Physician`)
- **What:** the exact AI-proposed action description
- **Risk score:** pulled live from `RiskScorerNode` output
- **Decision:** `approve` / `reject`
- **Rationale:** prompted from the stakeholder at runtime
- **Timestamp:** UTC

This is saved as a separate HMAC-signed `authority_ledger.json` — the action-level evidence chain that Articles 12–14 demand.

---

### Problem 5 — Art. 3(23): Behavioral Drift Voids CE Marking

> *"If an agent dynamically discovers new tools at runtime, Art. 3(23) classifies this as a 'Substantial Modification', instantly voiding the system's CE marking."*

**How the backbone solves it:**

`RuntimeStateVersioner` takes a cryptographic baseline snapshot of the tool catalogue and policy bindings **before** execution begins. After each functional node runs, it takes a new snapshot and compares against the baseline via `DriftDetector`. If the tool catalogue or schema changes, it emits a `HIGH` severity drift warning and writes the diff to state for the audit trail.

---

### Problem 6 — GDPR Art. 5/14: The "Lethal Trifecta" (AEPD Rule of 2)

> *"An agent should not simultaneously combine all three of the following without human oversight — processing untrusted input, accessing sensitive data, and taking autonomous action affecting individuals."* — AEPD Guidance, Feb 2026

**How the backbone solves it:**

`LethalTrifectaGuard` evaluates all three legs against the live `GraphState` before any external action executes. If all three are simultaneously active and no `HumanJuryNode` has recorded a decision upstream, it raises `LethalTrifectaError` and writes a full evaluation report to the audit trail. Since the backbone always routes through `HumanJuryNode` for `PRE_EXECUTION` actions, the trifecta guard passes cleanly — but it **guarantees** that this remains true even if someone rewires the graph.

---

### Problem 7 — prEN 18283: Bias in AI-Assisted Decisions

> *"Bias management requirements apply across all high-risk AI systems regardless of domain."*

**How the backbone solves it:**

`BiasFilterNode` scans the LLM's recommendation for domain-specific sensitive terms (race, gender, age, disability, etc.) before any action is taken. If detected, it escalates directly to `HumanJuryNode` — the same oversight gate — rather than letting a potentially biased recommendation proceed autonomously.

---

### Problem 8 — Art. 13/50: No Third-Party Disclosure Infrastructure

> *"Article 50 mandates that affected third parties must be informed when interacting with an AI."*

**How the backbone solves it:**

`TransparencyEngine` fires after the human approval, recording an `AI_INTERACTION_DISCLOSURE` event for every case processed. `SyntheticMarkerNode` then appends a visible AI disclaimer to the final recommendation before it exits the graph — satisfying both Art. 13 (transparency to deployers) and Art. 50 (transparency to affected persons).

---

### Problem 9 — Step 9: No Framework Provides an Action Inventory

> *"The provider's foundational compliance task is an exhaustive inventory of the agent's actions, data flows, connected systems, and affected persons. That inventory is the regulatory map. No framework provides tooling to generate it."*

**How the backbone solves it:**

`ComplianceManifestGenerator` performs a **static traversal** of the entire graph before execution begins — requiring zero runtime. It catalogues every `FunctionalNode`, `LLMNode`, `HumanJuryNode`, and their metadata, flags missing `CredentialVault` attachments, and saves a machine-readable `compliance_manifest.json` for your notified body.

---

### Problem 10 — Art. 9/14: No Risk Taxonomy Per Action Type

> *"Risk classification must be action-level, not system-level."*

**How the backbone solves it:**

`PolicyRegistry` maps each action type (`case_analysis`, `final_output`) to a structured `ActionPolicy` with a risk tier, reversibility flag, oversight level, regulatory tags, and affected parties classification. `RiskScorerNode` reads this registry at runtime and dynamically escalates oversight based on both the registered policy **and** live telemetry (confidence score, affected party type).

---

## The Execution Order: A Compliance Walkthrough

```
[A] CredentialVault          → Art. 15(4): JIT NHI token, no static credentials
[B] LLMNode                  → domain-aware analysis of the case
[C] FunctionalNode (parse)   → extract risk_level, recommendation, confidence
[D] RiskScorerNode           → Art. 14: route to HumanJuryNode if PRE_EXECUTION
[E] BiasFilterNode           → prEN 18283: escalate to jury if bias detected
[F] HumanJuryNode            → Art. 14: human approval gate
    + AuthorityLedger        → Art. 12/14: fourth-tier signed authority record
[G] LethalTrifectaGuard      → GDPR Art. 5: AEPD Rule-of-2 runtime enforcement
    + TransparencyEngine     → Art. 13/50: third-party disclosure event
    + RuntimeStateVersioner  → Art. 3(23): post-execution drift snapshot
[H] SyntheticMarkerNode      → Art. 50(2): AI disclaimer on final output

Pre-execution (static):
    ComplianceManifestGenerator → Step 9: regulatory action inventory

Throughout (in AuditLogger):
    PIIRedactionEngine       → GDPR Art. 17: strip PII before HMAC signing
    HMAC-SHA256              → Art. 12: tamper-evident causal trace
```

---

## Live Results (Verified with `ollama/phi4:latest`)

| Domain | Regulatory Regime | LLM Risk Level | Confidence | Stakeholder Role |
|:---|:---|:---|:---|:---|
| **Healthcare** | EU AI Act + MDR + HIPAA + FDA 21 CFR 11 | CRITICAL | 0.95 | Attending Physician |
| **Finance** | EU AI Act + MiFID II + DORA + FINRA | CRITICAL | 0.95 | Risk Officer |
| **Pharma** | EU AI Act + ICH GCP + EMA + FDA 21 CFR 11 | MEDIUM | 0.85 | Principal Investigator |
| **Legal** | EU AI Act + DSA + UPL | HIGH | 0.90 | Supervising Attorney |
| **HR** | EU AI Act + GDPR + Equality Act | MEDIUM | 0.80 | HR Director |

All 5 domains pass their compliance primitive checks. All 3 audit artefacts are HMAC-signed and PII-stripped.

---

## Environment Variables

| Variable | Purpose | Default |
|:---|:---|:---|
| `HMAC_SECRET` | Secret for signing all audit artefacts | `change-me-in-prod` |
| `REVIEWER_EMAIL` | Stakeholder ID written into authority records | `reviewer@enterprise.org` |
| `ENTERPRISE_API_KEY` | Mock credential injected via CredentialVault | `mock-jit-token-xyz` |

In production: inject `HMAC_SECRET` from AWS KMS / HashiCorp Vault. Never hardcode it.
