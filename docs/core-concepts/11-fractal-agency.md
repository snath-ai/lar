# Recursive Graph Composition (v1.5+)

`AdaptiveNode` can be nested: a generated subgraph can itself contain `AdaptiveNode` instances, which compose further subgraphs at runtime. This allows problems that require multiple layers of specialisation to be handled without pre-defining every layer's structure at development time.

Safety rails propagate through every level of nesting — the `TopologyValidator` passed to the parent `AdaptiveNode` is inherited by all child `AdaptiveNode` instances in the generated spec.

## When to Use Nested Composition

Use nested `AdaptiveNode` when both the number and structure of sub-pipelines are unknown at development time — the manager must decide both *how many* specialists to compose and *what each one does* based on the input it sees at runtime.

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

## Examples

### Fractal Polymath

See `examples/advanced/fractal_polymath.py` for a working example where a manager `AdaptiveNode` composes a `BatchNode` containing two specialist `AdaptiveNode` instances running in parallel threads.

### Multi-Site Clinical Trial (Pharma)

This architecture maps directly to a multi-site clinical trial. Each site has a different distribution of patient complexity, adverse event rates, and protocol deviations. A static graph cannot anticipate how many review pipelines any given site's data batch will need.

```
AdaptiveNode (Site Manager)
│   Receives: site_data_batch (patient records, AE reports, protocol logs)
│   Decides: which specialist sub-pipelines this batch requires and how many
│
└── Generates spec:
    ├── BatchNode (parallel site review)
    │   ├── Thread 1: LLMNode — Standard patient record review
    │   ├── Thread 2: LLMNode — Adverse event review  (only if AE rate > threshold)
    │   └── Thread 3: LLMNode — Protocol deviation review  (only if deviations present)
    └── LLMNode — Site-level summary for regulatory submission
```

The `TopologyValidator` passed to the manager is inherited by every child node — no site-level subgraph can call tools outside the approved clinical data toolset, regardless of what the LLM proposes. The HMAC-signed Causal Trace across all threads is the complete Article 12 audit record for that site's batch, reconstructible by a regulator from the log alone.

```python
from lar.adaptive import AdaptiveNode, TopologyValidator
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

### Art. 14 and Meaningful Oversight in Fractal Agents

A critical compliance gap emerges when `BatchNode` runs parallel branches that each produce a risk assessment: if those branches feed directly into a `ReduceNode`, the consolidated output discards per-dimension evidence before any human sees it. A principal investigator shown "MEDIUM overall" has no way to know that one branch returned CRITICAL.

**The pattern that closes this gap:**

```
BatchNode → BranchTriageNode → RouterNode
                                    ↓ "critical" → HumanJuryNode (early gate, pre-consolidation)
                                    ↓ "ok"       → ReduceNode → parse → HumanJuryNode (final gate)
```

`BranchTriageNode` (in `lar.compliance`) sits between `BatchNode` and `RouterNode`. It:

1. Parses every branch output (JSON-embedded risk assessments)
2. Writes `branch_findings_summary` — a per-dimension breakdown the `HumanJuryNode` includes in its context, so the human sees individual findings alongside the consolidated recommendation
3. Sets `branch_critical=True` if any branch exceeds the threshold, triggering the early-exit jury before `ReduceNode` compresses the evidence away

```python
from lar.compliance import BranchTriageNode
from lar import RouterNode

node_triage = BranchTriageNode(
    branch_output_keys=["safety_analysis", "efficacy_analysis", "regulatory_analysis"],
    critical_threshold="CRITICAL",   # or "HIGH" for stricter escalation
    next_node=node_branch_router,
)

node_branch_router = RouterNode(
    decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
    path_map={
        "critical": node_jury_early,   # Fires before ReduceNode
        "ok":       node_reduce,
    },
)

# Both HumanJuryNodes include branch_findings_summary in context_keys:
jury = HumanJuryNode(
    context_keys=["risk_level", "recommendation", "branch_findings_summary"],
    ...
)
```

This is the difference between compliance-on-paper (a single jury interrupt on an aggregated score) and meaningful oversight under Art. 14 (a human who can interrogate the evidence before it is destroyed).

The full working implementation with HMAC-signed artefact verification:

```bash
python examples/compliance/23_fractal_compliance_showcase.py
```

## See Also

- [AdaptiveNode API](../api-reference/adaptivenode.md)
- [BatchNode API](../api-reference/batchnode.md)
- [Defensive Constraints](10-defensive-constraints.md) — token budgets and node fatigue limits
- [Build a Compliant Agent from Scratch](../guides/build-compliant-agent.md)
