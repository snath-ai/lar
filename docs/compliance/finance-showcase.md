# EU AI Act Finance Showcase

> The definitive proof-of-concept. One command runs a live SME credit decision through the 12-step compliance sequence from Nannini et al. (2026) and produces three HMAC-signed audit artefacts. Lár ships **13 compliance primitives** in total — `BranchTriageNode` (the 13th) is demonstrated in the [Fractal Compliance Showcase](https://docs.snath.ai/compliance/fractal-showcase/).

```bash
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

**Source:** [`examples/compliance/22_eu_ai_act_finance_showcase.py`](https://github.com/snath-ai/lar/blob/main/examples/compliance/22_eu_ai_act_finance_showcase.py)

---

## What It Validates

The showcase runs a high-risk credit application (Annex III, point 5(b) — creditworthiness assessment) through every compliance primitive in sequence, then verifies the three output artefacts against their regulatory obligations.

| # | Primitive | Article / Standard | Validated |
|:---|:---|:---|:---|
| 1 | `CredentialVault` | Art. 15(4) — JIT privilege minimisation | `jit_token_present = True` |
| 2 | `PIIRedactionEngine` | GDPR Art. 17 — data minimisation | SSN + Name stripped before HMAC signing |
| 3 | `AuditLogger` + HMAC-SHA256 | Art. 12 — causal audit logging | Tamper-evident log produced |
| 4 | `PolicyRegistry` + `RiskScorerNode` | Art. 9 + Art. 14 — risk management | `computed_oversight_level` written to state |
| 5 | `HumanJuryNode` | Art. 14 — human oversight interrupt | Structural block, not a prompt |
| 6 | `AuthorityLedger` | Art. 12/14 — Fourth Tier oversight record | Stakeholder + rationale + UTC timestamp |
| 7 | `LethalTrifectaGuard` | AEPD Rule of 2 / GDPR Art. 5 | Blocks untrusted input + PII + autonomous action |
| 8 | `TransparencyEngine` | Art. 13 + Art. 50 — third-party disclosure | Art. 50 flag raised for external write |
| 9 | `RuntimeStateVersioner` | Art. 3(23) — substantial modification | Drift report against conformity baseline |
| 10 | `ComplianceManifestGenerator` | Step 9 — external action inventory | All tools, LLMs, routers catalogued |
| 11 | `BiasFilterNode` | prEN 18283 — bias management | Protected-characteristic scan on LLM output |
| 12 | `SyntheticMarkerNode` | Art. 50(2) — AI content marking | Machine-readable disclaimer on final output |

---

## Execution Trace

The showcase runs the FINANCE backbone against a €500,000 SME loan application. Every step is yielded by the `GraphExecutor` generator — the exact path an auditor reconstructs from the log.

| Step | Node | Outcome | State Changes |
|:---|:---|:---|:---|
| 0 | `FunctionalNode` (CredentialVault) | ✅ success | `+ jit_token_present = True` |
| 1 | `LLMNode` (credit risk analysis) | ✅ success | `+ ai_output` (170 tokens) |
| 2 | `FunctionalNode` (JSON parse) | ✅ success | `+ recommendation, model_confidence, risk_level` |
| 3 | `RiskScorerNode` | ✅ success | `+ computed_oversight_level` |
| 4 | `HumanJuryNode` (Risk Officer gate) | ✅ success | `+ jury_decision = "approve"` |
| 5 | `FunctionalNode` (LethalTrifecta + Transparency) | ✅ success | `+ _trifecta_check`, `~ drift_report` |
| 6 | `SyntheticMarkerNode` | ✅ success | `+ final_output` (AI-disclaimed) |

---

## The Three Output Artefacts

Every run writes three HMAC-SHA256 signed files to `enterprise_audit/`. These are the inputs to a conformity assessment body review.

### Artefact 1 — Article 12 Causal Trace (`run_<uuid>.json`)

The exact JSON an auditor receives for Step 1:

```json
{
  "step": 1,
  "node": "LLMNode",
  "prompt": "You are a credit risk analyst. Assess the following loan/credit application.\nApplication: Credit application from business client. Requested limit: €500,000...\n\nReply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose.",
  "state_diff": {
    "added": {
      "ai_output": "{\"risk_level\": \"CRITICAL\", \"recommendation\": \"Do not approve the loan due to high D/E ratio and missed payments.\", \"confidence\": 0.95}"
    },
    "removed": {},
    "updated": {}
  },
  "run_metadata": {
    "prompt_tokens": 100,
    "output_tokens": 70,
    "total_tokens": 170,
    "model": "ollama/phi4:latest"
  },
  "outcome": "success"
}
```

The log contains every variable change, every rendered prompt, every token cost — no guesswork. PII (`name`, `ssn`, `account_number`) is stripped before signing.

### Artefact 2 — Article 14 Authority Ledger (`authority_ledger.json`)

The Fourth Tier oversight record — who approved, in what role, with what rationale:

```json
{
  "stakeholder_id": "reviewer@enterprise.org",
  "stakeholder_role": "Risk Officer",
  "decision": "approve",
  "rationale": "Reviewed FINANCE case. AI recommendation verified against policy.",
  "timestamp": "2026-05-08T16:29:00Z"
}
```

This is the evidentiary chain the paper's footnote 18 requires: action proposal → risk assessment → human determination → execution outcome.

### Artefact 3 — Step 9 Action Inventory (`compliance_manifest.json`)

The `ComplianceManifestGenerator` statically traverses the full graph before execution and produces an exhaustive inventory:

```
External Actions    : 2
Third-Party Actions : 2   ← Art. 50 disclosure triggered
Unvaulted Tools     : 0   ← All tools JIT-credentialed
```

Risk flags surfaced:
```
[HIGH]   AdaptiveNode detected — Art. 3(23) substantial modification candidate
[MEDIUM] Third-party affecting actions present — Art. 50 disclosure required
```

The full log is **HMAC-SHA256 signed** — tamper-evident:
```
Signature: 55931245a2c8117f1c1dc4f6b4499b866f272d99bd9273cd01d313e435a658a5
```

---

## Nannini et al. (2026) — 12-Step Coverage Map

The paper (Section 8.1) defines a 12-step conformity assessment sequence. Here is Lár's implementation status for each:

| Step | Paper Requirement | Lár Primitive | Type |
|:---|:---|:---|:---|
| **0** | Scope: Art. 3(1) AI system definition | Domain config + classification doc | Docs |
| **1** | GPAI layer: Art. 53 documentation chain | Model-agnostic (LiteLLM) + config | Docs |
| **2** | Classify: Annex III / high-risk determination | `DOMAIN_PRESETS` + `conformity_id` | Docs |
| **3** | QMS: prEN 18286 lifecycle management | Manifest + Ledger + Causal Trace | Artefacts |
| **4** | Risk management: prEN 18228 / Art. 9 | `PolicyRegistry` + `RiskScorerNode` | Runtime |
| **5** | Data governance: prEN 18284 + prEN 18283 | `PIIRedactionEngine` + `BiasFilterNode` | Runtime |
| **6** | Trustworthiness: Art. 12–14 | `AuditLogger` + `HumanJuryNode` + `AuthorityLedger` | Runtime |
| **7** | Cybersecurity: prEN 18282 / Art. 15(4) | `CredentialVault` (JIT NHI) | Runtime |
| **8** | CRA applicability | Secure-by-design architecture | Docs |
| **9** | Adjacent legislation inventory | `ComplianceManifestGenerator` | Runtime |
| **10** | Conformity assessment artefacts | Manifest + Ledger + Trace → Annex IV | Artefacts |
| **11** | Post-market monitoring + drift | `RuntimeStateVersioner` | Runtime |

---

## Running Other Domains

The same backbone covers every regulated vertical:

```python
from lar.enterprise.backbone import build_and_run

result = build_and_run(case=my_case, domain="HEALTHCARE")  # MDR + EU AI Act + FDA 21 CFR 11
result = build_and_run(case=my_case, domain="PHARMA")      # ICH GCP + EMA + FDA 21 CFR 11
result = build_and_run(case=my_case, domain="HR")          # Equality Act + EU AI Act + GDPR
result = build_and_run(case=my_case, domain="LEGAL")       # DSA + UPL + EU AI Act
```

---

## See Also

- [Full Nannini et al. (2026) Mapping →](https://docs.snath.ai/compliance/paper-compliance-mapping/)
- [EU AI Act Deep Dive →](https://docs.snath.ai/compliance/eu-ai-act-deep-dive/)
- [Enterprise Reference Implementation →](https://docs.snath.ai/compliance/enterprise-reference/)
- [Auditor's Guide →](https://docs.snath.ai/compliance/auditor_guide/)
