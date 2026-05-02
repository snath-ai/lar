import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode
from lar.compliance import PIIRedactionEngine
from lar.logger import AuditLogger

# Redact emails and ssn, but leave other things
redactor = PIIRedactionEngine(sensitive_keys=["email", "ssn"], mode="REDACT")
logger = AuditLogger(log_dir="temp_logs", hmac_secret="secret123", pii_redactor=redactor)

executor = GraphExecutor(offline_mode=True, logger=logger)

# Simulating an agent processing a user's PII
setup = AddValueNode("email", "user@example.com", 
    AddValueNode("ssn", "000-00-0000", 
        AddValueNode("public_data", "Non-sensitive", None)))

print("Running PII Redaction Example...")
for step in executor.run_step_by_step(setup, {}):
    pass

print("\n--- Let's look at the generated Audit Log History ---")
history = logger.get_history()
for entry in history:
    print(f"Step {entry['step']}:")
    print(f"  state_after: {json.dumps(entry.get('state_after', {}))}")
    print(f"  state_diff: {json.dumps(entry.get('state_diff', {}))}")

# Clean up temp dir
import shutil
if os.path.exists("temp_logs"):
    shutil.rmtree("temp_logs")
