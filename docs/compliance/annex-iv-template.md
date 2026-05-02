# EU AI Act — Annex IV Technical Documentation Template

> **Instructions for the Provider (You):**
> Under the EU AI Act (Article 11), the legal "Provider" (the organisation placing the High-Risk AI System on the market) must draw up technical documentation in accordance with Annex IV *before* conformity assessment.
> 
> **Lár generates the architectural and action-inventory evidence for this document automatically.** You must fill in the business, data, and testing details.

---

## 1. General Description of the AI System

### 1.1 Provider Information
- **Name:** [Your Company Name]
- **Address:** [Your Address]
- **Contact:** [Compliance Officer Email]

### 1.2 System Identification
- **System Name/Version:** [e.g., Credit-Decision-Agent v1.2]
- **Intended Purpose:** [e.g., To assess the creditworthiness of SME loan applicants based on historical financial data and current debt obligations.]
- **EU AI Act High-Risk Category:** [e.g., Annex III, Section 5(b) - Evaluating creditworthiness]

### 1.3 Architecture and Logic (Lár Framework)
This system is orchestrated using the **Lár Framework**. It operates as a deterministic Directed Acyclic Graph (DAG) rather than an unconstrained autonomous loop.

- **System Topology:** [Provide a high-level flowchart or Mermaid diagram of your Lár graph]
- **Pre-trained Models Used:** [e.g., OpenAI `gpt-4o`, Anthropic `claude-3-opus`, Meta `Llama-3`]
- **Oversight Architecture:** The system uses Lár's `RiskScorerNode` to enforce commensurate human-in-the-loop oversight.

---

## 2. Action Inventory & Capabilities (Auto-Generated)

> **Instructions:** Run `python your_app.py --generate-manifest` (using Lár's `ComplianceManifestGenerator`). Copy the contents of `compliance_manifest.json` or the resulting markdown report and paste it here.

[PASTE LÁR MANIFEST HERE]

*This section details every external API call, database modification, and tool the agent is technically capable of invoking, proving that the system's operational envelope is strictly defined and bounded.*

---

## 3. Data Governance (Article 10)

### 3.1 Training / Fine-Tuning Data
> **Instructions:** If you fine-tuned a model, describe the datasets here. If using an off-the-shelf foundation model, reference the model provider's model card.

- **Data Sources:** [e.g., Public SME financial records 2015-2023]
- **Data Preparation:** [e.g., Deduplication, PII stripping via Presidio]

### 3.2 Inference Data & PII Handling
- **Input Data:** [e.g., User-provided PDF financial statements]
- **Data Minimisation:** The system utilizes Lár's `PIIRedactionEngine` to strip sensitive fields (e.g., SSN, health markers) before cryptographic logging, ensuring compliance with GDPR Art. 17.

---

## 4. Human Oversight & Risk Management (Article 14)

### 4.1 "Rule of 2" (Lethal Trifecta Guard)
The system employs Lár's `LethalTrifectaGuard` at runtime. The system will **hard-block** any action that simultaneously combines:
1. Untrusted input
2. Sensitive personal data
3. Autonomous action affecting individuals
...unless prior human approval (via a `HumanJuryNode`) has been cryptographically recorded for the current execution trace.

### 4.2 The "Fourth Tier" Authority Ledger
Every high-risk decision escalating to a human is recorded in the **Authority Ledger** (`authority_ledger.json`). This logs the stakeholder identity, role, rationale, and exact timestamp of the intervention.

---

## 5. Accuracy, Robustness, and Cybersecurity (Article 15)

### 5.1 Systemic Risk Mitigation (State Isolation)
Where parallel agentic workflows are used, the system implements Lár's `BatchNode`. Parallel threads operate on perfectly isolated (deep-copied) state objects to prevent hallucination contagion between concurrent reasoners.

### 5.2 Metacognitive Boundaries
Where the system generates its own sub-graphs (`DynamicNode`), the `TopologyValidator` enforces a strict cycle-detection algorithm and tool allowlist. The system's action capabilities cannot expand at runtime beyond the inventory declared in Section 2.

### 5.3 Performance Metrics
- **Validation Set Accuracy:** [e.g., 94.2% agreement with expert human underwriters]
- **Drift Monitoring:** The system uses Lár's `RuntimeStateVersioner` to detect structural modifications to the tool catalogue at runtime.

---

## 6. Record Keeping (Article 12)

The system automatically generates a **Causal Trace** for every execution. 
- **Storage Location:** `[e.g., AWS S3 bucket /secure-audit-logs/]`
- **Retention Period:** `[e.g., 5 years]`
- **Integrity:** Every log is cryptographically signed using HMAC-SHA256 by the Lár `AuditLogger`. The prompt, system instruction, and exact memory modifications (`state_diff`) are immutably bound to the signature.

---

**Signed by Provider:**

___________________________  
[Name, Title]  
[Date]
