from typing import Optional, List, Dict, Any
import logging

from lar.node import BaseNode
from lar.state import GraphState

logger = logging.getLogger(__name__)

class PromptInjectionError(Exception):
    """Raised when an adversarial prompt injection is detected."""
    pass

class PromptInjectionGuard(BaseNode):
    """
    Article 15 Cybersecurity Guard: Detects adversarial inputs (prompt injection)
    to prevent unauthorized alterations to the AI system's behavior or outputs.
    
    This fulfills the EU AI Act Art. 15(5) requirement for technical solutions to
    address inputs designed to cause the AI model to make a mistake (adversarial examples
    or model evasion).
    """

    # A simple reference list of known injection vectors/patterns.
    # In a production system, this could call an external classification model or regex suite.
    DEFAULT_HEURISTICS = [
        "ignore all previous instructions",
        "forget your previous instructions",
        "system prompt",
        "you are now",
        "instead of what you were doing",
        "override",
        "disregard"
    ]

    def __init__(
        self,
        input_keys: List[str],
        heuristics: Optional[List[str]] = None,
        block_on_detection: bool = True,
        next_node: Optional[BaseNode] = None,
    ):
        """
        Args:
            input_keys: A list of state keys to scan for prompt injections.
            heuristics: A list of substring heuristics to detect adversarial intent.
            block_on_detection: If True, raises PromptInjectionError. If False, flags the state.
            next_node: The next node to execute.
        """
        super().__init__(next_node=next_node)
        self.input_keys = input_keys
        self.heuristics = heuristics or self.DEFAULT_HEURISTICS
        self.block_on_detection = block_on_detection

    def execute(self, state: GraphState) -> GraphState:
        injection_detected = False
        detected_patterns = []

        for key in self.input_keys:
            value = state.get(key)
            if value and isinstance(value, str):
                lower_val = value.lower()
                for pattern in self.heuristics:
                    if pattern in lower_val:
                        injection_detected = True
                        detected_patterns.append(pattern)

        if injection_detected:
            if self.block_on_detection:
                raise PromptInjectionError(
                    f"Adversarial prompt injection detected based on heuristics: {detected_patterns}"
                )
            else:
                logger.warning(f"Adversarial prompt injection detected: {detected_patterns}")
                state.set("_adversarial_flag", True)

        return state
