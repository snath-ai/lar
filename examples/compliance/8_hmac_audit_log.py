"""
LÁR COMPLIANCE PATTERN: Cryptographic Audit Logs (Basic)

USAGE:
1. Initialize `GraphExecutor` with the `hmac_secret` keyword argument.
2. The executor automatically signs the final `flight_recorder.json` log with an HMAC-SHA256 signature.
3. To verify authenticity, compute the HMAC-SHA256 hash of the JSON payload (excluding the signature field) and compare it against the saved signature.
"""

import os
import json
import hmac
import hashlib
from lar import GraphExecutor, LLMNode


def main():
    print("\n" + "="*50)
    print("LAR COMPLIANCE PATTERN: Cryptographic Audit Logs")
    print("="*50)
    print("This example demonstrates how to cryptographically sign")
    print("the AuditLog output using an HMAC-SHA256 signature to")
    print("prove the execution trace was not tampered with.")
    print("-" * 50 + "\n")

    # 1. Define a simple agent graph
    agent = LLMNode(
        model_name="ollama/phi4:latest",
        prompt_template="What is the capital of {country}?",
        output_key="capital"
    )
    
    # 2. Define the Secret Key (In production, load this from Secure Vault)
    SECRET_KEY = os.getenv("LAR_HMAC_SECRET", "super_secret_enterprise_key_123")
    LOG_DIR = "hmac_compliance_logs"

    print(f"[i] Using HMAC Secret: {SECRET_KEY}")
    print(f"[i] Logs will be saved to: {LOG_DIR}/\n")

    # 3. Instantiate the Executor WITH the HMAC secret
    # EXPLICIT USAGE: Passing the `hmac_secret` to GraphExecutor is all you need to do.
    # The executor will automatically generate an HMAC-SHA256 signature and append it
    # to the resulting JSON log to prevent tampering.
    executor = GraphExecutor(log_dir=LOG_DIR, hmac_secret=SECRET_KEY)
    
    # 4. Run the graph
    print("[+] Executing graph...")
    initial_state = {"country": "Ireland"}
    
    for step_log in executor.run_step_by_step(agent, initial_state):
        print(f"  -> Step {step_log['step']} ({step_log['node']}) completed.")

    # 5. Extract the generated log file
    files = os.listdir(LOG_DIR)
    latest_log = max([os.path.join(LOG_DIR, f) for f in files], key=os.path.getctime)
    
    print(f"\n[+] Execution complete. Reading log file: {latest_log}")
    with open(latest_log, "r") as f:
        log_data = json.load(f)
        
    print("\n--- AUDIT LOG INTEGRITY CHECK ---")
    
    # The signature is appended by the logger
    saved_signature = log_data.get("signature")
    print(f"1. Signature found in log: {saved_signature}")
    
    # 6. Verify the signature manually
    clean_payload = {k: v for k, v in log_data.items() if k != "signature"}
    payload_str = json.dumps(clean_payload, sort_keys=True, separators=(',', ':'))
    
    mac = hmac.new(
        key=SECRET_KEY.encode('utf-8'),
        msg=payload_str.encode('utf-8'),
        digestmod=hashlib.sha256,
    )
    computed_signature = mac.hexdigest()
    
    print(f"2. Re-computed signature: {computed_signature}")
    
    if saved_signature == computed_signature:
        print("\n[VERIFICATION SUCCESSFUL]: The audit log has not been tampered with.")
    else:
        print("\n[VERIFICATION FAILED]: The audit log is corrupt or was tampered with.")

if __name__ == "__main__":
    main()
