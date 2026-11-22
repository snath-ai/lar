# Security & Compliance

Lár is designed to be the "Glass Box" alternative to "Black Box" agent frameworks. 
For enterprise deployments in regulated industries (FinTech, Healthcare, Defense), we prioritize **determinism**, **auditability**, and **air-gap capability**.

---

## 1. Security By Design

### A. Tamper-evident audit logs
Every run writes two artifacts to `lar_logs/` (directory `0700`, files `0600`):

*   `run_<id>.chain.jsonl`: one line per step, written and `fsync`'d **as each step completes**. Every line carries `prev_hash`, `entry_hash` (SHA-256 over the previous hash and the entry) and, if you set `hmac_secret`, an HMAC. Editing, deleting or reordering a line breaks the chain. A hard crash leaves every completed step on disk. If a step cannot be written, the run stops with `AuditWriteError` (fail closed).
*   `run_<id>.json`: the end-of-run summary, signed with HMAC-SHA256 and bound to the chain via `chain.head`.

Check them with `AuditLogger.verify_chain(...)` and `AuditLogger.verify_signature(...)` (constant-time comparison); `AuthorityLedger.verify(...)` does the same for the human-decision ledger.

**What this does *not* protect against.** The HMAC key is symmetric and is held by the process being audited, so anyone who controls that process or has the key can rewrite history and re-sign it. For stronger guarantees, ship `chain.head` to an external write-once store, or sign with an asymmetric key held in a KMS/HSM. The logs record what ran; they are **not** by themselves a 21 CFR Part 11 or EU AI Act conformity claim.

### B. Data sovereignty
*   Lár's own code makes **no network calls** other than the LLM calls you configure (via LiteLLM) and contains no telemetry. Third-party dependencies (including LiteLLM) were not audited for their own network behaviour; review them for your threat model.
*   Switch from `gpt-4` to a local `ollama/...` model in one line if prompts must not leave your network.
*   Prompts and state can contain personal data. Use `PIIRedactionEngine` on the logger (key-based, known-value and e-mail/IBAN/SSN pattern scrubbing; it is heuristic and does not catch every name or address). Checkpoints hold the **full** run state in clear text; protect that directory like a database. The console no longer echoes prompts unless `LLMNode(console_prompt_preview=True)`.

### C. Fail-closed human oversight
*   `HumanJuryNode` with no TTY and no `human_decision_provider` **halts**; it never picks an answer for you. Auto-selection exists only if you explicitly configure `automation_boundary={"<type>": "auto_first_choice"}`.
*   A decision does not stop anything unless the graph routes on it: use `decision_routes={"reject": None}` (or a cleanup node). `LethalTrifectaGuard` accepts only an approving decision.
*   `resume_human_decision` validates the decision against the node's choices, can be bound to your own authorisation check via `authorize=`, and claims the case exactly once. Lár does **not** authenticate reviewers; pass the identity your own auth layer verified.

### D. Heuristic guards are not classifiers
`PromptInjectionGuard`, `BiasFilterNode` and `ProhibitedPracticeGuard` are lightweight keyword/regex checks (see `examples/compliance/2_security_firewall.py`). They reduce obvious risk and produce evidence; they are easy to evade and will flag some legitimate text. Do not present a clean pass as compliance.

---

## 2. Supported Versions

Security patches and bug fixes are applied to the `latest minor release` of the Lár Engine framework.

| Status      | Version Format                               | Security Support                                         |
|-------------|-----------------------------------------------|-----------------------------------------------------------|
| Supported   | Latest Minor Release (e.g., 1.0.x)            | Full patches and critical bug fixes are provided.         |
| Unsupported | Previous Minor Releases (e.g., 0.x.x)         | No new security patches will be issued. Users should upgrade immediately. |

---

## 3. Reporting a Vulnerability

We take the security of the *Lár Engine* framework and its users seriously. If you discover a vulnerability, we ask that you follow the process of **responsible disclosure**.

- **Reporting Channel**: Please report vulnerabilities exclusively via email to: [**axdithya@snath.ai**](mailto:axdithya@snath.ai) or [**vinay@snath.ai**](mailto:vinay@snath.ai)
- **Response Time**: We commit to acknowledging receipt of your email within 24 hours and providing an initial assessment of the vulnerability within 48 hours.
- **Public Disclosure**: **Do not open public GitHub Issues, Pull Requests, or discuss vulnerabilities on public forums (e.g., social media or Discord)**. Public disclosure before a fix is released endangers all users.