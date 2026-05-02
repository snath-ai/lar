from typing import List, Optional
from lar.node import BaseNode, HumanJuryNode
from lar.state import GraphState

class BiasFilterNode(BaseNode):
    """
    Evaluates state variables against fairness criteria to detect potential bias.
    If bias is detected (simulated here via keyword heuristics or a threshold),
    it routes to a human jury for oversight.
    Operationalizes prEN 18283 (Bias Management).
    """
    def __init__(self, 
                 input_key: str, 
                 sensitive_terms: List[str] = None,
                 next_node: Optional[BaseNode] = None,
                 jury_node: Optional[HumanJuryNode] = None):
        self.input_key = input_key
        self.sensitive_terms = sensitive_terms or ["race", "gender", "age", "religion", "disability", "ethnicity"]
        self.next_node = next_node
        self.jury_node = jury_node

    def execute(self, state: GraphState):
        content = str(state.get(self.input_key, "")).lower()
        
        # Simple heuristic bias detection: check if sensitive terms are present in the output
        bias_detected = any(term in content for term in self.sensitive_terms)
        
        state.set("bias_detected", bias_detected)
        
        if bias_detected and self.jury_node:
            print(f"  [BiasFilterNode] WARNING: Potential bias detected regarding sensitive terms in '{self.input_key}'. Escalating to Human Jury.")
            # Route to human jury
            return self.jury_node
            
        return self.next_node
