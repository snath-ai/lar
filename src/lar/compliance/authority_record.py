"""
lar.compliance.authority_record
================================
Structured Authority Record for HumanJuryNode.

EU AI Act Reference: Articles 12–14 (Logging, Transparency, Human Oversight)
Paper Reference: Section 9, Finding (10) — "A fourth tier is absent: infrastructure
governing human-agent interaction at runtime, capable of... maintaining an immutable
oversight record."

The paper states plainly:
  "The essential requirements in Articles 12–14 impose obligations that can only be
   demonstrated through action-level records of human authority exercise, not through
   system-level documentation of oversight design."

This module provides:
  - AuthorityRecord: An immutable, timestamped, cryptographically-signable record of
    a human's exercise of authority over an AI-proposed action.
  - AuthorityLedger: A persistent append-only store of all authority records produced
    during a graph run. Can be flushed to JSON and signed alongside the AuditLogger.
"""

from __future__ import annotations

import json
import datetime
import hmac
import hashlib
import os
from typing import Any, Dict, List, Optional


class AuthorityRecord:
    """
    Immutable record of a single human authority exercise over an AI action.

    Fields match the paper's required evidence chain:
    "action proposal → risk assessment → human determination → execution outcome"
    """

    def __init__(
        self,
        action_description: str,
        stakeholder_id: str,
        stakeholder_role: str,
        decision: str,
        rationale: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
        risk_score: Optional[float] = None,
    ):
        self.timestamp: str = datetime.datetime.utcnow().isoformat() + "Z"
        self.action_description = action_description
        self.stakeholder_id = stakeholder_id
        self.stakeholder_role = stakeholder_role
        self.decision = decision
        self.rationale = rationale
        self.context_snapshot = context_snapshot or {}
        self.risk_score = risk_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_type": "AUTHORITY_EXERCISE",
            "eu_ai_act_article": "Art. 12, 14",
            "timestamp": self.timestamp,
            "action_description": self.action_description,
            "stakeholder_id": self.stakeholder_id,
            "stakeholder_role": self.stakeholder_role,
            "decision": self.decision,
            "rationale": self.rationale,
            "risk_score_at_decision": self.risk_score,
            "context_snapshot_keys": list(self.context_snapshot.keys()),
        }


class AuthorityLedger:
    """
    Append-only ledger of all authority records produced during a graph run.

    Usage::

        ledger = AuthorityLedger(hmac_secret="my-secret")

        # Inside HumanJuryNode, after capturing human decision:
        ledger.record(
            action_description="Execute wire transfer of $50,000",
            stakeholder_id="alice@company.com",
            stakeholder_role="CFO",
            decision="approve",
            rationale="Verified against Q4 budget approval.",
            context_snapshot=state.get_all(),
            risk_score=0.82,
        )

        ledger.save("authority_ledger.json")
    """

    def __init__(self, hmac_secret: Optional[str] = None):
        self.hmac_secret = hmac_secret
        self._records: List[Dict[str, Any]] = []

    def record(
        self,
        action_description: str,
        stakeholder_id: str,
        stakeholder_role: str,
        decision: str,
        rationale: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
        risk_score: Optional[float] = None,
    ) -> AuthorityRecord:
        """Create and append an AuthorityRecord to the ledger."""
        rec = AuthorityRecord(
            action_description=action_description,
            stakeholder_id=stakeholder_id,
            stakeholder_role=stakeholder_role,
            decision=decision,
            rationale=rationale,
            context_snapshot=context_snapshot,
            risk_score=risk_score,
        )
        self._records.append(rec.to_dict())
        print(
            f"  [AuthorityLedger]: Recorded authority exercise by '{stakeholder_id}' "
            f"({stakeholder_role}) — Decision: '{decision}'"
        )
        return rec

    def get_records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def save(self, filepath: str) -> None:
        """Persist the ledger to JSON, optionally signing it with HMAC-SHA256."""
        payload = {
            "ledger_type": "AUTHORITY_EXERCISE_LEDGER",
            "eu_ai_act_reference": "Articles 12–14: Human Oversight Evidence Chain",
            "total_records": len(self._records),
            "records": self._records,
        }
        if self.hmac_secret:
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            sig = hmac.new(
                key=self.hmac_secret.encode("utf-8"),
                msg=canonical.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).hexdigest()
            payload["signature"] = sig

        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  [AuthorityLedger]: Ledger saved to: {filepath}")
