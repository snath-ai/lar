"""
RECURSIVE GRAPH COMPOSITION & PARALLELISM DEMO (Lár v1.5.0)

Demonstrates two advanced Lár features:

1.  **Recursive Subgraph Injection:**
    Using `AdaptiveNode` to compose a subgraph that itself contains `AdaptiveNode`
    instances. The "Manager" designs a graph containing two specialised sub-agents
    (Cipher & Poet), each of which composes its own validated subgraph at runtime.
    The validator is inherited at every level — safety rails propagate through the
    full recursion depth.

2.  **True Parallelism (BatchNode):**
    Using `BatchNode` to run the Cipher Agent and Poet Agent in parallel threads.
    Each thread maintains its own isolated GraphState; results are merged back to
    the main branch on completion.

Model: ollama/liquid-thinking (Recommended for reasoning) or any capable model.
"""

import sys
import os
import json
from pathlib import Path

# Add src to path for easy execution from inside 'examples/'
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

import lar
from lar import GraphState, GraphExecutor, LLMNode, RouterNode, ToolNode, BatchNode
from lar.dynamic import AdaptiveNode, TopologyValidator
from dotenv import load_dotenv

load_dotenv()

# --- 1. The "God Mode" Tool (Shared Tooling) ---
def run_python_code(code: str, *args) -> str:
    """
    Executes a snippet of Python code and returns the stdout.
    """
    import io
    from contextlib import redirect_stdout
    
    # Clean up markdown if present
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]
        
    print(f"\n[Tool: run_python_code] Executing:\n{code[:100]}...\n")
    
    f = io.StringIO()
    try:
        with redirect_stdout(f):
            # Create a local scope for variables
            local_scope = {"inputs": args}
            if len(args) > 0:
                local_scope["input_1"] = args[0]
                
            exec(code, {}, local_scope)
        output = f.getvalue()
        if not output:
             output = str(local_scope)
    except Exception as e:
        output = f"Error: {str(e)}"
        
    print(f"[Tool Output]: {output[:200]}...")
    return output

# --- 2. The Validator (Shared Rails) ---
# We allow children to use code execution.
validator = TopologyValidator(allowed_tools=[run_python_code])

# --- 3. The Manager (Recursive Parent) ---
manager_prompt = """
You are a Project Manager AI.
You have a complex project with 2 independent tracks that need to be done by SPECIALIZED SUB-AGENTS.

Track A: "Invent a new python encryption cipher (Cipher X)."
Track B: "Write a short poem about the concept of secrecy."

Your job is NOT to do the work yourself.
Your job is to DELEGATE to two `AdaptiveNode` agents using a `BatchNode` for parallel execution.

Design a graph with the following structure:
1. `parallel_workers` (BatchNode):
   - `concurrent_nodes`: ["cipher_agent", "poet_agent"]
   - `next`: "verifier"

2. `cipher_agent` (AdaptiveNode):
   - `prompt`: "You are a Cipher Specialist. Your goal is to invent a python cipher for 'Lár Secret'.\\n\\nDesign a graph that has:\\n1. An LLMNode to write the code.\\n2. A ToolNode using `run_python_code` to execute it.\\n\\nOutput only the JSON GraphSpec."
   - `output_key`: "cipher_result"

3. `poet_agent` (AdaptiveNode):
   - `prompt`: "You are a Poet who codes. Write a Python script that prints a short poem about secrecy.\\n\\nDesign a graph that has:\\n1. An LLMNode to write the script.\\n2. A ToolNode using `run_python_code` to execute it.\\n\\nOutput only the JSON GraphSpec."
   - `output_key`: "poem_result"

4. `verifier` (LLMNode):
Return ONLY the JSON GraphSpec.
Strictly follow this structure:
{
  "nodes": [
    {
       "id": "parallel_workers",
       "type": "BatchNode",
       "concurrent_nodes": ["cipher_agent", "poet_agent"],
       "next": "verifier"
    },
    {
       "id": "cipher_agent",
       "type": "AdaptiveNode",
       "prompt": "...",
       "output_key": "cipher_result"
    },
    {
       "id": "poet_agent",
       "type": "AdaptiveNode",
       "prompt": "...",
       "output_key": "poem_result"
    },
    {
       "id": "verifier",
       "type": "LLMNode",
       "prompt": "...",
       "output_key": "final_review",
       "next": null
    }
  ],
  "entry_point": "parallel_workers"
}
"""

recursive_polymath = AdaptiveNode(
    llm_model="ollama/liquid-thinking",
    prompt_template=manager_prompt,
    validator=validator,
    next_node=None
)

if __name__ == "__main__":
    print("Starting Recursive Polymath Agent (Nested Subgraphs & Parallel Execution)...")
    print("   Manager Model: ollama/liquid-thinking")
    
    # Enable verbose logging for demo
    executor = GraphExecutor(log_dir="lar_logs")
    
    initial_state = {}
    
    print("\n[Manager] Designing the Agent Team (Cipher & Poet)...")
    try:
        final_state = {}
        for step_log in executor.run_step_by_step(recursive_polymath, initial_state):
            final_state = step_log.get("state_after", {})
        
        print("\n" + "="*50)
        print("MISSION ACCOMPLISHED")
        print("="*50)
        
        print(f"\nFinal Generated Output:")
        # The parent AdaptiveNode stores its final answer in its default output_key
        result = final_state.get("dynamic_out", str(final_state))
        
        # Clean up markdown if the LLM wrapped it
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()
            
        print(f"\n{result}\n")
                
    except Exception as e:
        print(f"\nAgency Failed: {e}")
