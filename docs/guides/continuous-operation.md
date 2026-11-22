# Continuously Running Agents

> How to deploy a Lár agent as a persistent, production-grade service inside a company.

A "continuously running agent" is not a Lár-specific concept — it is a deployment pattern. Lár handles the execution spine. You choose the hosting shell: a FastAPI server, a queue consumer, a scheduled cron job, or an event-driven webhook handler. This guide shows all four.

---

## The Core Pattern

Lár's `GraphExecutor` is a plain Python generator. It does not own your process, does not maintain a server, and does not impose a runtime. This means plugging it into any hosting model is trivial — no adapters, no framework lock-in.

```python
from lar import GraphExecutor, GraphState

executor = GraphExecutor(hmac_secret="your-secret")

def run_agent(input_data: dict) -> dict:
    state = GraphState(initial_state=input_data)
    result = {}
    for step in executor.run_step_by_step(entry_node, state):
        result = step["state_after"]
    return result
```

That function is what you expose — however you like.

---

## Option 1: FastAPI Server (Recommended for APIs)

The simplest production deployment. One endpoint per agent workflow.

```python
# examples/basic/4_fastapi_server.py
from fastapi import FastAPI
from lar import GraphExecutor, GraphState

app = FastAPI()
executor = GraphExecutor(hmac_secret=os.environ["HMAC_SECRET"])

@app.post("/run")
def run_agent(payload: dict):
    state = GraphState(initial_state=payload)
    final_state = {}
    for step in executor.run_step_by_step(entry_node, state):
        final_state = step["state_after"]
    return final_state
```

Deploy to AWS, Railway, or Heroku. Scale horizontally — each request is stateless. State lives in `GraphState`, not in the server.

---

## Option 2: Queue Consumer (Recommended for Background Jobs)

For long-running tasks triggered by events (Slack messages, emails, webhook calls). Use any queue: SQS, RabbitMQ, Redis Streams.

```python
import json, redis
from lar import GraphExecutor, GraphState

r = redis.Redis()
executor = GraphExecutor(hmac_secret=os.environ["HMAC_SECRET"])

while True:
    _, raw = r.blpop("agent:jobs")          # blocks until a job arrives
    payload = json.loads(raw)

    state = GraphState(initial_state=payload)
    for step in executor.run_step_by_step(entry_node, state):
        pass                                 # audit log written automatically

    r.rpush("agent:results", json.dumps(step["state_after"]))
```

---

## Option 3: Scheduled / Cron Agent

For periodic compliance checks, post-market monitoring (Art. 72), or nightly batch runs.

```python
# Run with: cron  0 2 * * *  python scheduled_agent.py
from lar import GraphExecutor, GraphState

executor = GraphExecutor(hmac_secret=os.environ["HMAC_SECRET"])

payload = {"report_date": "2026-08-01", "domain": "finance"}
state = GraphState(initial_state=payload)

for step in executor.run_step_by_step(monitoring_entry_node, state):
    pass

print("Post-market monitoring run complete. Audit log written.")
```

See: [`examples/compliance/12_post_market_monitoring.py`](../../examples/compliance/12_post_market_monitoring.py)

---

## Option 4: Long-Running with Human Approval Pause

The most important pattern for regulated deployments. The agent runs, hits a `HumanJuryNode`, and halts. The process can be killed. When the human responds — minutes, hours, or days later — the graph resumes from exactly that node with exactly that state.

```python
from lar import GraphExecutor, HumanJuryNode, FileCheckpointStore, resume_human_decision

store = FileCheckpointStore("/var/agent/checkpoints")
executor = GraphExecutor(hmac_secret=os.environ["HMAC_SECRET"])

jury = HumanJuryNode(
    prompt="Approve this loan?", choices=["approve", "reject"],
    output_key="jury_decision", context_keys=["application"],
    next_node=post_approval_node,            # needs a stable _node_id (see below)
    checkpoint_store=store, case_id_key="case_id",
    automation_boundary={"loan_review": "always_human"}, decision_type="loan_review",
)

# --- First run: the agent reaches the HumanJuryNode and pauses ---
state = {"case_id": "LOAN-77", "application": "SME loan €500k"}
for step in executor.run_step_by_step(entry_node, state):
    pass
# The pause is written to disk BEFORE the node refuses to auto-decide. The step
# reports outcome "error" (there is no "halted" outcome); the reliable signal is
# the checkpoint itself:
if store.exists("LOAN-77"):
    print("Awaiting human approval. Process may exit.")

# --- Approval webhook received (hours later, possibly a different process) ---
# `reviewer` is the identity YOUR auth layer verified; Lár does not authenticate anyone.
for step in resume_human_decision(
    checkpoint_store=store, case_id="LOAN-77", decision="approve",
    executor=executor, node_registry={"post_approval_node": post_approval_node},
    stakeholder_id=reviewer, stakeholder_role="CREDIT_OFFICER",
    rationale="Risk within policy limits.",
):
    pass
```

`resume_human_decision` validates the decision against the node's `choices`, claims the checkpoint atomically (only one resolver wins), resumes at the node routed for that decision, records the human in the `AuthorityLedger` if one is attached, and only deletes the checkpoint after the resumed run finishes. Do **not** hand-write the decision into a JSON file: that skips validation, the claim, and the evidence record.

This is what EU AI Act Art. 14 requires in practice: pause before an irreversible action, await a human determination, resume with that determination as part of the verified state.

See: [`examples/patterns/11_durable_checkpoint.py`](../../examples/patterns/11_durable_checkpoint.py) (cross-process pause and resume) and [`examples/compliance/1_human_in_the_loop.py`](../../examples/compliance/1_human_in_the_loop.py)

---

## Crash Recovery in Production

Transient failures (rate limits, OOM, deployment restarts) are unavoidable at scale. Because Lár's routers are pure Python, resumption is deterministic — not an approximation.

```python
CHECKPOINT = "/var/agent/checkpoint.json"

for step in executor.run_step_by_step(entry_node, state):
    # Checkpoint after every successful step
    with open(CHECKPOINT, "w") as f:
        json.dump(step["state_after"], f)

# On next startup: load checkpoint and resume
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT) as f:
        restored = json.load(f)
    for step in executor.run_step_by_step(resume_node, restored):
        pass
```

At 10,000 runs/day with 40% transient failure rate → **$9.48/day saved** vs frameworks that replay from scratch.

See: [`examples/patterns/10_resumable_cost_demo.py`](../../examples/patterns/10_resumable_cost_demo.py)

---

## Compliance in Continuous Operation

Every run produces a HMAC-SHA256 signed audit log automatically. In a continuously running service:

- Pass `hmac_secret=os.environ["HMAC_SECRET"]` to `GraphExecutor` — logs are tamper-evident
- Logs are written to `lar_logs/run_<uuid>.json` by default — configure `log_dir` for your storage
- The `ComplianceManifestGenerator` primitive can run once at startup to produce a static action inventory for your Notified Body

```python
executor = GraphExecutor(
    hmac_secret=os.environ["HMAC_SECRET"],
    log_dir="/var/agent/audit_logs"    # configure for your storage
)
```

---

## See Also

- [Resumable Graphs →](../core-concepts/12-resumable-graphs.md)
- [Build a Compliant Agent →](build-compliant-agent.md)
- [Deployment →](deployment.md)
- [FastAPI Server example →](../../examples/basic/4_fastapi_server.py)
- [Post-Market Monitoring (Art. 72) →](../../examples/compliance/12_post_market_monitoring.py)
