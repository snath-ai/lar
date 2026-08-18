# Resumable Graphs

**Correction (this page was substantially rewritten after an independent verification pass — see CHANGELOG.md [2.2.3]):** an earlier version of this page claimed "most agent frameworks cannot reliably resume a crashed execution" as a structural limitation of probabilistic routing. That's not accurate. LangGraph ships a real, automatic checkpointer: state is persisted after every step, keyed by `thread_id`, and a resumed run continues from the last successful checkpoint — it does not re-execute already-completed routing decisions, so the "probabilistic router branches differently on resume" scenario described below doesn't actually apply once a real checkpointer is in use. That's currently *more* automatic than Lár's own resumability pattern, which requires the developer to manually track and hardcode which node to resume at (see `examples/patterns/9_resumable_graph.py`, which says so directly in its own comments).

What's genuinely true and worth keeping: every `RouterNode` in Lár is a pure Python function — same state in, same decision out, deterministically, every time it's called. That's a real property of Lár's routing design. It's a different claim from "resumption works here and can't work elsewhere," though, and this page previously conflated the two.

---

## What Actually Makes Resume Cheap

Whether you're using Lár's manual state-serialization or a framework with an automatic checkpointer, the actual cost saving comes from the same place: **not re-running steps that already completed successfully.** The alternative — no persistence at all, so a crash means starting over from step 0 — is what actually wastes tokens:

1. All in-memory context is lost
2. Every step, including previously-completed LLM calls, gets re-run from scratch
3. If those re-run steps involve an LLM call, you pay for them again

Lár's `GraphState` being a plain, JSON-serializable dict makes it simple to build your own save/restore around this. It just isn't automatic yet the way a real checkpointer is.

---

## How Lár Does It

The `GraphExecutor` is a Python generator. It yields control back to you after every single node execution — it never takes over your process. This means the state is always accessible, always serialisable, and always decoupled from the execution engine.

The causal trace — the HMAC-signed flight recorder written on every run — is not just an audit log. Every entry is a resumption checkpoint. The step number, the state diff, the node that ran, the outcome — all present. You always know exactly where to restart.

**Resuming a crashed execution:**

```python
from lar import GraphExecutor
import json

# Load the state saved at the last successful step
with open("checkpoint.json", "r") as f:
    recovered_state = json.load(f)

# run_step_by_step takes a plain dict and wraps it in GraphState internally --
# pass the loaded dict directly, not a pre-built GraphState instance.
executor = GraphExecutor()

for step in executor.run_step_by_step(start_node=failed_node, initial_state=recovered_state):
    print(f"Resumed at: {step['node']}")
```

Note: `failed_node` is the node you resume at. As of this writing, Lár does not automatically track and persist which node to resume at — you have to know and hardcode it yourself (see the caveat in `examples/patterns/9_resumable_graph.py`).

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

Reference implementations:
- [`examples/patterns/9_resumable_graph.py`](../../examples/patterns/9_resumable_graph.py) — Time Traveller: crash, serialise state, resume from exact node
- [`examples/patterns/10_resumable_cost_demo.py`](../../examples/patterns/10_resumable_cost_demo.py) — Cost Demo: live 4-step legal pipeline, 302 vs ~776 token comparison printed to console

---

## The Cost Reality

If you have no persistence at all, a crash means re-running every step from scratch — including previously-completed LLM calls. Lár resumes from the saved step (once you've built the save/restore, and correctly track the resume node) — no redundant token spend. A framework with an automatic checkpointer gets the same saving without the manual tracking.

| Run | Steps Executed | Tokens Sent | Cost (GPT-4o) |
|:---|:---|:---|:---|
| **Resumed from saved state** | Step 3 only | **302 tokens** | **$0.0006** |
| **No persistence — full retry** | Steps 0+1+3 | ~776 tokens | $0.0016 |

> At 10,000 runs/day with a 40% transient failure rate → **$9.48/day saved vs. having no persistence at all.**

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
