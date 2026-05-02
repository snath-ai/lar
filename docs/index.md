
# **Ready to build Auditable AI Agents**
 


**Lár** (Irish for "core" or "center") is the open source standard for **Deterministic, Auditable, and Air-Gap Capable** AI agents, powered by **LiteLLM**.

It is a **"define-by-run"** framework that acts as a **Flight Recorder** for your agent, creating a complete audit trail for every single step.

!!! info "Not a Wrapper"
    **Lár is NOT a wrapper.**
    It is a standalone, ground-up engine designed for reliability. It does not wrap LangChain, OpenAI Swarm, or any other library. It is pure, dependency-lite Python code optimized for "Code-as-Graph" execution.

## The "Black Box" Problem

You are a developer launching a **mission-critical AI agent**. It works on your machine, but in production, it fails.
You don't know **why**, **where**, or **how much** it cost. You just get a 100-line stack trace from a "magic" framework.

## The "Glass Box" Solution

**Lár removes the magic.**

It is a simple engine that runs **one node at a time**, logging every single step to a forensic **Flight Recorder**.

This means you get:
1.  **Instant Debugging**: See the exact node and error that caused the crash.
2.  **Free Auditing**: A complete history of every decision and token cost, built-in by default.
3.  **Total Control**: Build deterministic "assembly lines," not chaotic chat rooms.

> *"This demonstrates that for a graph without randomness or external model variability, Lár executes deterministically and produces identical state traces."*

*Stop guessing. Start building agents you can trust.*

## What's New in v1.4.1 (Feb 2026)?

**Reasoning Models (System 2) are now first-class citizens.**
Lár supports **DeepSeek R1**, **OpenAI o1**, and **Liquid Thinking** out of the box.

*   **Audit Logic:** Captures "hidden" reasoning traces into metadata.
*   **Clean State:** delivers only the final answer to your downstream nodes.
*   **Robustness:** Handles malformed tags from local models.

[Read the Reasoning Models Guide](core-concepts/5-reasoning-models.md)


## 🇪🇺 EU AI Act Ready (August 2026 Enforcement)

Lár is the first agentic framework to ship with a complete, production-ready **Compliance Backbone**. It provides all 12 primitives required to pass an EU AI Act conformity assessment out of the box, including:

*   **Immutable Audit Trails (Art. 12)**: Cryptographically signed causal traces.
*   **Action-Level Authority Ledger (Art. 14)**: The "Fourth Tier" of human oversight tracking.
*   **Rule of 2 Enforcement (GDPR Art. 5)**: Belt-and-suspenders runtime blocking (`LethalTrifectaGuard`).
*   **Automated Annex IV Manifests (Art. 11)**: Auto-generated static inventory of your agent's capabilities.

[Read the EU AI Act Deep Dive](compliance/eu-ai-act-deep-dive.md) | [Explore the Enterprise Reference Implementation](compliance/enterprise-reference.md)

!!! warning "Legal Disclaimer"
    Lár is open-source software infrastructure, not legal or compliance advice. Using Lár does not automatically guarantee compliance with the EU AI Act, GDPR, HIPAA, or any other regulation. Organizations are solely responsible for ensuring their AI systems undergo proper legal review and conformity assessments.

## Demos & Examples

Learn by building with our ready-made demos:

*   **[The Validation Suite](case-studies/validation-suite.md)**: Three "Kitchen Sink" executable scripts proving Deterministic routing and Fractal Agency safety.
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