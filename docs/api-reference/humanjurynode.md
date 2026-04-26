# HumanJuryNode

The `HumanJuryNode` provides the authoritative "Human-in-the-Loop" (HITL) capability required for high-risk deployments. It pauses the agent's execution entirely, displays critical context directly to the console (or connected interface), and yields control to a human overseer to make a routing decision.

This satisfies requirements like the **EU AI Act's Article 14** (Human Oversight) by guaranteeing deterministic intersection points before an AI can execute terminal or high-stakes actions.

## Usage

```python
from lar import HumanJuryNode

def deploy_to_prod():
    # Production deployment sequence
    pass

jury_node = HumanJuryNode(
    prompt="Approve the deployment of this generated patch to production?",
    choices=["approve", "reject", "re-generate"],
    output_key="jury_verdict",           # Where the human's string choice is saved
    context_keys=["code_diff", "tests"], # What the human sees before deciding
    next_node=evaluator_router           # Standard routing follows
)
```

## How It Works

When `GraphExecutor` encounters a `HumanJuryNode`, it:
1. Stops the execution loop.
2. Extracts the state values corresponding to your `context_keys`.
3. Renders the context visually.
4. Prompts the terminal: `[?] Approve the deployment...? (approve/reject/re-generate):`
5. Blocks until exact-match input is received.
6. Writes the chosen keyword to the `GraphState` under `output_key`.
7. Proceeds immediately to `next_node`.

> [!TIP]
> **Headless / CI Mode**: You can easily bypass juries in automated testing environments without altering graph structure by explicitly injecting a pre-defined verdict into state before the run starts, or overriding `SKIP_JURY` checks to dynamically map to an `AddValueNode` (see the Validation Suite examples).

## Parameters

| Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `prompt` | `str` | Required | The explicit question asked to the human operator. |
| `choices` | `list[str]` | Required | An array of acceptable string responses (e.g., `["yes", "no"]`). |
| `output_key` | `str` | `"jury_decision"` | The key where the operator's exact response string will be saved. |
| `context_keys` | `list[str]` | `[]` | A list of state keys whose values should be printed to the screen to help the human make their decision. |
| `next_node` | `Node` | `None` | The next node to transition to. Often a `RouterNode` that reads the `jury_decision`. |
