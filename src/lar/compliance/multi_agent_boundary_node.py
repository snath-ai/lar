"""
lar.compliance.multi_agent_boundary_node
========================================
MultiAgentBoundaryNode — Art. 3 Sub-Agent System Boundary Marker.

EU AI Act Art. 3(1) defines an "AI system".  Art. 25 assigns responsibilities
along the value chain — providers and deployers must know which agents are
"internal" (covered by the parent CE) and which are "external" (independently
assessed).  (Recital 12 was previously cited alongside these two articles for
a "multi-actor AI system chains" framing; verified against the regulation text,
Recital 12 is in fact about the definition of "AI system" itself — capability
to infer, machine-basis, autonomy, adaptiveness — and says nothing about
multi-actor chains or conformity obligations.  That citation has been removed;
the multi-actor-boundary framing below is this node's own reasonable extension
of Art. 25's value-chain responsibility structure, not a direct textual claim.)

This node marks and records whether a sub-agent call crosses the Art. 3 boundary.
Use one ``MultiAgentBoundaryNode`` per sub-agent invocation.  Results accumulate
in ``state[output_key]`` (a list) so the full multi-agent map is auditable.

Usage::

    from lar.compliance import MultiAgentBoundaryNode

    # Internal BatchNode branch — covered by parent CE
    boundary_internal = MultiAgentBoundaryNode(
        agent_name="CreditScorerAgent",
        placement="INTERNAL",
        provider_entity="Acme Bank AI Team",
        purpose="Runs credit scoring sub-graph as an internal branch.",
        next_node=batch_entry_node,
    )

    # External call to a third-party agent marketplace
    boundary_external = MultiAgentBoundaryNode(
        agent_name="SupplierKYCAgent",
        placement="EXTERNAL_MARKET",
        provider_entity="KYC-as-a-Service GmbH",
        purpose="Verifies supplier identity via external API.",
        conformity_id="CE-KYC-2026-007",
        next_node=kyc_tool_node,
    )
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from lar.node import BaseNode
from lar.state import GraphState


class MultiAgentBoundaryNode(BaseNode):
    """
    Records Art. 3 / Art. 25 boundary classification for each sub-agent call.

    Appends a boundary record to ``state[output_key]`` (initialised to ``[]``
    if absent) and logs the classification to stdout.

    A warning is emitted when an ``EXTERNAL_MARKET`` agent has no
    ``conformity_id`` — the Art. 25 obligation is then unverifiable.

    EU References:
      - Art. 3(1) — Definition of AI System
      - Art. 25 — Responsibilities Along the AI Value Chain
    (A "Recital 12 — multi-actor chains" citation was previously listed here;
    Recital 12 is actually about the definition of "AI system" and does not
    address multi-actor chains — removed. See module docstring.)
    """

    EU_REFERENCE = (
        "Art. 3(1) EU AI Act — Definition of AI System; "
        "Art. 25 — Responsibilities Along the AI Value Chain"
    )

    PLACEMENT_TYPES = ("INTERNAL", "EXTERNAL_MARKET")

    def __init__(
        self,
        agent_name: str,
        placement: str,
        provider_entity: str,
        purpose: str,
        conformity_id: Optional[str] = None,
        output_key: str = "multi_agent_boundaries",
        next_node: Optional[BaseNode] = None,
    ):
        """
        Args:
            agent_name: Human-readable name of the sub-agent.
            placement: ``"INTERNAL"`` (covered by parent CE) or
                       ``"EXTERNAL_MARKET"`` (independently placed on market —
                       separate Art. 9+ conformity obligations apply).
            provider_entity: Legal name of the entity responsible for this sub-agent.
            purpose: What the sub-agent does (one sentence).
            conformity_id: CE Declaration of Conformity ID for EXTERNAL_MARKET agents.
            output_key: State key for the accumulated boundary records list.
            next_node: Next node after this one.
        """
        if placement not in self.PLACEMENT_TYPES:
            raise ValueError(
                f"placement must be one of {self.PLACEMENT_TYPES}, got '{placement}'"
            )
        self.agent_name = agent_name
        self.placement = placement
        self.provider_entity = provider_entity
        self.purpose = purpose
        self.conformity_id = conformity_id
        self.output_key = output_key
        self.next_node = next_node

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        record: Dict = {
            "agent_name": self.agent_name,
            "placement": self.placement,
            "provider_entity": self.provider_entity,
            "purpose": self.purpose,
            "conformity_id": self.conformity_id,
            "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
            "eu_reference": self.EU_REFERENCE,
            "requires_separate_conformity": self.placement == "EXTERNAL_MARKET",
        }

        # Append to accumulator list — multiple boundary nodes may fire in one graph
        existing: List[Dict] = state.get(self.output_key) or []
        existing.append(record)
        state.set(self.output_key, existing)

        if self.placement == "EXTERNAL_MARKET":
            status = "EXTERNAL — separate Art. 9+ obligations apply"
            if not self.conformity_id:
                print(
                    f"  [MultiAgentBoundaryNode] WARNING: EXTERNAL_MARKET agent "
                    f"'{self.agent_name}' has no conformity_id. "
                    f"Art. 25 obligations unverifiable."
                )
        else:
            status = "INTERNAL — covered by parent system CE"

        print(f"  [MultiAgentBoundaryNode] '{self.agent_name}': {status}")
        return self.next_node
