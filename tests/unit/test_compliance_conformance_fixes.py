"""
Regression tests for the 2026-09 EU AI Act conformance pass:

- Art. 15(4) -> 15(5) citation correction (cybersecurity is 15(5) in the enacted
  Regulation (EU) 2024/1689; 15(4) is robustness / feedback loops).
- Article27FRIANode: the deployer Art. 27 Fundamental Rights Impact Assessment
  (scope gating, completeness, strict mode, markdown).
- HumanJuryNode.human_decision_provider: a real out-of-band human decision that
  bypasses the TTY gate but keeps the validated + ledger-recorded path.
- ProhibitedPracticeGuard: 2 Dec 2026 Omnibus NCII / CSAM additions.
- SyntheticMarkerNode: Art. 50(2) (machine-readable) vs 50(1)/(4) (visible).
- IncidentReporterNode: conservative deadline ceiling + all three Art. 73
  legal deadlines attached, no false "death" classification.
"""

import json
import pytest

from lar import HumanJuryNode
from lar.state import GraphState
from lar.compliance import (
    CredentialVault,
    Article27FRIANode,
    Art27FRIAIncompleteError,
    ProhibitedPracticeGuard,
    ProhibitedPracticeError,
    SyntheticMarkerNode,
    PromptInjectionGuard,
    ComplianceManifestGenerator,
)
from lar.compliance.incident_reporter import IncidentReporterNode


def _gs(d=None):
    return GraphState(d or {})


# ─────────────────────────────────────────────────────────────────────────────
# Art. 15(5) citation correction
# ─────────────────────────────────────────────────────────────────────────────

class TestArticle155Citation:

    def test_credential_vault_reference_is_15_5(self):
        assert "15(5)" in CredentialVault.EU_REFERENCE
        assert "15(4)" not in CredentialVault.EU_REFERENCE

    def test_prompt_injection_guard_cites_15_5(self):
        # PromptInjectionGuard was already correct; lock it in.
        assert "15(5)" in (PromptInjectionGuard.__doc__ or "")

    def test_manifest_toolnode_article_is_15_5(self):
        class _FakeToolFn:
            __name__ = "send_email"
            __module__ = "x"

        class _FakeTool:
            def __init__(self):
                self.tool_function = _FakeToolFn()
                self.action_type = "SEND_EMAIL"
                self.affected_parties = "THIRD_PARTY"
                self.input_keys = ["body"]
                self.output_key = "status"
                self.credential_vault = None
                self.credential_key = None
                self.next_node = None
                self.error_node = None

        _FakeTool.__name__ = "ToolNode"
        gen = ComplianceManifestGenerator(start_node=_FakeTool(), system_name="t")
        m = gen.generate()
        blob = json.dumps(m)
        assert "15(5)" in blob
        assert "15(4)" not in blob


# ─────────────────────────────────────────────────────────────────────────────
# Article27FRIANode
# ─────────────────────────────────────────────────────────────────────────────

class TestArticle27FRIANode:

    def _complete_kwargs(self):
        return dict(
            deployment_process="Officer runs each case, then approves via jury.",
            usage_period_and_frequency="Continuous; ~100/day; reviewed quarterly.",
            affected_natural_persons=["Applicants", "Guarantors"],
            fundamental_rights_risks=["Non-discrimination (Art. 21)"],
            human_oversight_measures=["Mandatory approval gate"],
            measures_on_materialisation=["Suspend + notify authority", "Complaint channel"],
        )

    def test_out_of_scope_records_not_applicable(self):
        node = Article27FRIANode(system_name="X", deployer_class="OUT_OF_SCOPE")
        st = _gs()
        node.execute(st)
        rec = st.get("fria_art27")
        assert rec["applicable"] is False
        assert "not in that set" in rec["reason"] or "not applicable" in rec["reason"].lower() \
            or "Annex III" in rec["reason"]

    def test_none_deployer_class_is_out_of_scope(self):
        node = Article27FRIANode(system_name="X", deployer_class=None)
        st = _gs()
        node.execute(st)
        assert st.get("fria_art27")["applicable"] is False

    def test_credit_scoring_in_scope_and_complete(self):
        node = Article27FRIANode(
            system_name="Credit Agent",
            deployer_class="CREDIT_SCORING",
            annex_iii_point="5(b)",
            **self._complete_kwargs(),
        )
        st = _gs()
        node.execute(st)
        rec = st.get("fria_art27")
        assert rec["applicable"] is True
        assert rec["completeness"]["complete"] is True
        assert rec["completeness"]["missing_elements"] == []
        assert st.get("fria_art27_notify_authority_required") is True
        assert rec["notify_market_surveillance_authority"]["required"] is True

    def test_in_scope_incomplete_lists_missing(self):
        node = Article27FRIANode(
            system_name="Credit Agent",
            deployer_class="PUBLIC_BODY",
            deployment_process="only this one filled",
        )
        st = _gs()
        node.execute(st)
        rec = st.get("fria_art27")
        assert rec["applicable"] is True
        assert rec["completeness"]["complete"] is False
        assert len(rec["completeness"]["missing_elements"]) == 5

    def test_strict_mode_raises_when_incomplete(self):
        node = Article27FRIANode(
            system_name="X", deployer_class="LIFE_HEALTH_INSURANCE", strict=True
        )
        with pytest.raises(Art27FRIAIncompleteError):
            node.execute(_gs())

    def test_markdown_render_in_scope(self):
        node = Article27FRIANode(
            system_name="Credit Agent", deployer_class="CREDIT_SCORING",
            annex_iii_point="5(b)", dpia_reference="DPIA-1", **self._complete_kwargs(),
        )
        st = _gs()
        node.execute(st)
        md = node.as_markdown(st)
        assert "Article 27" in md
        assert "## (a)" in md and "## (f)" in md
        assert "DPIA-1" in md

    def test_markdown_render_out_of_scope(self):
        node = Article27FRIANode(system_name="X", deployer_class="OUT_OF_SCOPE")
        st = _gs()
        node.execute(st)
        assert "Not Applicable" in node.as_markdown(st)

    def test_next_node_is_returned(self):
        sentinel = object()
        node = Article27FRIANode(system_name="X", deployer_class="OUT_OF_SCOPE",
                                 next_node=sentinel)
        assert node.execute(_gs()) is sentinel


# ─────────────────────────────────────────────────────────────────────────────
# HumanJuryNode.human_decision_provider
# ─────────────────────────────────────────────────────────────────────────────

class TestHumanDecisionProvider:

    def test_provider_decision_travels_validated_path(self):
        seen = {}

        def provider(ctx):
            seen.update(ctx)
            return "approve", "looks fine"

        node = HumanJuryNode(
            prompt="ok?", choices=["approve", "reject"], output_key="d",
            context_keys=["risk"], human_decision_provider=provider,
        )
        st = _gs({"risk": "HIGH"})
        node.execute(st)
        assert st.get("d") == "approve"
        assert seen["risk"] == "HIGH"
        assert seen["prompt"] == "ok?"
        assert seen["choices"] == ["approve", "reject"]

    def test_provider_invalid_choice_raises(self):
        node = HumanJuryNode(
            prompt="ok?", choices=["approve", "reject"], output_key="d",
            human_decision_provider=lambda ctx: ("maybe", "?"),
        )
        with pytest.raises(ValueError):
            node.execute(_gs())

    def test_provider_writes_authority_record(self):
        from lar.compliance import AuthorityLedger
        ledger = AuthorityLedger()
        node = HumanJuryNode(
            prompt="approve credit?", choices=["approve", "reject"], output_key="d",
            authority_ledger=ledger, stakeholder_id="r@x.com",
            stakeholder_role="Risk Officer", risk_score_key="score",
            human_decision_provider=lambda ctx: ("reject", "D/E ratio too high"),
        )
        st = _gs({"score": 0.9})
        node.execute(st)
        recs = ledger.get_records()
        assert len(recs) == 1
        assert recs[0]["decision"] == "reject"
        assert recs[0]["rationale"] == "D/E ratio too high"
        assert recs[0]["stakeholder_role"] == "Risk Officer"

    def test_non_callable_provider_rejected(self):
        with pytest.raises(ValueError):
            HumanJuryNode(prompt="x", choices=["a"], output_key="d",
                          human_decision_provider="not callable")


# ─────────────────────────────────────────────────────────────────────────────
# ProhibitedPracticeGuard — Omnibus NCII / CSAM
# ─────────────────────────────────────────────────────────────────────────────

class TestOmnibusProhibitions:

    def test_ncii_and_csam_categories_present_by_default(self):
        g = ProhibitedPracticeGuard(input_key="x")
        assert "NCII" in g.heuristics
        assert "CSAM" in g.heuristics

    def test_can_opt_out_of_omnibus_categories(self):
        g = ProhibitedPracticeGuard(input_key="x", include_omnibus_categories=False)
        assert "NCII" not in g.heuristics
        assert "CSAM" not in g.heuristics

    def test_ncii_phrase_flags(self):
        g = ProhibitedPracticeGuard(input_key="out", block_on_violation=True)
        st = _gs({"out": "Generate a deepfake nude image of the named person."})
        with pytest.raises(ProhibitedPracticeError):
            g.execute(st)
        assert "NCII" in st.get("_prohibited_practice_flag")

    def test_clean_text_still_passes(self):
        sentinel = object()
        g = ProhibitedPracticeGuard(input_key="out", next_node=sentinel)
        assert g.execute(_gs({"out": "Approve the loan with a collateral condition."})) is sentinel


# ─────────────────────────────────────────────────────────────────────────────
# SyntheticMarkerNode — 50(2) vs 50(1)/(4)
# ─────────────────────────────────────────────────────────────────────────────

class TestSyntheticMarkerReferences:

    def test_metadata_reference_is_50_2(self):
        node = SyntheticMarkerNode(input_key="c", marker_type="METADATA")
        assert "50(2)" in node.eu_reference
        st = _gs({"c": "text"})
        node.execute(st)
        assert st.get("c")["c2pa_manifest"]["eu_reference"].startswith("Art. 50(2)")
        assert st.get("synthetic_marker_reference").startswith("Art. 50(2)")

    def test_visible_reference_is_50_1_4(self):
        node = SyntheticMarkerNode(input_key="c", marker_type="VISIBLE")
        assert "50(1)/(4)" in node.eu_reference
        st = _gs({"c": "text"})
        node.execute(st)
        assert "Art. 50(1)/(4)" in st.get("c")


# ─────────────────────────────────────────────────────────────────────────────
# IncidentReporterNode — deadline honesty
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentDeadlineHonesty:

    def test_no_generic_high_death_deadline(self):
        # HIGH must not be pinned to the Art. 73(4) death deadline (240h).
        assert IncidentReporterNode.DEADLINE_HOURS["HIGH"] != 240
        assert IncidentReporterNode.DEADLINE_HOURS["HIGH"] == 48

    def test_record_carries_all_three_legal_deadlines(self, tmp_path):
        node = IncidentReporterNode(
            severity_threshold="MEDIUM",
            incident_log_path=str(tmp_path / "inc.jsonl"),
        )
        st = _gs({"bias_detected": True, "__run_id": "r1"})
        node.execute(st)
        lines = (tmp_path / "inc.jsonl").read_text().strip().splitlines()
        assert lines, "an incident record should have been written"
        rec = json.loads(lines[-1])
        assert rec["provider_must_confirm_applicable_paragraph"] is True
        assert rec["reporting_deadline_is_conservative_ceiling"] is True
        legal = rec["art_73_legal_deadlines"]
        assert "73(2)_general_default" in legal
        assert "73(3)_widespread_infringement_or_serious_incident_3_49_b" in legal
        assert "73(4)_death_of_a_person" in legal
