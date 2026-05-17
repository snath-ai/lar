"""
lar.compliance.dynamic_tool_discovery_monitor
=============================================
DynamicToolDiscoveryMonitor — Post-Conformity Tool Addition Monitor.

EU AI Act Art. 3(23): A substantial modification that changes the AI system's
intended purpose or performance resets CE-marking obligations.  Adding new tools
(ToolNode function names) after the conformity baseline was established is a
potential substantial modification trigger.

This node:
  - Records the conformity-assessed tool catalogue at baseline (``baseline_tools``).
  - On each ``execute``, compares ``state[catalogue_state_key]`` to the baseline.
  - Flags or blocks any tools added since the baseline was assessed.
  - Flags tools removed from the baseline (capability reduction — also relevant).

Usage::

    from lar.compliance import DynamicToolDiscoveryMonitor

    monitor = DynamicToolDiscoveryMonitor(
        baseline_tools=["send_email", "query_crm", "generate_pdf"],
        block_on_undisclosed=True,
        next_node=proceed_node,
    )

    # At runtime the executor sets state["tool_catalogue"] to the current list;
    # the monitor checks it on every pass.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Set

from lar.node import BaseNode
from lar.state import GraphState


class UndisclosedToolError(Exception):
    """Raised when a tool not present in the conformity baseline is discovered."""
    pass


class DynamicToolDiscoveryMonitor(BaseNode):
    """
    Checks whether the live tool catalogue matches the conformity-assessed baseline.

    Expects ``state[catalogue_state_key]`` to be a list of tool-name strings
    (set by the deployer at graph startup, or updated dynamically by AdaptiveNode).

    On a mismatch it either blocks (raises ``UndisclosedToolError``) or writes a
    report to ``state[output_key]`` and continues.

    EU Reference: Art. 3(23) EU AI Act — Substantial Modification;
                  Art. 9 (Post-Market Monitoring Plan)
    """

    EU_REFERENCE = (
        "Art. 3(23) EU AI Act — Substantial Modification; "
        "Art. 9 — Post-Market Monitoring Plan"
    )

    def __init__(
        self,
        baseline_tools: List[str],
        catalogue_state_key: str = "tool_catalogue",
        block_on_undisclosed: bool = False,
        output_key: str = "tool_discovery_report",
        next_node: Optional[BaseNode] = None,
    ):
        """
        Args:
            baseline_tools: Tool names present at conformity assessment time.
            catalogue_state_key: State key holding the current tool name list.
            block_on_undisclosed: If ``True``, raise ``UndisclosedToolError`` when
                new tools are found.  Default ``False`` logs a warning and continues.
            output_key: State key for the discovery report dict.
            next_node: Next node after execution.
        """
        self.baseline: Set[str] = set(baseline_tools)
        self.catalogue_key = catalogue_state_key
        self.block_on_undisclosed = block_on_undisclosed
        self.output_key = output_key
        self.next_node = next_node

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        current_tools: List[str] = state.get(self.catalogue_key) or []
        current_set: Set[str] = set(current_tools)

        new_tools = sorted(current_set - self.baseline)
        removed_tools = sorted(self.baseline - current_set)

        report: Dict = {
            "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
            "eu_reference": self.EU_REFERENCE,
            "baseline_count": len(self.baseline),
            "current_count": len(current_set),
            "new_tools": new_tools,
            "removed_tools": removed_tools,
            "substantial_modification_flag": len(new_tools) > 0,
        }
        state.set(self.output_key, report)

        if new_tools:
            msg = (
                f"[DynamicToolDiscoveryMonitor] {len(new_tools)} UNDISCLOSED TOOL(S) "
                f"detected post-conformity-baseline: {new_tools}. {self.EU_REFERENCE}"
            )
            print(f"\n{'!' * 60}\n{msg}\n{'!' * 60}\n")
            if self.block_on_undisclosed:
                raise UndisclosedToolError(msg)
        else:
            print(
                f"  [DynamicToolDiscoveryMonitor] Tool catalogue matches baseline "
                f"({len(current_set)} tool(s)). No substantial modification detected."
            )

        if removed_tools:
            print(
                f"  [DynamicToolDiscoveryMonitor] {len(removed_tools)} tool(s) removed "
                f"from baseline (capability reduction): {removed_tools}."
            )

        return self.next_node
