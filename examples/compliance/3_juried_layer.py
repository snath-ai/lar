
import os
import json
import re
from lar import BaseNode, GraphExecutor, ToolNode, LLMNode
from typing import Dict, Any

# Ensure API Key (Mock setup for other providers, but we use Ollama here)
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "mock-key")

# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/

# --- 1. THE PROPOSER (LLM) ---
# We use a real LLM (phi4 via Ollama) to generate the proposal.
# It MUST output JSON.
PROMPT_TEMPLATE = """
You are a Customer Service AI.
The user request is: "{user_request}"

You must propose a refund action.
Return ONLY valid JSON in this format:
{{{{
    "action": "refund",
    "amount": <integer_value>,
    "reason": "<short_reason>"
}}}}
Do not write any text outside the JSON.
"""


# Validates the Proposer's output
class JsonParserNode(BaseNode):
    def __init__(self, next_node=None):
        self.next_node = next_node
        
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        raw_text = state.get("proposal_txt", "")
        print(f"\n[Parser] Raw LLM Output: {raw_text}")
        
        # Simple regex to extract JSON if there is extra chatter
        try:
            # Try direct parse
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try regex extraction
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                # Fallback for demo safety
                # NEVER turn "could not read the proposal" into a valid-looking proposal (the old
                # fallback was a $0 refund, which the jury then APPROVED). Mark it unreadable instead.
                print("  [Parser] ⚠️ Failed to parse JSON. Marking the proposal unreadable.")
                data = {"parse_error": True}
        
        state.set("proposal", data)
        print(f"  [Parser] Parsed Proposal: {json.dumps(data)}")
        return self.next_node

# --- 3. THE JURY (DETERMINISTIC) ---
class JuryNode(BaseNode):
    def __init__(self, next_node=None):
        self.next_node = next_node

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        proposal = state.get("proposal", {})
        amount = proposal.get("amount")

        # INVARIANT 0: an unreadable or malformed proposal is never approved, and never defaulted to $0.
        if (proposal.get("parse_error") or isinstance(amount, bool)
                or not isinstance(amount, (int, float)) or amount <= 0):
            print("\n[Jury] Proposal missing or malformed.")
            print("  -> ❌ VERDICT: REJECTED (no valid positive amount)")
            state.set("verdict", "REJECTED")
            state.set("rejection_reason", "Proposal could not be read as a valid positive amount; sent for review.")
            return self.next_node

        print(f"\n[Jury] Deliberating on proposal: ${amount} refund...")
        
        # INVARIANT: Refunds over $500 require Human Override (or are rejected)
        if amount > 500:
            print("  -> ❌ VERDICT: REJECTED (Amount > $500)")
            state.set("verdict", "REJECTED")
            state.set("rejection_reason", "Policy Violation: Refunds > $500 require Level 2 Auth.")
        else:
            print("  -> ✅ VERDICT: APPROVED")
            state.set("verdict", "APPROVED")
        
        return self.next_node

# --- 4. THE KERNEL (GATEKEEPER) ---
class ExecutionNode(BaseNode):
    def __init__(self, next_node=None):
        self.next_node = next_node

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        verdict = state.get("verdict")
        
        if verdict == "APPROVED":
            proposal = state.get("proposal")
            print(f"\n[Kernel] 🟢 COMMIT: processing_refund(${proposal['amount']})... SUCCESS.")
            state.set("final_output", f"Refund of ${proposal['amount']} processed successfully.")
        else:
            reason = state.get("rejection_reason")
            print(f"\n[Kernel] 🔴 BLOCKED: Execution denied by Jury. Reason: {reason}")
            state.set("final_output", f"Action Blocked: {reason}")
            
        return None  # End of graph

# --- WIRING ---
executor = GraphExecutor()

# Initialize Nodes
kernel = ExecutionNode()
jury = JuryNode(next_node=kernel)
parser = JsonParserNode(next_node=jury)

# Wire the LLM
# Ensure you have run: `ollama pull phi4`
proposer = LLMNode(
    model_name="ollama/phi4", 
    prompt_template=PROMPT_TEMPLATE,
    output_key="proposal_txt",
    next_node=parser # Wired directly! 
)

# --- 5. EXECUTION HELPER ---
def run_and_print(executor, start_node, initial_state):
    print(f"--- STARTING RUN ---")
    try:
        for step_log in executor.run_step_by_step(start_node, initial_state):
            pass
    except Exception as e:
        print(f"Error: {e}")
        print("Ensure you have 'ollama' running and 'phi4' pulled: `ollama pull phi4`")
        
    print("--- RUN COMPLETE ---\n")

# --- RUN DEMO ---
print("--- CASE 1: SAFE PROPOSAL ($100) ---")
# Prompt engineering: We explicitly ask for 100
initial_state_1 = {"user_request": "Please refund the customer $100 for the delay."}
run_and_print(executor, proposer, initial_state_1)

print("\n\n--- CASE 2: RISKY PROPOSAL ($1000) ---")
# Prompt engineering: We explicitly ask for 1000
initial_state_2 = {"user_request": "Please refund the enterprise client $1000 immediately."}
run_and_print(executor, proposer, initial_state_2)
