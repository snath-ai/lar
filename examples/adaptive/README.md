# Adaptive Execution Examples

This directory contains examples of **runtime graph composition** using the `AdaptiveNode` primitive — a validated subgraph injection mechanism for problems whose processing structure cannot be fully determined at development time.

## What is Adaptive Execution in Lár?

Adaptive execution means the agent can:
1. Analyse a problem at runtime
2. Ask an LLM to design a processing subgraph tailored to that problem
3. Pass the generated spec through `TopologyValidator` (cycle detection, tool allowlist, structural integrity)
4. Inject the validated subgraph into the live execution path
5. Return control to the main graph once the subgraph completes

The key distinction: **the audit trail never breaks**. Every generated spec is logged to the Causal Trace (Art. 12). Every tool reference is checked against an explicit allowlist before execution (Art. 9). The graph remains fully traceable throughout.

## When to Use AdaptiveNode

**Use AdaptiveNode when:**
- Problem complexity varies and requires a different number of processing steps
- You need to dispatch to a domain-specific subgraph based on query classification
- A pipeline step's structure depends on runtime inputs

**Do NOT use AdaptiveNode when:**
- Problem structure is known and fixed — use a static graph
- Security constraints require a fully pre-defined execution path
- Debugging simplicity is the priority

## Safety Constraints

All adaptive execution examples use `TopologyValidator` to enforce:

**What the validator enforces:**
- No infinite loops (cycle detection via DFS)
- No unauthorised tool usage (explicit allowlist)
- No dangling node references (structural validation)

**What you must also control in production:**
- Sandbox any code execution tools (Docker, e2b, WebAssembly)
- Set a `max_nodes` limit in your validator (prevents resource exhaustion)
- Log all generated specs to the audit trail (AdaptiveNode does this by default)
- Test with adversarial prompts to verify allowlist enforcement

## Examples Overview

| Example | Capability | Risk Level | Production Ready |
|---------|-----------|------------|------------------|
| 1_dynamic_depth.py | Adaptive worker count | Low | Yes with node limits |
| 2_tool_inventor.py | Runtime code generation | HIGH | No — requires sandboxed executor |
| 3_self_healing.py | Error recovery pipeline | Medium | Yes with circuit breaker |
| 4_adaptive_deep_dive.py | Structural adaptation | Medium | Yes with depth limits |
| 5_expert_summoner.py | Domain subgraph dispatch | Low | Yes |

## Running the Examples

All examples use local Ollama models by default:

```bash
# Install Ollama: https://ollama.ai
ollama pull phi4

# Run an example
python 1_dynamic_depth.py
```

To use OpenAI or other providers, change the `llm_model` parameter.

## Code Structure

Every example follows this pattern:

```python
# 1. Define allowed tools
def safe_tool():
    return "result"

# 2. Create validator (required — enforces Art. 9 / Art. 3(23))
validator = TopologyValidator(allowed_tools=[safe_tool])

# 3. Define the adaptive prompt
PROMPT = """
Design a graph to solve: {problem}
Output JSON with nodes and entry_point.
"""

# 4. Create AdaptiveNode
adaptive_node = AdaptiveNode(
    llm_model="ollama/phi4",
    prompt_template=PROMPT,
    validator=validator,
    next_node=exit_node,
    context_keys=["problem"]
)

# 5. Execute
executor.run_step_by_step(adaptive_node, {"problem": "..."})
```

## Inspecting Generated Subgraphs

To see what spec the LLM generated:

```python
executor = GraphExecutor(log_dir="debug_logs")
list(executor.run_step_by_step(adaptive_node, initial_state))

import json
with open("debug_logs/run_<id>.json") as f:
    log = json.load(f)

for step in log["steps"]:
    if step["node"] == "AdaptiveNode":
        print(json.dumps(step["state_diff"]["added"]["__graph_spec_json__"], indent=2))
```

## Common Patterns

### Pattern 1: Adaptive Worker Count

Allocate processing resources proportional to query complexity:
```python
# Simple query: 1 researcher node
# Complex query: 3 sequential researcher nodes
```
See: `1_dynamic_depth.py`

### Pattern 2: Runtime Code Generation

Generate and execute code for novel computations:
```python
# Input: "Calculate 20th Fibonacci"
# Subgraph: LLMNode writes function → ToolNode executes it → result stored
```
See: `2_tool_inventor.py`

### Pattern 3: Error Recovery

Detect failures and compose a recovery subgraph:
```python
# DB connection fails → subgraph: rotate credentials → retry connection
```
See: `3_self_healing.py`

### Pattern 4: Domain Dispatch

Route to a specialised subgraph based on query domain:
```python
# Legal question → load legal_expert spec
# Medical question → load medical_expert spec
```
See: `5_expert_summoner.py`

## Best Practices

1. **Start static, add adaptive nodes last**: Build your core graph statically. Add `AdaptiveNode` only where runtime structural variation is genuinely required.

2. **Fail safely**: Always configure `next_node` — `AdaptiveNode` falls through to it if validation fails.

3. **Minimise the allowlist**: Only include tools that are strictly necessary. A smaller allowlist reduces the attack surface for prompt injection.

4. **All specs are logged**: `AdaptiveNode` automatically captures the generated spec in the Causal Trace. Review logs during testing.

5. **Limit recursion depth**: If nesting `AdaptiveNode` inside a generated subgraph, track depth in state and enforce a `max_depth` guard.

## Further Reading

- API Documentation: `docs/api-reference/adaptivenode.md`
- Topology Validation: `docs/api-reference/topologyvalidator.md`
- Compliance: `docs/compliance/eu-ai-act-deep-dive.md`

## Questions?

Open an issue: https://github.com/snath-ai/lar/issues
