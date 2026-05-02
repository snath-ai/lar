import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode, HumanJuryNode
from lar.compliance import BiasFilterNode

# Setup human jury for oversight if bias is detected
jury = HumanJuryNode("Review flagged content for bias", ["approve", "reject"], "jury_decision")
jury.next_node = None

# Filter node watches the 'draft_report' key
filter_node = BiasFilterNode(
    input_key="draft_report",
    sensitive_terms=["gender", "race"], # Simplified heuristics
    jury_node=jury,
    next_node=None
)

# Simulating an agent generating a report that accidentally triggers a sensitive term
setup = AddValueNode("draft_report", "The candidate's gender might be a factor in this role.", filter_node)

executor = GraphExecutor(offline_mode=True)
print("Running Runtime Bias Detection Example...")
for step in executor.run_step_by_step(setup, {}):
    pass
