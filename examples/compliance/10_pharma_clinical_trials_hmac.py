"""
LÁR COMPLIANCE PATTERN: Cryptographic Audit Logs (FDA 21 CFR 11 / GxP)

USAGE:
1. Initialize `GraphExecutor` with the `hmac_secret` keyword argument (e.g. loaded from a strict access-controlled Vault).
2. The executor automatically signs the final `flight_recorder.json` log with an HMAC-SHA256 signature to comply with FDA Part 11 requirements.
3. To verify data integrity for clinical trials, compute the HMAC-SHA256 hash of the JSON payload (excluding the signature field) and compare it against the saved signature.
"""

import os
import json
import hmac
import hashlib
from lar import GraphExecutor, LLMNode, FunctionalNode
def router_node(state: dict) -> dict:
    """Mock routing of sensitive clinical trial data based on LLM analysis."""
    classification = state.get("trial_classification", "")
    
    if "ADVERSE_EVENT" in classification:
        state["routing_action"] = "ESCALATED_TO_PHARMACOVIGILANCE"
        state["priority"] = "CRITICAL"
    else:
        state["routing_action"] = "FILED_ROUTINE_MONITORING"
        state["priority"] = "NORMAL"
        
    return state

def main():
    print("\n" + "="*65)
    print("LAR COMPLIANCE: Pharmaceutical Clinical Trials (GxP/FDA 21 CFR 11)")
    print("="*65)
    print("In life sciences, AI processing clinical trial data must produce")
    print("a tamper-proof audit trail (FDA 21 CFR Part 11).")
    print("This example shows a Clinical AI analyzing patient notes for")
    print("Adverse Events, routing the data, and cryptographically sealing")
    print("the entire reasoning trace using a secure GxP vault key.")
    print("-" * 65 + "\n")

    # 1. Define the Clinical Graph
    
    # Node 1: Clinical AI Analyst
    clinical_ai = LLMNode(
        model_name="ollama/phi4:latest",
        prompt_template="Analyze the following clinical trial patient note. Does it describe a Severe Adverse Event (SAE) requiring immediate escalation? \nPatient Note: {patient_note}\n\nRespond with exactly one word: 'ADVERSE_EVENT' or 'ROUTINE'.",
        output_key="trial_classification"
    )
    
    # Node 2: Data Router
    data_router = FunctionalNode(
        func=router_node
    )
    
    # Connect them
    clinical_ai.next_node = data_router
    
    # 2. Setup the Secure Environment
    # In a pharmaceutical company, this secret is strictly controlled
    GXP_VAULT_KEY = os.getenv("PHARMA_GXP_SECRET", "fda_compliant_vault_key_777")
    AUDIT_DIR = "clinical_audit_logs"

    print(f"[i] Environment Secured. FDA Part 11 Compliance Key Loaded.")
    print(f"[i] Immutable Clinical Ledgers will be written to: {AUDIT_DIR}/\n")

    # 3. Instantiate the Executor wrapped in the Cryptographic Logger
    # EXPLICIT USAGE: The `hmac_secret` parameter acts as your cryptographic seal.
    # By simply passing it here, the engine ensures the JSON log cannot be altered
    # without invalidating the mathematical signature.
    executor = GraphExecutor(log_dir=AUDIT_DIR, hmac_secret=GXP_VAULT_KEY)
    
    # 4. Inject High-Risk Patient State and Run
    initial_state = {
        "patient_id": "SUBJ-9921-A",
        "patient_note": "Patient reports severe chest pain and shortness of breath 2 hours after administering the trial compound. Vitals are unstable."
    }
    
    print(f"[+] INITIATING CLINICAL ANALYSIS FOR: {initial_state['patient_id']}")
    
    for step_log in executor.run_step_by_step(clinical_ai, initial_state):
        if step_log["node"] == "LLMNode":
            print(f"  -> AI Classification: {step_log['state_diff'].get('trial_classification', 'PENDING')}")
        elif step_log["node"] == "DataRouter":
            print(f"  -> System Action:     {step_log['state_diff'].get('routing_action', 'FAILED')}")

    # 5. Extract and Validate the Cryptographic Ledger
    files = os.listdir(AUDIT_DIR)
    latest_log = max([os.path.join(AUDIT_DIR, f) for f in files], key=os.path.getctime)
    
    print(f"\n[+] Processing Complete. Sealing Clinical Ledger: {latest_log}")
    with open(latest_log, "r") as f:
        log_data = json.load(f)
        
    print("\n--- FDA 21 CFR PART 11 COMPLIANCE CHECK ---")
    
    saved_signature = log_data.get("signature")
    print(f"1. On-Disk Signature: {saved_signature}")
    
    # Verify the signature
    clean_payload = {k: v for k, v in log_data.items() if k != "signature"}
    payload_str = json.dumps(clean_payload, sort_keys=True, separators=(',', ':'))
    
    mac = hmac.new(
        key=GXP_VAULT_KEY.encode('utf-8'),
        msg=payload_str.encode('utf-8'),
        digestmod=hashlib.sha256,
    )
    computed_signature = mac.hexdigest()
    
    print(f"2. KMS Re-computed:   {computed_signature}")
    
    if saved_signature == computed_signature:
        print("\n[QA PASS]: Ledger is mathematically authentic. Trial data integrity verified.")
    else:
        print("\n[FRAUD WARNING]: Ledger tampering detected. Regulatory compliance breached.")

if __name__ == "__main__":
    main()
