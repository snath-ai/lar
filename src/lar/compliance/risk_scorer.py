from typing import Optional, Literal
from lar.node import BaseNode, HumanJuryNode
from lar.state import GraphState
from .policy_registry import PolicyRegistry

class RiskScorerNode(BaseNode):
    """
    Dynamically computes the necessary oversight level for an action instance based on 
    the action's registered policy and live telemetry.
    Operationalises EU AI Act Art. 14 (Commensurate human oversight).
    """
    def __init__(self, 
                 next_node: BaseNode, 
                 jury_node: HumanJuryNode,
                 confidence_key: str = "model_confidence", 
                 action_type_key: str = "action_type"):
        self.next_node = next_node
        self.jury_node = jury_node
        self.confidence_key = confidence_key
        self.action_type_key = action_type_key
        self._validate_next_node(next_node)
        self._validate_next_node(jury_node, "jury_node")

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        action_type = state.get(self.action_type_key)
        confidence = state.get(self.confidence_key, 1.0)
        
        registry = PolicyRegistry()
        policy = registry.get_policy(action_type) if action_type else None
        
        # Default fallback
        oversight_level = "RETROSPECTIVE"
        
        if policy:
            oversight_level = policy.oversight_level
            
            # Escalate if irreversible
            if not policy.reversibility:
                oversight_level = "PRE_EXECUTION"
                
            # Escalate if confidence is low
            if confidence < 0.7:
                if oversight_level == "RETROSPECTIVE":
                    oversight_level = "REALTIME"
                elif oversight_level == "REALTIME":
                    oversight_level = "PRE_EXECUTION"
                    
            # Escalate if third parties affected
            if policy.affected_parties in ["THIRD_PARTY", "BOTH"]:
                if oversight_level == "RETROSPECTIVE":
                    oversight_level = "REALTIME"
                    
        state.set("computed_oversight_level", oversight_level)
        print(f"  [RiskScorerNode]: Action '{action_type}' scored as {oversight_level}")
        
        if oversight_level == "PRE_EXECUTION":
            return self.jury_node
        return self.next_node
