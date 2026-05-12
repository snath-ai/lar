
# Lár — The PyTorch for Agents

**Lár** (Irish for "core" or "center") is the first agent execution engine built for regulated environments. Teams building AI agents in finance, healthcare, legal, and enterprise need a framework that can pass regulatory scrutiny — not just work in a demo. Lár makes auditability a structural property of the engine, not an add-on.

Every design decision — deterministic graphs, step-level state diffs, cryptographic audit trails, topology validation, human oversight primitives — exists to satisfy EU AI Act requirements out of the box.

!!! info "Not a Wrapper"
    **Lár is NOT a wrapper.**
    It is a standalone, ground-up engine. It does not wrap LangChain, OpenAI Swarm, or any other library. It is pure, dependency-lite Python code optimized for "Code-as-Graph" execution.

## Compliance by Design

Lár is the first agentic framework to ship with a complete, production-ready **Enterprise Compliance Backbone** — all 13 primitives required for EU AI Act conformity assessment:

| Primitive | EU AI Act Article |
|---|---|
| Cryptographically signed Causal Trace | Art. 12 — Record-Keeping |
| `HumanJuryNode` — deterministic oversight interrupt | Art. 14 — Human Oversight |
| `TopologyValidator` — cycle detection, tool allowlist | Art. 3(23) — Substantial Modification |
| `RiskScorerNode` + routing | Art. 9 — Risk Management |
| `LethalTrifectaGuard` | GDPR Art. 5 — Rule of 2 |
| `ComplianceManifest` (Annex IV auto-generation) | Art. 11 — Technical Documentation |
| `SyntheticMarkerNode` | Art. 50(2) — Synthetic Content Marking |
| `BiasFilter` | prEN 18283 — Bias Management |
| `CredentialVault` (JIT provisioning) | Art. 15(4) — Privilege Minimisation |
| `RuntimeStateVersioner` (drift detection) | Art. 3(23) — Substantial Modification |

**[Read the EU AI Act Deep Dive →](compliance/eu-ai-act-deep-dive.md)** | **[Enterprise Reference Implementation →](compliance/enterprise-reference.md)**

!!! warning "Legal Disclaimer"
    Lár is open-source software infrastructure, not legal or compliance advice. Using Lár does not automatically guarantee compliance with the EU AI Act, GDPR, HIPAA, or any other regulation. Organizations are solely responsible for ensuring their AI systems undergo proper legal review and conformity assessments.

## How It Works: The "Glass Box"

Lár runs **one node at a time**, logging every single step to a forensic **Flight Recorder**. The `GraphExecutor` is a Python generator — every node yields a structured audit entry: state before, state diff, token usage, rendered prompt, outcome.

1.  **Instant Debugging**: The exact node that failed, the exact data it received, the exact error — all in the log.
2.  **Built-in Auditing**: A complete, immutable history of every decision and token cost, by default, on every run.
3.  **Deterministic Control**: Explicit graphs, not probabilistic chat rooms.

> *"This demonstrates that for a graph without randomness or external model variability, Lár executes deterministically and produces identical state traces."*

## What's New in v1.4.1 (Feb 2026)?

**Reasoning Models (System 2) are now first-class citizens.**
Lár supports **DeepSeek R1**, **OpenAI o1**, and **Liquid Thinking** out of the box.

*   **Audit Logic:** Captures "hidden" reasoning traces into metadata.
*   **Clean State:** delivers only the final answer to your downstream nodes.
*   **Robustness:** Handles malformed tags from local models.

[Read the Reasoning Models Guide](core-concepts/5-reasoning-models.md)


## EU AI Act Ready (August 2026 Enforcement)

Lár is the first agentic framework to ship with a complete, production-ready **Compliance Backbone**. It provides all 13 primitives required to pass an EU AI Act conformity assessment out of the box, including:

*   **Immutable Audit Trails (Art. 12)**: Cryptographically signed causal traces.
*   **Action-Level Authority Ledger (Art. 14)**: The "Fourth Tier" of human oversight tracking.
*   **Rule of 2 Enforcement (GDPR Art. 5)**: Belt-and-suspenders runtime blocking (`LethalTrifectaGuard`).
*   **Automated Annex IV Manifests (Art. 11)**: Auto-generated static inventory of your agent's capabilities.

[Read the EU AI Act Deep Dive](compliance/eu-ai-act-deep-dive.md) | [Explore the Enterprise Reference Implementation](compliance/enterprise-reference.md)

## Demos & Examples

Learn by building with our ready-made demos:

*   **[The Validation Suite](case-studies/validation-suite.md)**: Three "Kitchen Sink" executable scripts proving deterministic routing and `TopologyValidator` safety guarantees under adversarial conditions.
*   **[DMN: The Showcase](https://github.com/snath-ai/DMN)**: A Cognitive Architecture that sleeps, dreams, and remembers.
*   **[Lar-JEPA: World Model Orchestrator](https://github.com/snath-ai/Lar-JEPA)**: A post-LLM conceptual testbed proving Lár can safely route abstract latent states from Predictive World Models.
*   **[RAG Agent Demo](https://github.com/snath-ai/rag-demo)**: A self-correcting RAG agent with local vector search.
*   **[Customer Support Swarm](https://github.com/snath-ai/customer-support-demo)**: A multi-agent orchestration pattern.
*   **[Pattern Library](core-concepts/4-core-patterns.md)**: 21+ robust engineering patterns (RAG, Swarms, Safety, etc).

## Power Your IDE (Cursor / Windsurf)

Make your IDE an expert Lár Architect with this **2-Step Workflow**:

1.  **Reference The Rules**: In your chat, type `@lar/IDE_MASTER_PROMPT.md`. This loads the strict typing rules.
2.  **Use The Template**: Fill out `@lar/IDE_PROMPT_TEMPLATE.md` with your agent requirements.

[Read the Full Guide](ide_setup.md)

## Ready for Production?

Lár is designed to be deployed as a standard Python library.
Read our **[Deployment Guide](guides/deployment.md)** to learn how to wrap your graph in **FastAPI** and deploy to AWS/Heroku.

Get Started in 3 Minutes [https://docs.snath.ai/getting-started/](https://docs.snath.ai/getting-started/)

## Author
**[Lár](https://github.com/snath-ai/lar)** was created by **[Aadithya Vishnu Sajeev](https://github.com/axdithyaxo)**.