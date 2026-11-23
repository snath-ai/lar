"""
lar.patterns
============
Three small, dependency-free building blocks for the "model proposes, code checks" design.
They are core (no ``lar.compliance`` imports) and are plain functions/nodes you can use alone.

* :class:`RuleFloor`        deterministic rules set a minimum caution level; the model may only RAISE it.
* :func:`check_proposal` / :class:`ProposeValidateNode`
                            a model-proposed value (an amount, a recipient...) is validated against the
                            value computed from facts; the irreversible action always uses the computed one.
* :class:`ApprovalBinding`  a human approval is bound to the exact facts the reviewer saw, and an
                            idempotency key makes the action safe to repeat after a crash.

What these do NOT do: they do not authenticate reviewers, and they cannot judge facts you did not give them.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .node import BaseNode, FunctionalNode, RouterNode

DEFAULT_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


# --------------------------------------------------------------------------- RuleFloor
class RuleFloor:
    """
    Combine deterministic rule results with a model's opinion so that the model can only raise caution.

    ``decide`` returns ``(level, reasons, needs_human)``:
      * the level is ``max(rule level, model level)``, never lower than the rules;
      * a missing/invalid model answer fails TOWARD oversight (floor ``invalid_floor``, reason ``model_output_invalid``);
      * any ``flags`` (tool errors, suspected injection, low confidence...) force human review;
      * a model that rated LOWER than the rules is logged (``model_rated_lower_than_rules``) and ignored.
    """

    def __init__(self, levels: Sequence[str] = DEFAULT_LEVELS, human_from: Optional[str] = None,
                 invalid_floor: Optional[str] = None, min_confidence: Optional[float] = None):
        if len(set(levels)) != len(levels) or len(levels) < 2:
            raise ValueError("levels must be 2+ distinct names ordered from least to most cautious")
        self.levels = tuple(levels)
        self.human_from = human_from or levels[1]       # this level and above need a human
        self.invalid_floor = invalid_floor or levels[1]
        for lv in (self.human_from, self.invalid_floor):
            if lv not in self.levels:
                raise ValueError(f"{lv!r} is not one of {self.levels}")
        self.min_confidence = min_confidence

    def rank(self, level: str) -> int:
        try:
            return self.levels.index(level)
        except ValueError:
            raise ValueError(f"unknown level {level!r}; expected one of {self.levels}") from None

    def max_level(self, a: str, b: str) -> str:
        return a if self.rank(a) >= self.rank(b) else b

    def decide(self, rule_level: str, rule_reasons: Iterable[str] = (), model_level: Optional[str] = None,
               model_confidence: Optional[float] = None, flags: Iterable[str] = ()) -> Tuple[str, List[str], bool]:
        level = rule_level
        self.rank(level)                                  # validate
        reasons = list(rule_reasons)
        flagged = False
        if model_level is None or model_level not in self.levels:
            reasons.append("model_output_invalid")
            level = self.max_level(level, self.invalid_floor)
            flagged = True
        else:
            if self.rank(model_level) < self.rank(level):
                reasons.append("model_rated_lower_than_rules")     # rules win; the gap is on record
            level = self.max_level(level, model_level)
        if self.min_confidence is not None and model_confidence is not None \
                and (not isinstance(model_confidence, (int, float)) or isinstance(model_confidence, bool)
                     or not math.isfinite(model_confidence) or model_confidence < self.min_confidence):
            reasons.append("low_model_confidence")
            flagged = True
        for f in flags:
            reasons.append(f)
            flagged = True
        needs_human = flagged or self.rank(level) >= self.rank(self.human_from)
        return level, reasons, needs_human


# ------------------------------------------------------------------ propose and validate
def check_proposal(value: Any, expected: float, cap: Optional[float] = None, tolerance: float = 0.01) -> List[str]:
    """
    Validate a MODEL-PROPOSED number. Returns the problems found (empty list = acceptable).
    A missing or garbled value is a problem to escalate; it is never defaulted to 0 or approved.
    Readable-but-wrong values (negative, over the cap, different from the computed amount) are caught too.
    """
    if value is None:
        return ["missing"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ["not_a_number"]
    if not math.isfinite(value):
        return ["not_finite"]
    problems: List[str] = []
    if value < 0:
        problems.append("negative")
    if cap is not None and value > cap:
        problems.append("over_cap")
    if abs(value - expected) > tolerance:
        problems.append("differs_from_computed_amount")
    return problems


class ProposeValidateNode(FunctionalNode):
    """
    Reads the model's proposal from state, compares it with the value computed from facts, and writes:

      * ``<out>_problems``  list of problems (also ``<out>_problems`` = ["no_valid_output"] if the model gave nothing)
      * ``<out>_used``      ALWAYS the computed value: the action never uses the model's number
      * ``<out>_ok``        True when the proposal matched

    Route on ``<out>_ok`` (or on ``<out>_problems``) to send mismatches to human review.
    """

    def __init__(self, proposed_key: str, expected_fn: Callable[[Dict[str, Any]], float], out: str = "amount",
                 cap: Optional[float] = None, tolerance: float = 0.01, next_node: Optional[BaseNode] = None):
        self.proposed_key, self.expected_fn, self.out = proposed_key, expected_fn, out
        self.cap, self.tolerance = cap, tolerance

        def _run(state):
            expected = self.expected_fn(state.get_all())
            problems = check_proposal(state.get(self.proposed_key), expected, self.cap, self.tolerance)
            state.set(f"{self.out}_problems", problems)
            state.set(f"{self.out}_used", expected)
            state.set(f"{self.out}_ok", not problems)

        super().__init__(func=_run, next_node=next_node)


# --------------------------------------------------------------------------- ApprovalBinding
def fingerprint(facts: Any) -> str:
    """Stable SHA-256 over the canonical JSON of the facts."""
    return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class ApprovalBinding:
    """
    Bind an approval to the facts the reviewer was shown, and make the action safe to repeat.

    1. Before review:   ``binding.bind(state, facts)``            stores the fingerprint of what the reviewer will see.
    2. After approval:  ``binding.check_node(live_fn, ok, stale)`` re-reads the facts from the system of record;
                        if they changed while the case waited, the approval is void and the run goes to ``stale``.
    3. Before acting:   ``binding.intent(state, action)``         sets a deterministic idempotency key so a retry
                        after a crash cannot execute the action twice (the receiving system must honour the key).

    ``facts`` should hold ONLY what the reviewer's decision depends on (amount, payee, case id...).
    """

    def __init__(self, fp_key: str = "approval_fp", case_id_key: str = "case_id",
                 idempotency_key: str = "idempotency_key"):
        self.fp_key, self.case_id_key, self.idem_key = fp_key, case_id_key, idempotency_key

    def bind(self, state, facts: Any) -> str:
        fp = fingerprint(facts)
        state.set(self.fp_key, fp)
        return fp

    def is_valid(self, state, live_facts: Any) -> bool:
        bound = state.get(self.fp_key)
        return bool(bound) and bound == fingerprint(live_facts)     # no bound fingerprint = never approved = invalid

    def check_node(self, live_facts_fn: Callable[[Dict[str, Any]], Any], ok_node: Optional[BaseNode],
                   stale_node: Optional[BaseNode]) -> RouterNode:
        def route(state):
            try:
                live = live_facts_fn(state.get_all())
            except Exception:                                      # cannot re-read the record: fail closed
                return "stale"
            return "ok" if self.is_valid(state, live) else "stale"
        return RouterNode(route, {"ok": ok_node, "stale": stale_node})

    def intent(self, state, action: str) -> str:
        key = f"{state.get(self.case_id_key)}:{action}"
        state.set(self.idem_key, key)
        state.set("action_intent", {"action": action, "idempotency_key": key, "bound_fp": state.get(self.fp_key)})
        return key


__all__ = ["RuleFloor", "check_proposal", "ProposeValidateNode", "ApprovalBinding", "fingerprint", "DEFAULT_LEVELS"]
