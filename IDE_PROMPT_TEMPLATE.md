# Lár Agent Request Template

**Goal**: [Describe what the agent should do, e.g., "Analyze a PDF and extract financial tables"]

**Inputs**:
- [e.g., PDF File Path]
- [e.g., User Query]

**Tools Needed**:
- [e.g., PDF Parser]
- [e.g., Search Tool]

**Constraints**:
- [ ] Use `gemini-1.5-pro` (or `ollama/phi4:latest` for local/air-gapped) for reasoning.
- [ ] Output must be valid JSON matching the `TargetSchema`.
- [ ] **Forward Wiring**: Define all nodes with `next_node=None` first, then wire them together at the end.
- [ ] **EU AI Act Compliance**: If this graph performs high-risk actions, it MUST use `CredentialVault` for auth, `SupplierAgreementRegistry` for APIs, and route through an asynchronous `SuspendNode` + `HumanJuryNode` pattern.
- [ ] **HMAC State**: State must be cryptographically signed when suspended to disk.

---
**Instruction to IDE**:
Reference `@lar/IDE_MASTER_PROMPT.md` for the core Lár v2.2.0 coding standards, and `@lar/IDE_INTEGRATION_PROMPT.md` if adding a third-party SDK.
Generate the `lar` code for this agent in a single file named `agent.py`.
Include a verification block at the bottom to run it immediately.
