# Integrating Lár with an ISO 9001 / EU AI Act Quality Management System

The EU AI Act (Article 17) requires Providers of High-Risk AI systems to establish a **Quality Management System (QMS)**. 

If your organisation already has an ISO 9001 QMS, you do not need to start from scratch. The EU AI Act's QMS requirements map closely to ISO 9001, with specific additions for AI risk management and data governance.

**Lár is not a QMS.** Lár is the runtime engine that generates the *evidence records* required by your QMS. This guide explains how to pipe Lár's outputs into your existing corporate compliance processes.

---

## 1. Document & Record Control (ISO 9001 Clause 7.5)

Your QMS requires you to maintain documented information and retain evidence of system operation.

### How Lár provides the evidence:
Lár's `AuditLogger` outputs a JSON file for every single execution (e.g., `run_037c96e8.json`). 

**Integration Steps:**
1. Configure Lár to write logs to a secure, append-only location (e.g., AWS S3 with Object Lock).
2. Enable Lár's `hmac_secret` feature. 
3. Update your QMS Record Control Procedure to state: *"All AI execution traces are cryptographically signed at runtime using HMAC-SHA256 and stored in [S3 Bucket] with a 10-year retention period, satisfying EU AI Act Art. 12."*

---

## 2. Design and Development (ISO 9001 Clause 8.3)

Your QMS requires you to plan, control, and verify the design of your products. The EU AI Act requires a clear understanding of the system's capabilities.

### How Lár provides the evidence:
Lár provides the `ComplianceManifestGenerator`.

**Integration Steps:**
1. Integrate the manifest generator into your CI/CD pipeline (GitHub Actions / GitLab CI).
2. Require the pipeline to fail if the manifest detects a `HIGH` severity dynamic topology change that has not been approved.
3. Attach the generated `compliance_manifest.json` as an automated artifact to every Jira Release Ticket. 
4. Update your QMS Design Verification Procedure to state: *"For every major release, an automated action inventory (Manifest) is generated to verify the system's operational envelope remains bounded."*

---

## 3. Control of Nonconforming Outputs (ISO 9001 Clause 8.7)

Your QMS must prevent unintended use of nonconforming products. In AI, this means stopping catastrophic hallucinations or policy violations before they impact the real world.

### How Lár provides the evidence:
Lár provides the `LethalTrifectaGuard` and the `HumanJuryNode`.

**Integration Steps:**
1. Implement the `LethalTrifectaGuard` as a pre-execution hook on all `ToolNodes`.
2. When the guard blocks an action, it raises a `LethalTrifectaError`.
3. Catch this error and pipe it into your corporate IT Service Management tool (e.g., ServiceNow, Jira Service Desk) as a "Nonconformance Event."
4. Update your QMS: *"Runtime nonconformances (e.g., automated PII extraction without oversight) are mathematically blocked by the Lethal Trifecta Guard, generating an automatic nonconformance ticket for Root Cause Analysis."*

---

## 4. Performance Evaluation / Post-Market Monitoring (ISO 9001 Clause 9)

The EU AI Act (Article 72) mandates a Post-Market Monitoring (PMM) system. You must actively monitor the AI in the real world to detect continuous risks or performance degradation.

### How Lár provides the evidence:
Lár provides the `IncidentReporter` utility (see `examples/compliance/12_post_market_monitoring.py`).

**Integration Steps:**
1. Run the `IncidentReporter` on a cron job (e.g., weekly) over your `enterprise_audit/` log directory.
2. The reporter aggregates metrics: number of `CRITICAL` risk scores, frequency of `HumanJuryNode` rejections, and structural `DriftReport` flags.
3. Pipe the resulting JSON/Markdown report directly to your Compliance Officer or Management Review meeting.
4. Update your QMS: *"A weekly automated Post-Market Monitoring report aggregates runtime execution logs to detect concept drift, elevated risk scores, or an increase in human-in-the-loop rejection rates."*

---

## Summary of the Integration Pipeline

| Lár Primitive | Outputs To | QMS / Corporate System |
|:---|:---|:---|
| `AuditLogger` + `AuthorityLedger` | AWS S3 (Append-only) | ISO 9001 7.5 (Record Control) |
| `ComplianceManifestGenerator` | CI/CD Artifacts | ISO 9001 8.3 (Design Validation) |
| `LethalTrifectaGuard` Exception | Jira / ServiceNow | ISO 9001 8.7 (Nonconformance) |
| `IncidentReporter` | Email / Slack / PDF | ISO 9001 9.0 (Post-Market Monitoring) |
