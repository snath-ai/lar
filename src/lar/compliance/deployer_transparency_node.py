"""
lar.compliance.deployer_transparency_node
==========================================
DeployerTransparencyNode — Art. 13 Instructions for Use.

Art. 13 EU AI Act requires providers to supply deployers with sufficient
information to understand and correctly use the AI system.  This is distinct
from Art. 50 third-party disclosure (handled by TransparencyEngine) — Art. 13
is a provider-to-deployer obligation.

This node:
  - Generates a machine-readable instructions-for-use document per session.
  - Writes it to ``state[output_key]`` for downstream export / audit inclusion.
  - Exposes ``as_markdown()`` for human-readable deployer documentation.

Usage::

    from lar.compliance import DeployerTransparencyNode

    art13 = DeployerTransparencyNode(
        system_name="Credit Decision Agent v2.2",
        intended_purpose="Creditworthiness assessment for retail banking (Annex III §5b)",
        known_limitations=["English-language inputs only", "Max income €500k"],
        human_oversight_requirements=["All CRITICAL risk decisions require CFO approval"],
        prohibited_uses=["Consumer profiling", "Insurance scoring"],
        conformity_id="CE-FINANCE-2026-001",
        next_node=audit_node,
    )
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from lar.node import BaseNode
from lar.state import GraphState


class DeployerTransparencyNode(BaseNode):
    """
    Generates an Art. 13 Instructions-for-Use disclosure for deployers.

    Writes a structured dict to ``state[output_key]`` covering:
    intended purpose, known limitations, human oversight requirements,
    prohibited uses, and data governance notes.

    EU Reference: Art. 13 EU AI Act — Transparency and Provision of Information
    to Deployers; Annex IV (Technical Documentation).
    """

    EU_REFERENCE = (
        "Art. 13 EU AI Act — Transparency and Provision of Information to Deployers; "
        "Annex IV (Technical Documentation)"
    )

    def __init__(
        self,
        system_name: str,
        intended_purpose: str,
        known_limitations: List[str],
        human_oversight_requirements: List[str],
        prohibited_uses: List[str],
        data_governance_notes: Optional[str] = None,
        conformity_id: Optional[str] = None,
        output_key: str = "deployer_instructions",
        next_node: Optional[BaseNode] = None,
    ):
        """
        Args:
            system_name: Human-readable name of the AI system.
            intended_purpose: Precise description matching Annex III classification.
            known_limitations: Bullet-point list of documented limitations.
            human_oversight_requirements: What human review is required and when.
            prohibited_uses: Explicitly prohibited use cases (Art. 13(3)(b)).
            data_governance_notes: GDPR / data-flow obligations for deployers.
            conformity_id: CE Declaration of Conformity reference number.
            output_key: State key for the generated disclosure dict.
            next_node: Next node after this one.
        """
        self.system_name = system_name
        self.intended_purpose = intended_purpose
        self.known_limitations = known_limitations
        self.human_oversight_requirements = human_oversight_requirements
        self.prohibited_uses = prohibited_uses
        self.data_governance_notes = data_governance_notes
        self.conformity_id = conformity_id
        self.output_key = output_key
        self.next_node = next_node

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        disclosure = {
            "schema": "lar-art13-instructions-for-use-v1",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "eu_reference": self.EU_REFERENCE,
            "system_name": self.system_name,
            "conformity_id": self.conformity_id,
            "intended_purpose": self.intended_purpose,
            "known_limitations": self.known_limitations,
            "human_oversight_requirements": self.human_oversight_requirements,
            "prohibited_uses": self.prohibited_uses,
            "data_governance_notes": self.data_governance_notes,
        }
        state.set(self.output_key, disclosure)
        print(
            f"  [DeployerTransparencyNode] Art. 13 instructions-for-use generated "
            f"for '{self.system_name}' → state['{self.output_key}']"
        )
        return self.next_node

    def as_markdown(self, state: GraphState) -> str:
        """Return a human-readable Markdown document from the generated disclosure."""
        d = state.get(self.output_key) or {}
        lines = [
            f"# Instructions for Use — {d.get('system_name', self.system_name)}",
            f"**EU Reference:** {d.get('eu_reference', self.EU_REFERENCE)}",
            f"**Generated:** {d.get('generated_at', '—')}",
            f"**Conformity ID:** {d.get('conformity_id', 'N/A')}",
            "",
            "## Intended Purpose",
            d.get("intended_purpose", "—"),
            "",
            "## Known Limitations",
        ]
        for lim in d.get("known_limitations", []):
            lines.append(f"- {lim}")
        lines += ["", "## Human Oversight Requirements"]
        for req in d.get("human_oversight_requirements", []):
            lines.append(f"- {req}")
        lines += ["", "## Prohibited Uses"]
        for p in d.get("prohibited_uses", []):
            lines.append(f"- {p}")
        if d.get("data_governance_notes"):
            lines += ["", "## Data Governance Notes", d["data_governance_notes"]]
        return "\n".join(lines)
