import datetime
from typing import Any

class TransparencyEngine:
    """
    Triggers and manages AI interaction disclosures for third parties affected by an agent's actions.
    Operationalises EU AI Act Art. 13 and Art. 50.
    """
    def __init__(self, logger_callback=None):
        self.logger_callback = logger_callback

    def flag(self, action_type: str, tool_name: str, affected_description: str, run_id: str = "unknown") -> None:
        """
        Record a disclosure event when a third party is affected by the agent.
        """
        event = {
            "type": "AI_INTERACTION_DISCLOSURE",
            "action_type": action_type,
            "tool_name": tool_name,
            "affected_description": affected_description,
            "timestamp": datetime.datetime.now().isoformat(),
            "run_id": run_id
        }
        
        print(f"  [TransparencyEngine] DISCLOSURE REQUIRED: Tool '{tool_name}' affected third parties ({affected_description}).")
        if self.logger_callback:
            self.logger_callback(event)
