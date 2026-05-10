"""
BranchTriageNode — post-BatchNode compliance primitive for fractal agents.

After a BatchNode runs parallel branches, this node:
  1. Parses each branch output (JSON embedded in state) to extract risk_level + finding.
  2. Builds branch_findings_summary — a structured string the HumanJuryNode surfaces
     to the human reviewer so they see per-dimension risk, not just a consolidated score.
  3. Sets branch_critical (bool) — True if any branch breached the threshold.

Wire it between BatchNode and RouterNode:

    node_batch  → node_triage → node_router
                                    ↓ "critical" → HumanJuryNode → ReduceNode
                                    ↓ "ok"       → ReduceNode

Regulatory basis:
  Art. 14 EU AI Act — human oversight must be *meaningful*. Showing only a consolidated
  score hides dimension-level evidence the PI needs to make an informed decision. This node
  ensures the raw branch findings reach the jury context before consolidation discards them.

  Art. 3(23) EU AI Act — substantial modification. In fractal agents, each AdaptiveNode
  branch can return a CRITICAL assessment that changes the overall risk profile. Surfacing
  this before ReduceNode compresses it preserves the evidence trail.
"""

import json
from typing import List, Optional
from lar.node import BaseNode
from lar.state import GraphState


class BranchTriageNode(BaseNode):
    """
    Parses parallel branch outputs after BatchNode, builds a human-readable summary,
    and flags whether any branch exceeded the risk threshold.

    Parameters
    ----------
    branch_output_keys : List[str]
        State keys written by each BatchNode branch (e.g. ['safety_analysis',
        'efficacy_analysis', 'regulatory_analysis']).
    risk_level_key : str
        The JSON field inside each branch output that holds the risk level string.
        Defaults to 'risk_level'. Expected values: LOW / MEDIUM / HIGH / CRITICAL.
    finding_key : str
        The JSON field inside each branch output that holds the 1-sentence finding.
        Defaults to 'finding'.
    critical_threshold : str
        The risk level at or above which branch_critical is set to True.
        Defaults to 'CRITICAL'. Set to 'HIGH' to escalate earlier.
    summary_state_key : str
        State key where the formatted branch findings summary is written.
        HumanJuryNode should include this in its context_keys.
    critical_flag_key : str
        State key where the boolean CRITICAL flag is written.
        RouterNode decision_function reads this key.
    next_node : BaseNode, optional
        The next node in the graph (typically a RouterNode).
    """

    _RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def __init__(
        self,
        branch_output_keys: List[str],
        risk_level_key: str = "risk_level",
        finding_key: str = "finding",
        critical_threshold: str = "CRITICAL",
        summary_state_key: str = "branch_findings_summary",
        critical_flag_key: str = "branch_critical",
        next_node: Optional[BaseNode] = None,
    ):
        if not branch_output_keys:
            raise ValueError("branch_output_keys must be a non-empty list")
        self.branch_output_keys  = branch_output_keys
        self.risk_level_key      = risk_level_key
        self.finding_key         = finding_key
        self.critical_threshold  = critical_threshold.upper()
        self.summary_state_key   = summary_state_key
        self.critical_flag_key   = critical_flag_key
        self.next_node           = next_node

    def _parse_branch(self, raw: str) -> dict:
        """Extract the first JSON object from a branch output string."""
        if not raw:
            return {}
        try:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        threshold_rank = self._RISK_ORDER.get(self.critical_threshold, 3)
        critical_found = False
        summary_lines  = []

        for key in self.branch_output_keys:
            raw    = state.get(key, "")
            parsed = self._parse_branch(raw)

            level   = str(parsed.get(self.risk_level_key, "UNKNOWN")).upper()
            finding = parsed.get(self.finding_key, raw[:120] if raw else "no output")
            label   = key.replace("_analysis", "").replace("_", " ").upper()

            rank = self._RISK_ORDER.get(level, -1)
            if rank >= threshold_rank:
                critical_found = True

            summary_lines.append(f"  {label:<14}: {level:<8} — {finding}")

        header  = f"Branch findings (threshold: {self.critical_threshold}):"
        summary = header + "\n" + "\n".join(summary_lines)

        state.set(self.summary_state_key, summary)
        state.set(self.critical_flag_key, critical_found)

        if critical_found:
            print(
                f"  [BranchTriageNode] CRITICAL threshold breached — "
                f"escalation required before consolidation."
            )
        else:
            print(
                f"  [BranchTriageNode] All branches within threshold — "
                f"proceeding to consolidation."
            )

        return self.next_node
