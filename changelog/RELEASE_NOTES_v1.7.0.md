# Lár v1.7.0 Release Notes

## What's New

### 1. Enterprise Streaming & Structured JSON Capabilities (`LLMNode`)
`LLMNode` has received a major upgrade with enterprise-grade features seamlessly integrated into the LiteLLM backend.

* **Streaming Support**: Direct terminal streaming capability. When instantiated with `stream=True`, output is streamed chunk-by-chunk to `sys.stdout` while generating a cohesive `total_tokens` usage metric under the hood. 
* **Structured Output Support**: Easily ensure outputs match Pydantic schemas by passing `response_format=<PydanticModel>`.
* **Snath Cloud Hooks**: New parameters `fallbacks`, `caching`, and `success_callbacks` have been added to prepare for deep infrastructure observability hooks and integrations.

### 2. Precise Token Budget Merging (`BatchNode`)
* **Thread-Safe Budget Deductions**: State modifications executed in parallel across `BatchNode` threads now strictly compute delta token costs to avoid race-condition overwriting. The parent graph mathematically merges total budgets correctly from all worker nodes.

### 3. Compliance and Audit Trails (For Auditors)
* We have introduced a formal Verification Script (`examples/compliance/11_verify_audit_log.py`) directly for Compliance officers and auditors to authenticate JSON audit log files offline via `HMAC-SHA256` signatures to certify anti-tampering (Crucial for FDA/EU-AI Act adherence). Usage documentation has also been promoted to the `README.md`.

## Bug Fixes & Refactors
* Updated standard unit tests to correctly mock API generations for streaming branches and to ensure budget accuracy upon branch reconciliation.


