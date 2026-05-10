"""
Unit tests for BranchTriageNode.

Covers:
- Clean JSON branch outputs at every risk level
- CRITICAL threshold routing (default and custom thresholds)
- Malformed / empty / missing branch outputs
- branch_findings_summary format and content
- branch_critical flag correctness
- Custom state key names
- next_node passthrough
- Construction validation
"""

import json
import pytest
from unittest.mock import MagicMock

from lar import GraphExecutor, AddValueNode, RouterNode, apply_diff
from lar.node import BaseNode
from lar.state import GraphState
from lar.compliance import BranchTriageNode


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_branch_output(risk_level: str, finding: str = "test finding", confidence: float = 0.9) -> str:
    return json.dumps({"risk_level": risk_level, "finding": finding, "confidence": confidence})

def run_triage(node: BranchTriageNode, initial_state: dict) -> dict:
    """Run node through GraphExecutor and return final state."""
    executor = GraphExecutor()
    log = list(executor.run_step_by_step(start_node=node, initial_state=initial_state))
    final = dict(initial_state)
    for step in log:
        final = apply_diff(final, step["state_diff"])
    return final


# ─────────────────────────────────────────────────────────────────────────────
# Construction validation
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_branch_output_keys_raises():
    with pytest.raises(ValueError, match="branch_output_keys"):
        BranchTriageNode(branch_output_keys=[])

def test_valid_construction():
    node = BranchTriageNode(branch_output_keys=["a", "b"])
    assert node.critical_threshold == "CRITICAL"
    assert node.summary_state_key == "branch_findings_summary"
    assert node.critical_flag_key == "branch_critical"
    assert node.next_node is None


# ─────────────────────────────────────────────────────────────────────────────
# No CRITICAL — all branches within threshold
# ─────────────────────────────────────────────────────────────────────────────

def test_all_low_no_critical():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a", "b", "c"],
        next_node=end,
    )
    state = {
        "a": make_branch_output("LOW"),
        "b": make_branch_output("LOW"),
        "c": make_branch_output("MEDIUM"),
    }
    final = run_triage(node, state)
    assert final["branch_critical"] is False

def test_all_medium_no_critical():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["x", "y"], next_node=end)
    state = {
        "x": make_branch_output("MEDIUM", "finding x"),
        "y": make_branch_output("MEDIUM", "finding y"),
    }
    final = run_triage(node, state)
    assert final["branch_critical"] is False

def test_high_below_critical_threshold():
    """HIGH does not trigger CRITICAL threshold (default)."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a"], next_node=end)
    state = {"a": make_branch_output("HIGH")}
    final = run_triage(node, state)
    assert final["branch_critical"] is False


# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL threshold fires
# ─────────────────────────────────────────────────────────────────────────────

def test_one_critical_branch_sets_flag():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["safety", "efficacy", "regulatory"],
        next_node=end,
    )
    state = {
        "safety":     make_branch_output("CRITICAL", "3 deaths, DSMB suspension"),
        "efficacy":   make_branch_output("MEDIUM",   "PFS improved"),
        "regulatory": make_branch_output("LOW",      "No deviations"),
    }
    final = run_triage(node, state)
    assert final["branch_critical"] is True

def test_all_critical_branches():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a", "b"], next_node=end)
    state = {
        "a": make_branch_output("CRITICAL"),
        "b": make_branch_output("CRITICAL"),
    }
    final = run_triage(node, state)
    assert final["branch_critical"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Custom threshold
# ─────────────────────────────────────────────────────────────────────────────

def test_high_threshold_triggers_on_high():
    """Setting critical_threshold='HIGH' means HIGH branches trigger escalation."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="HIGH",
        next_node=end,
    )
    state = {"a": make_branch_output("HIGH", "elevated risk")}
    final = run_triage(node, state)
    assert final["branch_critical"] is True

def test_high_threshold_does_not_trigger_on_medium():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="HIGH",
        next_node=end,
    )
    state = {"a": make_branch_output("MEDIUM")}
    final = run_triage(node, state)
    assert final["branch_critical"] is False

def test_medium_threshold_triggers_on_medium():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="MEDIUM",
        next_node=end,
    )
    state = {"a": make_branch_output("MEDIUM")}
    final = run_triage(node, state)
    assert final["branch_critical"] is True

def test_low_threshold_triggers_on_low():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="LOW",
        next_node=end,
    )
    state = {"a": make_branch_output("LOW")}
    final = run_triage(node, state)
    assert final["branch_critical"] is True


# ─────────────────────────────────────────────────────────────────────────────
# branch_findings_summary content
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_contains_all_dimensions():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["safety_analysis", "efficacy_analysis"],
        next_node=end,
    )
    state = {
        "safety_analysis":   make_branch_output("HIGH",   "hepatotoxicity noted"),
        "efficacy_analysis": make_branch_output("MEDIUM", "PFS improved"),
    }
    final = run_triage(node, state)
    summary = final["branch_findings_summary"]
    assert "SAFETY" in summary
    assert "EFFICACY" in summary
    assert "HIGH" in summary
    assert "MEDIUM" in summary
    assert "hepatotoxicity noted" in summary
    assert "PFS improved" in summary

def test_summary_strips_analysis_suffix_for_label():
    """'safety_analysis' should appear as 'SAFETY' in the summary label."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["safety_analysis"], next_node=end)
    state = {"safety_analysis": make_branch_output("LOW", "all clear")}
    final = run_triage(node, state)
    assert "SAFETY" in final["branch_findings_summary"]
    assert "safety_analysis" not in final["branch_findings_summary"]

def test_summary_includes_threshold_label():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="HIGH",
        next_node=end,
    )
    state = {"a": make_branch_output("LOW")}
    final = run_triage(node, state)
    assert "HIGH" in final["branch_findings_summary"]


# ─────────────────────────────────────────────────────────────────────────────
# Malformed / missing / empty branch outputs
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_branch_key_does_not_crash():
    """A branch key not present in state should produce UNKNOWN, not raise."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["missing_key"], next_node=end)
    state = {}
    final = run_triage(node, state)
    assert final["branch_critical"] is False
    assert "UNKNOWN" in final["branch_findings_summary"]

def test_empty_string_branch_output():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a"], next_node=end)
    state = {"a": ""}
    final = run_triage(node, state)
    assert final["branch_critical"] is False
    assert "UNKNOWN" in final["branch_findings_summary"]

def test_malformed_json_branch_output():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a"], next_node=end)
    state = {"a": "not json at all"}
    final = run_triage(node, state)
    assert final["branch_critical"] is False

def test_json_missing_risk_level_key():
    """JSON present but missing risk_level field — should be UNKNOWN, not crash."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a"], next_node=end)
    state = {"a": json.dumps({"finding": "something", "confidence": 0.8})}
    final = run_triage(node, state)
    assert final["branch_critical"] is False
    assert "UNKNOWN" in final["branch_findings_summary"]

def test_json_embedded_in_prose():
    """LLMs often wrap JSON in prose or markdown — the parser should still extract it."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["a"], next_node=end)
    state = {"a": 'Here is my assessment:\n```json\n{"risk_level": "CRITICAL", "finding": "severe"}\n```'}
    final = run_triage(node, state)
    assert final["branch_critical"] is True

def test_malformed_does_not_trigger_critical():
    """UNKNOWN rank is -1 — should never trigger escalation."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_threshold="LOW",
        next_node=end,
    )
    state = {"a": "garbage"}
    final = run_triage(node, state)
    assert final["branch_critical"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Custom state key names
# ─────────────────────────────────────────────────────────────────────────────

def test_custom_summary_state_key():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        summary_state_key="my_custom_summary",
        next_node=end,
    )
    state = {"a": make_branch_output("LOW")}
    final = run_triage(node, state)
    assert "my_custom_summary" in final
    assert "branch_findings_summary" not in final

def test_custom_critical_flag_key():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        critical_flag_key="my_critical_flag",
        next_node=end,
    )
    state = {"a": make_branch_output("CRITICAL")}
    final = run_triage(node, state)
    assert "my_critical_flag" in final
    assert final["my_critical_flag"] is True
    assert "branch_critical" not in final

def test_custom_risk_level_and_finding_keys():
    """BranchTriageNode should read from whatever JSON fields are configured."""
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a"],
        risk_level_key="severity",
        finding_key="summary",
        next_node=end,
    )
    state = {"a": json.dumps({"severity": "CRITICAL", "summary": "custom finding field"})}
    final = run_triage(node, state)
    assert final["branch_critical"] is True
    assert "custom finding field" in final["branch_findings_summary"]


# ─────────────────────────────────────────────────────────────────────────────
# Integration with RouterNode — the canonical fractal wiring pattern
# ─────────────────────────────────────────────────────────────────────────────

def test_router_routes_to_ok_when_no_critical():
    """Full wiring: BranchTriageNode → RouterNode → correct path."""
    ok_node      = AddValueNode(key="path_taken", value="ok")
    critical_node = AddValueNode(key="path_taken", value="critical")

    router = RouterNode(
        decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
        path_map={"critical": critical_node, "ok": ok_node},
    )
    triage = BranchTriageNode(
        branch_output_keys=["safety", "efficacy"],
        next_node=router,
    )

    state = {
        "safety":   make_branch_output("HIGH"),
        "efficacy": make_branch_output("MEDIUM"),
    }
    final = run_triage(triage, state)
    assert final["path_taken"] == "ok"

def test_router_routes_to_critical_when_critical():
    ok_node       = AddValueNode(key="path_taken", value="ok")
    critical_node = AddValueNode(key="path_taken", value="critical")

    router = RouterNode(
        decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
        path_map={"critical": critical_node, "ok": ok_node},
    )
    triage = BranchTriageNode(
        branch_output_keys=["safety", "efficacy"],
        next_node=router,
    )

    state = {
        "safety":   make_branch_output("CRITICAL", "fatal adverse event"),
        "efficacy": make_branch_output("MEDIUM",   "acceptable efficacy"),
    }
    final = run_triage(triage, state)
    assert final["path_taken"] == "critical"

def test_branch_findings_summary_survives_into_downstream_state():
    """summary must be in state when downstream nodes (jury) execute."""
    capture = {}

    class CaptureSummary(BaseNode):
        def execute(self, state: GraphState):
            capture["summary"] = state.get("branch_findings_summary")
            return None

    triage = BranchTriageNode(
        branch_output_keys=["a"],
        next_node=CaptureSummary(),
    )
    state = {"a": make_branch_output("HIGH", "elevated risk")}
    executor = GraphExecutor()
    list(executor.run_step_by_step(start_node=triage, initial_state=state))

    assert capture["summary"] is not None
    assert "elevated risk" in capture["summary"]


# ─────────────────────────────────────────────────────────────────────────────
# Mixed batch: some branches CRITICAL, some clean
# ─────────────────────────────────────────────────────────────────────────────

def test_mixed_levels_with_one_critical():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(
        branch_output_keys=["a", "b", "c", "d"],
        next_node=end,
    )
    state = {
        "a": make_branch_output("LOW"),
        "b": make_branch_output("MEDIUM"),
        "c": make_branch_output("HIGH"),
        "d": make_branch_output("CRITICAL", "fatal outcome"),
    }
    final = run_triage(node, state)
    assert final["branch_critical"] is True
    summary = final["branch_findings_summary"]
    assert "LOW" in summary
    assert "MEDIUM" in summary
    assert "HIGH" in summary
    assert "CRITICAL" in summary
    assert "fatal outcome" in summary

def test_single_branch_low():
    end = AddValueNode(key="done", value=True)
    node = BranchTriageNode(branch_output_keys=["only"], next_node=end)
    state = {"only": make_branch_output("LOW", "all clear")}
    final = run_triage(node, state)
    assert final["branch_critical"] is False
    assert "all clear" in final["branch_findings_summary"]
