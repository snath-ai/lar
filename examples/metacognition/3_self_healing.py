
"""
Example 27: Error Recovery Pipeline

Demonstrates how AdaptiveNode can compose a validated recovery subgraph
when a known failure condition is detected.

Scenario:
1. Agent tries to connect to a 'database'.
2. It fails (Simulated Error).
3. Router detects error -> Routes to "Doctor" (AdaptiveNode).
4. Doctor analyses error -> Composes a validated recovery subgraph:
   [ Rotate Creds -> Retry Connect ]
5. Recovery subgraph executes and the connection succeeds.

Expected Output:
- First connection attempt fails with AuthFailed error
- AdaptiveNode composes and injects recovery subgraph
- Credentials are rotated
- Connection succeeds on retry
- Final: "Connected to DB!"

Compliance tags: Art. 3(23) (via TopologyValidator), Art. 12 (Causal Trace logging)
"""

import json
from lar import (
    GraphExecutor, GraphState, 
    AdaptiveNode, TopologyValidator,
    AddValueNode, ToolNode, RouterNode, BaseNode
)
from dotenv import load_dotenv

load_dotenv()

# --- 1. Mock Database (Proper Class Instead of Globals) ---

class MockDatabase:
    """Simulated database with credential management."""
    def __init__(self):
        self.credentials = {"user": "admin", "pass": "wrong_password"}
        self.correct_password = "correct_password"
    
    def connect(self) -> str:
        """Attempt to connect with current credentials."""
        print(f"    [Tool: connect_db] Connecting with user={self.credentials['user']}...")
        
        if self.credentials["pass"] != self.correct_password:
            raise ValueError("AuthFailed: Invalid Password")
        
        return "Connected to DB!"
    
    def rotate_credentials(self) -> str:
        """Fix the password to enable successful connection."""
        print("    [Tool: rotate_creds] Rotating password to correct value...")
        self.credentials["pass"] = self.correct_password
        return "Credentials Rotated"
    
    def reset(self):
        """Reset to initial broken state for testing."""
        self.credentials["pass"] = "wrong_password"

# Global DB instance (singleton pattern for this example)
mock_db = MockDatabase()

# --- 2. Define the Tools (Now Use MockDatabase) ---

def connect_to_db(dummy_param: str = "") -> str:
    """
    Wrapper for database connection.
    Note: Parameter needed for ToolNode compatibility.
    """
    return mock_db.connect()

def rotate_credentials() -> str:
    """Wrapper for credential rotation."""
    return mock_db.rotate_credentials()

# --- 3. Define the Validator ---

validator = TopologyValidator(allowed_tools=[connect_to_db, rotate_credentials])

# --- 4. Define the Static Graph (The "Happy Path" that fails) ---

# Node 3: Success State
success_node = AddValueNode("status", "Success")

# Node 1: Initial Connection Attempt
# This will fail on first try due to wrong password
connect_node = ToolNode(
    tool_function=connect_to_db,
    input_keys=[], # No inputs needed (uses mock_db singleton)
    output_key="db_conn",
    next_node=success_node,
    error_node=None  # We'll set this to doctor below
)

# --- 5. Define the Doctor (Dynamic Node) ---

DOCTOR_PROMPT = """
You are a Self-Healing Runtime.
Error Detected: "{last_error}"

The error is "AuthFailed: Invalid Password".
Design a recovery subgraph to fix this error.

Required Steps:
1. Call 'rotate_credentials' tool (no inputs needed)
2. Call 'connect_to_db' tool again (no inputs needed)

Output ONLY valid JSON matching this schema:
{{
  "nodes": [
    {{
      "id": "fix",
      "type": "ToolNode",
      "tool_name": "rotate_credentials",
      "input_keys": [],
      "output_key": "fix_status",
      "next": "retry"
    }},
    {{
      "id": "retry",
      "type": "ToolNode",
      "tool_name": "connect_to_db",
      "input_keys": [],
      "output_key": "db_conn",
      "next": null
    }}
  ],
  "entry_point": "fix"
}}

Output ONLY the JSON, no explanations.
"""

doctor = AdaptiveNode(
    llm_model="ollama/phi4",
    prompt_template=DOCTOR_PROMPT,
    validator=validator,
    next_node=success_node,
    context_keys=["last_error"]
)

# Wire the error_node to doctor for error recovery
connect_node.error_node = doctor

# --- 6. Run with Error Handling ---

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST CASE: Self-Healing Pipeline")
    print("="*60)
    
    try:
        # Reset database to broken state
        mock_db.reset()
        
        executor = GraphExecutor()
        initial_state = {}

        print("\n--- Starting Execution ---")
        print("Initial DB State: Password is WRONG")
        print("Expected: Connection fails -> Doctor heals -> Retry succeeds\n")
        
        results = list(executor.run_step_by_step(connect_node, initial_state))
        
        # Extract final state
        final_state = results[-1].get("state_after", {})
        
        print("\n" + "="*60)
        print("RESULT")
        print("="*60)
        print(f"Final DB Connection: {final_state.get('db_conn')}")
        print(f"Status: {final_state.get('status')}")
        
        # Verify success
        if final_state.get('db_conn') == "Connected to DB!":
            print("\nSelf-healing successful!")
        else:
            print("\nSelf-healing failed!")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("Note: Ensure ollama/phi4 is installed and running")
