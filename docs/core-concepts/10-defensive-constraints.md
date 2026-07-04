# Defensive Constraints (v1.6.0)

As agents become more autonomous (like the `DynamicNode` introduced in v1.5 — now `AdaptiveNode`), they run the risk of two major problems:
1. **Context Bloat:** Parallel workers returning huge documents that overwhelm the downstream context window (The "Black Hole").
2. **Infinite Loops:** An agent getting stuck in a self-correction loop and burning through API credits.

Lár v1.6.0 introduces architectural solutions to make your agents production-ready and mathematically safe.

---

## 1. Memory Compression (`ReduceNode`)

Prior to v1.6.0, running a `BatchNode` to gather 10 essays in parallel would dump all 10 essays directly back into the `GraphState` simultaneously. This would create a "black hole", instantly maximizing the context window of any downstream model reading the state.

We solved this by introducing the `ReduceNode` (a subclass of `LLMNode`). 

The `ReduceNode` is designed to be placed immediately after a `BatchNode` (The "Map" phase). It reads the bloated keys from the state, asks a fast/cheap LLM to summarize or extract the critical insights into a new key, and then **explicitly calls `state.delete(key)` on the massive upstream reports**.

This guarantees the state "baton" passed between nodes remains light and focused.

### Implementation Example

```python
from lar import BatchNode, ReduceNode, LLMNode

# 1. The Map Phase: Three agents researching in parallel
researcher_1 = LLMNode(model_name="ollama/phi4", prompt_template="Research AI in healthcare.", output_key="healthcare")
researcher_2 = LLMNode(model_name="ollama/phi4", prompt_template="Research AI in finance.", output_key="finance")
researcher_3 = LLMNode(model_name="ollama/phi4", prompt_template="Research AI in robotics.", output_key="robotics")

# 2. The Reduce Phase: Read the 3 heavy reports, extract insights, and delete the raw text
reducer = ReduceNode(
    model_name="ollama/phi4",
    prompt_template="Summarize the core themes: 1. {healthcare} 2. {finance} 3. {robotics}",
    input_keys=["healthcare", "finance", "robotics"], # These keys will be DELETED after execution
    output_key="executive_summary"
)

# Batch them together, and route directly to the reducer
map_phase = BatchNode(
    nodes=[researcher_1, researcher_2, researcher_3],
    next_node=reducer
)
```

---

## 2. Economic Constraints (Token Budgets)

Instead of relying on a "Max Steps" blunt instrument or guessing how much an Agent costs, Lár now supports mathematical dollar-amount ceilings via `token_budget`.

You can populate the initial graph state with an integer `token_budget`. Every time an `LLMNode` executes, it will read its exact token usage from LiteLLM and subtract it from the `token_budget` state variable before routing to the next node.

If a model attempts to execute and the `token_budget` is `0` or negative, the engine will intercept the call, throw an `error`, and gracefully terminate the workflow, protecting your API credits.

### Implementation Example

```python
from lar import GraphExecutor, LLMNode

executor = GraphExecutor()

# Give the agent a strict max budget of 2500 tokens
initial_state = {
    "task": "Write a 50 page book about the Roman Empire.",
    "token_budget": 2500 
}

book_writer = LLMNode(
    model_name="openai/gpt-4o",
    prompt_template="{task}",
    output_key="book_draft"
)

# The executor will run the node. 
# If the generation exceeds 2500 tokens, the state budget will drop below zero.
# The next LLMNode in the chain will immediately refuse to run and yield an error log.
for log in executor.run_step_by_step(book_writer, initial_state):
    print(log["outcome"])
```

---

## 3. Node Fatigue (Infinite Loop Protection)

To prevent true infinite loops (e.g. `RouterNode` bouncing back and forth between a `FixCodeNode` and a `TestCodeNode` forever without technically burning a massive amount of tokens instantly), the `GraphExecutor` safely tracks the number of times it visits a specific node class.

Every time a node runs, the executor increments its counter. If a single node is hit more times than the global `max_node_fatigue` limit, the engine physically trips a circuit breaker and kills the run, ensuring that no `RouterNode` can infinitely spin a single subset of a graph without human intervention.

### Implementation Example

```python
from lar import GraphExecutor

# Set the maximum times any single node can be executed in one graph run to 5
executor = GraphExecutor(max_node_fatigue=5)

# If an agent gets stuck in a self-correction loop passing over the same 
# LLMNode 6 times, the executor will intercept it and throw a FATIGUE Error.
```

For a masterclass showcase of all three features working together, see [`examples/advanced/11_map_reduce_budget.py`](https://github.com/snath-ai/lar/blob/main/examples/advanced/11_map_reduce_budget.py) in the open-source repository.
