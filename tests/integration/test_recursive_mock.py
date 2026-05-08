
import sys
import os
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add core source to Path
sys.path.append(str(Path(__file__).parent.parent / "src"))

import lar
from lar import GraphState, GraphExecutor, LLMNode, RouterNode, ToolNode, BatchNode
from lar.adaptive import DynamicNode, TopologyValidator

# --- MOCKING ---
from unittest.mock import patch
import lar.node # EXPLICIT IMPORT

def mock_completion_side_effect(*args, **kwargs):
    model = kwargs.get("model")
    messages = kwargs.get("messages")
    prompt = messages[-1]["content"] if messages else ""
    
    # 1. Manager Prompt -> Returns JSON with BatchNode ("parallel_workers")
    if "Project Manager AI" in prompt:
        print(f"  [Mock LLM] generating Manager GraphSpec...")
        return _mock_response({
            "nodes": [
                {
                    "id": "parallel_workers",
                    "type": "BatchNode",
                    "concurrent_nodes": ["cipher_agent", "poet_agent"],
                    "next": "verifier"
                },
                {
                    "id": "cipher_agent",
                    "type": "DynamicNode",
                    "prompt": "Cipher Specialist Prompt...",
                    "output_key": "cipher_result"
                },
                {
                    "id": "poet_agent",
                    "type": "DynamicNode",
                    "prompt": "Poet who codes...",
                    "output_key": "poem_result"
                },
                {
                    "id": "verifier",
                    "type": "LLMNode",
                    "prompt": "Review: {{cipher_result}} {{poem_result}}",
                    "output_key": "final_review",
                    "next": None
                }
            ],
            "entry_point": "parallel_workers"
        })
    
    # 2. Cipher Agent Prompt -> Returns JSON with Code Generation
    elif "Cipher Specialist" in prompt:
         print(f"  [Mock LLM] generating Cipher Agent GraphSpec...")
         return _mock_response({
             "nodes": [
                 {
                     "id": "coder",
                     "type": "LLMNode",
                     "prompt": "Write cipher code.",
                     "output_key": "code",
                     "next": "executor"
                 },
                 {
                     "id": "executor",
                     "type": "ToolNode",
                     "tool_name": "run_python_code",
                     "input_keys": ["code"],
                     "output_key": "cipher_result",
                     "next": None
                 }
             ],
             "entry_point": "coder"
         })

    # 3. Poet Agent Prompt -> Returns JSON with Poem Generation
    elif "Poet who codes" in prompt:
         print(f"  [Mock LLM] generating Poet Agent GraphSpec...")
         return _mock_response({
             "nodes": [
                 {
                     "id": "poet",
                     "type": "LLMNode",
                     "prompt": "Write poem code.",
                     "output_key": "code",
                     "next": "printer"
                 },
                 {
                     "id": "printer",
                     "type": "ToolNode",
                     "tool_name": "run_python_code",
                     "input_keys": ["code"],
                     "output_key": "poem_result",
                     "next": None
                 }
             ],
             "entry_point": "poet"
         })
         
    # 4. Leaf Code/Poem Generators -> Returns Python Code
    elif "Write cipher code" in prompt:
         return _mock_response("print('Cipher Result: XYZ-123')")
    elif "Write poem code" in prompt:
         return _mock_response("print('Poem Result: Roses are red...')")
    
    # 5. Verifier -> Returns Review
    elif "Review:" in prompt:
         return _mock_response("Verifier Result: Excellent work.")
         
    print(f"  [Mock LLM] Unknown Prompt: {prompt[:50]}...")
    return _mock_response("Unknown Prompt")

def _mock_response(content):
    if isinstance(content, dict):
        content = json.dumps(content)
    
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = content
    mock_resp.choices[0].message.reasoning_content = None # Ensure no reasoning confusion
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 10
    return mock_resp

# Apply Patch Globally
patcher = patch('lar.node.completion', side_effect=mock_completion_side_effect)
patcher.start()



# --- The "God Mode" Tool (Shared Tooling) ---
def run_python_code(code: str, *args) -> str:
    # Minimal mock execution
    if "Cipher Result" in code: return "Cipher Result: XYZ-123"
    if "Poem Result" in code: return "Poem Result: Roses are red..."
    return "Executed Code."

# --- Validator ---
validator = TopologyValidator(allowed_tools=[run_python_code])

# --- Manager Definition ---
# Same prompt as original
manager_prompt = "You are a Project Manager AI..." 

recursive_polymath = DynamicNode(
    llm_model="mock-model", 
    prompt_template=manager_prompt,
    validator=validator,
    next_node=None 
)

def test_recursive_mock():
    print("Starting Recursive Polymath Experiment (MOCKED)...")
    executor = GraphExecutor(log_dir="test_logs")
    
    initial_state = {}
    
    logs = []
    # Run!
    for step in executor.run_step_by_step(recursive_polymath, initial_state):
        print(f"Step {step.get('step')}: {step.get('node')} - {step.get('outcome')}")
        logs.append(step)
    
    # Verification
    final_state = logs[-1]["state_after"]
    print("\nFinal State Keys:", final_state.keys())
    
    assert "cipher_result" in final_state
    assert "poem_result" in final_state
    assert final_state["cipher_result"] == "Cipher Result: XYZ-123"
    assert final_state["poem_result"] == "Poem Result: Roses are red..."
    
    print("\n✅ Mock Test Completed Successfully. Framework logic verified.")

if __name__ == "__main__":
    test_recursive_mock()
