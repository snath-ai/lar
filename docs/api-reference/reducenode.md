# ReduceNode

The `ReduceNode` is a critical primitive for **Context Compression** in Lár. It allows the agent to synthesize multiple pieces of data from the `GraphState` into a single, cohesive summary, and critically, it **automatically deletes** the raw origin inputs after completion to prevent token bloat downstream.

## Why Reduce?

As agents run, especially after parallel `BatchNode` execution, the `GraphState` (or "notepad") can fill up with large blocks of raw data. If you pass this entire state into subsequent AI calls, you rapidly burn through your token budgets and risk the model losing focus on the critical context (the "Needle in a Haystack" problem). 

`ReduceNode` solves this by forcing a synthesis step and cleaning up the workspace.

## Usage

```python
from lar import ReduceNode

reduce_node = ReduceNode(
    model_name="ollama/llama3.2",
    prompt_template=(
        "You are a senior analyst. Synthesise the following two perspectives "
        "into a single, balanced 200-word summary.\n\n"
        "--- Perspective A ---\n{perspective_a}\n\n"
        "--- Perspective B ---\n{perspective_b}\n\n"
        "Synthesis:"
    ),
    input_keys=["perspective_a", "perspective_b"],  # Keys to read AND auto-delete
    output_key="synthesis",                         # Where to save the result
    generation_config={"temperature": 0.4},
    next_node=evaluator_node
)
```

## Parameters

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `model_name` | `str` | `"gpt-4o"` | The underlying LiteLLM model identifier to execute the synthesis. |
| `prompt_template` | `str` | Required | The template mapping the `input_keys` into a reduction prompt. |
| `input_keys` | `list[str]` | `[]` | The list of state keys to extract, inject into the prompt, and then **delete from the GraphState**. |
| `output_key` | `str` | `"reduced_output"` | The specific state key where the newly synthesized content will be saved. |
| `system_instruction` | `str` | `""` | Optional system instructions. |
| `generation_config` | `dict` | `{}` | `temperature`, `max_tokens`, etc. |
| `next_node` | `Node` | `None` | The next node to route to. |

## The Auto-Delete Mechanism

Unlike `LLMNode` or `ToolNode`, when the `ReduceNode` finishes running successfully, it actively calls `state.pop(key)` on every key listed in your `input_keys` array before saving the `output_key`.

If you need to keep one of the raw inputs for later, you should explicitly map it out via a different node or avoid using `ReduceNode` for that particular key flow.
