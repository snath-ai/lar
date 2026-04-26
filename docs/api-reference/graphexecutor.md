# GraphExecutor

The `GraphExecutor` is the central engine of the Lár framework. It is responsible for orchestrating the deterministic trace of the Directed Acyclic Graph (DAG) state machine. It manages `GraphState` diffing, handles terminal conditions, tracks node fatigue (infinite loop prevention), and writes to the cryptographic `AuditLogger`.

## Working with `run_step_by_step`

The primary execution mechanism is the `run_step_by_step()` generator. Unlike traditional frameworks that abstract state away, Lár yields exact execution diffs back to the caller at every node boundary. 

This enables you to build incredibly rich, real-time observables, UI hooks, and terminal traces without modifying the graph elements.

```python
from lar import GraphExecutor, AuditLogger, TokenTracker

audit_logger = AuditLogger(log_dir="logs/", hmac_secret="super-secret")
token_tracker = TokenTracker()

executor = GraphExecutor(
    logger=audit_logger,
    tracker=token_tracker,
    user_id="customer-123",
    max_node_fatigue=25,     # Triggers abort if graph loops > 25 times
)

for step_log in executor.run_step_by_step(
    start_node=entry_point_node,
    initial_state={"token_budget": 50000},
):
    node_name = step_log.get("node")
    diff = step_log.get("state_diff", {})
    metadata = step_log.get("run_metadata")

    print(f"[{node_name}] Executed. GraphState updated: {diff.get('added')}")
```

## Anatomy of a `step_log`

Every iteration yields a dictionary with extreme deterministic precision mapping the exact boundaries of the function.

```json
{
  "step": 4,                               // Global trace index
  "node": "ToolNode",                      // Type of node executed
  "state_before": {"token_budget": 5000},  // Snapshot
  "state_diff": {                          // The isolated 'delta'
    "added": {"word_count": 25},
    "removed": {},
    "updated": {}
  },
  "state_after": {"token_budget": 5000, "word_count": 25}, // Snapshot
  "outcome": "success",                    // 'success', 'error', 'max_steps_reached'
  "run_metadata": {"total_tokens": 0}      // Extracted metrics
}
```

## The Token Tracker
If you initialize the executor with a `TokenTracker()`, the engine will aggregate `run_metadata` from every single node inside its trace. At the end of execution, you can retrieve a budget snapshot:

```python
summary = token_tracker.get_summary()
print(summary['total_tokens'])
```

## Parameters

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `logger` | `AuditLogger` | `None` | Plugs in the file-based auditing mechanism. |
| `tracker` | `TokenTracker` | `None` | Plugs in the token aggregation mechanism. |
| `hmac_secret` | `str` | `None` | Automatically hashes the final audit log if provided. |
| `user_id` | `str` | `None` | Puts the user origin context inside the audit log root dict. |
| `max_node_fatigue` | `int` | `50` | Failsafe limit preventing infinite routing loops. |
| `offline_mode` | `bool` | `False` | Disables external API calls (currently a mock setting parameter). |
