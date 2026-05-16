"""
LÁR COMPLIANCE PATTERN: Cryptographic Audit Logs (High-Risk Trading)

USAGE:
1. Initialize `GraphExecutor` with the `hmac_secret` keyword argument (e.g. loaded from an AWS KMS Vault).
2. The executor automatically signs the final `flight_recorder.json` log with an HMAC-SHA256 signature.
3. To verify authenticity for SEC/FINRA audits, compute the HMAC-SHA256 hash of the JSON payload (excluding the signature field) and compare it against the saved signature.
"""

import os
import json
import hmac
import hashlib
from lar import GraphExecutor, LLMNode, FunctionalNode

def execute_trade(state: dict) -> dict:
    """Mock execution of a financial trade."""
    decision = state.get("trading_decision", "")
    if "BUY" in decision:
        state["trade_execution_status"] = "EXECUTED_BUY_100_SHARES"
        state["transaction_id"] = "TXN-99812-FIN"
    elif "SELL" in decision:
        state["trade_execution_status"] = "EXECUTED_SELL_100_SHARES"
        state["transaction_id"] = "TXN-99813-FIN"
    else:
        state["trade_execution_status"] = "HELD_POSITION"
        
    return state

def main():
    print("\n" + "="*60)
    print("LAR COMPLIANCE: High-Risk Algorithmic Trading")
    print("="*60)
    print("In highly regulated environments (FINRA, SEC), AI agents")
    print("cannot execute trades without an unalterable audit trail.")
    print("This example shows an Analyst LLM making a decision, a")
    print("functional node executing it, and the GraphExecutor sealing")
    print("the entire transaction history with an HMAC-SHA256 signature.")
    print("-" * 60 + "\n")

    # 1. Define the Trading Graph
    
    # Node 1: AI Analyst
    analyst = LLMNode(
        model_name="ollama/phi4:latest",
        prompt_template="Analyze the following market data: {market_data}. Should we BUY, SELL, or HOLD? Respond with only one of those 3 words.",
        output_key="trading_decision"
    )
    
    # Node 2: Execution Engine
    trade_executor = FunctionalNode(
        func=execute_trade
    )
    
    # Connect them
    analyst.next_node = trade_executor
    
    # 2. Setup the Secure Environment
    # In a real bank, this secret is injected via HashiCorp Vault or AWS KMS
    SECURE_VAULT_SECRET = os.getenv("BANK_KMS_SECRET", "finra_compliant_key_x99")
    AUDIT_DIR = "financial_audit_logs"

    print(f"[i] Environment Secured. KMS Key Loaded.")
    print(f"[i] Immutable Ledgers will be written to: {AUDIT_DIR}/\n")

    # 3. Instantiate the Executor wrapped in the Cryptographic Logger
    # EXPLICIT USAGE: Passing the `hmac_secret` to GraphExecutor is all you need to do
    # to turn on cryptographic auditing. Once passed, every execution log is sealed.
    executor = GraphExecutor(log_dir=AUDIT_DIR, hmac_secret=SECURE_VAULT_SECRET)
    
    # 4. Inject High-Risk State and Run
    initial_state = {
        "ticker": "AAPL",
        "market_data": "Earnings beat expectations by 12%. Guidance raised. CEO announced buybacks."
    }
    
    print(f"[+] INITIATING TRADE SEQUENCE FOR: {initial_state['ticker']}")
    
    for step_log in executor.run_step_by_step(analyst, initial_state):
        if step_log["node"] == "LLMNode":
            print(f"  -> Analyst Decision: {step_log['state_diff'].get('trading_decision', 'PENDING')}")
        elif step_log["node"] == "FunctionalNode":
            print(f"  -> Broker Execution: {step_log['state_diff'].get('trade_execution_status', 'FAILED')}")

    # 5. Extract and Validate the Cryptographic Ledger
    files = os.listdir(AUDIT_DIR)
    latest_log = max([os.path.join(AUDIT_DIR, f) for f in files], key=os.path.getctime)
    
    print(f"\n[+] Trading Complete. Sealing Ledger: {latest_log}")
    with open(latest_log, "r") as f:
        log_data = json.load(f)
        
    print("\n--- COMPLIANCE / REGULATORY CHECK ---")
    
    saved_signature = log_data.get("signature")
    print(f"1. On-Disk Signature: {saved_signature}")
    
    # Verify the signature
    clean_payload = {k: v for k, v in log_data.items() if k != "signature"}
    payload_str = json.dumps(clean_payload, sort_keys=True, separators=(',', ':'))
    
    mac = hmac.new(
        key=SECURE_VAULT_SECRET.encode('utf-8'),
        msg=payload_str.encode('utf-8'),
        digestmod=hashlib.sha256,
    )
    computed_signature = mac.hexdigest()
    
    print(f"2. KMS Re-computed:   {computed_signature}")
    
    if saved_signature == computed_signature:
        print("\n[SEC PASS]: Ledger is mathematically authentic. Trade is cleared for audit.")
    else:
        print("\n[FRAUD ALERT]: Ledger tampering detected. Signature mismatch.")

if __name__ == "__main__":
    main()
