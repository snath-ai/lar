import sys
import os
import json
import hmac
import hashlib
import argparse
from pathlib import Path

# Add Lár to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lar import GraphExecutor, LLMNode, ToolNode, RouterNode, FunctionalNode, HumanJuryNode
from lar.state import GraphState
from lar.logger import AuditLogger
from lar.compliance.authority_record import AuthorityLedger

# ==============================================================================
# SECURE RESUMABLE COMPLIANCE (HMAC-TAMPER-PROOF)
# ==============================================================================
# In enterprise environments, Human-in-the-Loop oversight (Art. 14 EU AI Act)
# can take 48+ hours for a reviewer to approve. We cannot keep a Python thread
# hanging for 2 days. 
#
# This script demonstrates:
# 1. Asynchronous Suspend: The graph pauses at the compliance gate and exits.
# 2. HMAC State Integrity: The suspended state is cryptographically signed.
#    If a malicious actor alters the JSON payload while the agent is offline,
#    the resume sequence will reject it.
# 3. Asynchronous Resume: Wakes back up, loads state, injects the human signature,
#    and completes the final action.
# ==============================================================================

STATE_FILE = "suspended_state.json"
STATE_SECRET = "super-secret-hmac-key"

def sign_state(state_dict: dict, secret: str) -> str:
    """Generate deterministic HMAC-SHA256 signature of the state dictionary."""
    payload = json.dumps(state_dict, sort_keys=True)
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Secure Resumable Compliance Agent")
    parser.add_argument("--resume", choices=["approve", "reject", "tamper"], help="Resume the graph with a decision")
    args = parser.parse_args()

    # 1. Init ledgers
    os.makedirs("resume_audit_logs", exist_ok=True)
    audit_logger = AuditLogger(log_dir="resume_audit_logs", hmac_secret=STATE_SECRET)
    authority_ledger = AuthorityLedger(hmac_secret=STATE_SECRET)

    # --------------------------------------------------------------------------
    # GRAPH DEFINITION
    # --------------------------------------------------------------------------
    
    # Node 4: Final Action
    def execute_treatment(state: GraphState):
        decision = state.get("jury_decision", "reject")
        if decision == "approve":
            print("\n   [ACTION] 🏥 Treatment Plan Executed Successfully.")
        else:
            print("\n   [ACTION] 🛑 Treatment Rejected by CMO. Halted.")

    action_node = FunctionalNode(func=execute_treatment, next_node=None)

    # Node 3: The Native Human Jury
    jury_node = HumanJuryNode(
        prompt="[URGENT] Chief Medical Officer: Approve AI treatment plan?",
        choices=["approve", "reject"],
        output_key="jury_decision",
        context_keys=["ai_recommendation"],
        authority_ledger=authority_ledger,
        stakeholder_id="cmo@hospital.com",
        stakeholder_role="Chief Medical Officer",
        action_description="Execution of AI-recommended medical treatment plan.",
        next_node=action_node
    )

    # Node 2: Suspend Node (The Pause)
    def suspend_logic(state: GraphState):
        print("\n⏳ [SuspendNode] Compliance Gate Reached. Suspending to disk...")
        
        # Serialize state and sign it
        raw_state = state.get_all()
        signature = sign_state(raw_state, STATE_SECRET)
        
        bundle = {
            "signature": signature,
            "state": raw_state
        }
        
        with open(STATE_FILE, "w") as f:
            json.dump(bundle, f, indent=2)
            
        print(f"🔒 State cryptographically signed and saved to {STATE_FILE}.")
        print("💤 Exiting process to free resources. Waiting for CMO approval.")
        sys.exit(0)

    suspend_node = FunctionalNode(func=suspend_logic, next_node=jury_node)

    # Node 1: AI Analysis
    analysis_node = LLMNode(
        model_name="ollama/phi4:latest",
        prompt_template="Patient presents with high BP. Analyze: {patient_data}. Keep it to 1 sentence.",
        output_key="ai_recommendation",
        next_node=suspend_node
    )

    # --------------------------------------------------------------------------
    # EXECUTION ENGINE
    # --------------------------------------------------------------------------
    executor = GraphExecutor(log_dir="resume_audit_logs", hmac_secret=STATE_SECRET, logger=audit_logger)

    if args.resume:
        # RESUME MODE
        if not os.path.exists(STATE_FILE):
            print(f"❌ Error: No suspended state found at {STATE_FILE}")
            sys.exit(1)
            
        print("\n🔄 RESUMING GRAPH FROM DISK...")
        with open(STATE_FILE, "r") as f:
            bundle = json.load(f)
            
        saved_signature = bundle.get("signature")
        raw_state = bundle.get("state")
        
        # Simulate a malicious tamper
        if args.resume == "tamper":
            print("\n😈 [Malicious Actor]: Tampering with state JSON to alter AI recommendation...")
            raw_state["ai_recommendation"] = "DISCHARGE PATIENT IMMEDIATELY."
            # We don't recalculate the signature! We leave the old signature intact to try to fool it.
        
        # HMAC Integrity Check
        expected_sig = sign_state(raw_state, STATE_SECRET)
        if not hmac.compare_digest(expected_sig, saved_signature):
            print("\n🚨 [SECURITY ALERT] HMAC VERIFICATION FAILED! 🚨")
            print("The state file was tampered with while the agent was suspended.")
            print("Execution HALTED.")
            sys.exit(1)
            
        print("✅ HMAC Signature Verified. State is pristine.")
        
        # Mock the built-in input to feed the CLI argument directly into HumanJuryNode
        import builtins
        _orig_input = builtins.input
        def mock_input(prompt):
            print(f"{prompt}{args.resume}")
            return args.resume
        builtins.input = mock_input
        
        # Resume execution at jury_node
        try:
            for step in executor.run_step_by_step(jury_node, raw_state):
                 print(f"Step {step.get('step')} (RESUMED): {step.get('node')} -> {step.get('outcome')}")
        finally:
            builtins.input = _orig_input
             
        authority_ledger.save("resume_audit_logs/authority_ledger.json")
        os.remove(STATE_FILE)
        print("\n✅ Resumed Execution Complete. Time machine cleaned up.")

    else:
        # START MODE
        print("\n🟢 STARTING FRESH RUN")
        initial_state = {"patient_data": "Age 45, Heart rate 110bpm. Past history of hypertension."}
        
        try:
            for step in executor.run_step_by_step(analysis_node, initial_state):
                 print(f"Step {step.get('step')}: {step.get('node')} -> {step.get('outcome')}")
        except SystemExit:
            # Expected exit from SuspendNode
            pass

if __name__ == "__main__":
    main()
