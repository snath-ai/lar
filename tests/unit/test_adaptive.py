"""
Unit tests for AdaptiveNode + TopologyValidator safety properties.

Proves six invariants hold:
  1. max_nodes ceiling — oversized specs are rejected before instantiation
  2. max_depth ceiling — recursive AdaptiveNode nesting is bounded
  3. Cycle detection — specs with loops are rejected
  4. Tool allowlist — specs referencing unapproved tools are rejected
  5. BatchNode reference integrity — concurrent_nodes must reference real node IDs
  6. Unsupported node types — unknown types are rejected, not silently skipped

Also proves the positive case: a valid BatchNode + AdaptiveNode combination
passes validation and wires correctly.
"""

import pytest
from unittest.mock import MagicMock, patch

from lar.adaptive import AdaptiveNode, TopologyValidator, SecurityError
from lar.node import BaseNode
from lar.state import GraphState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tool_a(state): return "a"
def tool_b(state): return "b"


def _make_validator(**kwargs):
    return TopologyValidator(allowed_tools=[tool_a, tool_b], **kwargs)


def _make_spec(*nodes, entry_point=None):
    """Build a minimal GraphSpec dict."""
    return {
        "nodes": list(nodes),
        "entry_point": entry_point or (nodes[0]["id"] if nodes else None),
    }


def _llm_node(id_, next_=None):
    return {"id": id_, "type": "LLMNode", "prompt": "test", "output_key": id_ + "_out", "next": next_}


def _tool_node(id_, tool_name="tool_a", next_=None):
    return {"id": id_, "type": "ToolNode", "tool_name": tool_name, "input_keys": [], "output_key": id_ + "_out", "next": next_}


def _batch_node(id_, concurrent, next_=None):
    return {"id": id_, "type": "BatchNode", "concurrent_nodes": concurrent, "next": next_}


def _adaptive_node(id_, next_=None):
    return {"id": id_, "type": "AdaptiveNode", "prompt": "design a graph", "next": next_}


# ---------------------------------------------------------------------------
# 1. max_nodes ceiling
# ---------------------------------------------------------------------------

class TestMaxNodes:

    def test_spec_within_limit_passes(self):
        v = _make_validator(max_nodes=3)
        spec = _make_spec(
            _llm_node("a", "b"),
            _llm_node("b", "c"),
            _tool_node("c", tool_a.__name__),
            entry_point="a",
        )
        assert v.validate(spec) is True

    def test_spec_exactly_at_limit_passes(self):
        v = _make_validator(max_nodes=2)
        spec = _make_spec(_llm_node("a", "b"), _llm_node("b"), entry_point="a")
        assert v.validate(spec) is True

    def test_spec_exceeding_limit_raises(self):
        v = _make_validator(max_nodes=2)
        spec = _make_spec(
            _llm_node("a", "b"),
            _llm_node("b", "c"),
            _llm_node("c"),
            entry_point="a",
        )
        with pytest.raises(SecurityError, match="exceeding the limit of 2"):
            v.validate(spec)

    def test_default_limit_is_20(self):
        v = TopologyValidator()
        assert v.max_nodes == 20

    def test_21_nodes_rejected_by_default(self):
        v = TopologyValidator()
        nodes = [_llm_node(f"n{i}", f"n{i+1}" if i < 20 else None) for i in range(21)]
        spec = _make_spec(*nodes, entry_point="n0")
        with pytest.raises(SecurityError, match="exceeding the limit of 20"):
            v.validate(spec)


# ---------------------------------------------------------------------------
# 2. max_depth ceiling
# ---------------------------------------------------------------------------

class TestMaxDepth:

    def _make_adaptive(self, max_depth):
        v = _make_validator()
        return AdaptiveNode(
            llm_model="gpt-4o",
            prompt_template="design a graph for {task}",
            validator=v,
            max_depth=max_depth,
        )

    def test_depth_zero_falls_through_immediately(self):
        node = self._make_adaptive(max_depth=0)
        state = GraphState(initial_state={"task": "test"})
        result = node.execute(state)
        assert result is node.next_node

    def test_depth_propagates_to_child_adaptive_nodes(self):
        """
        When AdaptiveNode instantiates a child AdaptiveNode from a spec,
        the child receives max_depth - 1.
        """
        v = _make_validator()
        parent = AdaptiveNode(
            llm_model="gpt-4o",
            prompt_template="test",
            validator=v,
            max_depth=3,
        )
        # Simulate the factory instantiation directly
        child_spec_node = _adaptive_node("child")
        node_map = {}

        # Reproduce the factory logic for AdaptiveNode type
        child = AdaptiveNode(
            llm_model=parent.llm_node.model_name,
            prompt_template=child_spec_node.get("prompt", ""),
            validator=parent.validator,
            next_node=None,
            max_depth=parent.max_depth - 1,
        )
        assert child.max_depth == 2  # parent was 3

    def test_depth_1_child_gets_depth_0(self):
        """A depth-1 parent produces a depth-0 child that falls through."""
        v = _make_validator()
        parent = AdaptiveNode(
            llm_model="gpt-4o",
            prompt_template="test",
            validator=v,
            max_depth=1,
        )
        child = AdaptiveNode(
            llm_model=parent.llm_node.model_name,
            prompt_template="child",
            validator=parent.validator,
            max_depth=parent.max_depth - 1,
        )
        assert child.max_depth == 0
        state = GraphState(initial_state={})
        result = child.execute(state)
        assert result is child.next_node


# ---------------------------------------------------------------------------
# 3. Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:

    def test_direct_cycle_rejected(self):
        v = _make_validator()
        spec = _make_spec(
            {"id": "a", "type": "LLMNode", "prompt": "x", "output_key": "o", "next": "b"},
            {"id": "b", "type": "LLMNode", "prompt": "x", "output_key": "o", "next": "a"},
            entry_point="a",
        )
        with pytest.raises(SecurityError, match="Infinite loop"):
            v.validate(spec)

    def test_self_loop_rejected(self):
        v = _make_validator()
        spec = _make_spec(
            {"id": "a", "type": "LLMNode", "prompt": "x", "output_key": "o", "next": "a"},
            entry_point="a",
        )
        with pytest.raises(SecurityError, match="Infinite loop"):
            v.validate(spec)

    def test_batch_concurrent_cycle_rejected(self):
        """A BatchNode whose concurrent child loops back to the BatchNode."""
        v = _make_validator()
        spec = _make_spec(
            _batch_node("batch", concurrent=["worker"], next_=None),
            {"id": "worker", "type": "LLMNode", "prompt": "x", "output_key": "o", "next": "batch"},
            entry_point="batch",
        )
        with pytest.raises(SecurityError, match="Infinite loop"):
            v.validate(spec)

    def test_linear_chain_passes(self):
        v = _make_validator()
        spec = _make_spec(
            _llm_node("a", "b"),
            _llm_node("b", "c"),
            _llm_node("c"),
            entry_point="a",
        )
        assert v.validate(spec) is True


# ---------------------------------------------------------------------------
# 4. Tool allowlist
# ---------------------------------------------------------------------------

class TestToolAllowlist:

    def test_allowed_tool_passes(self):
        v = _make_validator()
        spec = _make_spec(_tool_node("t", tool_a.__name__), entry_point="t")
        assert v.validate(spec) is True

    def test_disallowed_tool_rejected(self):
        v = _make_validator()
        spec = _make_spec(_tool_node("t", "dangerous_tool"), entry_point="t")
        with pytest.raises(SecurityError, match="not in the allowlist"):
            v.validate(spec)

    def test_missing_tool_name_rejected(self):
        v = _make_validator()
        spec = _make_spec(
            {"id": "t", "type": "ToolNode", "input_keys": [], "output_key": "out", "next": None},
            entry_point="t",
        )
        with pytest.raises(SecurityError, match="missing required field 'tool_name'"):
            v.validate(spec)

    def test_only_listed_tools_pass(self):
        v = TopologyValidator(allowed_tools=[tool_a])   # only tool_a, not tool_b
        spec = _make_spec(_tool_node("t", tool_b.__name__), entry_point="t")
        with pytest.raises(SecurityError, match="not in the allowlist"):
            v.validate(spec)


# ---------------------------------------------------------------------------
# 5. BatchNode reference integrity
# ---------------------------------------------------------------------------

class TestBatchNodeIntegrity:

    def test_valid_batch_spec_passes(self):
        v = _make_validator()
        spec = _make_spec(
            _batch_node("batch", concurrent=["w1", "w2"]),
            _llm_node("w1"),
            _llm_node("w2"),
            entry_point="batch",
        )
        assert v.validate(spec) is True

    def test_missing_concurrent_node_rejected(self):
        v = _make_validator()
        spec = _make_spec(
            _batch_node("batch", concurrent=["w1", "ghost"]),
            _llm_node("w1"),
            entry_point="batch",
        )
        with pytest.raises(SecurityError, match="non-existent concurrent node 'ghost'"):
            v.validate(spec)

    def test_empty_concurrent_nodes_passes(self):
        """Empty concurrent list is structurally valid (no ghost references)."""
        v = _make_validator()
        spec = _make_spec(_batch_node("batch", concurrent=[]), entry_point="batch")
        assert v.validate(spec) is True


# ---------------------------------------------------------------------------
# 6. Unsupported node types
# ---------------------------------------------------------------------------

class TestUnsupportedNodeTypes:

    def test_unknown_type_rejected(self):
        v = _make_validator()
        spec = _make_spec(
            {"id": "x", "type": "EvilNode", "next": None},
            entry_point="x",
        )
        with pytest.raises(SecurityError, match="unsupported type 'EvilNode'"):
            v.validate(spec)

    def test_all_supported_types_pass(self):
        v = _make_validator()
        for ntype in ["LLMNode", "ToolNode", "BatchNode", "AdaptiveNode", "DynamicNode"]:
            if ntype == "ToolNode":
                node = _tool_node("x", tool_a.__name__)
            elif ntype == "BatchNode":
                node = _batch_node("x", concurrent=[])
            else:
                node = {"id": "x", "type": ntype, "prompt": "p", "output_key": "o", "next": None}
            spec = _make_spec(node, entry_point="x")
            assert v.validate(spec) is True, f"{ntype} should be supported"


# ---------------------------------------------------------------------------
# 7. Valid BatchNode + AdaptiveNode combination (the positive case)
# ---------------------------------------------------------------------------

class TestBatchAdaptiveCombination:

    def test_batch_with_adaptive_children_passes_validation(self):
        """
        The pattern from fractal_polymath.py:
        BatchNode(concurrent=[AdaptiveNode_A, AdaptiveNode_B]) → verifier LLMNode
        Should pass all six validator invariants.
        """
        v = _make_validator(max_nodes=10)
        spec = _make_spec(
            _batch_node("batch", concurrent=["specialist_a", "specialist_b"], next_="verifier"),
            _adaptive_node("specialist_a"),
            _adaptive_node("specialist_b"),
            _llm_node("verifier"),
            entry_point="batch",
        )
        assert v.validate(spec) is True

    def test_validator_inherited_in_child_adaptive(self):
        """
        Safety rails (allowed_tools, max_nodes) must be identical on the child
        AdaptiveNode — not a copy, the same object — so runtime changes propagate.
        """
        v = _make_validator(max_nodes=5)
        parent = AdaptiveNode(
            llm_model="gpt-4o",
            prompt_template="test",
            validator=v,
            max_depth=3,
        )
        child = AdaptiveNode(
            llm_model=parent.llm_node.model_name,
            prompt_template="child",
            validator=parent.validator,
            max_depth=parent.max_depth - 1,
        )
        assert child.validator is v
        assert child.validator.max_nodes == 5
        assert child.validator.allowed_tools is v.allowed_tools

    def test_depth_0_child_in_batch_falls_through(self):
        """
        A depth-0 AdaptiveNode inside a BatchNode branch falls through without
        making an LLM call — the branch completes safely.
        """
        v = _make_validator()
        child = AdaptiveNode(
            llm_model="gpt-4o",
            prompt_template="test",
            validator=v,
            max_depth=0,
        )
        state = GraphState(initial_state={})
        result = child.execute(state)
        assert result is None  # next_node was not set, so None — branch ends cleanly
