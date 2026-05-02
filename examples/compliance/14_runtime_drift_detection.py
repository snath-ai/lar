import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode
from lar.compliance import RuntimeStateVersioner

versioner = RuntimeStateVersioner()

# Simulating an agent changing its tools over time
step1 = AddValueNode("tool_catalogue", ["search_web", "read_file"],
    AddValueNode("state_schema_keys", ["query", "result"],
        AddValueNode("policy_bindings", {"search_web": "LOW_RISK"})))

step2 = AddValueNode("tool_catalogue", ["search_web", "read_file", "execute_code"],
    AddValueNode("state_schema_keys", ["query", "result"],
        AddValueNode("policy_bindings", {"search_web": "LOW_RISK", "execute_code": "HIGH_RISK"})))

step1.next_node.next_node.next_node = step2

executor = GraphExecutor(offline_mode=True, versioner=versioner)
print("Running Runtime Drift Detection Example...")
print("Note: Executor takes a snapshot every 10 steps. We'll simulate it by calling manually for demo.")

state = {}
executor.run_step_by_step(step1, state)

# Simulate GraphExecutor capturing periodic snapshots:
snap1 = versioner.snapshot(
    tool_catalogue=["search_web", "read_file"],
    state_schema_keys=["query", "result"],
    policy_bindings={"search_web": "LOW_RISK"}
)
print(f"Snapshot 1: {json.dumps(snap1, indent=2)}")

snap2 = versioner.snapshot(
    tool_catalogue=["search_web", "read_file", "execute_code"], # Drift!
    state_schema_keys=["query", "result"],
    policy_bindings={"search_web": "LOW_RISK", "execute_code": "HIGH_RISK"}
)
print(f"Snapshot 2: {json.dumps(snap2, indent=2)}")
