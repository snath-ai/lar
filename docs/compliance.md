# Compliance & Safety (EU AI Act Ready - Aug 2026)

> **Legal Disclaimer**: The Lár framework provides architectural patterns to *assist* with compliance. It does not guarantee compliance on its own. You are responsible for the final validation of your system.

Lár is engineered to meet the stringent requirements of the **EU AI Act (2026)** and **FDA 21 CFR Part 11** for High-Risk AI Systems.

Unlike "Black Box" frameworks that obfuscate decision paths, Lár is a "Glass Box" engine designed for forensic auditability.

---

## EU AI Act Alignment

The EU AI Act (fully enforceable August 2026) imposes strict obligations on "High-Risk" systems (e.g., Medical Devices, Employment, Credit Scoring, Critical Infrastructure).

### Understanding Your Role (Art. 3)

It is critical to understand that **Lár is infrastructure, not an AI system.** 

*   **You (The Organisation):** If you use Lár to build and deploy a high-risk agentic workflow, you are legally the **Provider** (Art. 3(3)) or **Deployer** (Art. 3(4)). The legal burden of compliance falls on you.
*   **Lár (The Framework):** Lár acts as a component supplier. We provide the architectural primitives (nodes, executor, loggers) that generate the forensic *evidence* you need to pass a conformity assessment. 

Lár implements a complete **"Fourth Tier"** compliance architecture natively, providing 12 production-ready primitives that seamlessly integrate into the execution graph:

| Primitive | EU AI Act / Regulatory Match | Description |
| :--- | :--- | :--- |
| **`PolicyRegistry`** | Art. 9, 14 | Maps actions to risk tiers and determines oversight requirements. |
| **`RiskScorerNode`** | Art. 14 | Pre-execution dynamic risk scoring and human-in-the-loop routing. |
| **`RuntimeStateVersioner`** | Art. 3(23) | Detects "Substantial Modifications" (behavioral drift) during runtime. |
| **`CredentialVault`** | Art. 15(4) | Non-Human Identity (NHI) Just-in-Time privilege minimization. |
| **`TransparencyEngine`** | Art. 13, 50 | Automated disclosure flagging for third-party interactions. |
| **`PIIRedactionEngine`** | GDPR Art. 5, 17 | Right to Erasure: Cleans PII from states before cryptographic logging. |
| **`AuditLogger` (Causal Trace)** | Art. 12 | Immutable State-Diff logs capturing explicit model reasoning traces. |
| **`SyntheticMarkerNode`** | Art. 50(2) | Injects visible disclaimers or C2PA metadata into generated content. |
| **`BiasFilterNode`** | prEN 18283 | Evaluates state variables for bias heuristics before final output. |
| **`ComplianceManifestGenerator`** | Step 9, All | Statically walks the graph and auto-generates the exhaustive regulatory action inventory for auditors. |
| **`LethalTrifectaGuard`** | GDPR Art. 5, Art. 14 | Runtime pre-execution guard enforcing the AEPD "Rule of 2" — blocks any action that combines untrusted input + sensitive data + autonomous effect without prior human approval. |
| **`AuthorityLedger`** | Art. 12, 14 | The "Fourth Tier" — captures who exercised authority, their role, rationale, and risk score into a tamper-evident, HMAC-signed oversight record on every `HumanJuryNode` decision. |

---

## Enterprise Reference Implementation

> The canonical, working reference that ticks every compliance box the April 2026 EU AI Act research paper identifies.

Lár ships a **single reusable backbone** that wires all 12 primitives into an end-to-end auditable graph. Target any regulated vertical by supplying a domain name:

```bash
python src/lar/enterprise/run.py HEALTHCARE  # MDR + EU AI Act + GDPR + FDA 21 CFR 11
python src/lar/enterprise/run.py FINANCE     # MiFID II + DORA + FINRA + EU AI Act
python src/lar/enterprise/run.py PHARMA      # ICH GCP + EMA + FDA 21 CFR 11
python src/lar/enterprise/run.py LEGAL       # DSA + UPL + EU AI Act
python src/lar/enterprise/run.py HR          # Equality Act + EU AI Act + GDPR
```

Every run writes three HMAC-SHA256 signed artefacts to `enterprise_audit/`:

| Artefact | What It Contains | Article |
|:---|:---|:---|
| `run_<uuid>.json` | Full causal trace — every node, state diff, reasoning | Art. 12 |
| `authority_ledger.json` | Who approved, their role, rationale, risk score, UTC timestamp | Art. 12, 14 |
| `compliance_manifest.json` | Static graph inventory — every tool, LLM, router catalogued before execution | Step 9 |

**To add your own domain**, add one dict to `DOMAIN_PRESETS` in `backbone.py`:

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
        "You are an insurance claims AI. Assess the following claim.\n"
        "Claim: {case_summary}\n\n"
        "Reply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), "
        "recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose."
    ),
}
```

📖 **[Full guide: customisation, execution walkthrough, and paper-to-primitive mapping →](compliance/enterprise-reference.md)**

---

### 1. Article 12: Record-Keeping (Logging)
**Requirement**: Systems must enable "automatic recording of events ('logs') over their lifetime" to ensure traceability.

**Lár Solution**: `State-Diff Ledger`

Every Lár agent automatically produces a `flight_recorder.json` log. This is not a simple debugging print stream; it is a **forensic ledger** containing:

*   **Timestamp**: UTC-aligned execution time.
*   **Input/Output**: The exact rendered `prompt` sent, any `system_instruction` used, and the raw completion received.
*   **Model ID**: The specific version of the model used (e.g., `gpt-4-0613`).
*   **State Diff**: The exact variables changed in memory.

Below is a **real log** produced by `python src/lar/enterprise/run.py FINANCE`:

**Run ID `037c96e8` — FINANCE domain, `ollama/phi4:latest`**

| Step | Node | Outcome | State Changes |
| :--- | :--- | :--- | :--- |
| 0 | `FunctionalNode` (CredentialVault) | ✅ | `+ jit_token_present` |
| 1 | `LLMNode` (credit risk analysis) | ✅ | `+ ai_output` · 170 tokens |
| 2 | `FunctionalNode` (JSON parse) | ✅ | `+ recommendation, risk_level, model_confidence` |
| 3 | `RiskScorerNode` | ✅ | `+ computed_oversight_level` |
| 4 | `HumanJuryNode` | ✅ | `+ jury_decision = "approve"` |
| 5 | `FunctionalNode` (LethalTrifecta + Transparency) | ✅ | `+ _trifecta_check`, `~ drift_report` |
| 6 | `SyntheticMarkerNode` | ✅ | `+ final_output` |

**Real JSON — Step 1 (LLMNode), Article 12 Causal Trace:**

```json
{
  "step": 1,
  "node": "LLMNode",
  "prompt": "You are a credit risk analyst. Assess the following loan/credit application.\nApplication: Credit application from business client. Requested limit: €500,000...\n\nReply with ONLY a single JSON object: risk_level (LOW/MEDIUM/HIGH/CRITICAL), recommendation (max 2 sentences), confidence (float 0.0-1.0). No prose.",
  "state_diff": {
    "added": {
      "ai_output": "{\n  \"risk_level\": \"CRITICAL\",\n  \"recommendation\": \"Do not approve the loan due to high D/E ratio and missed payments.\",\n  \"confidence\": 0.95\n}"
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

**Real AuthorityLedger — Step 4 (HumanJuryNode), Article 14 Fourth Tier:**

```json
{
  "stakeholder_id": "reviewer@enterprise.org",
  "stakeholder_role": "Risk Officer",
  "decision": "approve",
  "rationale": "Reviewed FINANCE case. AI recommendation verified against policy.",
  "timestamp": "2026-05-02T22:18:08.183967Z"
}
```

Both files are HMAC-SHA256 signed. Signature of the causal trace:
```
55931245a2c8117f1c1dc4f6b4499b866f272d99bd9273cd01d313e435a658a5
```


### 2. Article 13: Transparency & Interpretability
**Requirement**: High-risk AI systems must be designed "in such a way that their operation is sufficiently transparent to enable users to interpret the system's output."

**Lár Solution**: "Glass Box" Architecture

*   **No Hidden Prompts**: Lár does not inject "system prompts" behind your back. You own 100% of the prompt.
*   **Explicit Routing**: The logic flow is defined in standard Python code (Nodes and Edges), not in a hidden neural network or a complex "Agent Executor" loop.
*   **Interpretability**: Any Python developer can read `graph.add_edge("Triage", "Human")` and understand the decision path without needing to understand the LLM's internal weights.

### 3. Article 14: Human Oversight
**Requirement**: Systems must be designed so that they can be "effectively overseen by natural persons," including the ability to "interrupt the system" or "override" decisions.

**Lár Solution**: Native `Interrupt` Pattern

Lár treats "Human Intervention" as a first-class citizen in the graph.

*   **Pause & Resume**: You can execute the graph up to a checkpoint (e.g., `before="ExecuteTool"`), inspect the state, and resume.
*   **State Modification**: A human supervisor can manually edit the memory (e.g., correcting a hallucinated argument) before approving the next step.

#### 🔋 The Compliance-Relevant Superpower: Resumable Graphs

Most frameworks block the LLM loop waiting for human input — burning API time and accumulating context. Lár's generator architecture means you can **checkpoint the state to disk, kill the process, and resume later** with zero LLM calls wasted.

```python
# Checkpoint before sending to a human reviewer
for step in executor.run_step_by_step(start_node, state):
    if step["node"] == "HumanJuryNode":
        json.dump(step["state_after"], open("checkpoint.json", "w"))
        break  # Stop — no idle LLM calls while waiting for approval

# Hours later, after approval via email/Slack:
state = json.load(open("checkpoint.json"))
for step in executor.run_step_by_step(post_jury_node, state):
    ...  # Only sends the remaining steps to the LLM
```

**Real cost numbers** (from [`examples/patterns/10_resumable_cost_demo.py`](../examples/patterns/10_resumable_cost_demo.py)):

| Approach | Tokens Sent on Resume | Tokens Wasted on Retry |
|:---|:---|:---|
| **Lár** | 302 (Step 3 only) | **0** |
| **Competitor** | 776 (full pipeline) | 474 |

> At 10,000 runs/day: **$9.48/day saved.** More importantly, no PII from early steps is re-transmitted on retry — a GDPR data minimisation benefit too.


### 4. Systemic Risks in Complex Topologies (`BatchNode` & `DynamicNode`)

#### `BatchNode` — Compliant Parallel Execution

Every branch of a `BatchNode` runs with a **deep-copied, isolated `GraphState`**. A hallucinating sub-agent cannot corrupt another branch. On completion, only differing keys are merged back and captured in the Causal Trace.

| Compliance Concern | Behaviour |
|:---|:---|
| State poisoning between branches | `copy.deepcopy()` at fork — total isolation |
| Merge auditability | Only changed keys written back; all visible in `state_diff` |
| Token budget overrun | Thread budgets reconciled atomically after join |
| Infinite loops in branches | `MAX_STEPS=50` internal brake per thread |

#### `DynamicNode` — Art. 3(23) Safe Self-Modification

`DynamicNode` lets an LLM design a subgraph at runtime. Before executing a single node the **`TopologyValidator`** enforces:

1. **Cycle detection** — DFS blocks mathematically infinite loops.
2. **Tool allowlist** — The LLM can only wire tools you pre-approved. No unapproved functions can be injected.
3. **Structural integrity** — Every `next` pointer must reference a real node. Dangling references are rejected.

The proposed JSON spec is written to state as `__graph_spec_json__` **before** execution — meaning auditors can see exactly what topology the LLM designed and what actually ran.

`ComplianceManifestGenerator` flags every `DynamicNode` with a `HIGH` severity warning so providers must explicitly document it before CE-marking submission.

📖 **[Full compliance breakdown with causal trace examples →](compliance/eu-ai-act-deep-dive.md#7-systemic-risks-in-complex-topologies-batchnode--dynamicnode)**

---

## FDA 21 CFR Part 11 (Electronic Records)

For healthcare and pharmaceutical applications (e.g., Drug Discovery pipelines), Lár supports the key requirements of **Part 11**:

1.  **Validation**: The deterministic nature of the graph means you can run regression tests. Given Input X and Fixed Seed Y, the graph traverses effectively the same path.
2.  **Audit Trails**: The `GraphExecutor` logs are immutable and time-stamped.
3.  **Authority Checks**: Lár's `SecurityNode` pattern allows you to implement permissions (e.g., "Only User A can approve Tool B") directly in the graph logic.

### Cryptographic Audit Trails (HMAC Signing)

To truly comply with enterprise regulations (like HIPAA, SOC2, FDA GxP, SEC/FINRA), an audit log is not enough—you must prove mathematically that the log has not been tampered with.

Lár v1.5.1 introduced **Cryptographic Signatures** for the audit log. By passing an `hmac_secret` (e.g., from AWS KMS or HashiCorp Vault) to the `GraphExecutor`, the engine will sign the final JSON execution trace using HMAC-SHA256. 

```python
from lar import GraphExecutor

# Instantiating the executor with an HMAC secret turns on Cryptographic Auditing
executor = GraphExecutor(
    log_dir="secure_logs", 
    hmac_secret="your_enterprise_secret_key"
)
```

**How to verify (For Auditors):**
If a single character of the payload (like a node output, reasoning string, or token cost) is altered manually after execution, the signature verification will instantly fail. 

We provide a standalone verification script specifically for Compliance Officers to mathematically prove a log's authenticity:

**Step 1:** Locate the generated JSON audit log (e.g., `secure_logs/run_xyz.json`).
**Step 2:** Obtain the enterprise HMAC Secret Key used during the agent's execution.
**Step 3:** Run the verification script from your terminal:
```bash
python examples/compliance/11_verify_audit_log.py secure_logs/run_xyz.json your_enterprise_secret_key
```

**Outcome:** The script will output either `[+] VERIFICATION SUCCESSFUL` (authentic) or `[-] VERIFICATION FAILED` (tampered).

Lár includes four reference implementations to demonstrate this across different industries:
*   [8_hmac_audit_log.py](../examples/compliance/8_hmac_audit_log.py) (Basic usage)
*   [9_high_risk_trading_hmac.py](../examples/compliance/9_high_risk_trading_hmac.py) (Algorithmic Trading & FINRA)
*   [10_pharma_clinical_trials_hmac.py](../examples/compliance/10_pharma_clinical_trials_hmac.py) (Clinical Data Routing & FDA 21 CFR 11)
*   [11_verify_audit_log.py](../examples/compliance/11_verify_audit_log.py) (Standalone Auditor Script)

---

## Risk Mitigation: Dynamic Graphs (Self-Modifying Code)

Lár v1.1 introduces `DynamicNode`, which allows agents to rewrite their execution topology at runtime. While powerful, "Self-Modifying Code" is traditionally a compliance red flag.

**How Lár mitigates this risk:**

### 1. The "Code-as-Event" Principle
In Lár, a topological change is not a hidden internal state. It is an explicit **Event**.
- The `DynamicNode` outputs a JSON `GraphSpec`.
- This JSON spec is **logged physically** in the audit trail before execution.
- **Auditor Verification**: An auditor can replay the exact moment the agent decided to "add a research step" and verify *why* (based on the context).

### 2. Deterministic Topology Validation
The `TopologyValidator` is a **non-AI, deterministic guardrail**.
- **Allowlists**: It enforces that dynamically spawned nodes can ONLY use tools from a pre-approved list. An agent *cannot* invent a "Delete Database" tool if that function isn't in the Python allowlist.
- **Cycle Prevention**: It mathematically proves that the new subgraph is a DAG (Directed Acyclic Graph) or a bounded loop, preventing "Runaway Agent" scenarios.

### 3. Structural Constraints
The modifications are local. A `DynamicNode` can only swap *itself* or its immediate downstream path. It cannot rewrite history or modify upstream nodes, ensuring "Forward-Only" integrity.

---

## 4. GDPR: The Lethal Trifecta (AEPD Rule of 2)
**Requirement**: The Spanish DPA (AEPD, Feb 2026) mandated that an agent must not simultaneously combine all three of: untrusted input, sensitive data access, and autonomous action affecting individuals — without human oversight.

**Lár Solution**: `LethalTrifectaGuard`

A runtime pre-execution guard configured with three predicate functions (one per leg). Before any `ToolNode` executes, the guard evaluates all three legs against the live `GraphState`. If all three are simultaneously active and no `HumanJuryNode` has recorded a decision upstream (checked via a configurable state key), the guard raises `LethalTrifectaError` and blocks the action, writing a full trifecta evaluation report to state for the audit trail.

```python
from lar.compliance import LethalTrifectaGuard, LethalTrifectaError

guard = LethalTrifectaGuard(
    untrusted_input_fn=lambda s: s.get("user_query") is not None,
    sensitive_data_fn=lambda s: s.get("patient_health_data") is not None,
    autonomous_action_fn=lambda s: True,
    human_approval_state_key="jury_decision",
)
guard.check(state, action_label="update_patient_record")
```

---

## 5. Articles 12 & 14: The "Fourth Tier" — Authority Records
**Requirement**: The EU AI Act paper (Section 9, Finding 10) identifies that all current governance tooling lacks a "fourth tier" — infrastructure that maintains immutable, action-level records of **who** exercised authority, in **what role**, with **what rationale**, at **what risk score**.

**Lár Solution**: `AuthorityLedger` + upgraded `HumanJuryNode`

Attach an `AuthorityLedger` to any `HumanJuryNode`. On every human decision, the node captures stakeholder identity, role, rationale (prompted at runtime), the upstream `RiskScorerNode` score, and a UTC timestamp into a signed record. The full ledger is saved as HMAC-SHA256 signed JSON alongside the `AuditLogger` output — completing the evidence chain: **action proposal → risk assessment → human determination → execution outcome**.

```python
from lar.compliance import AuthorityLedger
from lar import HumanJuryNode

ledger = AuthorityLedger(hmac_secret="your-secret")

jury_node = HumanJuryNode(
    prompt="Approve AI-proposed diagnosis?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    authority_ledger=ledger,
    stakeholder_id="dr.smith@hospital.org",
    stakeholder_role="Attending Physician",
    action_description="AI diagnosis — update patient record",
    risk_score_key="risk_score",
)
```

---

## Summary for Auditors

| Feature | Lár Implementation | Compliance Value |
| :--- | :--- | :--- |
| **Determinism** | State Machines vs. Loops | Eliminates "Runaway Agent" risk. |
| **Observability** | JSON Flight Recorder | Meets Art. 12 (Recording). |
| **Control** | Standard HIL Patterns | Meets Art. 14 (Oversight). |
| **Privacy** | Local/Air-Gapped Capable | Meets GDPR / Data Sovereignty. |
| **Trifecta Guard** | Runtime AEPD enforcement | Meets GDPR Art. 5, Art. 14 (AEPD Rule of 2). |
| **Authority Records** | `AuthorityLedger` | Closes the "Fourth Tier" gap — Art. 12/14 action-level evidence chain. |
