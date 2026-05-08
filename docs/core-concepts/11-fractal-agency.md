# Recursive Graph Composition (v1.5+)

`AdaptiveNode` can be nested: a generated subgraph can itself contain `AdaptiveNode` instances, which compose further subgraphs at runtime. This allows problems that require multiple layers of specialisation to be handled without pre-defining every layer's structure at development time.

Safety rails propagate through every level of nesting — the `TopologyValidator` passed to the parent `AdaptiveNode` is inherited by all child `AdaptiveNode` instances in the generated spec.

## When to Use Nested Composition

Use nested `AdaptiveNode` when:
- A problem requires parallel specialised sub-pipelines, each with their own structure
- The number of specialised sub-pipelines is itself determined at runtime

A concrete example: a manager agent that receives a complex multi-disciplinary question, decides how many specialist sub-agents to spawn (and what kind), and then dispatches them in parallel via `BatchNode`.

## Architecture

```
AdaptiveNode (Manager)
│
├── Generates JSON spec containing BatchNode + child AdaptiveNodes
├── TopologyValidator validates the full spec
│
└── Injects subgraph:
    ├── BatchNode
    │   ├── Thread 1: AdaptiveNode (Specialist A)
    │   │   └── Generates + validates + injects its own subgraph
    │   └── Thread 2: AdaptiveNode (Specialist B)
    │       └── Generates + validates + injects its own subgraph
    └── LLMNode (Synthesiser)
```

## Validator Inheritance

The parent's `TopologyValidator` is passed to every child `AdaptiveNode` instantiated from the generated spec. This means:
- The same tool allowlist applies at every level
- Cycle detection runs on every nested spec independently
- A rejected spec at any level causes that branch to fall through to `next_node` without halting the rest of the graph

## Token Budget Propagation

When a `token_budget` is set in state, the budget is shared across all parallel branches. After `BatchNode` merges results, the total spend across all threads is reconciled mathematically:

```
budget_remaining = initial_budget - sum(spend_per_thread)
```

This prevents unbounded execution costs regardless of nesting depth.

## Example

See `examples/advanced/fractal_polymath.py` for a working example where a manager `AdaptiveNode` composes a `BatchNode` containing two specialist `AdaptiveNode` instances running in parallel threads.

```python
from lar.dynamic import AdaptiveNode, TopologyValidator
from lar import GraphExecutor

def run_python_code(code: str) -> str:
    # Sandboxed executor — Docker/e2b required in production
    ...

validator = TopologyValidator(allowed_tools=[run_python_code])

manager = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=manager_prompt,  # Asks LLM to design BatchNode + child AdaptiveNodes
    validator=validator,
    next_node=None
)

executor = GraphExecutor(log_dir="audit_logs")
list(executor.run_step_by_step(manager, {}))
```

## Compliance

Every level of nesting produces its own Causal Trace entry (Art. 12). An auditor can reconstruct the full decision tree — which specs were proposed, which were validated, which were rejected — from the audit log alone.

## See Also

- [AdaptiveNode API](../api-reference/dynamicnode.md)
- [BatchNode API](../api-reference/batchnode.md)
- [Defensive Constraints](10-defensive-constraints.md) — token budgets and node fatigue limits
