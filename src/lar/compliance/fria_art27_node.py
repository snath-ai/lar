"""
lar.compliance.fria_art27_node
==============================
Article27FRIANode — the **Article 27 Fundamental Rights Impact Assessment**
(a *deployer* obligation), as a structured, machine-readable template generator.

This is the Act's named, standalone FRIA — distinct from
``FundamentalRightsImpactNode`` (a runtime Art. 9(2)(a) output-screening heuristic
that is explicitly *not* the Art. 27 FRIA).

Who must do it — Art. 27(1). Only these deployers of Annex III high-risk systems
(and NOT for Annex III point 2, critical infrastructure):
  * bodies governed by public law;
  * private entities providing public services;
  * any deployer using a system for creditworthiness evaluation / credit scoring
    (Annex III 5(b)); or for risk assessment and pricing in life and health
    insurance (Annex III 5(c)).

What it must contain — Art. 27(1)(a)-(f):
  (a) the deployer's processes in which the system will be used, in line with its
      intended purpose;
  (b) the period of time and frequency of intended use;
  (c) the categories of natural persons and groups likely to be affected;
  (d) the specific risks of harm to those categories, taking into account the
      information the provider gave under Art. 13;
  (e) the implementation of human oversight measures, per the instructions for use;
  (f) the measures to take if those risks materialise, including internal
      governance arrangements and complaint mechanisms.

Also modelled:
  * Art. 27(3) — once performed, the deployer notifies the market surveillance
    authority of the results (via the AI Office template, Art. 27(5)).
  * Art. 27(4), as reinforced by the Digital Omnibus (Regulation (EU) 2026/1744)
    — the FRIA may incorporate or cross-refer relevant parts of a GDPR Art. 35
    Data Protection Impact Assessment rather than duplicating them.

Lár generates the template and checks completeness; the deployer supplies the
substantive content and files it with the authority. Using this node is not the
assessment.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from lar.node import BaseNode
from lar.state import GraphState


# Deployer classes that are IN SCOPE for Art. 27.
IN_SCOPE_DEPLOYER_CLASSES = (
    "PUBLIC_BODY",
    "PRIVATE_PUBLIC_SERVICE",
    "CREDIT_SCORING",           # Annex III 5(b)
    "LIFE_HEALTH_INSURANCE",    # Annex III 5(c)
)
OUT_OF_SCOPE_DEPLOYER_CLASSES = ("OUT_OF_SCOPE", "NONE", None)

_DEFAULT_CHARTER_RIGHTS = [
    "Dignity (Art. 1)",
    "Respect for private and family life (Art. 7)",
    "Protection of personal data (Art. 8)",
    "Freedom of expression and information (Art. 11)",
    "Non-discrimination (Art. 21)",
    "Rights of the child (Art. 24)",
    "Rights of the elderly (Art. 25)",
    "Integration of persons with disabilities (Art. 26)",
    "Consumer protection (Art. 38)",
    "Right to an effective remedy and to a fair trial (Art. 47)",
]


class Art27FRIAIncompleteError(Exception):
    """Raised in strict mode when an in-scope FRIA is missing a required element."""
    pass


class Article27FRIANode(BaseNode):
    """
    Generates an Art. 27 Fundamental Rights Impact Assessment record.

    On ``execute`` it writes ``state[output_key]`` (default ``"fria_art27"``):
      * out of scope → ``{"applicable": False, "reason": ...}``
      * in scope     → the full structured FRIA dict, plus
                       ``state["fria_art27_notify_authority_required"] = True``.

    EU Reference: Art. 27 EU AI Act — Fundamental Rights Impact Assessment
    (deployer obligation); Art. 27(3) authority notification; Art. 27(4) +
    Regulation (EU) 2026/1744 DPIA cross-reference.
    """

    EU_REFERENCE = (
        "Art. 27 EU AI Act — Fundamental Rights Impact Assessment (deployer "
        "obligation); Art. 27(3) authority notification; Art. 27(4) / "
        "Regulation (EU) 2026/1744 — may cross-refer a GDPR Art. 35 DPIA"
    )

    _REQUIRED_ELEMENTS = (
        ("deployment_process", "27(1)(a) deployer processes / intended-purpose use"),
        ("usage_period_and_frequency", "27(1)(b) period of time and frequency of use"),
        ("affected_natural_persons", "27(1)(c) categories of affected natural persons/groups"),
        ("fundamental_rights_risks", "27(1)(d) specific risks of harm (informed by Art. 13 info)"),
        ("human_oversight_measures", "27(1)(e) human oversight measures per instructions for use"),
        ("measures_on_materialisation", "27(1)(f) measures on materialisation + governance + complaints"),
    )

    def __init__(
        self,
        system_name: str,
        deployer_class: Optional[str],
        intended_purpose: str = "",
        annex_iii_point: str = "",
        deployment_process: str = "",
        usage_period_and_frequency: str = "",
        affected_natural_persons: Optional[List[str]] = None,
        fundamental_rights_risks: Optional[List[str]] = None,
        human_oversight_measures: Optional[List[str]] = None,
        measures_on_materialisation: Optional[List[str]] = None,
        provider_info_reference: Optional[str] = None,
        dpia_reference: Optional[str] = None,
        charter_rights_considered: Optional[List[str]] = None,
        output_key: str = "fria_art27",
        strict: bool = False,
        next_node: Optional[BaseNode] = None,
    ):
        """
        Args:
            deployer_class: one of ``PUBLIC_BODY | PRIVATE_PUBLIC_SERVICE |
                CREDIT_SCORING | LIFE_HEALTH_INSURANCE`` (in scope) or
                ``OUT_OF_SCOPE`` / ``None``.
            strict: if True and the deployer is in scope, raise
                ``Art27FRIAIncompleteError`` when any 27(1)(a)-(f) element is empty.
        """
        self.system_name = system_name
        self.deployer_class = deployer_class
        self.intended_purpose = intended_purpose
        self.annex_iii_point = annex_iii_point
        self.deployment_process = deployment_process
        self.usage_period_and_frequency = usage_period_and_frequency
        self.affected_natural_persons = affected_natural_persons or []
        self.fundamental_rights_risks = fundamental_rights_risks or []
        self.human_oversight_measures = human_oversight_measures or []
        self.measures_on_materialisation = measures_on_materialisation or []
        self.provider_info_reference = provider_info_reference
        self.dpia_reference = dpia_reference
        self.charter_rights_considered = charter_rights_considered or list(_DEFAULT_CHARTER_RIGHTS)
        self.output_key = output_key
        self.strict = strict
        self.next_node = next_node

    # ── Scope ────────────────────────────────────────────────────────────────

    def in_scope(self) -> bool:
        return self.deployer_class in IN_SCOPE_DEPLOYER_CLASSES

    # ── Execute ──────────────────────────────────────────────────────────────

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        if not self.in_scope():
            record = {
                "schema": "lar-art27-fria-v1",
                "applicable": False,
                "deployer_class": self.deployer_class,
                "reason": (
                    "Art. 27 applies only to deployers that are public bodies, "
                    "private providers of public services, or deployers doing "
                    "credit scoring (Annex III 5(b)) / life & health insurance "
                    "risk pricing (Annex III 5(c)). This deployer class is not "
                    "in that set."
                ),
                "eu_reference": self.EU_REFERENCE,
            }
            state.set(self.output_key, record)
            print(
                f"  [Article27FRIANode] deployer_class='{self.deployer_class}' — "
                f"Art. 27 FRIA not applicable; recorded rationale."
            )
            return self.next_node

        missing = [
            desc for attr, desc in self._REQUIRED_ELEMENTS
            if not getattr(self, attr)
        ]

        record = {
            "schema": "lar-art27-fria-v1",
            "applicable": True,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "eu_reference": self.EU_REFERENCE,
            "system_name": self.system_name,
            "deployer_class": self.deployer_class,
            "intended_purpose": self.intended_purpose,
            "annex_iii_point": self.annex_iii_point,
            # Art. 27(1)(a)-(f)
            "a_deployment_process": self.deployment_process,
            "b_usage_period_and_frequency": self.usage_period_and_frequency,
            "c_affected_natural_persons": self.affected_natural_persons,
            "d_fundamental_rights_risks": self.fundamental_rights_risks,
            "d_provider_info_reference_art13": self.provider_info_reference,
            "e_human_oversight_measures": self.human_oversight_measures,
            "f_measures_on_materialisation": self.measures_on_materialisation,
            # supporting / procedural
            "charter_rights_considered": self.charter_rights_considered,
            "dpia_reference_art27_4": self.dpia_reference,
            "notify_market_surveillance_authority": {
                "required": True,
                "basis": "Art. 27(3) — notify the authority of the results via the AI Office template (Art. 27(5))",
            },
            "completeness": {
                "complete": not missing,
                "missing_elements": missing,
            },
        }
        state.set(self.output_key, record)
        state.set("fria_art27_notify_authority_required", True)

        status = "COMPLETE" if not missing else f"INCOMPLETE — missing {len(missing)} element(s)"
        print(
            f"  [Article27FRIANode] Art. 27 FRIA generated for '{self.system_name}' "
            f"(deployer_class={self.deployer_class}) → state['{self.output_key}'] [{status}]"
        )
        if missing:
            for m in missing:
                print(f"      · missing: {m}")
            if self.strict:
                raise Art27FRIAIncompleteError(
                    f"Art. 27 FRIA for '{self.system_name}' is missing required "
                    f"element(s): {missing}"
                )
        return self.next_node

    # ── Human-readable export ────────────────────────────────────────────────

    def as_markdown(self, state: GraphState) -> str:
        d = state.get(self.output_key) or {}
        if not d.get("applicable", False):
            return (
                f"# Article 27 FRIA — Not Applicable\n\n"
                f"**System:** {self.system_name}\n\n"
                f"**Deployer class:** {d.get('deployer_class')}\n\n"
                f"{d.get('reason', '')}\n"
            )
        lines = [
            f"# Fundamental Rights Impact Assessment (EU AI Act Article 27)",
            f"**System:** {d.get('system_name')}",
            f"**Deployer class:** {d.get('deployer_class')}",
            f"**Annex III point:** {d.get('annex_iii_point') or '—'}",
            f"**Generated:** {d.get('generated_at')}",
            f"**EU reference:** {d.get('eu_reference')}",
            "",
            "## (a) Deployer processes / intended-purpose use",
            d.get("a_deployment_process") or "_[to be completed by deployer]_",
            "",
            "## (b) Period of time and frequency of use",
            d.get("b_usage_period_and_frequency") or "_[to be completed by deployer]_",
            "",
            "## (c) Categories of affected natural persons and groups",
        ]
        lines += [f"- {p}" for p in d.get("c_affected_natural_persons", [])] or ["_[to be completed]_"]
        lines += ["", "## (d) Specific risks of harm (informed by Art. 13 provider information)"]
        lines += [f"- {r}" for r in d.get("d_fundamental_rights_risks", [])] or ["_[to be completed]_"]
        if d.get("d_provider_info_reference_art13"):
            lines += ["", f"_Provider information relied on:_ {d['d_provider_info_reference_art13']}"]
        lines += ["", "## (e) Human oversight measures (per instructions for use)"]
        lines += [f"- {m}" for m in d.get("e_human_oversight_measures", [])] or ["_[to be completed]_"]
        lines += ["", "## (f) Measures on materialisation (incl. internal governance & complaint mechanisms)"]
        lines += [f"- {m}" for m in d.get("f_measures_on_materialisation", [])] or ["_[to be completed]_"]
        lines += ["", "## Charter rights considered"]
        lines += [f"- {r}" for r in d.get("charter_rights_considered", [])]
        lines += [
            "",
            "## Procedural",
            f"- **DPIA cross-reference (Art. 27(4)):** {d.get('dpia_reference_art27_4') or 'none provided'}",
            f"- **Authority notification (Art. 27(3)):** required — file the AI Office template with the market surveillance authority.",
        ]
        comp = d.get("completeness", {})
        if not comp.get("complete", False):
            lines += ["", f"> ⚠ INCOMPLETE — missing: {comp.get('missing_elements')}"]
        return "\n".join(lines)
