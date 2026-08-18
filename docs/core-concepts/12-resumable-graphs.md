# Resumable Graphs

**Correction (this page was substantially rewritten after an independent verification pass — see CHANGELOG.md [2.2.3]):** an earlier version of this page claimed "most agent frameworks cannot reliably resume a crashed execution" as a structural limitation of probabilistic routing. That's not accurate. LangGraph ships a real, automatic checkpointer: state is persisted after every step, keyed by `thread_id`, and a resumed run continues from the last successful checkpoint — it does not re-execute already-completed routing decisions, so the "probabilistic router branches differently on resume" scenario described below doesn't actually apply once a real checkpointer is in use. That's currently *more* automatic than Lár's own resumability pattern, which requires the developer to manually track and hardcode which node to resume at (see `examples/patterns/9_resumable_graph.py`, which says so directly in its own comments).

What's genuinely true and worth keeping: every `RouterNode` in Lár is a pure Python function — same state in, same decision out, deterministically, every time it's called. That's a real property of Lár's routing design. It's a different claim from "resumption works here and can't work elsewhere," though, and this page previously conflated the two.

**Update (v2.3.0):** general step-checkpointing (arbitrary node → arbitrary node, described in "How Lár Does It" below) is still the manual, DIY pattern described on this page — that part of the original correction stands. What changed is narrower and specific: `HumanJuryNode` pauses now have a first-class durable checkpoint (`lar.checkpoint`), so the claim in "Resumable Human Oversight" below — that the process can die while waiting on a human and still resume correctly — is now actually true, when `checkpoint_store`/`case_id_key` are configured. It is opt-in, not automatic by default, and it only covers this one pause point, not arbitrary crash recovery.

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
- [`examples/patterns/11_durable_checkpoint.py`](../../examples/patterns/11_durable_checkpoint.py) — Durable Human Oversight: real two-process pause/resume via `HumanJuryNode` + `lar.checkpoint`

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

The `HumanJuryNode` is the most important resumption use case in production, and as of v2.3.0 it has a real durable checkpoint behind it — not the same-process `input()` block it used to be on its own.

By default, `HumanJuryNode` still just blocks on `input()` in the current process/thread: nothing is written to disk until a decision arrives, so a process killed mid-wait loses the pause entirely. Passing `checkpoint_store` and `case_id_key` changes that: the checkpoint — full state snapshot plus which node to resume at — is written to disk *before* the node blocks or applies an `automation_boundary` policy, so the pause survives the process dying while waiting.

```python
from lar import HumanJuryNode, FileCheckpointStore, resume_human_decision

store = FileCheckpointStore(directory="checkpoints")

jury_node = HumanJuryNode(
    prompt="Approve this case?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    next_node=notify_node,          # notify_node._node_id must be set
    checkpoint_store=store,
    case_id_key="case_id",          # state key holding the case identifier
)
```

When the decision arrives later — possibly in a completely different process, hours or days after the pause, e.g. from a web form or API call — resolve it with `resume_human_decision`, not by re-running the graph from the top:

```python
node_registry = {"notify_node": notify_node}  # same live objects as the original run

for step in resume_human_decision(
    checkpoint_store=store,
    case_id="CASE-4471",
    decision="approve",
    executor=executor,
    node_registry=node_registry,
):
    print(step["node"], step["outcome"])
```

This writes the decision to state, resumes at `next_node` directly, and never re-executes the paused `HumanJuryNode` — so nothing security-relevant gets recomputed from state that may have drifted after the checkpoint was taken. If an `authority_ledger` is attached, the Art. 12/14 record is written identically whether the decision resolved in-process or out-of-process.

A `node_registry` is required because a checkpoint records graph *position* (a node's `_node_id`), not graph *topology* — resuming needs the same live node objects the original run used, the same way a resumed LangGraph run needs the same compiled graph, not one reconstructed from nothing.

Verified with a real two-process test — see [`examples/patterns/11_durable_checkpoint.py`](../../examples/patterns/11_durable_checkpoint.py): one `python` invocation pauses and exits with nothing held in memory, a second, unrelated `python` invocation resumes correctly from what's on disk alone.

This is what EU AI Act Art. 14 actually requires in practice: the ability to pause before an irreversible action, await a human determination, and resume with that determination as part of the verified state — durably, not just within a single process's lifetime.

---

## See Also

- [Human Oversight — `HumanJuryNode` →](../api-reference/humanjurynode.md)
- [The Causal Trace — Art. 12 Audit Logging →](../api-reference/graphexecutor.md)
- [Fractal Agency — Resumable Adaptive Graphs →](11-fractal-agency.md)
