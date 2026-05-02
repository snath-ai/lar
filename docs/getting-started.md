
# Getting Started

## Build a Production-Ready "Master Planner" in 3 Minutes

This quick-start guide will help you build your first **Auditable Agent**. Unlike a chatbot, this agent is a **Deterministic Workflow**: it accepts a task, evaluates it, and routes it to an exact specialist.
Because it's built on Lár, it produces a **cryptographically signed causal trace** by default. Lár is also the only framework that ships with a complete **EU AI Act Deployment Package**, providing out-of-the-box primitives for Art. 14 Human Oversight, GDPR Art. 17 right-to-erasure, and Art. 72 Post-Market Monitoring. (See the [Enterprise Compliance Reference](compliance/enterprise-reference.md) for advanced use cases).

!!! warning "Legal Disclaimer"
    Lár is open-source software infrastructure, not legal or compliance advice. Using Lár does not automatically guarantee compliance with the EU AI Act, GDPR, HIPAA, or any other regulation. Organizations are solely responsible for ensuring their AI systems undergo proper legal review and conformity assessments.

---

### 1. Optimize Your IDE (Agentic Workflow)

**Using Cursor, Windsurf, or Antigravity?**
Lár is designed to be written by AI.

1.  **Open the Repo**: Open the `lar` folder in your IDE.
2.  **Ask**: "Build a Lár agent that checks stocks."
3.  **Interactive Mode**: The IDE will either **Draft a Blueprint** for you or ask for `IDE_PROMPT_TEMPLATE.md`.

*If the IDE hallucinates, tell it:*
> "Read `lar/IDE_MASTER_PROMPT.md` and `lar/examples/` first."

### 2. Install & Scaffold (New in v1.4.0)

You can install the core Lár engine and new CLI directly from PyPI:

```bash
pip install lar-engine
```

Then, generate a new agent project instantly:

```bash
lar new agent my-agent
cd my-agent
poetry install
```

This creates a production-ready folder structure with `pyproject.toml`, `.env`, and a template agent.
### 3. **Set Up Environment Variables**
`Lár` uses a unified adapter `(LiteLLM)`. Depending on the models you run, you must set the corresponding API keys in your `.env` file:

Create a `.env` file:

```bash
# Required for running Gemini models:
GEMINI_API_KEY="YOUR_GEMINI_KEY_HERE" 
# Required for running OpenAI models (e.g., gpt-4o):
OPENAI_API_KEY="YOUR_OPENAI_KEY_HERE"
# Required for running Anthropic models (e.g., Claude):
ANTHROPIC_API_KEY="YOUR_ANTHROPIC_KEY_HERE"
```



### 4. Universal Model Support (Powered by LiteLLM)
Refactoring code to switch providers is a thing of the past. Lár is built on **LiteLLM**, giving you instant access to 100+ providers (OpenAI, Anthropic, VertexAI, Bedrock, etc) and local models.

Switching is just changing **one string**.

**Cloud (OpenAI):**
```python
node = LLMNode(model_name="gpt-4o", ...)
```

**Local (Ollama):**
```python
# Just change the string! No imports. No refactoring.
node = LLMNode(model_name="ollama/phi4:latest", ...)
```

**Local (Llama.cpp / vLLM):**
```python
# Use ANY generic OpenAI endpoint
node = LLMNode(
    model_name="openai/custom", 
    generation_config={"api_base": "http://localhost:8080/v1"}
)
```

### 5. Create Your First “Glass Box” Agent

Now, build a simple Master Planner Agent that accepts a user’s task, evaluates it, and routes it to an exact specialist.

## Next Steps: Moving to Production

Once your agent is working locally, you want to deploy it as an API.
Check out our **[Deployment Guide](guides/deployment.md)** to see how to wrap your agent in a **FastAPI** server in 5 minutes.

[View Deployment Guide →](guides/deployment.md)

```python
import os
from lar import *
from lar.utils import compute_state_diff
from dotenv import load_dotenv
# Load your .env file
load_dotenv()
os.environ["GOOGLE_API_KEY"] # (This line is for Colab/Jupyter)

# 1. Define the "choice" logic for our Router
def plan_router_function(state: GraphState) -> str:
    """Reads the 'plan' from the state and returns a route key."""
    plan = state.get("plan", "").strip().upper()
    
    if "CODE" in plan:
        return "CODE_PATH"
    else:
        return "TEXT_PATH"

# 2. Define the agent's nodes (the "bricks")
# We build from the end to the start.

# --- The End Nodes (the destinations) ---
success_node = AddValueNode(
    key="final_status", 
    value="SUCCESS", 
    next_node=None # 'None' means the graph stops
)

chatbot_node = LLMNode(
    model_name="gemini/gemini-2.5-pro",
    prompt_template="You are a helpful assistant. Answer the user's task: {task}",
    output_key="final_response",
    next_node=success_node # After answering, go to success
)

code_writer_node = LLMNode(
    model_name="gemini/gemini-2.5-pro",
    prompt_template="Write a Python function for this task: {task}",
    output_key="code_string",
    next_node=success_node 
)

# --- 2. Define the "Choice" (The Router) ---
master_router_node = RouterNode(
    decision_function=plan_router_function,
    path_map={
        "CODE_PATH": code_writer_node,
        "TEXT_PATH": chatbot_node
    },
    default_node=chatbot_node # Default to just chatting
)

# --- 3. Define the "Start" (The Planner) ---
planner_node = LLMNode(
    model_name="gemini/gemini-2.5-pro",
    prompt_template="""
    Analyze this task: "{task}"
    Does it require writing code or just a text answer?
    Respond with ONLY the word "CODE" or "TEXT".
    """,
    output_key="plan",
    next_node=master_router_node # After planning, go to the router
)

# --- 4. Run the Agent ---
executor = GraphExecutor()
initial_state = {"task": "What is the capital of France?"}

# The executor runs the graph and returns the full log
result_log = list(executor.run_step_by_step(
    start_node=planner_node, 
    initial_state=initial_state
))

# --- 5. Inspect the "Glass Box" ---

print("--- AGENT FINISHED! ---")

# Reconstruct the final state
final_state = initial_state
for step in result_log:
    final_state = apply_diff(final_state, step["state_diff"])

print(f"\nFinal Answer: {final_state.get('final_response')}")
print("\n--- FULL AUDIT LOG (The 'Glass Box') ---")
print(json.dumps(result_log, indent=2))
```



The Output (Your Forensic Flight Recorder)

When you run this, you get more than an answer. You get a **compliance artifact**.
This log is your proof of *exactly* what the agent did, step-by-step.

```json
[
  {
    "step": 0,
    "node": "LLMNode",
    "state_before": {
      "task": "What is the capital of France?"
    },
    "state_diff": {
      "added": {
        "plan": "TEXT"
      },
      "removed": {},
      "modified": {}
    },
    "run_metadata": {
      "prompt_tokens": 42,
      "output_tokens": 1,
      "total_tokens": 43
    },
    "outcome": "success"
  },
  {
    "step": 1,
    "node": "RouterNode",
    "state_before": {
      "task": "What is the capital of France?",
      "plan": "TEXT"
    },
    "state_diff": {
      "added": {},
      "removed": {},
      "modified": {}
    },
    "run_metadata": {},
    "outcome": "success"
  },
  {
    "step": 2,
    "node": "LLMNode",
    "state_before": {
      "task": "What is the capital of France?",
      "plan": "TEXT"
    },
    "state_diff": {
      "added": {
        "final_response": "The capital of France is Paris."
      },
      "removed": {},
      "modified": {}
    },
    "run_metadata": {
      "prompt_tokens": 30,
      "output_tokens": 6,
      "total_tokens": 36
    },
    "outcome": "success"
  },
  {
    "step": 3,
    "node": "AddValueNode",
    "state_before": {
      "task": "What is the capital of France?",
      "plan": "TEXT",
      "final_response": "The capital of France is Paris."
    },
    "state_diff": {
      "added": {
        "final_status": "SUCCESS"
      },
      "removed": {},
      "modified": {}
    },
    "run_metadata": {},
    "outcome": "success"
  }
]
```

**That's it. You just built a Deterministic agent.**