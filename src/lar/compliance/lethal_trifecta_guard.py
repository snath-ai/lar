"""
lar.compliance.lethal_trifecta_guard
======================================
LethalTrifectaGuard — The AEPD "Rule of 2" Runtime Enforcer.

EU/GDPR Reference: Spanish Data Protection Authority (AEPD) Guidance, Feb 2026
Paper Reference: Section 7.2, Lines 1198–1206

The paper states:
  "The AEPD adopts the 'rule of 2' heuristic for agentic risk assessment:
   an agent should not simultaneously combine all three of the following without
   human oversight — processing untrusted input, accessing sensitive data, and
   taking autonomous action affecting individuals."

  This operationalises Simon Willison's 'lethal trifecta' and Meta's security
  framework, and is applied as a GDPR-grounded governance criterion.

This guard is used as a pre-execution check on ToolNode or any custom node.
Configure each 'leg' of the trifecta explicitly. If all three are active
simultaneously without a HumanJuryNode in the approval chain, the guard
raises a LethalTrifectaError and blocks execution.
"""

from __future__ import annotations

import datetime
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import GraphState


class LethalTrifectaError(Exception):
    """
    Raised when a ToolNode attempts to execute with all three legs of the
    lethal trifecta simultaneously active without human oversight.

    This is a GDPR/EU AI Act compliance violation under the AEPD's Rule of 2.
    """
    pass


class LethalTrifectaGuard:
    """
    Runtime guard that enforces the AEPD's 'Rule of 2' heuristic.

    The three legs of the trifecta:
      1. untrusted_input_fn  — Returns True if the current state contains
                               input from an untrusted external source
                               (e.g., user-supplied text, web-scraped content,
                               retrieved RAG documents).
      2. sensitive_data_fn   — Returns True if the current state contains or
                               is about to access sensitive/personal data
                               (e.g., health records, financial data, PII).
      3. autonomous_action_fn — Returns True if the action being executed
                                modifies external state affecting a natural person
                                (e.g., sends email, writes to DB, triggers payment).

    If all three evaluate to True simultaneously, the guard raises
    LethalTrifectaError unless `human_approved` is set to True in state
    (i.e., a HumanJuryNode has already run in this execution path).

    Usage::

        guard = LethalTrifectaGuard(
            untrusted_input_fn=lambda s: s.get("user_query") is not None,
            sensitive_data_fn=lambda s: s.get("customer_health_data") is not None,
            autonomous_action_fn=lambda s: True,  # this ToolNode always modifies state
            human_approval_state_key="jury_decision",
        )

        # In your ToolNode:
        guard.check(state, action_label="send_treatment_recommendation")
    """

    def __init__(
        self,
        untrusted_input_fn: Callable[["GraphState"], bool],
        sensitive_data_fn: Callable[["GraphState"], bool],
        autonomous_action_fn: Callable[["GraphState"], bool],
        human_approval_state_key: str = "jury_decision",
        block_on_violation: bool = True,
    ):
        """
        Args:
            untrusted_input_fn: Callable that returns True if Leg 1 is active.
            sensitive_data_fn: Callable that returns True if Leg 2 is active.
            autonomous_action_fn: Callable that returns True if Leg 3 is active.
            human_approval_state_key: State key to check for prior human approval.
                If the value at this key is not None, the guard is satisfied.
            block_on_violation: If True, raise LethalTrifectaError on violation.
                If False, log a warning and allow execution (for audit-only mode).
        """
        self.untrusted_input_fn = untrusted_input_fn
        self.sensitive_data_fn = sensitive_data_fn
        self.autonomous_action_fn = autonomous_action_fn
        self.human_approval_state_key = human_approval_state_key
        self.block_on_violation = block_on_violation

    def check(self, state: "GraphState", action_label: str = "unknown_action") -> dict:
        """
        Evaluates the trifecta for the current state.

        Returns a dict with evaluation results (useful for audit logging).
        Raises LethalTrifectaError if all three legs are active without prior approval.

        Args:
            state: The current GraphState.
            action_label: Human-readable label for the action being checked.

        Returns:
            dict: Trifecta evaluation result.
        """
        leg1 = bool(self.untrusted_input_fn(state))
        leg2 = bool(self.sensitive_data_fn(state))
        leg3 = bool(self.autonomous_action_fn(state))
        all_active = leg1 and leg2 and leg3

        # Check if a HumanJuryNode has already approved in this path
        human_approved = state.get(self.human_approval_state_key) is not None

        result = {
            "check_type": "LETHAL_TRIFECTA_AEPD_RULE_OF_2",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "action": action_label,
            "leg1_untrusted_input": leg1,
            "leg2_sensitive_data": leg2,
            "leg3_autonomous_action": leg3,
            "all_three_active": all_active,
            "human_prior_approval": human_approved,
            "violation": all_active and not human_approved,
            "eu_reference": "AEPD Guidance Feb 2026, GDPR Art. 5 / EU AI Act Art. 14",
        }

        if all_active and not human_approved:
            msg = (
                f"[LethalTrifectaGuard] COMPLIANCE VIOLATION — AEPD Rule of 2 triggered for "
                f"action '{action_label}'.\n"
                f"  Leg 1 (Untrusted Input): {leg1}\n"
                f"  Leg 2 (Sensitive Data):  {leg2}\n"
                f"  Leg 3 (Autonomous Action): {leg3}\n"
                f"  Human Prior Approval: {human_approved}\n"
                f"  → Insert a HumanJuryNode before this ToolNode to resolve this violation.\n"
                f"  → GDPR Art. 5 / EU AI Act Art. 14 / AEPD Guidance Feb 2026"
            )
            print(f"\n{'!'*60}")
            print(msg)
            print(f"{'!'*60}\n")
            if self.block_on_violation:
                raise LethalTrifectaError(msg)
        elif all_active and human_approved:
            print(
                f"  [LethalTrifectaGuard]: All 3 trifecta legs active for '{action_label}' "
                f"but human approval on record — proceeding."
            )
        else:
            active_legs = sum([leg1, leg2, leg3])
            print(
                f"  [LethalTrifectaGuard]: '{action_label}' — "
                f"{active_legs}/3 trifecta legs active. Safe to proceed."
            )

        # Write the result to state for audit trail
        state.set("_trifecta_check", result)
        return result
