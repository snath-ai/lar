"""
Unit tests for all compliance primitives in lar.compliance.

Covers:
- PIIRedactionEngine (REDACT / HASH modes, recursive dicts, lists)
- CredentialVault (JIT retrieval, audit callback, missing credential)
- AuthorityRecord + AuthorityLedger (creation, dict serialization, HMAC sign, save/load)
- PolicyRegistry + ActionPolicy (register, get, singleton, clear)
- RiskScorerNode (oversight level routing, confidence escalation, irreversibility escalation)
- BiasFilterNode (bias detected → jury, no bias → next_node, custom terms)
- LethalTrifectaGuard (all 3 legs → raise, partial legs → pass, human approval bypasses)
- SyntheticMarkerNode (VISIBLE disclaimer, METADATA C2PA wrapper, output_key override)
- ProhibitedPracticeGuard (social scoring raise, manipulation raise, clean pass, audit-only mode)
- TransparencyEngine (flag calls callback)
- RuntimeStateVersioner + DriftDetector (snapshot, drift on tool_catalogue, drift on schema)
- ComplianceManifestGenerator (traversal, summary counts, risk flags, markdown output)
- IncidentReporter (empty dir, empty report, no crash)
"""

import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from lar import AddValueNode, GraphExecutor, apply_diff
from lar.state import GraphState
from lar.compliance import (
    PIIRedactionEngine,
    CredentialVault,
    AuthorityRecord,
    AuthorityLedger,
    PolicyRegistry,
    ActionPolicy,
    RiskScorerNode,
    BiasFilterNode,
    LethalTrifectaGuard,
    LethalTrifectaError,
    SyntheticMarkerNode,
    ProhibitedPracticeGuard,
    ProhibitedPracticeError,
    TransparencyEngine,
    RuntimeStateVersioner,
    DriftDetector,
    ComplianceManifestGenerator,
    IncidentReporter,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _gs(d: dict) -> GraphState:
    """Wrap a plain dict in a GraphState."""
    return GraphState(d)


def _run_node(node, initial: dict) -> dict:
    """Run a single node graph, return final state dict."""
    executor = GraphExecutor()
    log = list(executor.run_step_by_step(start_node=node, initial_state=initial))
    final = dict(initial)
    for step in log:
        final = apply_diff(final, step["state_diff"])
    return final


# ─────────────────────────────────────────────────────────────────────────────
# PIIRedactionEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestPIIRedactionEngine:

    def test_redact_mode_default(self):
        eng = PIIRedactionEngine()
        result = eng.process_dict({"email": "alice@example.com", "score": 99})
        assert result["email"] == "[REDACTED]"
        assert result["score"] == 99

    def test_redact_mode_explicit(self):
        eng = PIIRedactionEngine(sensitive_keys=["ssn"], mode="REDACT")
        result = eng.process_dict({"ssn": "123-45-6789", "other": "safe"})
        assert result["ssn"] == "[REDACTED]"
        assert result["other"] == "safe"

    def test_hash_mode(self):
        eng = PIIRedactionEngine(sensitive_keys=["phone"], mode="HASH")
        result = eng.process_dict({"phone": "555-1234", "x": 1})
        assert len(result["phone"]) == 64  # SHA-256 hex digest
        assert result["phone"] != "555-1234"

    def test_hash_mode_is_deterministic(self):
        eng = PIIRedactionEngine(sensitive_keys=["name"], mode="HASH")
        a = eng.process_dict({"name": "Alice"})
        b = eng.process_dict({"name": "Alice"})
        assert a["name"] == b["name"]

    def test_hash_different_values_differ(self):
        eng = PIIRedactionEngine(sensitive_keys=["name"], mode="HASH")
        a = eng.process_dict({"name": "Alice"})
        b = eng.process_dict({"name": "Bob"})
        assert a["name"] != b["name"]

    def test_recursive_nested_dict(self):
        eng = PIIRedactionEngine(sensitive_keys=["email"])
        data = {"user": {"email": "bob@example.com", "age": 30}}
        result = eng.process_dict(data)
        assert result["user"]["email"] == "[REDACTED]"
        assert result["user"]["age"] == 30

    def test_list_of_dicts(self):
        eng = PIIRedactionEngine(sensitive_keys=["email"])
        data = {"records": [{"email": "a@b.com", "id": 1}, {"email": "c@d.com", "id": 2}]}
        result = eng.process_dict(data)
        assert result["records"][0]["email"] == "[REDACTED]"
        assert result["records"][1]["email"] == "[REDACTED]"
        assert result["records"][0]["id"] == 1

    def test_non_sensitive_keys_untouched(self):
        eng = PIIRedactionEngine(sensitive_keys=["email"])
        data = {"diagnosis": "hypertension", "notes": "patient stable"}
        result = eng.process_dict(data)
        assert result == data

    def test_default_sensitive_keys(self):
        eng = PIIRedactionEngine()
        defaults = {"email", "ssn", "phone", "name", "address"}
        assert defaults.issubset(eng.sensitive_keys)

    def test_custom_sensitive_keys_replace_defaults(self):
        eng = PIIRedactionEngine(sensitive_keys=["patient_id"])
        result = eng.process_dict({"patient_id": "P-9999", "email": "doc@hosp.com"})
        assert result["patient_id"] == "[REDACTED]"
        assert result["email"] == "doc@hosp.com"  # not in custom list


# ─────────────────────────────────────────────────────────────────────────────
# CredentialVault
# ─────────────────────────────────────────────────────────────────────────────

class TestCredentialVault:

    def test_register_and_retrieve(self):
        vault = CredentialVault()
        vault.register_credential("MY_API_KEY", "secret-value")
        result = vault.get("my_tool", "read", "MY_API_KEY")
        assert result == "secret-value"

    def test_missing_credential_returns_none(self, monkeypatch):
        vault = CredentialVault()
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        result = vault.get("tool", "scope", "NONEXISTENT_KEY")
        assert result is None

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("TEST_VAULT_KEY", "env-secret")
        vault = CredentialVault()
        result = vault.get("tool", "scope", "TEST_VAULT_KEY")
        assert result == "env-secret"

    def test_registered_credential_takes_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-value")
        vault = CredentialVault()
        vault.register_credential("MY_KEY", "registered-value")
        assert vault.get("tool", "scope", "MY_KEY") == "registered-value"

    def test_audit_callback_fired_on_retrieval(self):
        events = []
        vault = CredentialVault(logger_callback=lambda e: events.append(e))
        vault.register_credential("K", "v")
        vault.get("my_tool", "read_scope", "K")
        assert len(events) == 1
        assert events[0]["type"] == "NHI_CREDENTIAL_ACCESS"
        assert events[0]["tool_name"] == "my_tool"
        assert events[0]["scope"] == "read_scope"

    def test_audit_callback_not_fired_on_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        events = []
        vault = CredentialVault(logger_callback=lambda e: events.append(e))
        vault.get("tool", "scope", "MISSING_KEY")
        assert len(events) == 0


# ─────────────────────────────────────────────────────────────────────────────
# AuthorityRecord + AuthorityLedger
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorityRecord:

    def test_to_dict_contains_required_fields(self):
        rec = AuthorityRecord(
            action_description="Wire $50k",
            stakeholder_id="cfo@corp.com",
            stakeholder_role="CFO",
            decision="approve",
            rationale="Within Q4 budget.",
            risk_score=0.82,
        )
        d = rec.to_dict()
        assert d["record_type"] == "AUTHORITY_EXERCISE"
        assert d["action_description"] == "Wire $50k"
        assert d["stakeholder_id"] == "cfo@corp.com"
        assert d["stakeholder_role"] == "CFO"
        assert d["decision"] == "approve"
        assert d["rationale"] == "Within Q4 budget."
        assert d["risk_score_at_decision"] == 0.82
        assert d["eu_ai_act_article"] == "Art. 12, 14"
        assert d["timestamp"].endswith("Z")

    def test_context_snapshot_keys_captured(self):
        rec = AuthorityRecord(
            action_description="Action",
            stakeholder_id="id",
            stakeholder_role="role",
            decision="approve",
            rationale="ok",
            context_snapshot={"risk_level": "HIGH", "recommendation": "proceed"},
        )
        assert "risk_level" in rec.to_dict()["context_snapshot_keys"]
        assert "recommendation" in rec.to_dict()["context_snapshot_keys"]

    def test_no_context_snapshot_defaults_empty(self):
        rec = AuthorityRecord("a", "b", "c", "d", "e")
        assert rec.to_dict()["context_snapshot_keys"] == []


class TestAuthorityLedger:

    def test_record_appended(self):
        ledger = AuthorityLedger()
        ledger.record("Action A", "user@a.com", "PI", "approve", "Looks good.")
        ledger.record("Action B", "user@b.com", "CRO", "reject", "Out of protocol.")
        records = ledger.get_records()
        assert len(records) == 2
        assert records[0]["decision"] == "approve"
        assert records[1]["decision"] == "reject"

    def test_save_and_reload(self, tmp_path):
        ledger = AuthorityLedger()
        ledger.record("Deploy model", "admin@x.com", "Admin", "approve", "All checks passed.")
        filepath = str(tmp_path / "ledger.json")
        ledger.save(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data["ledger_type"] == "AUTHORITY_EXERCISE_LEDGER"
        assert data["total_records"] == 1
        assert data["records"][0]["decision"] == "approve"

    def test_hmac_signature_present_when_secret_provided(self, tmp_path):
        ledger = AuthorityLedger(hmac_secret="test-secret")
        ledger.record("Action", "u", "r", "approve", "ok")
        filepath = str(tmp_path / "signed_ledger.json")
        ledger.save(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert "signature" in data
        assert len(data["signature"]) == 64

    def test_no_hmac_when_no_secret(self, tmp_path):
        ledger = AuthorityLedger()
        ledger.record("Action", "u", "r", "approve", "ok")
        filepath = str(tmp_path / "unsigned.json")
        ledger.save(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert "signature" not in data

    def test_empty_ledger_save(self, tmp_path):
        ledger = AuthorityLedger()
        filepath = str(tmp_path / "empty.json")
        ledger.save(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data["total_records"] == 0
        assert data["records"] == []


# ─────────────────────────────────────────────────────────────────────────────
# PolicyRegistry + ActionPolicy
# ─────────────────────────────────────────────────────────────────────────────

class TestPolicyRegistry:

    def setup_method(self):
        PolicyRegistry().clear()

    def test_singleton(self):
        a = PolicyRegistry()
        b = PolicyRegistry()
        assert a is b

    def test_register_and_get(self):
        registry = PolicyRegistry()
        policy = ActionPolicy(
            domain="finance",
            process="wire_transfer",
            decision_type="financial",
            risk_tier="HIGH",
            reversibility=False,
            oversight_level="PRE_EXECUTION",
            regulatory_tags=["EU_AI_ACT_ART_14"],
            affected_parties="THIRD_PARTY",
        )
        registry.register("wire_transfer", policy)
        retrieved = registry.get_policy("wire_transfer")
        assert retrieved is policy
        assert retrieved.domain == "finance"
        assert retrieved.reversibility is False

    def test_get_unregistered_returns_none(self):
        assert PolicyRegistry().get_policy("unknown_action") is None

    def test_clear_removes_all(self):
        registry = PolicyRegistry()
        registry.register("a", ActionPolicy("d", "p", "dt", "LOW", True, "RETROSPECTIVE"))
        registry.clear()
        assert registry.get_policy("a") is None


# ─────────────────────────────────────────────────────────────────────────────
# RiskScorerNode
# ─────────────────────────────────────────────────────────────────────────────

class TestRiskScorerNode:

    def setup_method(self):
        PolicyRegistry().clear()

    def test_no_policy_defaults_retrospective_routes_to_next(self):
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(next_node=next_node, jury_node=jury_node)
        final = _run_node(node, {})
        assert final["routed_to"] == "next"
        assert final["computed_oversight_level"] == "RETROSPECTIVE"

    def test_irreversible_action_escalates_to_pre_execution(self):
        PolicyRegistry().register(
            "wire_transfer",
            ActionPolicy("finance", "wire", "financial", "HIGH", False, "REALTIME"),
        )
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(next_node=next_node, jury_node=jury_node)
        final = _run_node(node, {"action_type": "wire_transfer", "model_confidence": 0.9})
        assert final["routed_to"] == "jury"
        assert final["computed_oversight_level"] == "PRE_EXECUTION"

    def test_low_confidence_escalates_oversight(self):
        PolicyRegistry().register(
            "send_email",
            ActionPolicy("comms", "email", "notification", "LOW", True, "RETROSPECTIVE"),
        )
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(next_node=next_node, jury_node=jury_node)
        final = _run_node(node, {"action_type": "send_email", "model_confidence": 0.5})
        assert final["computed_oversight_level"] == "REALTIME"
        assert final["routed_to"] == "next"

    def test_third_party_affected_escalates_retrospective_to_realtime(self):
        PolicyRegistry().register(
            "notify_patient",
            ActionPolicy("clinical", "notify", "communication", "LOW", True, "RETROSPECTIVE",
                         affected_parties="THIRD_PARTY"),
        )
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(next_node=next_node, jury_node=jury_node)
        final = _run_node(node, {"action_type": "notify_patient", "model_confidence": 0.95})
        assert final["computed_oversight_level"] == "REALTIME"

    def test_pre_execution_routes_to_jury(self):
        PolicyRegistry().register(
            "surgery_recommend",
            ActionPolicy("clinical", "recommend", "medical", "CRITICAL", False, "PRE_EXECUTION"),
        )
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(next_node=next_node, jury_node=jury_node)
        final = _run_node(node, {"action_type": "surgery_recommend", "model_confidence": 0.99})
        assert final["routed_to"] == "jury"

    def test_custom_confidence_key(self):
        PolicyRegistry().register(
            "action_x",
            ActionPolicy("d", "p", "dt", "LOW", True, "RETROSPECTIVE"),
        )
        next_node = AddValueNode(key="routed_to", value="next")
        jury_node = AddValueNode(key="routed_to", value="jury")
        node = RiskScorerNode(
            next_node=next_node,
            jury_node=jury_node,
            confidence_key="my_confidence",
        )
        final = _run_node(node, {"action_type": "action_x", "my_confidence": 0.4})
        assert final["computed_oversight_level"] == "REALTIME"


# ─────────────────────────────────────────────────────────────────────────────
# BiasFilterNode
# ─────────────────────────────────────────────────────────────────────────────

class TestBiasFilterNode:

    def test_no_bias_routes_to_next_node(self):
        end = AddValueNode(key="result", value="clean")
        jury = AddValueNode(key="result", value="biased")
        node = BiasFilterNode(input_key="output", next_node=end, jury_node=jury)
        final = _run_node(node, {"output": "The patient should take medication twice daily."})
        assert final["result"] == "clean"
        assert final["bias_detected"] is False

    def test_sensitive_term_triggers_bias_flag(self):
        end = AddValueNode(key="result", value="clean")
        jury = AddValueNode(key="result", value="biased")
        node = BiasFilterNode(input_key="output", next_node=end, jury_node=jury)
        final = _run_node(node, {"output": "Patients over 65 with a disability may need..."})
        assert final["bias_detected"] is True
        assert final["result"] == "biased"

    def test_default_sensitive_terms_includes_race_gender(self):
        node = BiasFilterNode(input_key="x")
        assert "race" in node.sensitive_terms
        assert "gender" in node.sensitive_terms
        assert "religion" in node.sensitive_terms

    def test_custom_sensitive_terms(self):
        end = AddValueNode(key="result", value="ok")
        jury = AddValueNode(key="result", value="flagged")
        node = BiasFilterNode(
            input_key="text",
            sensitive_terms=["cancer_patient"],
            next_node=end,
            jury_node=jury,
        )
        final = _run_node(node, {"text": "All cancer_patient cohorts should..."})
        assert final["bias_detected"] is True
        assert final["result"] == "flagged"

    def test_custom_terms_do_not_match_default_terms(self):
        end = AddValueNode(key="result", value="ok")
        jury = AddValueNode(key="result", value="flagged")
        node = BiasFilterNode(
            input_key="text",
            sensitive_terms=["cancer_patient"],
            next_node=end,
            jury_node=jury,
        )
        # "race" is a default term but not in custom list
        final = _run_node(node, {"text": "The trial race was completed."})
        assert final["bias_detected"] is False

    def test_bias_detected_without_jury_still_routes_to_next(self):
        end = AddValueNode(key="result", value="next")
        node = BiasFilterNode(input_key="text", next_node=end, jury_node=None)
        final = _run_node(node, {"text": "gender gap in outcomes"})
        assert final["bias_detected"] is True
        assert final["result"] == "next"

    def test_empty_content_no_bias(self):
        end = AddValueNode(key="result", value="ok")
        node = BiasFilterNode(input_key="text", next_node=end)
        final = _run_node(node, {"text": ""})
        assert final["bias_detected"] is False


# ─────────────────────────────────────────────────────────────────────────────
# LethalTrifectaGuard
# ─────────────────────────────────────────────────────────────────────────────

class TestLethalTrifectaGuard:

    def _make_guard(self, approval_key="jury_decision", block=True):
        return LethalTrifectaGuard(
            untrusted_input_fn=lambda s: s.get("user_query") is not None,
            sensitive_data_fn=lambda s: s.get("health_data") is not None,
            autonomous_action_fn=lambda s: True,
            human_approval_state_key=approval_key,
            block_on_violation=block,
        )

    def test_all_three_legs_active_no_approval_raises(self):
        guard = self._make_guard()
        state = _gs({"user_query": "query", "health_data": "record"})
        with pytest.raises(LethalTrifectaError):
            guard.check(state, "send_treatment")

    def test_only_two_legs_active_does_not_raise(self):
        guard = self._make_guard()
        # Only leg 1 + leg 3 (sensitive_data missing)
        state = _gs({"user_query": "query"})
        result = guard.check(state, "safe_action")
        assert result["violation"] is False

    def test_all_three_active_with_human_approval_does_not_raise(self):
        guard = self._make_guard()
        state = _gs({"user_query": "query", "health_data": "record", "jury_decision": "approve"})
        result = guard.check(state, "approved_action")
        assert result["violation"] is False
        assert result["human_prior_approval"] is True

    def test_audit_only_mode_does_not_raise_on_violation(self):
        guard = self._make_guard(block=False)
        state = _gs({"user_query": "q", "health_data": "d"})
        result = guard.check(state, "audit_only_action")
        assert result["violation"] is True  # detected
        # But no exception raised

    def test_result_written_to_state(self):
        guard = self._make_guard(block=False)
        state = _gs({"user_query": "q"})
        guard.check(state, "action")
        assert state.get("_trifecta_check") is not None
        assert state.get("_trifecta_check")["check_type"] == "LETHAL_TRIFECTA_AEPD_RULE_OF_2"

    def test_result_fields_correct_for_no_legs(self):
        guard = self._make_guard()
        state = _gs({})  # no untrusted input, no health data, but leg3 always True
        result = guard.check(state, "safe")
        assert result["leg1_untrusted_input"] is False
        assert result["leg2_sensitive_data"] is False
        assert result["leg3_autonomous_action"] is True
        assert result["all_three_active"] is False

    def test_custom_approval_key(self):
        guard = LethalTrifectaGuard(
            untrusted_input_fn=lambda s: True,
            sensitive_data_fn=lambda s: True,
            autonomous_action_fn=lambda s: True,
            human_approval_state_key="my_custom_approval",
        )
        state = _gs({"my_custom_approval": "approved"})
        result = guard.check(state, "action")
        assert result["violation"] is False


# ─────────────────────────────────────────────────────────────────────────────
# SyntheticMarkerNode
# ─────────────────────────────────────────────────────────────────────────────

class TestSyntheticMarkerNode:

    def test_visible_marker_appends_disclaimer_to_string(self):
        end = AddValueNode(key="done", value=True)
        node = SyntheticMarkerNode(input_key="report", marker_type="VISIBLE", next_node=end)
        final = _run_node(node, {"report": "Drug X shows efficacy."})
        assert "Drug X shows efficacy." in final["report"]
        assert "AI system" in final["report"]
        assert "Disclaimer" in final["report"]

    def test_visible_marker_on_dict_adds_disclaimer_field(self):
        end = AddValueNode(key="done", value=True)
        node = SyntheticMarkerNode(input_key="data", marker_type="VISIBLE", next_node=end)
        final = _run_node(node, {"data": {"value": 42}})
        assert "_ai_disclaimer" in final["data"]
        assert "Generated by AI" in final["data"]["_ai_disclaimer"]

    def test_metadata_marker_creates_c2pa_wrapper(self):
        end = AddValueNode(key="done", value=True)
        node = SyntheticMarkerNode(input_key="content", marker_type="METADATA", next_node=end)
        final = _run_node(node, {"content": "some text"})
        assert "c2pa_manifest" in final["content"]
        assert final["content"]["c2pa_manifest"]["assertion"] == "AI_GENERATED"
        assert final["content"]["content"] == "some text"

    def test_output_key_override_leaves_input_key_untouched(self):
        end = AddValueNode(key="done", value=True)
        node = SyntheticMarkerNode(
            input_key="raw", output_key="marked", marker_type="VISIBLE", next_node=end
        )
        final = _run_node(node, {"raw": "original text"})
        assert "raw" in final
        assert "marked" in final
        assert "Disclaimer" in final["marked"]

    def test_missing_input_key_skips_marking(self):
        end = AddValueNode(key="done", value=True)
        node = SyntheticMarkerNode(input_key="missing_key", next_node=end)
        final = _run_node(node, {})
        assert final["done"] is True

    def test_visible_is_default_marker_type(self):
        node = SyntheticMarkerNode(input_key="x")
        assert node.marker_type == "VISIBLE"


# ─────────────────────────────────────────────────────────────────────────────
# ProhibitedPracticeGuard
# ─────────────────────────────────────────────────────────────────────────────

class TestProhibitedPracticeGuard:
    """
    Tests call node.execute() directly because GraphExecutor catches all node exceptions
    internally (logging them as error steps) rather than re-raising them to the caller.
    Direct execute() is the correct boundary to test guard violation semantics.
    """

    def test_clean_output_passes_through(self):
        end = AddValueNode(key="result", value="ok")
        node = ProhibitedPracticeGuard(input_key="output", next_node=end)
        state = _gs({"output": "Patient should take 10mg daily. Standard protocol."})
        next_n = node.execute(state)
        assert next_n is end

    def test_social_scoring_raises(self):
        node = ProhibitedPracticeGuard(input_key="output")
        state = _gs({"output": "Based on their social credit score, this patient..."})
        with pytest.raises(ProhibitedPracticeError):
            node.execute(state)

    def test_manipulation_keyword_raises(self):
        node = ProhibitedPracticeGuard(input_key="output")
        state = _gs({"output": "You must act now or lose your chance."})
        with pytest.raises(ProhibitedPracticeError):
            node.execute(state)

    def test_vulnerability_exploitation_raises(self):
        node = ProhibitedPracticeGuard(input_key="output")
        state = _gs({"output": "To target elderly patients with this intervention..."})
        with pytest.raises(ProhibitedPracticeError):
            node.execute(state)

    def test_audit_only_mode_sets_flag_but_does_not_raise(self):
        end = AddValueNode(key="done", value=True)
        node = ProhibitedPracticeGuard(
            input_key="output", next_node=end, block_on_violation=False
        )
        state = _gs({"output": "social credit scoring is enabled"})
        node.execute(state)
        assert "SOCIAL_SCORING" in state.get("_prohibited_practice_flag")

    def test_empty_output_passes(self):
        end = AddValueNode(key="done", value=True)
        node = ProhibitedPracticeGuard(input_key="output", next_node=end)
        state = _gs({"output": ""})
        next_n = node.execute(state)
        assert next_n is end

    def test_case_insensitive_matching(self):
        node = ProhibitedPracticeGuard(input_key="output")
        state = _gs({"output": "SOCIAL CREDIT system assigned rank 4."})
        with pytest.raises(ProhibitedPracticeError):
            node.execute(state)

    def test_violation_flag_set_in_state(self):
        node = ProhibitedPracticeGuard(input_key="output", block_on_violation=False)
        state = _gs({"output": "target minors for this campaign"})
        node.execute(state)
        assert state.get("_prohibited_practice_flag") is not None
        assert "VULNERABILITY_EXPLOIT" in state.get("_prohibited_practice_flag")


# ─────────────────────────────────────────────────────────────────────────────
# TransparencyEngine
# ─────────────────────────────────────────────────────────────────────────────

class TestTransparencyEngine:

    def test_flag_calls_callback(self):
        events = []
        engine = TransparencyEngine(logger_callback=lambda e: events.append(e))
        engine.flag(
            action_type="send_notification",
            tool_name="email_tool",
            affected_description="trial participants",
            run_id="run-42",
        )
        assert len(events) == 1
        assert events[0]["type"] == "AI_INTERACTION_DISCLOSURE"
        assert events[0]["tool_name"] == "email_tool"
        assert events[0]["affected_description"] == "trial participants"
        assert events[0]["run_id"] == "run-42"

    def test_flag_without_callback_does_not_crash(self):
        engine = TransparencyEngine()
        engine.flag("send_sms", "sms_tool", "patients", "run-1")

    def test_flag_timestamp_present(self):
        events = []
        engine = TransparencyEngine(logger_callback=lambda e: events.append(e))
        engine.flag("action", "tool", "desc", "id")
        assert "timestamp" in events[0]

    def test_multiple_flags_all_captured(self):
        events = []
        engine = TransparencyEngine(logger_callback=lambda e: events.append(e))
        engine.flag("a1", "t1", "d1", "r1")
        engine.flag("a2", "t2", "d2", "r2")
        assert len(events) == 2
        assert events[1]["tool_name"] == "t2"


# ─────────────────────────────────────────────────────────────────────────────
# RuntimeStateVersioner + DriftDetector
# ─────────────────────────────────────────────────────────────────────────────

class TestRuntimeStateVersioner:

    def test_first_snapshot_stored_no_drift(self):
        versioner = RuntimeStateVersioner(conformity_baseline_id="v1")
        snap = versioner.snapshot(
            tool_catalogue=["email_tool"],
            state_schema_keys=["input", "output"],
            policy_bindings={"send_email": "REALTIME"},
        )
        assert snap["conformity_baseline_id"] == "v1"
        assert "drift_report" not in snap

    def test_identical_snapshots_no_drift(self):
        versioner = RuntimeStateVersioner()
        versioner.snapshot(["tool_a"], ["k1"], {"p": "v"})
        snap2 = versioner.snapshot(["tool_a"], ["k1"], {"p": "v"})
        assert "drift_report" not in snap2

    def test_tool_catalogue_change_triggers_high_severity_drift(self):
        versioner = RuntimeStateVersioner()
        versioner.snapshot(["tool_a"], ["k1"], {})
        snap2 = versioner.snapshot(["tool_a", "tool_b"], ["k1"], {})
        assert snap2["drift_report"]["drift_detected"] is True
        assert "tool_catalogue" in snap2["drift_report"]["changed_keys"]
        assert snap2["drift_report"]["severity"] == "HIGH"

    def test_schema_key_change_triggers_medium_drift(self):
        versioner = RuntimeStateVersioner()
        versioner.snapshot(["tool_a"], ["k1"], {})
        snap2 = versioner.snapshot(["tool_a"], ["k1", "k2"], {})
        assert snap2["drift_report"]["drift_detected"] is True
        assert "state_schema_keys" in snap2["drift_report"]["changed_keys"]
        assert snap2["drift_report"]["severity"] == "MEDIUM"

    def test_policy_change_triggers_medium_drift(self):
        versioner = RuntimeStateVersioner()
        versioner.snapshot(["t"], ["k"], {"action": "RETROSPECTIVE"})
        snap2 = versioner.snapshot(["t"], ["k"], {"action": "PRE_EXECUTION"})
        assert snap2["drift_report"]["drift_detected"] is True
        assert "policy_bindings" in snap2["drift_report"]["changed_keys"]

    def test_multiple_snapshots_drift_against_baseline(self):
        versioner = RuntimeStateVersioner()
        versioner.snapshot(["tool_a"], ["k1"], {})
        versioner.snapshot(["tool_a", "tool_b"], ["k1"], {})
        # Third snap — same as baseline
        snap3 = versioner.snapshot(["tool_a"], ["k1"], {})
        # Drift should be absent because tool_catalogue matches baseline
        assert "drift_report" not in snap3


class TestDriftDetector:

    def test_no_drift_identical_snapshots(self):
        a = {"tool_catalogue": ["t1"], "state_schema_keys": ["k1"], "policy_bindings": {}}
        report = DriftDetector.compare(a, dict(a))
        assert report.drift_detected is False
        assert report.severity == "LOW"

    def test_tool_catalogue_drift(self):
        a = {"tool_catalogue": ["t1"], "state_schema_keys": [], "policy_bindings": {}}
        b = {"tool_catalogue": ["t1", "t2"], "state_schema_keys": [], "policy_bindings": {}}
        report = DriftDetector.compare(a, b)
        assert report.drift_detected is True
        assert "tool_catalogue" in report.changed_keys
        assert report.severity == "HIGH"

    def test_schema_drift_only(self):
        a = {"tool_catalogue": ["t1"], "state_schema_keys": ["k1"], "policy_bindings": {}}
        b = {"tool_catalogue": ["t1"], "state_schema_keys": ["k1", "k2"], "policy_bindings": {}}
        report = DriftDetector.compare(a, b)
        assert report.drift_detected is True
        assert report.severity == "MEDIUM"


# ─────────────────────────────────────────────────────────────────────────────
# ComplianceManifestGenerator
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceManifestGenerator:

    def _simple_chain(self):
        """AddValueNode → AddValueNode (no LLMNode, just structural test)."""
        end = AddValueNode(key="done", value=True)
        start = AddValueNode(key="step", value=1, next_node=end)
        return start

    def test_generate_returns_dict_with_required_keys(self):
        manifest = ComplianceManifestGenerator(
            start_node=self._simple_chain(), system_name="Test System"
        )
        report = manifest.generate()
        assert "manifest_version" in report
        assert "system_name" in report
        assert report["system_name"] == "Test System"
        assert "summary" in report
        assert "action_inventory" in report
        assert "risk_flags" in report
        assert "generated_at" in report

    def test_generate_inventories_nodes(self):
        manifest = ComplianceManifestGenerator(start_node=self._simple_chain())
        report = manifest.generate()
        assert report["summary"]["total_nodes_inventoried"] > 0

    def test_save_creates_json_file(self, tmp_path):
        filepath = str(tmp_path / "manifest.json")
        manifest = ComplianceManifestGenerator(start_node=self._simple_chain())
        manifest.save(filepath)
        assert os.path.exists(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data["manifest_version"] == "2.0"

    def test_as_markdown_returns_string_with_headers(self):
        manifest = ComplianceManifestGenerator(
            start_node=self._simple_chain(), system_name="Pharma Agent"
        )
        md = manifest.as_markdown()
        assert "# Compliance Manifest: Pharma Agent" in md
        assert "## Summary" in md
        assert "## Risk Flags" in md
        assert "## Action Inventory" in md

    def test_tool_node_detected_in_inventory(self):
        from lar import ToolNode

        def dummy_tool(state):
            return {"result": "ok"}

        end = AddValueNode(key="done", value=True)
        tool = ToolNode(
            tool_function=dummy_tool,
            input_keys=["input"],
            output_key="result",
            next_node=end,
        )
        manifest = ComplianceManifestGenerator(start_node=tool)
        report = manifest.generate()
        types = [e["node_type"] for e in report["action_inventory"]]
        assert "ToolNode" in types

    def test_tool_without_vault_triggers_risk_flag(self):
        from lar import ToolNode

        def dummy_tool(state):
            return {}

        end = AddValueNode(key="done", value=True)
        tool = ToolNode(
            tool_function=dummy_tool,
            input_keys=[],
            output_key="out",
            next_node=end,
        )
        manifest = ComplianceManifestGenerator(start_node=tool)
        report = manifest.generate()
        severities = [f["severity"] for f in report["risk_flags"]]
        assert "HIGH" in severities

    def test_generate_called_implicitly_by_save(self, tmp_path):
        filepath = str(tmp_path / "m.json")
        manifest = ComplianceManifestGenerator(start_node=self._simple_chain())
        # Do NOT call generate() manually — save() should call it
        manifest.save(filepath)
        assert os.path.exists(filepath)

    def test_no_risk_flags_for_simple_safe_graph(self):
        manifest = ComplianceManifestGenerator(start_node=self._simple_chain())
        report = manifest.generate()
        # AddValueNode has no external actions or ToolNodes, so no HIGH flags
        high_flags = [f for f in report["risk_flags"] if f.get("severity") == "HIGH"]
        assert len(high_flags) == 0


# ─────────────────────────────────────────────────────────────────────────────
# IncidentReporter
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentReporter:

    def test_missing_log_dir_returns_no_logs_message(self, tmp_path):
        reporter = IncidentReporter(log_dir=str(tmp_path / "nonexistent"))
        report = reporter.generate_report()
        assert "No logs found" in report

    def test_empty_log_dir_generates_report_without_crash(self, tmp_path):
        reporter = IncidentReporter(log_dir=str(tmp_path))
        report = reporter.generate_report()
        assert "Post-Market Monitoring" in report
        assert "Total Executions Analyzed:** 0" in report

    def test_report_contains_required_sections(self, tmp_path):
        reporter = IncidentReporter(log_dir=str(tmp_path))
        report = reporter.generate_report()
        assert "Volume Metrics" in report
        assert "Risk & Incident Metrics" in report
        assert "Human Oversight" in report

    def test_run_log_parsed_and_counted(self, tmp_path):
        run_log = {
            "steps": [
                {"state_diff": {"added": {"risk_level": "CRITICAL"}, "updated": {}}},
                {"state_diff": {"added": {}, "updated": {}}},
            ]
        }
        log_path = tmp_path / "run_001.json"
        log_path.write_text(json.dumps(run_log))

        reporter = IncidentReporter(log_dir=str(tmp_path))
        report = reporter.generate_report()
        assert "Total Executions Analyzed:** 1" in report
        assert "CRITICAL Risk Scorer Events:** 1" in report

    def test_authority_ledger_parsed(self, tmp_path):
        ledger = AuthorityLedger()
        ledger.record("Deploy", "u1@c.com", "Admin", "approve", "ok")
        ledger.record("Override", "u2@c.com", "PI", "reject", "unsafe")
        ledger.save(str(tmp_path / "authority_ledger.json"))

        reporter = IncidentReporter(log_dir=str(tmp_path))
        report = reporter.generate_report()
        assert "Total Human Jury Decisions:** 2" in report
        assert "Approvals:** 1" in report
        assert "Rejections:** 1" in report
