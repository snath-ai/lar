import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, AddValueNode, HumanJuryNode
from lar.compliance import PolicyRegistry, ActionPolicy, RiskScorerNode

registry = PolicyRegistry()
registry.register("FINANCIAL_TRANSFER", ActionPolicy(
    domain="FINANCE",
    process="PAYMENT",
    decision_type="TRANSFER",
    risk_tier="HIGH",
    reversibility=False,
    oversight_level="RETROSPECTIVE",
    affected_parties="USER_ONLY"
))

# 1. Setup State
setup = AddValueNode("action_type", "FINANCIAL_TRANSFER",
    AddValueNode("model_confidence", 0.6, None))

# 2. Risk Scorer Node
jury = HumanJuryNode("Approve high risk action?", ["yes", "no"], "jury_decision")
# Set the jury next_node to None to terminate
jury.next_node = None

scorer = RiskScorerNode(next_node=None, jury_node=jury)

setup.next_node = scorer

# Reversibility=False triggers PRE_EXECUTION oversight
executor = GraphExecutor(offline_mode=True)
print("Running Risk Scored Routing Example...")
for step in executor.run_step_by_step(setup, {}):
    pass
