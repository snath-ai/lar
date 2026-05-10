# Resumable Graphs

Most agent frameworks cannot reliably resume a crashed execution. This is not a missing feature — it is a structural consequence of how they work. When a probabilistic framework retries from a checkpoint, the LLM router may make a different decision with the same input. The graph takes a different path. The "resume" is actually a new run wearing a checkpoint's clothes.

Lár is different by construction.

Every router in Lár is a pure Python function. Same state in, same decision out — deterministically. This means resumption is not an approximation. When Lár resumes at Step 47, it will take exactly the same path Step 47 would have taken if the crash never happened. The graph is reproducible. The resumption is exact.

---

## Why This Is Hard Everywhere Else

When a 50-step pipeline crashes at Step 48 in a standard framework:

1. All in-memory context is lost
2. The framework re-sends the entire conversation history to the LLM on retry — paying for Steps 0–47 again
3. The LLM router, being probabilistic, may branch differently — making the "resumed" run a different execution, not a continuation of the original

You don't get resumption. You get an expensive retry that happens to start with the same input.

---

## How Lár Does It

The `GraphExecutor` is a Python generator. It yields control back to you after every single node execution — it never takes over your process. This means the state is always accessible, always serialisable, and always decoupled from the execution engine.

The causal trace — the HMAC-signed flight recorder written on every run — is not just an audit log. Every entry is a resumption checkpoint. The step number, the state diff, the node that ran, the outcome — all present. You always know exactly where to restart.

**Resuming a crashed execution:**

```python
from lar import GraphExecutor, GraphState
import json

# Load the state saved at the last successful step
with open("checkpoint.json", "r") as f:
    recovered_state = json.load(f)

# Re-instantiate state and resume from the failed node
executor = GraphExecutor()
resumed_state = GraphState(initial_state=recovered_state)

for step in executor.run_step_by_step(start_node=failed_node, initial_state=resumed_state):
    print(f"Resumed at: {step['node']}")
```

**Saving a checkpoint on failure:**

```python
executor = GraphExecutor()
last_good_state = None

for step in executor.run_step_by_step(start_node=entry, initial_state=state):
    last_good_state = step["state_after"]
    
    # Persist after every step — zero overhead, just a dict
    with open("checkpoint.json", "w") as f:
        json.dump(last_good_state, f)
```

Reference implementation: [`examples/patterns/9_resumable_graph.py`](../../examples/patterns/9_resumable_graph.py)

---

## The Cost Reality

Every other framework re-sends the full conversation history on retry. When a 10-step pipeline crashes at Step 8, you pay for Steps 0–7 again. Lár resumes from the exact step that failed — no redundant token spend.

| Run | Steps Executed | Tokens Sent | Cost (GPT-4o) |
|:---|:---|:---|:---|
| **Lár — Resume** | Step 3 only | **302 tokens** | **$0.0006** |
| **Competitor — Retry** | Steps 0+1+3 | ~776 tokens | $0.0016 |

> At 10,000 runs/day with a 40% transient failure rate → **$9.48/day saved.**

---

## Time-Travel Debugging

The same property that enables crash recovery enables surgical debugging. If your agent produces a wrong output at Step 5, you do not rerun Steps 1–4. You load the state from Step 4, modify the prompt for Step 5, and run Step 5 alone — repeatedly, cheaply, until it is correct.

In a black-box framework, debugging means re-running the whole pipeline and hoping the LLM reproduces the same path. In Lár, you rewind to the exact state that produced the bad output and operate on it directly.

---

## Resumable Human Oversight

The `HumanJuryNode` is the most important resumption use case in production. When a high-risk action requires human approval, the graph does not busy-wait — it halts. The state is serialised. The process can be killed. When the human responds — minutes, hours, or days later — the graph resumes from exactly that node with exactly that state. No tokens wasted. No context lost. No LLM calls made while waiting.

This is what EU AI Act Art. 14 actually requires in practice: the ability to pause before an irreversible action, await a human determination, and resume with that determination as part of the verified state. Lár's generator architecture makes this a structural property, not a workaround.

---

## See Also

- [Human Oversight — `HumanJuryNode` →](../api-reference/humanjurynode.md)
- [The Causal Trace — Art. 12 Audit Logging →](../api-reference/graphexecutor.md)
- [Fractal Agency — Resumable Adaptive Graphs →](11-fractal-agency.md)
