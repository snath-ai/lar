# Build a Compliant Agent from Scratch

> **Who this is for:** Engineers building AI agents in regulated environments — finance, healthcare, pharma, legal, HR. And AI assistants helping them do it.
>
> **What you will build:** A working EU AI Act compliant agent, from a blank file, one primitive at a time. By the end you will have a pipeline that produces three HMAC-signed audit artefacts an auditor can independently verify.
>
> **The reference implementation:** Everything here is drawn from `examples/compliance/22_eu_ai_act_finance_showcase.py`. Run it any time to see the finished result.

---

## Before You Start: The Mental Model

Most agent frameworks are black boxes. You send a prompt, you get a response, something happened in between. That is fine for a chatbot. It is not acceptable for a system that makes credit decisions, clinical recommendations, or employment assessments.

The EU AI Act (enforced August 2026) requires that high-risk AI systems:
- Keep records of every decision (Art. 12)
- Allow humans to override before irreversible actions (Art. 14)
- Manage risk continuously (Art. 9)
- Protect against cybersecurity threats including credential abuse (Art. 15(4))

Lár satisfies these requirements at the execution layer — not through documentation written after the fact, but through primitives that fire during the run. Each step in this guide introduces one primitive, explains which regulation it satisfies, and shows you exactly how to wire it in.

---

## Step 0 — Install and Import

```bash
pip install lar-engine
```

```python
from lar import GraphExecutor, LLMNode, FunctionalNode, HumanJuryNode
from lar.state import GraphState
from lar.logger import AuditLogger
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
    LethalTrifectaGuard,
    SyntheticMarkerNode,
    ProhibitedPracticeGuard,
)
```

---

## Step 1 — Define Your Case

Your agent needs input. For a FINANCE domain this is a loan application. The keys you include here matter — any key containing personal data needs to be declared to the `PIIRedactionEngine` in Step 3.

```python
case = {
    "name":           "Jane Smith",         # PII — will be redacted
    "ssn":            "123-45-6789",        # PII — will be redacted
    "dob":            "1985-04-12",         # PII — will be redacted
    "account_number": "ACC-9982",           # PII — will be redacted
    "email":          "jane@example.com",   # PII — will be redacted
    "case_summary": (
        "Credit application for a €500,000 SME loan. "
        "Debt-to-equity ratio: 4.2. Three missed payments in last 18 months."
    ),
}
```

> **AI assistant note:** `case_summary` is the key the LLM prompt template reads from. Keep PII out of `case_summary` where possible — it goes into the prompt and into the signed log. The individual PII keys (`name`, `ssn`, etc.) are redacted before signing; `case_summary` is not.

---

## Step 2 — Credential Vault (Art. 15(4))

**Regulation:** Art. 15(4) requires just-in-time privilege minimisation. The agent must not hold standing credentials.

The `CredentialVault` stores credentials and issues scoped, single-use tokens at the moment of the specific action. The agent never holds the raw key.

```python
vault = CredentialVault()
vault.register_credential("ENTERPRISE_API_KEY", "your-api-key-here")

def fetch_credentials(state: GraphState):
    token = vault.get("llm_gateway", "read:cases", "ENTERPRISE_API_KEY")
    state.set("jit_token_present", token is not None)

node_creds = FunctionalNode(func=fetch_credentials, next_node=None)
```

**What to verify in the audit log:** `jit_token_present = True` at step 0. If this key is missing, the vault was bypassed.

---

## Step 3 — PII Redaction Engine (GDPR Art. 17)

**Regulation:** GDPR Art. 17 right to erasure, Art. 5(1)(c) data minimisation. Personal data must not persist in audit logs.

Declare every PII key. The `PIIRedactionEngine` strips these from the causal trace before the HMAC signature is computed — so personal data never enters the tamper-evident record.

```python
pii_keys = ["name", "ssn", "dob", "account_number", "email"]
redactor = PIIRedactionEngine(sensitive_keys=pii_keys)
```

The redactor is passed to the `AuditLogger` in Step 11. You do not need to call it manually.

> **Important:** If you add a new PII field to your case dict later, add it here too. A field missing from `pii_keys` will appear as plaintext in the signed log.

---

## Step 4 — Policy Registry (Art. 9 / Art. 14)

**Regulation:** Art. 9 risk management system. Every action type must be classified by risk tier, reversibility, and required oversight level before execution.

```python
registry = PolicyRegistry()
registry.register("case_analysis", ActionPolicy(
    domain="FINANCE",
    process="analysis",
    decision_type="case_analysis",
    risk_tier="HIGH",
    reversibility=False,          # credit decisions cannot be undone
    oversight_level="PRE_EXECUTION",  # human must approve before action
    regulatory_tags=["EU_AI_ACT", "GDPR", "MIFID_II"],
    affected_parties="THIRD_PARTY",   # the loan applicant
))
```

**`oversight_level` options:**
- `PRE_EXECUTION` — human approves before external action (required for HIGH/CRITICAL)
- `REALTIME` — human monitors during execution
- `RETROSPECTIVE` — human reviews after the fact (only appropriate for LOW risk)

---

## Step 5 — Authority Ledger + Audit Logger (Art. 12 / Art. 14)

**Regulation:** Art. 12 record-keeping, Art. 14 human oversight evidence chain.

The `AuthorityLedger` records every human oversight exercise: who approved, in what role, with what rationale, at what UTC timestamp, against what risk score. This is the evidentiary chain that proves oversight was operationalised, not just designed.

The `AuditLogger` records a state diff at every step and signs the full trace with HMAC-SHA256.

```python
import os

authority_ledger = AuthorityLedger(hmac_secret=os.getenv("HMAC_SECRET", "change-me-in-prod"))

audit_logger = AuditLogger(
    log_dir="enterprise_audit",
    hmac_secret=os.getenv("HMAC_SECRET", "change-me-in-prod"),
    pii_redactor=redactor,         # from Step 3
)
```

> **Key management:** The HMAC secret must be stored in your secrets manager (AWS KMS, HashiCorp Vault). The engineering team must not have access to the production key — otherwise the team that built the agent could alter its own audit trail.

---

## Step 6 — LLM Node

The LLM node is just an LLM call. Model-agnostic via LiteLLM — swap the string to change provider.

```python
node_llm = LLMNode(
    model_name="ollama/phi4:latest",   # or "gpt-4o", "gemini/gemini-1.5-pro", etc.
    prompt_template=(
        "You are a credit risk analyst. Assess the following application.\n"
        "Application: {case_summary}\n\n"
        "Reply with ONLY a single JSON object: "
        "risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
        "recommendation (max 2 sentences), "
        "confidence (float 0.0-1.0). No prose."
    ),
    output_key="ai_output",
    next_node=None,
)
```

Attach compliance metadata so the `ComplianceManifestGenerator` can classify this node:

```python
node_llm.compliance_metadata = {
    "action_type":      "llm_inference",
    "affected_parties": "THIRD_PARTY",
    "external_action":  True,
}
```

---

## Step 7 — Parse Output

LLMs return strings. Your downstream nodes need structured data. A pure Python function handles this — no LLM call, zero cost.

```python
import json

def parse_output(state: GraphState):
    raw = state.get("ai_output", "")
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        parsed = json.loads(raw[start:end]) if start >= 0 else {}
    except Exception:
        parsed = {"risk_level": "HIGH", "recommendation": raw[:200], "confidence": 0.5}
    state.set("risk_level",       parsed.get("risk_level", "HIGH"))
    state.set("recommendation",   parsed.get("recommendation", raw[:200]))
    state.set("model_confidence", float(parsed.get("confidence", 0.5)))

node_parse = FunctionalNode(func=parse_output, next_node=None)
```

---

## Step 8 — Bias Filter (prEN 18283)

**Regulation:** prEN 18283 bias management, Art. 10(2)(f-g).

The `BiasFilterNode` scans the LLM's recommendation for protected characteristic terms. If detected, it routes to the `HumanJuryNode` for oversight before any action is taken. This step must run before the risk scorer — the jury needs to see the bias flag.

```python
node_bias = BiasFilterNode(
    input_key="recommendation",
    sensitive_terms=["race", "gender", "age", "nationality", "religion", "disability"],
    next_node=None,     # wired below
    jury_node=None,     # wired below after jury is defined
)
```

---

## Step 9 — Human Jury Node (Art. 14)

**Regulation:** Art. 14 human oversight. For PRE_EXECUTION actions, the graph must physically halt and await human determination before proceeding.

`HumanJuryNode` is a structural graph interrupt — not a prompt instruction. The graph cannot reach the external action node without a human `approve` or `reject` being written to state.

```python
node_jury = HumanJuryNode(
    prompt="[FINANCE] AI recommendation ready. Do you approve?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    context_keys=["risk_level", "recommendation", "model_confidence"],
    next_node=None,
    authority_ledger=authority_ledger,     # records the decision
    stakeholder_id="reviewer@enterprise.org",
    stakeholder_role="Risk Officer",
    action_description="FINANCE AI case analysis — external action pending",
    risk_score_key="model_confidence",
)

# Now wire jury_node into the bias filter
node_bias.jury_node = node_jury
```

---

## Step 10 — Risk Scorer (Art. 9 + Art. 14)

**Regulation:** Art. 9 risk management, Art. 14 oversight commensurate with risk.

`RiskScorerNode` checks the action type against the `PolicyRegistry`, scores the risk, and routes to `HumanJuryNode` if the oversight level requires it.

```python
node_risk = RiskScorerNode(
    next_node=None,         # non-PRE_EXECUTION path (LOW/MEDIUM) — wired below
    jury_node=node_jury,    # PRE_EXECUTION path routes here
    confidence_key="model_confidence",
    action_type_key="action_type",
)
```

---

## Step 11 — Compliance Checks Node

This node fires three primitives in sequence after human approval:

**Lethal Trifecta Guard (AEPD Rule of 2 / GDPR Art. 5):** Blocks execution if the agent simultaneously holds untrusted input + sensitive data + autonomous action capability — unless human approval is on record.

**Transparency Engine (Art. 13 / Art. 50):** Flags every action that affects a third party, triggering Art. 50 disclosure obligations.

**Runtime State Versioner (Art. 3(23)):** Snapshots tool catalogue and policy bindings post-execution to detect drift from the conformity baseline.

```python
trifecta_guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("case_summary") is not None,
    sensitive_data_fn=lambda s: any(s.get(k) for k in pii_keys),
    autonomous_action_fn=lambda s: True,
    human_approval_state_key="jury_decision",
    block_on_violation=True,
)

transparency = TransparencyEngine()

versioner = RuntimeStateVersioner(conformity_baseline_id="CA-FIN-2026")
baseline = versioner.snapshot(
    tool_catalogue=["llm_analysis", "bias_filter", "external_write"],
    state_schema_keys=list(case.keys()) + ["ai_output", "jury_decision"],
    policy_bindings={"case_analysis": "PRE_EXECUTION"},
)

def compliance_checks(state: GraphState):
    trifecta_guard.check(state, action_label="external_write")
    transparency.flag(
        action_type="case_analysis",
        tool_name="external_write",
        affected_description="Case subject in FINANCE workflow",
        run_id=state.get("run_id", "unknown"),
    )
    snap = versioner.snapshot(
        tool_catalogue=["llm_analysis", "bias_filter", "external_write"],
        state_schema_keys=list(state._state.keys()),
        policy_bindings={"case_analysis": "PRE_EXECUTION"},
    )
    state.set("drift_report", snap.get("drift_report", {"drift_detected": False}))

node_checks = FunctionalNode(func=compliance_checks, next_node=None)
```

---

## Step 12 — Final Nodes

**Prohibited Practice Guard (Art. 5):** Checks the output does not contain EU AI Act prohibited practices — subliminal manipulation, social scoring, real-time biometric surveillance.

**Synthetic Marker (Art. 50(2)):** Appends a machine-readable AI content disclaimer to the final output.

```python
node_marker = SyntheticMarkerNode(
    input_key="recommendation",
    output_key="final_output",
    marker_type="VISIBLE",
    next_node=None,
)

node_prohibited = ProhibitedPracticeGuard(
    input_key="recommendation",
    next_node=node_marker,
    block_on_violation=True,
)
```

---

## Step 13 — Wire the Graph

Order matters. This is the correct sequence:

```python
node_creds.next_node  = node_llm
node_llm.next_node    = node_parse
node_parse.next_node  = node_bias      # bias scan before risk scoring
node_bias.next_node   = node_risk      # bias result visible to jury
node_risk.next_node   = node_checks    # LOW/MEDIUM path — no jury needed
node_jury.next_node   = node_checks    # HIGH/CRITICAL path — post-approval
node_checks.next_node = node_prohibited
# node_prohibited → node_marker (already wired above)
```

---

## Step 14 — Generate the Compliance Manifest (Step 9, Nannini et al.)

Before execution, statically traverse the full graph and produce an exhaustive inventory of every external action, affected party, and regulatory trigger.

```python
import os
os.makedirs("enterprise_audit", exist_ok=True)

manifest = ComplianceManifestGenerator(
    start_node=node_creds,
    system_name="AI Credit Decision Agent",
)
manifest.save("enterprise_audit/compliance_manifest.json")
```

This is your Annex IV technical documentation foundation. Generate it before every production deployment and store it alongside the run artefacts.

---

## Step 15 — Execute

```python
executor = GraphExecutor(
    log_dir="enterprise_audit",
    hmac_secret=os.getenv("HMAC_SECRET", "change-me-in-prod"),
    logger=audit_logger,
    versioner=versioner,
)

initial_state = {**case, "action_type": "case_analysis"}

for step in executor.run_step_by_step(node_creds, initial_state):
    node_name = step.get("node", "?")
    added = list(step.get("state_diff", {}).get("added", {}).keys())
    print(f"  ✓ {node_name:<30} → {added}")

authority_ledger.save("enterprise_audit/authority_ledger.json")
```

---

## Step 16 — Verify the Artefacts

Three files are now in `enterprise_audit/`. These are the inputs to a conformity assessment body review.

**Verify the HMAC signature:**
```bash
python examples/compliance/11_verify_audit_log.py \
  enterprise_audit/run_<uuid>.json \
  your_hmac_secret
```
Expected: `[+] VERIFICATION SUCCESSFUL`

**What an auditor checks:**

| Artefact | What to Verify |
|:---|:---|
| `compliance_manifest.json` | `tools_without_credential_vault = 0`. Art. 50 flags raised for third-party actions. |
| `authority_ledger.json` | Rationale is non-empty. Decision is consistent with rationale. Timestamp is realistic. |
| `run_<uuid>.json` | PII keys show `[REDACTED]`. Steps are consecutive. HMAC signature verifies. `bias_detected` present. |

---

## What You Now Have

A pipeline that:

1. Fetches credentials just-in-time — no standing privileges
2. Runs the LLM and parses the output
3. Scans for bias before risk scoring — bias result visible to the human jury
4. Halts at a structural interrupt for human approval on HIGH risk actions
5. Records the human decision with a cryptographic signature
6. Checks the Lethal Trifecta — blocks if untrusted input + PII + autonomous action without approval
7. Flags third-party transparency obligations
8. Detects drift from the conformity baseline
9. Guards against EU AI Act prohibited practices
10. Marks the output as AI-generated
11. Produces three HMAC-signed artefacts an auditor can independently verify

The full showcase running all of this end-to-end:

```bash
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

To retarget for another regulated domain:

```python
from lar.enterprise.backbone import build_and_run

result = build_and_run(case=my_case, domain="HEALTHCARE")  # MDR + EU AI Act + FDA 21 CFR 11
result = build_and_run(case=my_case, domain="PHARMA")      # ICH GCP + EMA + FDA 21 CFR 11
result = build_and_run(case=my_case, domain="HR")          # Equality Act + EU AI Act + GDPR
result = build_and_run(case=my_case, domain="LEGAL")       # DSA + UPL + EU AI Act
```

---

## See Also

- [Finance Showcase — live run through all 12 primitives →](https://docs.snath.ai/compliance/finance-showcase/)
- [Auditor's Guide — how to inspect the artefacts →](../compliance/auditor_guide.md)
- [Nannini et al. (2026) Full Mapping →](https://docs.snath.ai/compliance/paper-compliance-mapping/)
- [Enterprise Reference Implementation →](../compliance/enterprise-reference.md)
