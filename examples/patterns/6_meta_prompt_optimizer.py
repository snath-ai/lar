# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/
import os
import sys
from dotenv import load_dotenv
load_dotenv()
# LiteLLM Helper: Map GOOGLE_API_KEY to GEMINI_API_KEY if needed
if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from lar.node import LLMNode, ToolNode, RouterNode, AddValueNode
from lar.executor import GraphExecutor

"""
Example 8: Meta-Prompt Optimizer (Advanced)
------------------------------------------
Concepts:
- Iterative Prompt Refinement
- Evaluating performance
- Dynamic State Updates
"""

# Initial State
initial_prompt = "You are a helpful assistant."

# 1. The Student (The agent being optimized)
student = LLMNode(
    model_name="gemini/gemini-2.5-pro",
    # Note: We use {current_prompt} dynamically from state!
    prompt_template="{current_prompt}\n\nTask: Solve this math problem: 24 * 12 used to be 288, but what is 24 * 13?", 
    output_key="answer"
)

# 2. The Evaluator
def check_answer(state):
    ans = state.get("answer", "")
    if "312" in ans:
        return "CORRECT"
    return "WRONG"

evaluator = RouterNode(
    decision_function=check_answer,
    path_map={
        "CORRECT": None, # Success!
        "WRONG": None # Wired below
    }
)

# 3. The Optimizer (Meta-Agent)
optimizer = LLMNode(
    model_name="gemini-1.5-pro",
    prompt_template=(
        "The previous system prompt was: '{current_prompt}'.\n"
        "It failed to make the model solve '24 * 13'.\n"
        "Write a BETTER, more specific system prompt to ensure the model acts like a Calculator."
        "Output ONLY the new prompt."
    ),
    output_key="current_prompt" # Updates the prompt in state!
)

# Wiring
student.next_node = evaluator
# If WRONG, go to optimizer -> then back to student
optimizer.next_node = student
evaluator.path_map["WRONG"] = optimizer

if __name__ == "__main__":
    executor = GraphExecutor()
    print("--- Running Meta-Prompt Optimizer ---")
    
    start_state = {"current_prompt": "You are a poet."} # Bad prompt intentionally
    
    for step in executor.run_step_by_step(student, start_state, max_steps=10):
        print(f"Step {step['step']} ({step['node']})")
        if step['node'] == "LLMNode" and "current_prompt" in step['state_diff'].get("added", {}):
            print(f"  [Optimizer] New Prompt: {step['state_diff']['added']['current_prompt']}")
        if step['outcome'] == "success" and step['node'] == "RouterNode":
             # If router ends, we found it.
             pass
