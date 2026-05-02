import re
from typing import List, Optional
from lar.node import BaseNode
from lar.state import GraphState

class ProhibitedPracticeError(Exception):
    """Raised when an AI output violates EU AI Act Art. 5."""
    pass

class ProhibitedPracticeGuard(BaseNode):
    """
    A final-stage belt-and-suspenders guard that scans AI output for language 
    indicating prohibited practices under EU AI Act Art. 5 (effective Feb 2025).
    
    This includes:
    1. Subliminal, manipulative, or deceptive techniques.
    2. Exploitation of vulnerabilities (age, disability, social/economic situation).
    3. Social scoring (evaluating trustworthiness based on social behaviour).
    """
    def __init__(self, 
                 input_key: str, 
                 next_node: Optional[BaseNode] = None,
                 block_on_violation: bool = True):
        self.input_key = input_key
        self.next_node = next_node
        self.block_on_violation = block_on_violation
        
        # Simple heuristic regexes to detect risky phrasing in the final output.
        # In a full deployment, this might be supplemented with an LLM-as-a-judge.
        self.heuristics = {
            "SOCIAL_SCORING": re.compile(r'\b(social credit|trustworthiness score|social standing|behaviour score)\b', re.IGNORECASE),
            "MANIPULATION": re.compile(r'\b(must act now or|secretly track|coerce|exploit vulnerability|subliminal)\b', re.IGNORECASE),
            "VULNERABILITY_EXPLOIT": re.compile(r'\b(target elderly|target minors|leverage desperation)\b', re.IGNORECASE)
        }

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        content = str(state.get(self.input_key, ""))
        if not content:
            return self.next_node
            
        violations = []
        for risk_category, pattern in self.heuristics.items():
            if pattern.search(content):
                violations.append(risk_category)
                
        if violations:
            msg = (
                f"[ProhibitedPracticeGuard] EU AI ACT ART 5 VIOLATION DETECTED.\n"
                f"Flagged categories: {violations}\n"
                f"Output key scanned: '{self.input_key}'"
            )
            state.set("_prohibited_practice_flag", violations)
            
            print(f"\n{'!'*60}")
            print(msg)
            print(f"{'!'*60}\n")
            
            if self.block_on_violation:
                raise ProhibitedPracticeError(msg)
                
        return self.next_node
