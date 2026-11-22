
# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/

import os
import json
import re
from typing import Dict, Any
from lar import BaseNode, GraphExecutor, LLMNode

# Mock Key for non-local providers
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "mock-key")

# --- 1. PROPOSER (THE INTELLIGENCE) ---
# Extracts intent from natural language.
PROMPT_TEMPLATE = """
You are an IT Access Control Bot.
User Request: "{user_request}"

Extract the following:
1. User Name
2. Role Requested (viewer, editor, admin)
3. Resource (dev-db, prod-db, billing-system)

Return ONLY valid JSON:
{{{{
    "user": "<name>",
    "role": "<role>",
    "resource": "<resource>"
}}}}
"""

class ProposerParserNode(BaseNode):
    """Parses LLM output into structured JSON."""
    def __init__(self, next_node=None):
        self.next_node = next_node
        
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        raw = state.get("proposal_txt", "")
        print(f"\n[Proposer] Raw: {raw}")
        
        try:
            # Attempt to find JSON blob
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(raw)
        except:
             # Fallback for demo stability
            # NEVER substitute a valid-looking access request for one we could not read.
            print("  -> Parser Failed. Marking the request unreadable (the jury will escalate it).")
            data = {"parse_error": True}
            
        print(f"  -> Parsed: {json.dumps(data)}")
        state.set("proposal", data)
        return self.next_node

# --- 2. JURY (THE POLICY) ---
# Deterministic Rules. No AI here.
class AccessPolicyJury(BaseNode):
    def __init__(self, next_node=None):
        self.next_node = next_node

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        proposal = state.get("proposal", {})
        if proposal.get("parse_error") or not proposal.get("role") or not proposal.get("resource"):
            print("\n[Jury] Request unreadable or incomplete.")
            print("  -> ⚠️  VERDICT: ESCALATE (cannot evaluate policy on missing fields)")
            state.set("verdict", "ESCALATE")
            state.set("reason", "Request could not be read; a person must decide.")
            return self.next_node
        role = str(proposal.get("role", "")).lower()
        resource = str(proposal.get("resource", "")).lower()
        
        print(f"\n[Jury] Evaluating Policy for {role} access to {resource}...")
        
        # POLICY RULES
        risky_resource = "prod" in resource or "billing" in resource
        risky_role = "admin" in role
        
        if risky_resource or risky_role:
            print("  -> ⚠️  VERDICT: ESCALATE (High Risk Detected)")
            state.set("verdict", "ESCALATE")
            state.set("reason", "Admin/Prod access requires Manager Approval.")
        else:
            print("  -> ✅ VERDICT: APPROVED (Standard Access)")
            state.set("verdict", "APPROVED")
            
        return self.next_node

# --- 3. SUPERVISOR (THE ROUTER) ---
class SupervisorNode(BaseNode):
    def __init__(self, approved_node, escalate_node):
        self.approved_node = approved_node
        self.escalate_node = escalate_node
        
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        verdict = state.get("verdict")
        if verdict == "APPROVED":
            return self.approved_node
        return self.escalate_node

# --- 4. HUMAN MANAGER (THE INTERRUPT) ---
class HumanManagerNode(BaseNode):
    def __init__(self, next_node=None):
        self.next_node = next_node
        
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        reason = state.get("reason")
        proposal = state.get("proposal")
        
        print(f"\n[Human Manager] 🛑 STOP. Escalation Triggered.")
        print(f"  Reason: {reason}")
        print(f"  Request: {proposal}")
        
        # In a real app, this would be an API pause.
        # Here we simulate with input()
        decision = input("  > Manager, do you APPROVE this? (y/n): ").strip().lower()
        
        if decision == 'y':
            print("  -> Manager APPROVED override.")
            state.set("manager_override", True)
            state.set("verdict", "APPROVED")
            return self.next_node
        else:
            print("  -> Manager DENIED request.")
            state.set("verdict", "DENIED")
            return None # Stop graph

# --- 5. KERNEL (THE EXECUTION) ---
class AccessKernelNode(BaseNode):
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        proposal = state.get("proposal")
        print(f"\n[Kernel] 🟢 GRANTING ACCESS: User={proposal['user']} -> {proposal['resource']} ({proposal['role']}).")
        print("  -> Success. Audit log updated.")
        return None

# --- WIRING ---

# 1. Define Leaf Nodes first
kernel = AccessKernelNode()
human = HumanManagerNode(next_node=kernel)

# 2. Define Router
supervisor = SupervisorNode(approved_node=kernel, escalate_node=human)

# 3. Define Jury
jury = AccessPolicyJury(next_node=supervisor)

# 4. Define Parser
parser = ProposerParserNode(next_node=jury)

# 5. Define LLM
proposer = LLMNode(
    model_name="ollama/phi4",
    prompt_template=PROMPT_TEMPLATE,
    output_key="proposal_txt",
    next_node=parser
)

# --- EXECUTION ---
graph = GraphExecutor()

def run_scenario(name, request):
    print(f"\n\n{'='*60}\nSCENARIO: {name}\n{'='*60}")
    initial_state = {"user_request": request}
    try:
        # We assume run_step_by_step yields control so input() works
        for _ in graph.run_step_by_step(proposer, initial_state):
            pass
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Case 1: Safe
    run_scenario("Safe Request", "Can granted read access to dev-db for Alice?")
    
    # Case 2: Risky (Requires Input)
    run_scenario("Risky Request", "Please grant Bob ADMIN access to PROD-DB immediately.")
