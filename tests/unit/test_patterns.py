import pytest
from lar import (GraphState, FunctionalNode, RuleFloor, ProposeValidateNode, check_proposal, ApprovalBinding,
                 GraphExecutor)


# ---- RuleFloor
def test_model_cannot_lower_rules():
    f = RuleFloor()
    lvl, reasons, human = f.decide("HIGH", ["big"], model_level="LOW")
    assert lvl == "HIGH" and "model_rated_lower_than_rules" in reasons and human


def test_model_can_raise():
    lvl, _, human = RuleFloor().decide("LOW", [], model_level="CRITICAL")
    assert lvl == "CRITICAL" and human


@pytest.mark.parametrize("bad", [None, "", "banana", "low"])
def test_invalid_model_fails_toward_oversight(bad):
    lvl, reasons, human = RuleFloor().decide("LOW", [], model_level=bad)
    assert lvl == "MEDIUM" and "model_output_invalid" in reasons and human


def test_clean_low_goes_auto():
    assert RuleFloor().decide("LOW", [], model_level="LOW")[2] is False


def test_flags_force_human_even_when_low():
    lvl, reasons, human = RuleFloor().decide("LOW", [], model_level="LOW", flags=["tool_error:kyc"])
    assert lvl == "LOW" and human and "tool_error:kyc" in reasons


@pytest.mark.parametrize("conf", [0.1, float("nan"), "0.99", True])
def test_low_or_garbled_confidence_forces_human(conf):
    _, reasons, human = RuleFloor(min_confidence=0.8).decide("LOW", [], model_level="LOW", model_confidence=conf)
    assert human and "low_model_confidence" in reasons


def test_unknown_rule_level_rejected():
    with pytest.raises(ValueError):
        RuleFloor().decide("SEVERE", [], model_level="LOW")


# ---- propose / validate
@pytest.mark.parametrize("val,expect", [
    (100.0, []), (None, ["missing"]), ("100", ["not_a_number"]), (True, ["not_a_number"]),
    (float("inf"), ["not_finite"]), (float("nan"), ["not_finite"]),
])
def test_check_proposal_garbled(val, expect):
    assert check_proposal(val, 100.0, cap=1000) == expect


@pytest.mark.parametrize("val,problem", [(-100, "negative"), (0, "differs_from_computed_amount"),
                                         (50, "differs_from_computed_amount"), (5000, "over_cap")])
def test_check_proposal_readable_but_wrong(val, problem):
    assert problem in check_proposal(val, 100.0, cap=1000)


def test_node_always_uses_computed_value():
    n = ProposeValidateNode("proposed", lambda s: s["a"] + s["b"], out="amt", cap=1000)
    st = GraphState({"a": 40, "b": 60, "proposed": 9999})
    n.execute(st)
    assert st.get("amt_used") == 100 and st.get("amt_ok") is False and "over_cap" in st.get("amt_problems")
    st2 = GraphState({"a": 40, "b": 60, "proposed": 100})
    n.execute(st2)
    assert st2.get("amt_ok") is True and st2.get("amt_used") == 100


# ---- ApprovalBinding
def test_binding_valid_then_stale():
    b = ApprovalBinding(); st = GraphState({"case_id": "C1"})
    b.bind(st, {"amount": 100, "payee": "A"})
    assert b.is_valid(st, {"amount": 100, "payee": "A"})
    assert not b.is_valid(st, {"amount": 100, "payee": "B"})


def test_unbound_is_never_valid():
    assert not ApprovalBinding().is_valid(GraphState({}), {"x": 1})


def test_check_node_routes_and_fails_closed():
    ok = FunctionalNode(lambda s: s.set("r", "ok")); stale = FunctionalNode(lambda s: s.set("r", "stale"))
    live = {"v": {"amount": 100}}
    b = ApprovalBinding()
    node = b.check_node(lambda s: live["v"], ok, stale)
    st = GraphState({"case_id": "C1"}); b.bind(st, {"amount": 100})
    assert node.execute(st) is ok
    live["v"] = {"amount": 101}
    assert node.execute(st) is stale
    def boom(s): raise ConnectionError("down")
    assert b.check_node(boom, ok, stale).execute(st) is stale


def test_intent_key_is_deterministic():
    b = ApprovalBinding(); a = GraphState({"case_id": "C1"}); c = GraphState({"case_id": "C1"})
    assert b.intent(a, "write_off") == b.intent(c, "write_off") == "C1:write_off"
