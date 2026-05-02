# Resumable Graphs (Time-Travel Debugging)

Lár's `GraphExecutor` is designed as a pure Python generator. Instead of a "black box" loop that takes over your entire process, the executor yields control back to you after *every single node execution*. 

This generator-based architecture makes **Resumable Graphs** trivial to implement, allowing for unprecedented resilience in production environments.

## The Problem: Rate Limits & Transient Failures
Imagine your agent is running a 100-step data processing pipeline. At Step 99, the OpenAI API throws a `RateLimitError`. In standard frameworks, the loop crashes, all in-memory context is lost, and you must start over from Step 1—wasting time and money.

## The Solution: Pause, Save, Resume
With Lár, the state is fully decoupled from the execution engine.

1. **Pause & Save:** Because the `GraphState` is just a simple Python dictionary, you can serialize it (e.g., to JSON or a database) at any point. If an error occurs, simply catch the exception and save the `GraphState` exactly as it was at Step 98.
2. **Resume:** When the rate limit resets or the API comes back online, re-instantiate the graph, feed it the saved `GraphState`, and tell the executor to start precisely from the node that failed.

### Code Example
*(Reference `examples/patterns/9_resumable_graph.py`)*

```python
from lar import GraphExecutor, GraphState
import json

# 1. Load the saved state from disk (e.g., after a crash)
with open("saved_state.json", "r") as f:
    recovered_state_data = json.load(f)

# 2. Re-instantiate the state object
resumed_state = GraphState(initial_state=recovered_state_data)

# 3. Resume the executor, passing the recovered state and the node to start from
executor = GraphExecutor()
for step in executor.run_step_by_step(start_node=crashed_node, initial_state=resumed_state):
    print(f"Resumed execution at step: {step['node']}")
```

## "Time-Travel" Debugging
This architecture also unlocks "Time-Travel Debugging" during development. If an agent produces a bad output at Step 5, you don't have to rerun Steps 1-4. You can load the state from Step 4, tweak your prompt for Step 5, and run *only* Step 5 repeatedly until it's perfect.
