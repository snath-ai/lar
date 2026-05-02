# Auditor's Guide: Inspecting Lár Agents

> **Audience**: Compliance Officers, Quality Assurance (QA), Notified Bodies, and external Auditors.
> **Scope**: This guide explains how to verify the behavior of a "High-Risk AI System" built with the Lár engine, in accordance with the **EU AI Act (2026)**.

---

## 1. The "Glass Box" Concept

Most AI systems are "Black Boxes"—a prompt goes in, and an answer comes out, with no visibility into the intermediate steps or causal logic.

**Lár is different.** It is a "Glass Box." 
Every Lár agent is a **Graph** (a deterministic flowchart) of explicit steps. 

As an auditor, you have the right to mathematically inspect the state changes and causal links between every step.

---

## 2. The Three Required Artifacts

For every execution of a Lár Enterprise agent, the system produces three critical compliance artifacts. You should request these from the engineering team for any conformity assessment or incident investigation.

### A. The Action Inventory (`compliance_manifest.json`)
*Regulatory Basis: Annex IV & Step 9 of the EU AI Act Compliance Workflow*

This is the map of *what could happen*. It is generated statically before the agent ever runs.

**What to look for:**
* **Tool Inventory**: An exhaustive list of every external API, database, and system the agent can touch.
* **Risk Classifications**: The predefined risk level (e.g., HIGH, CRITICAL) for each action.
* **JIT Constraints**: Validation that tools rely on Just-In-Time (`CredentialVault`) tokens, rather than static global API keys.

### B. The Causal Trace (`run_<uuid>.json`)
*Regulatory Basis: Article 12 (Record-Keeping)*

This is the map of *what actually happened*. Lár generates a **State-Diff Ledger**. It does not just dump logs; it records exactly what changed at every step, what prompt was used, and what reasoning trace was generated.

**Verification Steps:**
1. **Traceability**: Can you follow the `step` numbers sequentially?
2. **Causality**: Can you see the exact variable added to the state diff that caused a router to branch?
3. **Data Erasure**: Verify that Personally Identifiable Information (PII) was scrubbed by the `PIIRedactionEngine` before the log was finalized (to satisfy GDPR Art. 17).

### C. The Authority Ledger (`authority_ledger.json`)
*Regulatory Basis: Article 14 (Human Oversight)*

For high-risk decisions, Lár halts execution and requires a human stakeholder to approve or reject the action.

**What to look for:**
* **Who & Role**: E.g., `dr.smith@hospital.org` (Attending Physician).
* **Rationale**: Did the human provide a documented reason for their approval/rejection?
* **Rubber-Stamping**: Are approvals happening faster than a human could feasibly read the context?

---

## 3. Cryptographic Verification (HMAC-SHA256)

A log is only useful if it hasn't been tampered with. Lár natively signs the causal trace and the authority ledger using an enterprise secret key.

**How to Verify a Log's Authenticity:**
We provide a standalone verification script for auditors.

1. Obtain the generated JSON log (e.g., `run_037c96e8.json`).
2. Obtain the enterprise HMAC Secret Key from the engineering team.
3. Run the verification script:
   ```bash
   python examples/compliance/11_verify_audit_log.py run_037c96e8.json your_enterprise_secret_key
   ```
   **Outcome:** The script will output either `[+] VERIFICATION SUCCESSFUL` (authentic) or `[-] VERIFICATION FAILED` (tampered).

---

## 4. Common Failure Modes & Anti-Patterns

When reviewing an agent's architecture, look for these compliance violations:

* **The Hallucinating Jury**: Did the LLM attempt an action, but the human jury (`HumanJuryNode`) approved it without a stated rationale?
* **The Lethal Trifecta**: Did the system process untrusted input, access sensitive data, AND take autonomous action without hitting a `HumanJuryNode`? (The `LethalTrifectaGuard` should catch this).
* **Behavioral Drift**: Did the agent attempt to use a tool that wasn't declared in the `compliance_manifest.json`? (The `RuntimeStateVersioner` should flag this as a Substantial Modification under Art. 3(23)).
