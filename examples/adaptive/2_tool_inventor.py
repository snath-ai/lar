
"""
Example 26: Runtime Code Generation

Demonstrates a validated subgraph that implements a two-step code generation
and execution pipeline. The AdaptiveNode composes:
1. LLMNode — writes a Python function into state key 'generated_code'.
2. ToolNode — executes the code via a safety-validated wrapper.

SECURITY WARNING:
The 'safe_python_exec' tool uses AST analysis as a first-pass safety check,
but in production all code execution MUST run in a hardened sandbox:
- Docker containers (Docker SDK)
- Cloud sandboxes (e.g., e2b.dev)
- WebAssembly runtimes
Never execute LLM-generated code with full system access.

Expected Output:
LLM generates a fibonacci function -> Executes it -> Returns 144 (12th Fibonacci number)

Compliance tags: Art. 3(23) (via TopologyValidator), Art. 12 (Causal Trace logging)
"""

import ast
import sys
from lar import (
    GraphExecutor, GraphState,
    AdaptiveNode, TopologyValidator,
    AddValueNode
)
from dotenv import load_dotenv

load_dotenv()

# --- 1. Define the Execution Tool with Safety Checks ---

DANGEROUS_MODULES = {
    'os', 'sys', 'subprocess', 'eval', 'exec', 'compile',
    'open', '__import__', 'input', 'file', 'globals', 'locals'
}

def validate_code_safety(code_str: str) -> tuple[bool, str]:
    """
    Validates Python code for dangerous patterns using AST.
    Returns: (is_safe, error_message)
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return False, f"Syntax Error: {e}"
    
    # Check for dangerous imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name in DANGEROUS_MODULES:
                    return False, f"Forbidden import: {name.name}"
        
        if isinstance(node, ast.ImportFrom):
            if node.module in DANGEROUS_MODULES:
                return False, f"Forbidden import: {node.module}"
        
        # Check for dangerous function calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in {'eval', 'exec', 'compile', '__import__'}:
                    return False, f"Forbidden function: {node.func.id}"
    
    return True, ""

def safe_python_exec(code_str: str) -> str:
    """
    Executes a Python function string after safety validation.
    Assumes the code defines a function named 'solution'.
    
    Returns: Result of solution() or error message
    """
    print(f"\n    [Tool: python_exec] Validating code...")
    
    # Strip markdown formatting
    cleaned = code_str.replace("```python", "").replace("```", "").strip()
    
    # Validate safety
    is_safe, error = validate_code_safety(cleaned)
    if not is_safe:
        return f"SECURITY ERROR: {error}"
    
    print(f"    [Tool: python_exec] Code passed validation")
    print(f"    [Tool: python_exec] Executing code (first 100 chars):\n    {cleaned[:100]}...")
    
    try:
        # Restricted execution environment
        # Only allow basic builtins, no dangerous ones
        safe_builtins = {
            'range': range,
            'len': len,
            'int': int,
            'float': float,
            'str': str,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'print': print
        }
        
        local_scope = {}
        exec(cleaned, {"__builtins__": safe_builtins}, local_scope)
        
        if "solution" not in local_scope:
            return "ERROR: Code did not define 'solution()' function"
        
        if not callable(local_scope["solution"]):
            return "ERROR: 'solution' is not a function"
        
        # Execute the generated function
        result = local_scope["solution"]()
        print(f"    [Tool: python_exec] Execution successful: {result}")
        return str(result)
        
    except Exception as e:
        return f"EXECUTION ERROR: {type(e).__name__}: {str(e)}"

# --- 2. Define the Validator ---

validator = TopologyValidator(allowed_tools=[safe_python_exec])

# --- 3. Define the Dynamic Node ---

# The Architect Prompt teaches the LLM to build a "Coder -> Executor" chain
DYNAMIC_PROMPT = """
You are a Software Architect.
User Request: "{request}"

Design a subgraph to solve this using Python code.

IMPORTANT: Generate ONLY valid JSON, no markdown, no explanations.

1. Create an LLMNode ("coder") to write Python code:
   - Prompt: "Write a Python function named 'solution' with no arguments that returns the answer to: {request}. Use only basic Python (no imports). Return ONLY the code."
   - Output Key: "generated_code"
   
2. Create a ToolNode ("executor") to run the code:
   - Tool Name: "safe_python_exec"
   - Input Keys: ["generated_code"]
   - Output Key: "result"

Output JSON matching this EXACT schema:
{{
  "nodes": [
    {{
      "id": "coder",
      "type": "LLMNode",
      "prompt": "Write a Python function named 'solution' with no arguments that returns: {request}. Use only basic Python, no imports. Return ONLY the code.",
      "output_key": "generated_code",
      "next": "executor"
    }},
    {{
      "id": "executor",
      "type": "ToolNode",
      "tool_name": "safe_python_exec",
      "input_keys": ["generated_code"],
      "output_key": "result",
      "next": null
    }}
  ],
  "entry_point": "coder"
}}
"""

end_node = AddValueNode("status", "Done")

dynamic_architect = AdaptiveNode(
    llm_model="ollama/phi4",
    prompt_template=DYNAMIC_PROMPT,
    validator=validator,
    next_node=end_node,
    context_keys=["request"]
)

# --- 4. Run with Error Handling ---

entry = dynamic_architect

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST CASE: Self-Programming Agent")
    print("="*60)
    print("Task: Calculate 12th Fibonacci number")
    print("Expected: Generate fib function -> Execute -> Return 144")
    print("="*60)
    
    try:
        executor = GraphExecutor()
        initial_state = {
            "request": "Calculate the 12th Fibonacci number"
        }

        print("\n--- Starting Execution ---\n")
        results = list(executor.run_step_by_step(entry, initial_state))
        
        final_state = results[-1].get("state_after", {})
        
        print("\n" + "="*60)
        print("RESULT")
        print("="*60)
        print(f"Final Result: {final_state.get('result')}")
        print(f"Status: {final_state.get('status')}")
        
        # Verify correctness
        expected = "144"
        if final_state.get('result') == expected:
            print(f"\nCorrect! 12th Fibonacci number is {expected}")
        elif final_state.get('result'):
            print(f"\nGot: {final_state.get('result')}, Expected: {expected}")
        else:
            print("\nExecution failed - check logs above")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("Note: Ensure ollama/phi4 is installed and running")
