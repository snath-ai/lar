# BatchNode API Reference

## Overview

`BatchNode` enables **true parallel execution** of multiple nodes using Python's `ThreadPoolExecutor`. This is essential for Fan-Out/Fan-In patterns where independent branches can run concurrently.

## Class Signature

```python
class BatchNode(BaseNode):
    def __init__(self, nodes: List[BaseNode], next_node: BaseNode = None)
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nodes` | `List[BaseNode]` | Yes | List of nodes to execute in parallel. Must be non-empty, and all elements must be `BaseNode` instances. |
| `next_node` | `BaseNode` | No | The single node to execute after all parallel nodes finish. Defaults to `None` (graph termination). |

## Behavior

### 1. **Execution Flow**
1. Snapshot the current state
2. Create deep copies of the state for each parallel node
3. Execute all nodes concurrently in separate threads
4. Merge non-conflicting updates back into the main state
5. Continue to `next_node`

### 2. **State Isolation**
Each node runs with its own **deep copy** of the state, preventing race conditions. Threads cannot interfere with each other's execution.

### 3. **State Merging Strategy**
After all threads complete, `BatchNode` merges results deterministically — completion order does not affect the outcome:

1. Results are sorted by node insertion index (not thread completion order)
2. A conflict scan runs across all local states: any key written by more than one branch with differing values is flagged
3. Conflicting keys are recorded in `state["_batch_conflicts"]` for inspection; the **first** branch (by insertion order) wins
4. Non-conflicting new and updated keys are merged into the main state

> [!NOTE]
> Design parallel branches to write to unique `output_key` values. Conflicts are surfaced rather than silently overwritten, but first-writer-wins is a convention, not a guarantee of semantic correctness.

### 4. **Error Handling**
- If any thread raises an exception, it's logged and `last_error` is set in the main state
- Other threads continue execution
- The `BatchNode` always proceeds to `next_node` (it doesn't fail-fast)

## Example Usage

### Simple Parallel Execution

```python
from lar import BatchNode, LLMNode, GraphExecutor

# Define three independent analysis tasks
analyst_1 = LLMNode(
    model_name="gpt-4",
    prompt_template="Analyze the sentiment of: {text}",
    output_key="sentiment_analysis"
)

analyst_2 = LLMNode(
    model_name="gpt-4",
    prompt_template="Extract key entities from: {text}",
    output_key="entity_extraction"
)

analyst_3 = LLMNode(
    model_name="gpt-4",
    prompt_template="Summarize: {text}",
    output_key="summary"
)

# Run all three in parallel
parallel_batch = BatchNode(
    nodes=[analyst_1, analyst_2, analyst_3],
    next_node=None  # End after merging results
)

# Execute
executor = GraphExecutor()
initial_state = {"text": "Apple announced record Q4 earnings..."}

for step in executor.run_step_by_step(parallel_batch, initial_state):
    print(f"Step {step['step']}: {step['node']}")

# Final state will have all three analyses
print(final_state.get("sentiment_analysis"))
print(final_state.get("entity_extraction"))
print(final_state.get("summary"))
```

### Newsroom Pattern (Real-World Example)

See [`examples/scale/3_parallel_newsroom.py`](https://github.com/snath-ai/lar/blob/main/examples/scale/3_parallel_newsroom.py) for a production pattern:

1. **Planner Node**: LLM generates story angles
2. **BatchNode**: 3 reporter agents research in parallel
3. **Aggregator Node**: Combine findings into final article

## Performance Considerations

### When to Use BatchNode

✅ **Good Use Cases**:
- Multiple LLM calls with independent inputs (e.g., translating to 5 languages)
- Parallel API requests (e.g., fetching data from 3 sources)
- Independent data processing tasks

❌ **Bad Use Cases**:
- Sequential dependencies (use linear chains)
- Shared mutable resources (threads will conflict)
- CPU-bound tasks in CPython (GIL limits parallelism - use ProcessPoolExecutor instead)

### Speedup Calculation

For I/O-bound tasks (LLM calls, API requests):
```
Sequential time: N × T
Parallel time: T + overhead

Speedup = N (ideal)
Real speedup ≈ 0.8N (accounting for thread overhead)
```

For 3 LLM calls at 2s each:
- Sequential: 6 seconds
- Parallel: ~2.2 seconds (**2.7x faster**)

## Common Patterns

### 1. **A/B Testing** (Compare Multiple Prompts)

```python
BatchNode(
    nodes=[
        LLMNode(model_name="gpt-4", prompt_template="Prompt A: {task}", output_key="result_a"),
        LLMNode(model_name="gpt-4", prompt_template="Prompt B: {task}", output_key="result_b"),
    ]
)
```

### 2. **Multi-Model Consensus**

```python
BatchNode(
    nodes=[
        LLMNode(model_name="gpt-4", prompt_template="{query}", output_key="gpt4_answer"),
        LLMNode(model_name="claude-3", prompt_template="{query}", output_key="claude_answer"),
        LLMNode(model_name="gemini-pro", prompt_template="{query}", output_key="gemini_answer"),
    ],
    next_node=vote_aggregator  # Majority voting
)
```

### 3. **Parallel Data Ingestion**

```python
BatchNode(
    nodes=[
        ToolNode(tool_function=fetch_twitter, input_keys=["query"], output_key="twitter_data"),
        ToolNode(tool_function=fetch_reddit, input_keys=["query"], output_key="reddit_data"),
        ToolNode(tool_function=fetch_news, input_keys=["query"], output_key="news_data"),
    ]
)
```

## Debugging

### Viewing Audit Logs

The audit log for a `BatchNode` step shows:
- `node`: "BatchNode"
- `state_diff`: All merged keys
- Individual child nodes are NOT logged (by design - they run in threads)

To debug child nodes, wrap them in a separate graph and inspect their logs independently.

## Validation

`BatchNode` validates construction parameters:
- `nodes` must be a non-empty list
- All elements must be `BaseNode` instances
- `next_node` must be `BaseNode` or `None`

**Example Error**:
```python
>>> BatchNode(nodes=["string"])  # Invalid
ValueError: nodes[0] must be a BaseNode instance, got str
```

## See Also

- [Multi-Agent Orchestration Guide](../guides/multi-agent-orchestration.md)
- [Parallel Corporate Swarm Example](https://github.com/snath-ai/lar/blob/main/examples/scale/4_parallel_corporate_swarm.py)
- [RouterNode API](routernode.md) - For sequential conditional logic
