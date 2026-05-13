# Fractal Agents

A fractal agent combines `AdaptiveNode` and `BatchNode`: a manager decides how many specialist sub-agents to spawn and what each one does, then runs them in parallel. The graph shape is never fixed at development time — it is determined by the input at runtime.

This is powerful. It also introduces a compliance gap that is not obvious until you think about what the human jury actually sees.

---

## The Compliance Gap — Read This First

When `BatchNode` runs parallel branches that each produce a risk assessment, the natural next step is `ReduceNode` to consolidate them into a single score. Then a `HumanJuryNode`.

**The problem:** the human jury sees the consolidated score. They do not see which individual branch triggered the alert. If three parallel reviews run on a contract — legal terms, financial liability, GDPR compliance — and the financial branch returns CRITICAL, the jury might only see "overall risk: HIGH." They approved without knowing *why*.

Under EU AI Act Art. 14, that is not meaningful human oversight. It is a rubber stamp on a number.

**The fix: `BranchTriageNode`**

Wire it between `BatchNode` and your routing logic:

```
BatchNode → BranchTriageNode → RouterNode
                                    ↓ "critical" → HumanJuryNode  ← fires before ReduceNode
                                    ↓ "ok"       → ReduceNode → HumanJuryNode
```

`BranchTriageNode` does three things:
1. Parses every branch output and extracts per-branch risk findings
2. Writes `branch_findings_summary` into state — the jury sees each branch's finding, not just the aggregate
3. Sets `branch_critical=True` if any branch exceeds the threshold — triggers an early human gate *before* `ReduceNode` destroys the per-dimension evidence

```python
from lar.compliance import BranchTriageNode
from lar import RouterNode, HumanJuryNode

node_triage = BranchTriageNode(
    branch_output_keys=["legal_review", "financial_review", "gdpr_review"],
    critical_threshold="CRITICAL",
    next_node=node_router,
)

node_router = RouterNode(
    decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
    path_map={
        "critical": node_jury_early,   # Human sees per-branch findings before consolidation
        "ok":       node_reduce,
    },
)

# Both jury nodes include branch_findings_summary in context
jury = HumanJuryNode(
    context_keys=["overall_risk", "recommendation", "branch_findings_summary"],
    ...
)
```

Without `BranchTriageNode`: the human sees `"risk: HIGH"`.
With `BranchTriageNode`: the human sees `"risk: HIGH — Financial branch CRITICAL: uncapped liability clause. GDPR branch HIGH: data retention clause missing."` That is what Art. 14 requires.

---

## How it Works

```
AdaptiveNode (Manager)
│
├── LLM generates JSON spec: BatchNode + child AdaptiveNodes + synthesiser
├── TopologyValidator validates the full spec (cycles, allowlist, depth)
│
└── Injects subgraph:
    ├── BatchNode (parallel threads)
    │   ├── Thread 1: AdaptiveNode (Specialist A)
    │   │   └── Generates + validates + executes its own subgraph
    │   └── Thread 2: AdaptiveNode (Specialist B)
    │       └── Generates + validates + executes its own subgraph
    ├── BranchTriageNode  ← compliance gate
    ├── RouterNode
    └── HumanJuryNode / ReduceNode
```

The manager makes one LLM call to design the structure. Each specialist makes one LLM call to design its own internal pipeline. All subsequent execution is deterministic Python.

---

## A Concrete Example: Contract Review

A legal team receives contracts of varying complexity. A simple two-page NDA needs one review. A multi-party software license with financial terms and data processing clauses needs three independent reviews run in parallel.

You don't hardcode both pipelines. The manager decides at runtime.

**State entering the manager:**
```python
{
    "document": "...(contract text)...",
    "doc_type": "software_license",
    "party_count": 3
}
```

**Manager prompt (simplified):**
```
Document type: {doc_type}, parties: {party_count}

If simple (NDA, <2 parties): 1 LLMNode — general review
If complex (license, >2 parties): BatchNode with 3 specialists:
  - legal_specialist: review terms and obligations
  - financial_specialist: review liability and payment clauses
  - compliance_specialist: review GDPR and data handling

Output JSON GraphSpec.
```

**What executes for "software_license, 3 parties":**

```
Manager AdaptiveNode
  → designs: BatchNode([legal, financial, compliance]) → BranchTriageNode → router

BatchNode (3 threads simultaneously):
  Thread 1: legal_specialist AdaptiveNode
    → designs: LLMNode("review obligations") → LLMNode("flag missing clauses")
    → output: {"risk": "MEDIUM", "finding": "arbitration clause absent"}

  Thread 2: financial_specialist AdaptiveNode
    → designs: LLMNode("review liability") → LLMNode("quantify exposure")
    → output: {"risk": "CRITICAL", "finding": "uncapped liability, no indemnity cap"}

  Thread 3: compliance_specialist AdaptiveNode
    → designs: LLMNode("check GDPR clauses")
    → output: {"risk": "HIGH", "finding": "data retention period unspecified"}

BranchTriageNode:
  branch_findings_summary:
    "Legal: MEDIUM — arbitration clause absent
     Financial: CRITICAL — uncapped liability
     Compliance: HIGH — GDPR retention clause missing"
  branch_critical: True (Thread 2 exceeded threshold)

RouterNode → "critical" → HumanJuryNode (fires before ReduceNode)

Human jury sees the full per-branch breakdown — not just a score.
Approves with rationale → signed AuthorityLedger record.
```

**What executes for a simple NDA:**

```
Manager AdaptiveNode
  → designs: LLMNode("general NDA review") → done
  (1 node, no parallel branches, no jury needed for low-risk)
```

Same entry point. Completely different execution shape. Both produce HMAC-signed causal traces.

---

## Validator Inheritance

The `TopologyValidator` passed to the manager propagates to every child `AdaptiveNode` automatically:

```python
validator = TopologyValidator(
    allowed_tools=[fetch_legal_database, flag_clause, summarize],
    max_nodes=10,   # No specialist can generate more than 10 nodes
)

manager = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=manager_prompt,
    validator=validator,   # Same validator, same limits, all the way down
    max_depth=3,           # Manager(1) → Specialist(2) → max depth
)
```

- The same tool allowlist applies at every nesting level
- `max_nodes` limits how large any individual spec can be
- `max_depth` prevents unbounded recursion (child gets `max_depth - 1`)
- Cycle detection runs independently on every generated spec
- A rejected spec at any level falls through to `next_node` without halting other branches

---

## Fractal Compliance Checklist

If you are deploying a fractal agent in a regulated context, verify all of these:

| ✓ | What to check | How |
|---|---|---|
| ☐ | Every branch output is structured (JSON with `risk` + `finding` keys) | Required for `BranchTriageNode` to parse findings |
| ☐ | `BranchTriageNode` is between `BatchNode` and any jury | Without it the jury sees consolidated score only — not Art. 14 compliant |
| ☐ | Both early-exit and final jury nodes include `branch_findings_summary` in `context_keys` | Ensures the human sees per-branch evidence at both gates |
| ☐ | `TopologyValidator` has a `max_nodes` limit set | Prevents LLM from generating an arbitrarily large subgraph |
| ☐ | `AdaptiveNode` has `max_depth` set | Prevents unbounded recursive nesting |
| ☐ | `GraphExecutor` has `hmac_secret` set | Signs the causal trace — required for Art. 12 tamper evidence |
| ☐ | `PIIRedactionEngine` fires before HMAC signing | Required for GDPR Art. 17 if inputs contain personal data |

---

## Token Budget Propagation

Token budgets are shared across all parallel branches. After `BatchNode` merges results, spend across all threads is reconciled:

```
budget_remaining = initial_budget - sum(spend_per_thread)
```

This prevents unbounded cost regardless of how many specialists the manager spawns.

---

## See Also

- [AdaptiveNode — how it works →](9-adaptive-graphs.md)
- [BranchTriageNode API →](../api-reference/branchTriageNode.md)
- [Fractal Compliance Showcase (full working example) →](../../examples/compliance/23_fractal_compliance_showcase.py)
- [Defensive Constraints — token budgets and node limits →](10-defensive-constraints.md)
- [Build a Compliant Agent from Scratch →](../guides/build-compliant-agent.md)
