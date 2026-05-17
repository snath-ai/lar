"""
lar.compliance.fria_node
========================
FundamentalRightsImpactNode — Art. 9 FRIA.

Scans AI outputs at runtime against six EU Charter dimensions:
  - DIGNITY           (EU Charter Art. 1)
  - PRIVACY           (EU Charter Art. 7/8)
  - NON_DISCRIMINATION(EU Charter Art. 21)
  - EXPRESSION        (EU Charter Art. 11)
  - JUSTICE           (EU Charter Art. 47)
  - DATA_PROTECTION   (EU Charter Art. 8 / GDPR)

EU AI Act Art. 9 requires high-risk system providers to assess impacts on
fundamental rights as part of the risk management system. This node operationalises
that requirement as a runtime gate — not just a design-time document.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from lar.node import BaseNode
from lar.state import GraphState


class FRIAViolation(Exception):
    """Raised when a fundamental rights dimension is violated."""
    pass


class FundamentalRightsImpactNode(BaseNode):
    """
    Runtime Fundamental Rights Impact Assessment gate.

    Checks the text in ``input_key`` against heuristic patterns for six EU
    Charter dimensions.  On a hit, it either blocks (raises ``FRIAViolation``)
    or writes findings to ``state['fria_findings']`` and continues.

    Usage::

        from lar.compliance import FundamentalRightsImpactNode

        fria = FundamentalRightsImpactNode(input_key="recommendation", next_node=output_node)

    Wire it after every LLMNode or ToolNode that produces text touching a person.
    """

    EU_REFERENCE = (
        "Art. 9 FRIA — EU AI Act; EU Charter Arts. 1 (Dignity), "
        "7/8 (Privacy/Data), 11 (Expression), 21 (Non-discrimination), 47 (Justice)"
    )

    # Heuristic patterns per Charter dimension — extend via custom_patterns arg
    _DEFAULT_PATTERNS: Dict[str, re.Pattern] = {
        "DIGNITY": re.compile(
            r"\b(degrading|humiliating|dehumaniz|inferior|subhuman|worthless person)\b",
            re.IGNORECASE,
        ),
        "PRIVACY": re.compile(
            r"\b(track\s+location|monitor\s+communications|covert\s+surveillance|"
            r"expose\s+personal|reveal\s+private|publish\s+(home\s+)?address|"
            r"disclose\s+identity\s+without\s+consent)\b",
            re.IGNORECASE,
        ),
        "NON_DISCRIMINATION": re.compile(
            r"\b(because\s+of\s+(their\s+)?(race|gender|religion|ethnicity|disability|"
            r"sexual\s+orientation)|racial\s+profil|gender\s+bias|ethnic\s+stereotyp|"
            r"discriminat\w+\s+(against|based\s+on))\b",
            re.IGNORECASE,
        ),
        "EXPRESSION": re.compile(
            r"\b(suppress(ing)?\s+speech|censor\w*|ban\w*\s+expression|"
            r"prohibit\w*\s+opinion|restrict\w*\s+journalism|silence\s+critic)\b",
            re.IGNORECASE,
        ),
        "JUSTICE": re.compile(
            r"\b(deny(ing)?\s+appeal|no\s+right\s+to\s+(contest|remedy|review)|"
            r"irrevocable\s+automated\s+(decision|penalty|sanction)|"
            r"without\s+due\s+process|no\s+judicial\s+recourse)\b",
            re.IGNORECASE,
        ),
        "DATA_PROTECTION": re.compile(
            r"\b(retain\s+indefinitely|store\s+permanently|never\s+delete|"
            r"profile\w*\s+without\s+consent|share\s+personal\s+data\s+without|"
            r"sell\s+personal\s+data)\b",
            re.IGNORECASE,
        ),
    }

    def __init__(
        self,
        input_key: str,
        next_node: Optional[BaseNode] = None,
        block_on_violation: bool = True,
        custom_patterns: Optional[Dict[str, re.Pattern]] = None,
    ):
        """
        Args:
            input_key: State key containing the text to assess.
            next_node: Node to proceed to if no blocking violation.
            block_on_violation: Raise ``FRIAViolation`` on any finding.
                Set to False to log findings and continue.
            custom_patterns: Additional ``{dimension: pattern}`` entries merged
                with the defaults.  Dimension names are arbitrary strings.
        """
        self.input_key = input_key
        self.next_node = next_node
        self.block_on_violation = block_on_violation
        self._patterns: Dict[str, re.Pattern] = dict(self._DEFAULT_PATTERNS)
        if custom_patterns:
            self._patterns.update(custom_patterns)

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        content = str(state.get(self.input_key) or "")
        findings: List[Dict] = []

        for dimension, pattern in self._patterns.items():
            match = pattern.search(content)
            if match:
                findings.append(
                    {
                        "dimension": dimension,
                        "matched_text": match.group(0),
                        "eu_reference": self.EU_REFERENCE,
                    }
                )

        state.set("fria_findings", findings)
        state.set("fria_passed", len(findings) == 0)

        if findings:
            dims = [f["dimension"] for f in findings]
            msg = (
                f"[FundamentalRightsImpactNode] FRIA VIOLATION — "
                f"{len(findings)} dimension(s) flagged: {dims}. "
                f"Reference: {self.EU_REFERENCE}"
            )
            print(f"\n{'!' * 60}\n{msg}\n{'!' * 60}\n")
            if self.block_on_violation:
                raise FRIAViolation(msg)
        else:
            print(
                f"  [FundamentalRightsImpactNode] FRIA passed — "
                f"no Charter violations detected in state['{self.input_key}']."
            )

        return self.next_node
