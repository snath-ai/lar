# AdaptiveNode API Reference

> **Note:** `DynamicNode` is a deprecated alias for `AdaptiveNode`. Use `AdaptiveNode` in new code.

## Overview

`AdaptiveNode` is a runtime graph composition primitive for regulated pipelines. When the structure of a processing step cannot be fully determined at development time, `AdaptiveNode` asks an LLM to produce a subgraph specification at execution time, validates it through `TopologyValidator`, instantiates the nodes, and injects the validated subgraph into the live execution path.

Compliance tags: **Art. 3(23)** (Substantial Modification control), **Art. 12** (Causal Trace logging), **Art. 9** (Risk Management)

> **Important:** `TopologyValidator` is required. Every generated spec is validated before any node executes. Skipping validation is not supported.

## Class Signature

```python
class AdaptiveNode(BaseNode):
    def __init__(
        self,
        llm_model: str,
        prompt_template: str,
        validator: TopologyValidator,
        next_node: BaseNode = None,
        context_keys: List[str] = [],
        system_instruction: str = None
    )
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `llm_model` | `str` | Yes | Model to generate the graph JSON spec |
| `prompt_template` | `str` | Yes | Prompt requesting the JSON spec. Must include schema instructions. |
| `validator` | `TopologyValidator` | Yes | Required for Art. 3(23) compliance — enforces cycle detection, tool allowlist, structural integrity |
| `next_node` | `BaseNode` | No | Node to resume after the injected subgraph completes |
| `context_keys` | `List[str]` | No | State keys to include in the LLM's context when designing the subgraph |
| `system_instruction` | `str` | No | System prompt for the graph-design LLM call |

## Execution Flow

1. **Compose spec**: Call LLM with `prompt_template` and `context_keys`
2. **Parse**: Extract graph specification from LLM response
3. **Validate**: `TopologyValidator` checks cycles, tool allowlist, structural integrity — raises `SecurityError` if invalid
4. **Instantiate**: Build nodes from the JSON spec
5. **Inject**: Return the subgraph entry node — `GraphExecutor` continues from there
6. **Resume**: Subgraph's terminal nodes flow to `next_node`

Every spec is logged to the Causal Trace (Art. 12) before execution.

## JSON GraphSpec Schema

```json
{
  "nodes": [
    {
      "id": "step_1",
      "type": "LLMNode",
      "prompt": "Analyse: {input}",
      "output_key": "analysis",
      "next": "step_2"
    },
    {
      "id": "step_2",
      "type": "ToolNode",
      "tool_name": "approved_tool",
      "input_keys": ["analysis"],
      "output_key": "result",
      "next": null
    }
  ],
  "entry_point": "step_1"
}
```

Supported node types: `LLMNode`, `ToolNode`, `BatchNode`, `AdaptiveNode`

## Compliance

### Art. 3(23) — Substantial Modification

`AdaptiveNode` must always be paired with `TopologyValidator`. The validator is the deterministic (non-AI) guardrail that prevents the generated spec from introducing cycles, unauthorised tools, or dangling references. Its rejection decisions are logged to the audit trail.

### Art. 12 — Causal Trace

The generated JSON spec is stored in `__graph_spec_json__` and captured in the audit log step for the `AdaptiveNode` execution. Auditors can inspect exactly what subgraph was composed and why.

### Art. 9 — Risk Management

The tool allowlist enforces privilege minimisation: only pre-approved functions can appear in `ToolNode` entries of generated specs.

## Example: Adaptive Worker Count

```python
from lar import AdaptiveNode, TopologyValidator, GraphExecutor, AddValueNode

def search_documents(query: str) -> str:
    return f"Results for {query}"

validator = TopologyValidator(allowed_tools=[search_documents])

PROMPT = """
Analyse query complexity: "{query}"

If simple (single fact lookup): compose 1 LLMNode to answer directly.
If complex (multi-step research): compose ToolNode(search_documents) -> LLMNode(synthesise).

Output JSON with nodes and entry_point.
"""

end_node = AddValueNode("status", "complete")

planner = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=PROMPT,
    validator=validator,
    next_node=end_node,
    context_keys=["query"]
)

executor = GraphExecutor()
results = list(executor.run_step_by_step(planner, {"query": "What is 2+2?"}))
```

## Example: Error Recovery

```python
from lar import AdaptiveNode, TopologyValidator

def rotate_credentials() -> str:
    # Rotate DB credentials
    return "rotated"

def retry_connection() -> str:
    # Retry DB connection
    return "connected"

validator = TopologyValidator(allowed_tools=[rotate_credentials, retry_connection])

RECOVERY_PROMPT = """
Error detected: "{last_error}"

Compose a recovery subgraph using allowed tools:
- rotate_credentials (no inputs)
- retry_connection (no inputs)

Output JSON with nodes and entry_point.
"""

recovery_node = AdaptiveNode(
    llm_model="gpt-4o",
    prompt_template=RECOVERY_PROMPT,
    validator=validator,
    context_keys=["last_error"]
)
```

## Audit Trail

Every `AdaptiveNode` execution produces a Causal Trace entry:

```json
{
  "step": 5,
  "node": "AdaptiveNode",
  "state_diff": {
    "added": {
      "__graph_spec_json__": "{ \"nodes\": [...], \"entry_point\": \"...\" }"
    }
  },
  "outcome": "success"
}
```

If `TopologyValidator` rejects the spec, `outcome` is `"error"` and the rejection reason is logged.

## Checklist

- Always provide `TopologyValidator` — no exceptions
- Minimise `allowed_tools` — principle of least privilege
- Review generated specs in audit logs during testing
- For code execution tools: sandbox with Docker, e2b, or WebAssembly
- Test with adversarial prompts to verify allowlist enforcement

## See Also

- [TopologyValidator API](topologyvalidator.md) — validation enforcement
- [Adaptive Graphs](../core-concepts/9-metacognition.md) — when and why to use AdaptiveNode
- [Red Teaming](../case-studies/red-teaming.md) — security testing
