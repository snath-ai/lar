<p align="center">
  <img src="https://raw.githubusercontent.com/snath-ai/.github/main/assets/lar-logo.png" width="80" alt="Lár Logo" />
</p>
<p align="center"><em>Lár: The PyTorch for Agents — The First EU AI Act-Ready Agent Execution Engine</em></p>
<p align="center">
  <a href="https://pypi.org/project/lar-engine/">
    <img alt="PyPI - Version" src="https://img.shields.io/pypi/v/lar-engine?style=for-the-badge&color=blue">
  </a>
  <a href="https://pypi.org/project/lar-engine/">
    <img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/lar-engine?style=for-the-badge&color=blueviolet">
  </a>
  <a href="https://docs.snath.ai/compliance/eu-ai-act-deep-dive/">
    <img alt="EU AI Act Ready" src="https://img.shields.io/badge/EU%20AI%20Act-Ready%20Aug%202026-green?style=for-the-badge">
  </a>
  <a href="https://github.com/sponsors/axdithyaxo">
    <img alt="Sponsor" src="https://img.shields.io/badge/Support-GitHub%20Sponsors-pink?style=for-the-badge&logo=github">
  </a>
</p>

# Lár — The First EU AI Act-Ready Agent Execution Engine

The EU AI Act enforcement deadline is August 2026. Teams building AI agents in finance, healthcare, legal, and enterprise need to prove to regulators exactly what their agent did, why, and what it cost — on every run. Existing frameworks cannot do this. Lár can.

Lár is a ground-up agent execution engine where **auditability is structural, not an add-on**. Every design decision — deterministic graphs, step-level state diffs, cryptographic audit trails, topology validation, human oversight primitives — exists to satisfy EU AI Act requirements out of the box.

> [!NOTE]
> **Lár is NOT a wrapper.** It does not wrap LangChain, OpenAI Swarm, or any other library. It is a standalone, dependency-lite Python engine optimized for "Code-as-Graph" execution.

---

## The 13 EU AI Act Compliance Primitives

Lár ships a complete **Enterprise Compliance Backbone** — all 13 primitives required for a conformity assessment under Nannini et al. (2026), the definitive compliance architecture paper for AI agents under EU law:

| Article | Requirement | Lár Primitive |
| :--- | :--- | :--- |
| **Art. 12** | Causal audit logging | `GraphExecutor` → HMAC-SHA256 signed JSON trace |
| **Art. 14** | Human oversight interrupt | `HumanJuryNode` + `AuthorityLedger` (Fourth Tier) |
| **Art. 3(23)** | Substantial modification guard | `AdaptiveNode` + `TopologyValidator` + `RuntimeStateVersioner` |
| **Art. 9** | Risk management gate | `RiskScorerNode` + `PolicyRegistry` |
| **Art. 15(4)** | JIT privilege minimisation | `CredentialVault` (NHI provisioning) |
| **GDPR Art. 17** | PII redaction before signing | `PIIRedactionEngine` |
| **Art. 50(2)** | Synthetic content marking | `SyntheticMarkerNode` |
| **prEN 18283** | Runtime bias detection | `BiasFilterNode` |
| **Art. 14 (fractal)** | Meaningful HITL in parallel agents — per-branch evidence before consolidation | `BranchTriageNode` |
| **AEPD Rule of 2** | Lethal trifecta block | `LethalTrifectaGuard` |
| **Art. 13** | Transparency disclosure | `TransparencyEngine` |
| **Step 9** | External action inventory | `ComplianceManifestGenerator` |
| **Art. 12/14** | Stakeholder authority record | `AuthorityLedger` |

**[Read the EU AI Act Deep Dive →](https://docs.snath.ai/compliance/eu-ai-act-deep-dive/)** | **[Nannini et al. (2026) Full Mapping →](https://docs.snath.ai/compliance/paper-compliance-mapping/)**

---

## See It Running: The Finance Showcase

One command runs a live SME credit decision through the compliance primitives and produces three HMAC-signed audit artefacts:

```bash
python examples/compliance/22_eu_ai_act_finance_showcase.py
```

| Step | Node | Outcome | State Changes |
| :--- | :--- | :--- | :--- |
| 0 | `FunctionalNode` (CredentialVault) | ✅ success | `+ jit_token_present = True` |
| 1 | `LLMNode` (credit risk analysis) | ✅ success | `+ ai_output` (170 tokens) |
| 2 | `FunctionalNode` (JSON parse) | ✅ success | `+ recommendation, model_confidence, risk_level` |
| 3 | `RiskScorerNode` | ✅ success | `+ computed_oversight_level` |
| 4 | `HumanJuryNode` (Risk Officer gate) | ✅ success | `+ jury_decision = "approve"` |
| 5 | `FunctionalNode` (LethalTrifecta + Transparency) | ✅ success | `+ _trifecta_check`, `~ drift_report` |
| 6 | `SyntheticMarkerNode` | ✅ success | `+ final_output` (AI-disclaimed) |

Every step produces a real Article 12 causal trace, a real Article 14 AuthorityLedger record, and a real Step 9 action inventory — all HMAC-SHA256 signed. PII is stripped before signing.

> **This is the difference.** Every step, every key written, every node that touched state — recorded. No guesswork, no external tooling required.

**[Full showcase breakdown — execution trace, real JSON artefacts, 12-step coverage map →](https://docs.snath.ai/compliance/finance-showcase/)**

> **Open-source vs. enterprise:** All 13 compliance primitives (`BranchTriageNode`, `BiasFilterNode`, `RiskScorerNode`, `CredentialVault`, etc.) are in `lar.compliance` and fully open-source under Apache 2.0. The finance showcase uses `build_and_run` from `lar.enterprise`, a convenience wrapper in the enterprise tier. Open-source users assemble the same pipeline from primitives — the step-by-step guide walks you through it: **[Build a Compliant Agent from Scratch →](https://docs.snath.ai/guides/build-compliant-agent/)**

---

## How It Works: The "Glass Box"

Lár runs **one node at a time**, yielding a structured audit entry after every step. The execution model is a Python generator — each yield contains the state before, the state diff, token usage, the rendered prompt, and the outcome.

This means:
1. **Instant Debugging**: The exact node that failed, the exact data it received, the exact error — all in the log.
2. **Built-in Auditing**: A complete, immutable history of every decision and token cost, by default, on every run.
3. **Deterministic Control**: Explicit graphs, not probabilistic chat rooms. The same input produces the same execution trace.

### Why Lár vs. LangChain / CrewAI

| Feature | Black Box (LangChain / CrewAI) | Glass Box (Lár) |
| :--- | :--- | :--- |
| **Debugging** | 100-line stack trace from inside `AgentExecutor`. Guess what went wrong. | Exact node, exact error, exact state — in the log. |
| **Auditability** | External paid tool (LangSmith) required. | Built-in. The `GraphExecutor` flight log is the audit trail. |
| **Multi-Agent** | "Chat room" — no guaranteed order, loops possible. | Deterministic assembly line — you define the exact path. |
| **Compliance** | None. No EU AI Act primitives. | 13 compliance primitives, cryptographic logs, Art. 14 oversight. |
| **Cost** | LLM call on every routing step. | Code-based routing — $0.00/route. |
| **Scale** | Crashes at 25 steps (recursion limit). | 60+ node graphs run to completion. |
| **Crash Recovery** | LLM router may branch differently on retry — "resume" is actually a new run. | Pure Python routers are deterministic. Same state in, same path out. Resumption is exact. |
| **Core Philosophy** | Sells "Magic." | Sells "Trust." |

LangGraph crashes at Step 25 on a 60-node graph:
```text
CRASH CONFIRMED: Recursion limit of 25 reached without hitting a stop condition.
LangGraph Engine stopped execution due to Recursion Limit.
```
See: [`examples/comparisons/langchain_swarm_fail.py`](examples/comparisons/langchain_swarm_fail.py)

---

## Build a Compliant Agent from Scratch

New to Lár? The step-by-step guide walks you through wiring every compliance primitive — from credential vault to HMAC-signed audit artefacts — starting from a blank file. Written for both engineers and AI assistants.

**[Read the guide →](https://docs.snath.ai/guides/build-compliant-agent/)** | **[Live showcase →](https://docs.snath.ai/compliance/finance-showcase/)** | **[Continuously Running Agents →](https://docs.snath.ai/guides/continuous-operation/)**

---

## Installation

```bash
pip install lar-engine
```

Or from source:

```bash
git clone https://github.com/snath-ai/lar.git
cd lar
poetry install
```

Create a `.env` file with your model API keys:

```bash
GEMINI_API_KEY="..."
OPENAI_API_KEY="..."
ANTHROPIC_API_KEY="..."
```

---

## Quick Start

```bash
pip install lar-engine
lar new agent my-bot
cd my-bot
python agent.py
```

### The `@node` Decorator (Low Code)

```python
from lar import node, GraphExecutor

@node(output_key="summary")
def summarize_text(state):
    text = state["text"]
    return my_llm.generate(text)
```

### A Full Agent in 10 Lines

```python
from lar import LLMNode, RouterNode, GraphExecutor

classify = LLMNode(model_name="gpt-4o", prompt_template="Classify: {input}", output_key="category")
route = RouterNode(decision_function=lambda s: s.get("category"), path_map={"A": node_a, "B": node_b})
classify.next_node = route

executor = GraphExecutor()
for step in executor.run_step_by_step(classify, {"input": "Hello"}):
    print(f"Step {step['step']} ({step['node']}): {step['outcome']}")
```

---

## Core Primitives

| Primitive | What it does |
| :--- | :--- |
| `LLMNode` | Calls any model via LiteLLM. Built-in exponential backoff, token logging, budget enforcement. |
| `RouterNode` | Deterministic `if/else` branching via a Python `decision_function`. |
| `ToolNode` | Runs any Python function. Separate `next_node` / `error_node` paths. |
| `BatchNode` | Fan-out / fan-in parallelism. Each thread gets an isolated `copy.deepcopy` of state. |
| `ReduceNode` | Summarises multi-agent outputs and deletes raw keys — explicit memory compression. |
| `AdaptiveNode` | Runtime graph composition: LLM generates a `GraphSpec` → `TopologyValidator` validates → injects subgraph. |
| `HumanJuryNode` | Art. 14 mandatory interrupt. Blocks execution for human approval. Produces signed `AuthorityRecord`. |
| `ClearErrorNode` | Resets `last_error` to `None`. Required for deterministic self-correction loops. |
| `@node` decorator | Converts any Python function into a Lár node. |

---

## Universal Model Support

Lár is built on **LiteLLM** — switch providers by changing one string. Zero refactoring.

```python
# Cloud
node = LLMNode(model_name="gpt-4o", ...)
node = LLMNode(model_name="gemini/gemini-2.5-pro", ...)
node = LLMNode(model_name="claude-opus-4-6", ...)

# Local (Ollama)
node = LLMNode(model_name="ollama/phi4", ...)
node = LLMNode(model_name="ollama/deepseek-r1:7b", ...)
```

**[Read the Full LiteLLM Setup Guide →](https://docs.snath.ai/guides/litellm_setup/)**

---

## Reasoning Models (System 2 Support)

Native support for **DeepSeek R1**, **OpenAI o1**, and **Liquid**. `<think>` tags are first-class citizens — extracted and saved to `run_metadata`, keeping the main context window clean.

```python
node = LLMNode(
    model_name="ollama/deepseek-r1:7b",
    prompt_template="Solve: {puzzle}",
    output_key="answer"
)
# state['answer'] = "The answer is 42."
# log['metadata']['reasoning_content'] = "<think>First, I calculate...</think>"
```

---

## Resumable Graphs

Most frameworks cannot reliably resume a crashed execution — not because the feature is missing, but because their routers are probabilistic. On retry, the LLM may branch differently. The "resume" is actually a new run that happens to start with the same input.

Lár's routers are pure Python functions. Same state in, same decision out — deterministically. When Lár resumes at Step 47, it takes exactly the path Step 47 would have taken. The resumption is exact, not approximate.

The `GraphExecutor` is a Python generator that yields after every node. `GraphState` is a plain dict — always serialisable, always decoupled from the engine. The causal trace written on every run is not just an audit log; every entry is a resumption checkpoint.

| Run | Steps Executed | Tokens Sent | Cost (GPT-4o) |
|:---|:---|:---|:---|
| **Lár — Resume** | Step 3 only | **302 tokens** | **$0.0006** |
| **Competitor — Retry** | Steps 0+1+3 | ~776 tokens | $0.0016 |

> At 10,000 runs/day with 40% transient failure rate → **$9.48/day saved.**

The same property powers `HumanJuryNode`: the graph halts before an irreversible action, the process can be killed, and when the human responds — hours later if needed — execution resumes from exactly that node with exactly that state. This is what EU AI Act Art. 14 requires in practice.

See: [`examples/patterns/9_resumable_graph.py`](examples/patterns/9_resumable_graph.py)

---

## Adaptive Graphs

When graph structure cannot be known at author-time, `AdaptiveNode` composes a validated subgraph at execution time.

- LLM generates a `GraphSpec` (JSON)
- `TopologyValidator` checks: cycle detection, tool allowlist, structural integrity
- Validated subgraph is injected into the live execution path
- Every spec is logged to the Causal Trace (Art. 3(23))

See: [`examples/adaptive/`](examples/adaptive/)

---

## Compliance & Safety

> [!IMPORTANT]
> **Who is the "Provider"?** Under the EU AI Act (Art. 3), Lár is a software component, not an AI system. The organisation deploying a high-risk agent is the legal **Provider**. Lár provides the 13 architectural primitives to generate the *evidence* (audit logs, manifests, oversight records) required for a conformity assessment.

> [!WARNING]
> **Legal Disclaimer:** Lár is open-source infrastructure, not legal advice. Using Lár does not automatically guarantee compliance. Organisations are solely responsible for legal review and conformity assessments.

**What Lár solves:**
- Cryptographic causal traces for every decision (Art. 12)
- Hardware-level routing to human approval before high-risk actions (Art. 14)
- Automated external action inventory for adjacent legislation (Step 9)

**What Lár cannot solve:**
- Model bias or unsuitability — if you plug in a biased model, Lár records the biased decision accurately; liability remains with the organisation
- Human negligence — a `HumanJuryNode` that is rubber-stamped will fail an audit for negligent oversight
- Data provenance — Lár cannot guarantee training data was legally acquired

---

## Cryptographic Audit Logs

```python
from lar import GraphExecutor

executor = GraphExecutor(
    log_dir="secure_logs",
    hmac_secret="your_enterprise_secret_key"
)
# Run your agent normally. Every log is HMAC-SHA256 signed.
```

Verify for auditors:
```bash
python examples/compliance/11_verify_audit_log.py secure_logs/run_xyz.json your_secret_key
# [+] VERIFICATION SUCCESSFUL  or  [-] VERIFICATION FAILED
```

Compliance pattern library:
- [`8_hmac_audit_log.py`](examples/compliance/8_hmac_audit_log.py) — Basic HMAC authentication
- [`9_high_risk_trading_hmac.py`](examples/compliance/9_high_risk_trading_hmac.py) — Algorithmic Trading / SEC
- [`10_pharma_clinical_trials_hmac.py`](examples/compliance/10_pharma_clinical_trials_hmac.py) — FDA 21 CFR Part 11
- [`11_verify_audit_log.py`](examples/compliance/11_verify_audit_log.py) — Standalone auditor script

---

## Example Library

#### 1. Basic Primitives (`examples/basic/`)
| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_simple_triage.py`](examples/basic/1_simple_triage.py)** | Classification & Linear Routing |
| **2** | **[`2_reward_code_agent.py`](examples/basic/2_reward_code_agent.py)** | Code-First Agent Logic |
| **3** | **[`3_support_helper_agent.py`](examples/basic/3_support_helper_agent.py)** | Lightweight Tool Assistant |
| **4** | **[`4_fastapi_server.py`](examples/basic/4_fastapi_server.py)** | FastAPI Wrapper (Deploy Anywhere) |

#### 2. Core Patterns (`examples/patterns/`)
| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_rag_researcher.py`](examples/patterns/1_rag_researcher.py)** | RAG (ToolNode) & State Merging |
| **2** | **[`2_self_correction.py`](examples/patterns/2_self_correction.py)** | "Judge" Pattern & Error Loops |
| **3** | **[`3_parallel_execution.py`](examples/patterns/3_parallel_execution.py)** | Fan-Out / Fan-In Aggregation |
| **4** | **[`4_structured_output.py`](examples/patterns/4_structured_output.py)** | Strict JSON Enforcement |
| **5** | **[`5_multi_agent_handoff.py`](examples/patterns/5_multi_agent_handoff.py)** | Multi-Agent Collaboration |
| **6** | **[`6_meta_prompt_optimizer.py`](examples/patterns/6_meta_prompt_optimizer.py)** | Prompt Optimisation (Iterative Refinement) |
| **7** | **[`7_integration_test.py`](examples/patterns/7_integration_test.py)** | Integration Builder (CoinCap) |
| **8** | **[`8_ab_tester.py`](examples/patterns/8_ab_tester.py)** | A/B Tester (Parallel Prompts) |
| **9** | **[`9_resumable_graph.py`](examples/patterns/9_resumable_graph.py)** | Time Traveller — Crash & Exact Resume |
| **10** | **[`10_resumable_cost_demo.py`](examples/patterns/10_resumable_cost_demo.py)** | Cost Demo — 302 vs 776 Tokens, $9.48/day Saved |
| **11** | **[`16_custom_logger_tracker.py`](examples/patterns/16_custom_logger_tracker.py)** | Advanced Observability |

#### 3. Reasoners & Comparisons (`examples/reasoning_models/`, `examples/comparisons/`)
| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_deepseek_r1.py`](examples/reasoning_models/1_deepseek_r1.py)** | Native `<think>` tag parsing |
| **2** | **[`2_openai_o1.py`](examples/reasoning_models/2_openai_o1.py)** | High-IQ O1 Planner Nodes |
| **3** | **[`3_liquid_thinking.py`](examples/reasoning_models/3_liquid_thinking.py)** | Fast Local Edge Inferencing |
| **4** | **[`langchain_swarm_fail.py`](examples/comparisons/langchain_swarm_fail.py)** | Proof of Context Crashes |
| **5** | **[`langchain_firewall_cost.py`](examples/comparisons/langchain_firewall_cost.py)** | API Cost Explosion (Firewall) |
| **6** | **[`langchain_tree_fail.py`](examples/comparisons/langchain_tree_fail.py)** | Agent Cycle Traps |

#### 4. Compliance & Safety (`examples/compliance/`)
| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_human_in_the_loop.py`](examples/compliance/1_human_in_the_loop.py)** | User Approval & Interrupts |
| **2** | **[`2_security_firewall.py`](examples/compliance/2_security_firewall.py)** | Blocking Jailbreaks with Code |
| **3** | **[`3_juried_layer.py`](examples/compliance/3_juried_layer.py)** | Proposer -> Jury -> Kernel |
| **4** | **[`4_access_control_agent.py`](examples/compliance/4_access_control_agent.py)** | **Flagship Access Control** |
| **5** | **[`5_context_contamination_test.py`](examples/compliance/5_context_contamination_test.py)** | Red Teaming: Social Engineering |
| **6** | **[`6_zombie_action_test.py`](examples/compliance/6_zombie_action_test.py)** | Red Teaming: Stale Authority |
| **7** | **[`7_hitl_agent.py`](examples/compliance/7_hitl_agent.py)** | Article 14 Compliance Node |
| **8** | **[`8_hmac_audit_log.py`](examples/compliance/8_hmac_audit_log.py)** | Immutable Cryptographic Logs |
| **9** | **[`9_high_risk_trading_hmac.py`](examples/compliance/9_high_risk_trading_hmac.py)** | Algorithmic Trading (SEC) |
| **10** | **[`10_pharma_clinical_trials_hmac.py`](examples/compliance/10_pharma_clinical_trials_hmac.py)** | FDA 21 CFR Part 11 Trial Logic |
| **11** | **[`11_verify_audit_log.py`](examples/compliance/11_verify_audit_log.py)** | Standalone Auditor Script |
| **12** | **[`12_post_market_monitoring.py`](examples/compliance/12_post_market_monitoring.py)** | Post-Market Monitoring (Art. 72) |
| **13** | **[`12_transparency_disclosure.py`](examples/compliance/12_transparency_disclosure.py)** | Transparency Engine (Art. 13) |
| **14** | **[`13_risk_scored_routing.py`](examples/compliance/13_risk_scored_routing.py)** | Risk-Scored Routing (Art. 14) |
| **15** | **[`14_runtime_drift_detection.py`](examples/compliance/14_runtime_drift_detection.py)** | Drift Detection (Art. 3(23)) |
| **16** | **[`15_jit_credential_vault.py`](examples/compliance/15_jit_credential_vault.py)** | JIT Credential Vault (Art. 15(4)) |
| **17** | **[`16_pii_redaction.py`](examples/compliance/16_pii_redaction.py)** | PII Redaction (GDPR Art. 17) |
| **18** | **[`17_causal_trace_logging.py`](examples/compliance/17_causal_trace_logging.py)** | Causal Trace Logging (Art. 12) |
| **19** | **[`18_synthetic_content_marking.py`](examples/compliance/18_synthetic_content_marking.py)** | Synthetic Content Marking (Art. 50) |
| **20** | **[`19_runtime_bias_detection.py`](examples/compliance/19_runtime_bias_detection.py)** | Bias Detection (prEN 18283) |
| **21** | **[`20_compliance_manifest.py`](examples/compliance/20_compliance_manifest.py)** | Compliance Manifest (Step 9) |
| **22** | **[`21_authority_and_trifecta.py`](examples/compliance/21_authority_and_trifecta.py)** | Rule of 2 Trifecta Guard |
| **23** | **[`22_eu_ai_act_finance_showcase.py`](examples/compliance/22_eu_ai_act_finance_showcase.py)** | **Full EU AI Act Pipeline Proof** |
| **24** | **[`23_fractal_compliance_showcase.py`](examples/compliance/23_fractal_compliance_showcase.py)** | **Fractal Agent — BatchNode + AdaptiveNode + Art. 14 Early-Exit HITL** |

#### 5. High Scale & Advanced (`examples/scale/`, `examples/advanced/`)
| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_corporate_swarm.py`](examples/scale/1_corporate_swarm.py)** | **Stress Test**: 60+ Node Graph |
| **2** | **[`2_mini_swarm_pruner.py`](examples/scale/2_mini_swarm_pruner.py)** | Dynamic Graph Pruning |
| **3** | **[`3_parallel_newsroom.py`](examples/scale/3_parallel_newsroom.py)** | True Parallelism (`BatchNode`) |
| **4** | **[`4_parallel_corporate_swarm.py`](examples/scale/4_parallel_corporate_swarm.py)** | Concurrent Branch Execution |
| **5** | **[`11_map_reduce_budget.py`](examples/advanced/11_map_reduce_budget.py)** | Memory Compression & Token Budgets |
| **6** | **[`fractal_polymath.py`](examples/advanced/fractal_polymath.py)** | Recursive Graph Composition (Nested AdaptiveNodes + Parallelism) |
| **7** | **[`13_world_model_jepa.py`](examples/advanced/13_world_model_jepa.py)** | Predictive World Models |

#### 6. Adaptive Execution (`examples/adaptive/`)
See the **[Adaptive Graphs Docs →](https://docs.snath.ai/core-concepts/9-adaptive-graphs)**

| # | Pattern | Concept |
| :---: | :--- | :--- |
| **1** | **[`1_dynamic_depth.py`](examples/adaptive/1_dynamic_depth.py)** | Adaptive Worker Count (1 Node vs N Nodes) |
| **2** | **[`2_tool_inventor.py`](examples/adaptive/2_tool_inventor.py)** | Runtime Code Generation (sandboxed executor) |
| **3** | **[`3_self_healing.py`](examples/adaptive/3_self_healing.py)** | Error Recovery Pipeline (validated recovery subgraph) |
| **4** | **[`4_adaptive_deep_dive.py`](examples/adaptive/4_adaptive_deep_dive.py)** | Structural Adaptation (topology determined at runtime) |
| **5** | **[`5_expert_summoner.py`](examples/adaptive/5_expert_summoner.py)** | Domain Subgraph Dispatch (pre-defined expert spec injection) |

---

## Showcase Projects

- **[snath-ai/DMN](https://github.com/snath-ai/DMN)** — A complete cognitive architecture built on Lár: bicameral mind (Fast/Slow), sleep cycles, episodic memory, catastrophic forgetting solved architecturally.
- **[snath-ai/Lar-JEPA](https://github.com/snath-ai/Lar-JEPA)** — Universal model routing: LLMs, JEPA world models, diffusion models as first-class routable nodes in the same graph.
- **[snath-ai/rag-demo](https://github.com/snath-ai/rag-demo)** — Self-correcting RAG agent with a local vector database.

---

## Agentic IDE Support

Lár is designed for **Cursor, Windsurf, and Antigravity**. Reference these files to make your IDE an expert Lár architect:

1. `@lar/IDE_MASTER_PROMPT.md` — strict typing rules and "Code-as-Graph" philosophy
2. `@lar/IDE_INTEGRATION_PROMPT.md` — generate production-ready API wrappers in seconds
3. `@lar/IDE_PROMPT_TEMPLATE.md` — fill in your agent's goal and ask the IDE to implement it

---

## Show Your Agents are Auditable

[![Glass Box Ready](https://img.shields.io/badge/Auditable-Glass%20Box%20Ready-54B848?style=flat&logo=checkmarx&logoColor=white)](https://docs.snath.ai)

```markdown
[![Glass Box Ready](https://img.shields.io/badge/Auditable-Glass%20Box%20Ready-54B848?style=flat&logo=checkmarx&logoColor=white)](https://docs.snath.ai)
```

---

## Author

**Lár** was created by **[Aadithya Vishnu Sajeev](https://github.com/axdithyaxo)**.

Lár is open-source. If this project helps you, consider supporting its development: [Sponsor on GitHub →](https://github.com/sponsors/axdithyaxo)

## Contributing

Read our **[Contribution Guidelines](CONTRIBUTING.md)** to report bugs, submit pull requests, and propose new features.

## License

**Lár** is licensed under the `Apache License 2.0`. Free to use in personal, academic, or commercial projects. Retain the `LICENSE` and `NOTICE` files in any distribution.
