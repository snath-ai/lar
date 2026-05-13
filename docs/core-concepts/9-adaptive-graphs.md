# Adaptive Graphs

Most agent pipelines are hardcoded: every branch exists at development time, every case is anticipated upfront. `AdaptiveNode` breaks that constraint — the number, type, and sequence of processing nodes is determined at runtime based on what the agent actually receives.

## What this actually is

This is **not** metacognition. The agent is not reasoning about itself.

Here is what literally happens:

1. You pre-define a set of approved tools (Python functions)
2. At runtime, an LLM receives the live input and outputs a **JSON graph spec** — a description of which tools to run and in what order
3. `TopologyValidator` runs pure Python static analysis on that JSON — no LLM involved, no probabilities, hard pass/fail
4. If valid, Lár instantiates real Python node objects from the spec and injects them into the live execution path
5. The executor continues through the generated nodes — the LLM does not run again

The "adaptive" decision is a **one-time LLM call that produces a data structure**. Everything after that is deterministic Python.

**The bottleneck it eliminates:** You stop having to pre-build a branch for every possible input shape. A simple document gets 1 node. A complex financial contract gets 3 nodes in sequence. You define the tools and the rules — the agent decides the structure.

**Honest tradeoffs:**
- One extra LLM call per `AdaptiveNode` activation, before any work starts
- The LLM must output valid JSON every call — `TopologyValidator` rejects malformed specs and falls back, but tokens are spent
- Graph depth is unpredictable — cap it with Lár's node budget limits (`GraphExecutor(max_nodes=...)`)
- The LLM pattern-matches from your prompt description; it does not reason about what tools actually do

**The real unlock** is `AdaptiveNode` + `BatchNode`. The LLM can decide both how many workers to spawn *and* that they run in parallel — covering input complexity that would require a combinatorial explosion of static branches to replicate.

## When to Use Adaptive Graphs

Use `AdaptiveNode` when:
- Problem complexity varies and requires a different number of processing steps (e.g., 1 researcher vs. 3)
- You need to dispatch to a domain-specific subgraph based on query classification
- Error recovery requires a pipeline whose structure depends on the error type

Do not use `AdaptiveNode` when:
- Problem structure is known at development time — use a static graph
- A fully pre-defined execution path is required for security or compliance reasons
- Debugging simplicity is the priority — static graphs are easier to trace

## How It Works

```
AdaptiveNode.execute(state)
│
├── 1. Call LLM with prompt_template + context_keys
│       → LLM outputs JSON GraphSpec
│
├── 2. TopologyValidator.validate(spec)
│       → Cycle detection (Art. 3(23))
│       → Tool allowlist check (Art. 9)
│       → Structural integrity check
│       → SecurityError if invalid → fall through to next_node
│
├── 3. Instantiate nodes from spec
│
└── 4. Return entry node → GraphExecutor continues
        Spec logged to Causal Trace (Art. 12)
```

The audit trail never breaks. The generated spec is logged before any subgraph node executes. If validation fails, the rejection reason is also logged.

## Compliance

`AdaptiveNode` satisfies Art. 3(23) (Substantial Modification) requirements through `TopologyValidator`:

| TopologyValidator invariant | EU AI Act requirement |
|---|---|
| Cycle detection | Prevents unbounded execution (Art. 9 risk management) |
| Tool allowlist | Privilege minimisation — only approved actions (Art. 9) |
| Structural integrity | Ensures graph is well-formed before injection (Art. 3(23)) |
| Spec logged to Causal Trace | Full audit trail of every topological change (Art. 12) |

## Patterns

### 1. Adaptive Worker Count

Allocate processing resources proportional to query complexity:

```python
PROMPT = """
Query: "{query}"
If simple: compose 1 LLMNode.
If complex: compose 3 sequential LLMNodes.
Output JSON with nodes and entry_point.
"""

planner = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=PROMPT,
    validator=TopologyValidator(),
    context_keys=["query"]
)
```

See: `examples/adaptive/1_dynamic_depth.py`

### 2. Domain Subgraph Dispatch

Select a pre-defined expert subgraph based on query classification:

```python
PROMPT = """
Query domain: "{query}"
If legal: output the legal_expert spec.
If medical: output a single node saying "refer to specialist".
"""
# validator has pre-approved tools for each domain
```

See: `examples/adaptive/5_expert_summoner.py`

### 3. Error Recovery

Compose a recovery subgraph when a known failure type is detected:

```python
PROMPT = """
Error: "{last_error}"
Compose a recovery subgraph using: rotate_credentials, retry_connection.
"""
```

See: `examples/adaptive/3_self_healing.py`

### 4. Runtime Code Generation (Sandboxed)

Generate and execute code for novel computations. **Requires a sandboxed executor** (Docker, e2b, WebAssembly). Never execute LLM-generated code with full system access.

See: `examples/adaptive/2_tool_inventor.py`

## Security Checklist

| Risk | Mitigation |
|---|---|
| Infinite loops | TopologyValidator cycle detection |
| Unauthorised tool calls | TopologyValidator allowlist |
| Dangling node references | TopologyValidator structural check |
| Prompt injection via allowed tools | Sandbox code execution tools |
| Resource exhaustion | Limit max_nodes in validator (extend TopologyValidator) |

## Quick Start

```python
from lar import AdaptiveNode, TopologyValidator, GraphExecutor

def my_approved_tool(input: str) -> str:
    return f"processed: {input}"

validator = TopologyValidator(allowed_tools=[my_approved_tool])

node = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template="Design a subgraph for: {task}. Output JSON.",
    validator=validator,
    context_keys=["task"]
)

executor = GraphExecutor()
results = list(executor.run_step_by_step(node, {"task": "summarise this document"}))
```

## Compliance in Adaptive Graphs

The graph shape changes at runtime. The compliance guarantees don't.

**Every generated spec is logged before it executes.** The Causal Trace (Art. 12) records the full JSON spec, the `TopologyValidator` result, and every node execution within the subgraph — whether that subgraph was hardcoded or generated at runtime. An auditor can reconstruct the exact topology that ran from the log alone.

**The safety decision is never delegated to an LLM.** `TopologyValidator` is pure Python — same spec in, same result out, deterministically. The LLM proposes a graph; a non-probabilistic function decides if it is safe to run. This matters for Art. 3(23) (Substantial Modification): you can prove the validator's decision, not just assert it.

**All 13 compliance primitives work inside generated subgraphs.** If your spec includes an `LLMNode` that processes personal data, wire `PIIRedactionEngine` after it exactly as you would in a static graph. `HumanJuryNode` halts the generated subgraph the same way it halts any other. `BiasFilterNode`, `ProhibitedPracticeGuard`, `LethalTrifectaGuard` — all fire correctly regardless of whether the node containing them was hardcoded or generated.

**In fractal agents (parallel specialist sub-agents), add `BranchTriageNode`.** Without it, the human jury only sees a consolidated score — not which parallel branch triggered the alert. That is not meaningful oversight under Art. 14. See [Fractal Agents →](11-fractal-agency.md) for the full pattern.

```python
executor = GraphExecutor(
    hmac_secret=os.environ["HMAC_SECRET"],  # Signs the causal trace including all generated specs
    log_dir="/var/audit_logs"
)

validator = TopologyValidator(
    allowed_tools=[approved_tool_1, approved_tool_2],
    max_nodes=15,    # Rejects any spec with more than 15 nodes
)

adaptive = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=YOUR_PROMPT,
    validator=validator,
    max_depth=3,     # Prevents unbounded recursive nesting
)
```

## See Also

- [AdaptiveNode API](../api-reference/adaptivenode.md)
- [TopologyValidator API](../api-reference/topologyvalidator.md)
- [Fractal Agents — BatchNode + AdaptiveNode + BranchTriageNode →](11-fractal-agency.md)
- [EU AI Act Deep Dive](../compliance/eu-ai-act-deep-dive.md)
