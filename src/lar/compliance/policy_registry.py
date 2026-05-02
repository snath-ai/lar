from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

@dataclass
class ActionPolicy:
    domain: str
    process: str
    decision_type: str
    risk_tier: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reversibility: bool
    oversight_level: Literal["RETROSPECTIVE", "REALTIME", "PRE_EXECUTION"]
    regulatory_tags: List[str] = field(default_factory=list)
    affected_parties: Literal["USER_ONLY", "THIRD_PARTY", "BOTH"] = "USER_ONLY"

class PolicyRegistry:
    """
    A singleton registry mapping action_type strings to their corresponding ActionPolicy.
    Operationalises EU AI Act Art. 9 and Art. 14 by providing risk and oversight levels 
    for different agent actions based on their domain and nature.
    """
    _instance = None
    _policies: Dict[str, ActionPolicy] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PolicyRegistry, cls).__new__(cls)
            cls._instance._policies = {}
        return cls._instance

    def register(self, action_type: str, policy: ActionPolicy) -> None:
        """Register a new policy for an action type."""
        self._policies[action_type] = policy

    def get_policy(self, action_type: str) -> Optional[ActionPolicy]:
        """Retrieve a policy for an action type."""
        return self._policies.get(action_type)

    def clear(self) -> None:
        """Clear all registered policies."""
        self._policies.clear()
