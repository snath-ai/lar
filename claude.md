# Lár Framework - Claude Rules

You are coding with **Lár**, a graph-based agent framework that treats "Code as the Graph".

## Core Principles
1.  **Strict Typing**: Every Node and Function MUST have Pydantic/Python type hints.
2.  **Explicit Linking**: Connect nodes using `.next_node = target` or `RouterNode(path_map={...})`.
3.  **No "Magic"**: Do not assume global state. Use `state.get()` and `state.set()`.
4.  **No Hidden Prompts**: All prompts must be visible in the `prompt_template` argument.

## Universal Model Support
Lár is powered by LiteLLM (100+ Providers). Switch seamlessly by changing the `model_name` string:
- Cloud: `model_name="gpt-4o"`, `model_name="gemini/gemini-1.5-pro"`
- Local: `model_name="ollama/phi4"`, `model_name="ollama/deepseek-r1:7b"`
- Reasoning (System 2): Treats `<think>` tags as first-class citizens. Thoughts are extracted and saved to `run_metadata`.

## Code Patterns to Follow

### 1. Defining a Node (Standard)
```python
from lar import LLMNode

architect = LLMNode(
    model_name="gemini/gemini-1.5-pro",
    prompt_template="Analyze {input}...",
    output_key="plan"
)
```

### 2. Defining a Node (Low Code - v1.4.0+)
```python
from lar import node

@node(output_key="summary")
def summarize_text(state):
    text = state["text"]
    return llm.generate(text)
```

### 3. Defining a Tool
```python
from lar import ToolNode

def my_tool(state):
    return "result"

tool = ToolNode(
    tool_function=my_tool,
    input_keys=["__state__"],
    output_key="result",
    next_node=success_node,
    error_node=fail_node # Native error handling
)
```

### 4. Defining a Router
```python
from lar import RouterNode

def decide(state):
    return "go_left"

router = RouterNode(
    decision_function=decide,
    path_map={
        "go_left": left_node,
        "go_right": right_node
    }
)
```

### 5. Defining a State Update (AddValueNode)
```python
from lar import AddValueNode

# Useful for setting predefined statuses or constants
node = AddValueNode(
    key="status",
    value="SUCCESS",
    next_node=None
)
```

### 6. Advanced Primitives (v1.5+)
- **BatchNode**: Parallelize nodes on separate threads (true parallelism).
- **ReduceNode**: Summarize multi-agent outputs, delete raw memory to compress state context.
- **AdaptiveNode**: Runtime graph composition — asks an LLM to design a validated subgraph, passes it through TopologyValidator, and injects it into the execution path. Use `DynamicNode` as a deprecated alias.
- **HumanJuryNode**: Mandatory human oversight interrupt satisfying EU AI Act Art. 14 (human oversight requirement).
- **BranchTriageNode**: Post-BatchNode compliance primitive for fractal agents. Parses all parallel branch outputs, builds `branch_findings_summary` for jury context, and sets `branch_critical=True` if any branch breaches the threshold. Wire it between `BatchNode` and `RouterNode`. Without this, the human jury only sees the consolidated score — not which individual branch triggered the alert. That is not meaningful oversight under Art. 14. Import from `lar.compliance`.
- **ClearErrorNode**: Clear error states for deterministic retry loops.

## Observability, Compliance, and Budgets
- **AuditLogger & TokenTracker**: Separate instances for file persistence and token cost aggregation across workflows.
- **Cryptographic Audit Logs**: Produce HMAC-SHA256 mathematical signature of trace via `GraphExecutor(hmac_secret="...")`.
- **Token Budgets & Node Limits (v1.6+)**: Guardrails against unlimited execution costs and recursion fatigue.

## Running Agents
Always include a `if __name__ == "__main__":` block that uses `GraphExecutor` to run the graph instantly for verification.

## Knowledge Base
- **Entry Point**: `lar/src/lar/executor.py`
- **Node Types**: `lar/src/lar/node.py`
- **Examples**: Look at `lar/examples/` for canonical patterns (Triage, RAG, Corporate Swarm, Compliance, Adaptive Execution).
