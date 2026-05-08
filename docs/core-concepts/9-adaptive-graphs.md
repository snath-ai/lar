# Adaptive Graphs

Most agent pipelines have a fixed structure defined at development time. Adaptive graphs allow part of that structure to be determined at execution time — specifically, when the number, type, or sequence of processing nodes depends on runtime inputs.

This is implemented via `AdaptiveNode` and `TopologyValidator`.

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

## See Also

- [AdaptiveNode API](../api-reference/dynamicnode.md)
- [TopologyValidator API](../api-reference/topologyvalidator.md)
- [EU AI Act Deep Dive](../compliance/eu-ai-act-deep-dive.md)
