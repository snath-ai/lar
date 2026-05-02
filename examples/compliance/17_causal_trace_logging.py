import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode
from lar.logger import AuditLogger

logger = AuditLogger(log_dir="temp_causal_logs", hmac_secret="secret123")
executor = GraphExecutor(offline_mode=True, logger=logger)

# Simulating an agent logging its chain of thought alongside the state update
step1 = AddValueNode("__reasoning_trace", "User requested a weather update. I will use the weather tool.",
    AddValueNode("tool_call", "get_weather", None))

print("Running Causal Trace Logging Example...")
for step in executor.run_step_by_step(step1, {}):
    pass

print("\n--- Let's look at the generated Audit Log ---")
history = logger.get_history()
for entry in history:
    if "reasoning_trace" in entry:
        print(f"Step {entry['step']} Reasoning: {entry['reasoning_trace']}")
        print(f"Step {entry['step']} Action: {json.dumps(entry.get('state_diff', {}))}")

# Clean up temp dir
import shutil
if os.path.exists("temp_causal_logs"):
    shutil.rmtree("temp_causal_logs")
