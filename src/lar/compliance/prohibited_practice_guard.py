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
    indicating a prohibited practice under EU AI Act Art. 5.

    Core Art. 5(1) bans (in force since 2 February 2025):
      1. Subliminal / manipulative / deceptive techniques  (Art. 5(1)(a))
      2. Exploitation of vulnerabilities — age, disability, socio-economic
         situation                                          (Art. 5(1)(b))
      3. Social scoring / trustworthiness evaluation from social behaviour
                                                            (Art. 5(1)(c))

    Digital Omnibus (Regulation (EU) 2026/1744) additions, applicable
    **2 December 2026**:
      4. AI systems designed or used to produce non-consensual intimate
         (sexually explicit) imagery of real, identifiable persons   (NCII)
      5. AI systems designed or used to produce child sexual abuse
         material                                                    (CSAM)

    These heuristics are a lightweight last line of defence — a substring scan,
    not a classifier. Pair with an upstream input filter and, for a real
    deployment, an LLM-as-judge or a dedicated safety classifier. A clean pass
    means "no flagged phrasing surfaced", not "Art. 5 compliant".
    """

    # Categories whose legal basis only begins to apply on 2 Dec 2026.
    OMNIBUS_CATEGORIES = ("NCII", "CSAM")

    def __init__(self,
                 input_key: str,
                 next_node: Optional[BaseNode] = None,
                 block_on_violation: bool = True,
                 include_omnibus_categories: bool = True):
        """
        Args:
            input_key: state key holding the text to scan.
            next_node: node to continue to when clean.
            block_on_violation: raise ``ProhibitedPracticeError`` on any hit.
            include_omnibus_categories: also scan for the 2 Dec 2026 NCII/CSAM
                additions (default True; set False to scan only the pre-2026 bans).
        """
        self.input_key = input_key
        self.next_node = next_node
        self.block_on_violation = block_on_violation
        self.include_omnibus_categories = include_omnibus_categories

        # Simple heuristic regexes to detect risky phrasing in the final output.
        self.heuristics = {
            "SOCIAL_SCORING": re.compile(
                r'\b(social credit|trustworthiness score|social standing|behaviour score)\b',
                re.IGNORECASE),
            "MANIPULATION": re.compile(
                r'\b(must act now or|secretly track|coerce|exploit vulnerability|subliminal)\b',
                re.IGNORECASE),
            "VULNERABILITY_EXPLOIT": re.compile(
                r'\b(target elderly|target minors|leverage desperation)\b',
                re.IGNORECASE),
        }
        if include_omnibus_categories:
            self.heuristics["NCII"] = re.compile(
                r'\b(non[- ]consensual (intimate|sexual|explicit)|deepfake (nude|porn)|'
                r'undress(ed|ing)? (image|photo|picture)|sexually explicit (image|deepfake) '
                r'of (a|an|the) (real|identifiable|named) (person|individual))\b',
                re.IGNORECASE)
            self.heuristics["CSAM"] = re.compile(
                r'\b(child sexual abuse material|csam|sexuali[sz]ed (image|depiction|content) '
                r'of a (child|minor)|minor in a sexual)\b',
                re.IGNORECASE)

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        content = str(state.get(self.input_key, ""))
        if not content:
            return self.next_node

        violations = []
        for risk_category, pattern in self.heuristics.items():
            if pattern.search(content):
                violations.append(risk_category)

        if violations:
            omnibus = [v for v in violations if v in self.OMNIBUS_CATEGORIES]
            basis = "Art. 5(1) EU AI Act"
            if omnibus:
                basis += (
                    f" (+ Regulation (EU) 2026/1744 additions {omnibus}, "
                    f"applicable 2 Dec 2026)"
                )
            msg = (
                f"[ProhibitedPracticeGuard] {basis} — PROHIBITED PRACTICE DETECTED.\n"
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
