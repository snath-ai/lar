import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode
from lar.compliance import SyntheticMarkerNode

# Simulating a system generating an image URL or text content
content_gen = AddValueNode("generated_text", "Here is a story about a brave knight.")

marker = SyntheticMarkerNode(
    input_key="generated_text",
    marker_type="VISIBLE",
    next_node=None
)
content_gen.next_node = marker

executor = GraphExecutor(offline_mode=True)
print("Running Synthetic Content Marking Example...")

state = {}
steps = list(executor.run_step_by_step(content_gen, state))

print("\n--- Marked Content ---")
print(steps[-1]["state_after"].get("generated_text"))
