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
import uuid
from typing import Any, Dict, List, Optional

from filelock import FileLock

from lar._security import secure_makedirs, secure_write_text

GENESIS_HASH = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


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
        self.record_id: str = str(uuid.uuid4())
        self.timestamp: str = datetime.datetime.utcnow().isoformat() + "Z"
        self.action_description = action_description
        self.stakeholder_id = stakeholder_id
        self.stakeholder_role = stakeholder_role
        self.decision = decision
        self.rationale = rationale
        self.context_snapshot = context_snapshot or {}
        self.risk_score = risk_score
        # Attest WHAT the reviewer saw without storing the (possibly personal) values:
        # a SHA-256 over the canonical context. A dispute can be settled by hashing the
        # case data from the original run and comparing.
        self.context_sha256 = hashlib.sha256(
            _canonical(self.context_snapshot).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_type": "AUTHORITY_EXERCISE",
            "eu_ai_act_article": "Art. 12, 14",
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "action_description": self.action_description,
            "stakeholder_id": self.stakeholder_id,
            "stakeholder_role": self.stakeholder_role,
            "decision": self.decision,
            "rationale": self.rationale,
            "risk_score_at_decision": self.risk_score,
            "context_snapshot_keys": list(self.context_snapshot.keys()),
            "context_sha256": self.context_sha256,
        }


class AuthorityLedger:
    """
    Append-only ledger of human authority records.

    v2.4.1 changes:
      - ``save()`` now MERGES with an existing ledger file instead of overwriting
        it, so a later run to the same path can no longer erase earlier records.
        Records are de-duplicated by ``record_id``.
      - Records are hash-chained (``prev_hash`` / ``record_hash``): removing,
        editing or reordering a record breaks ``verify()``.
      - Each record carries ``context_sha256``, an attestation of the values the
        reviewer was shown (the values themselves are not stored).
      - The file is written atomically with mode 0600.

    The HMAC is symmetric (see ``AuditLogger``): it detects tampering by anyone
    without the key, not by someone who holds it.

    Usage::

        ledger = AuthorityLedger(hmac_secret="my-secret", path="audit/authority_ledger.json")
        ledger.record(
            action_description="Execute wire transfer of $50,000",
            stakeholder_id="alice@company.com",
            stakeholder_role="CFO",
            decision="approve",
            rationale="Verified against Q4 budget approval.",
            context_snapshot=state.get_all(),
            risk_score=0.82,
        )
        ledger.save()
    """

    def __init__(self, hmac_secret: Optional[str] = None, path: Optional[str] = None):
        self.hmac_secret = hmac_secret
        self.path = path
        self._records: List[Dict[str, Any]] = []
        self._persisted_ids: set = set()
        self._last_hash = GENESIS_HASH
        if path and os.path.exists(path):
            self._load_existing(path)

    # -- chain helpers ------------------------------------------------------
    @staticmethod
    def _hash_record(prev_hash: str, record: Dict[str, Any]) -> str:
        body = {k: v for k, v in record.items() if k not in ("prev_hash", "record_hash")}
        return hashlib.sha256((prev_hash + _canonical(body)).encode("utf-8")).hexdigest()

    def _chain(self, rec: Dict[str, Any]) -> None:
        rec["prev_hash"] = self._last_hash
        rec["record_hash"] = self._hash_record(self._last_hash, rec)
        self._last_hash = rec["record_hash"]

    def _load_existing(self, path: str) -> None:
        with open(path) as f:
            data = json.load(f)
        self._records = list(data.get("records", []))
        # Ledgers written before v2.4.1 have no record_id / hash chain. Migrate them in
        # memory: keep every field, add an id, flag the record, and chain from the start.
        # (The migrated chain starts at the first legacy record; it cannot prove that
        # nothing was removed from the legacy file before migration.)
        self._records = self._migrate_legacy(self._records)
        self._persisted_ids = {r.get("record_id") for r in self._records}
        self._last_hash = self._records[-1]["record_hash"] if self._records else GENESIS_HASH

    def _migrate_legacy(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Give hash-less (pre-v2.4.1) records an id and a chain. No-op for modern records."""
        if not any("record_hash" not in r for r in records):
            return records
        self._last_hash = GENESIS_HASH
        for i, r in enumerate(records):
            # Deterministic id (position + content hash): migrating the same legacy file twice,
            # once at load and again at save, must give the same ids so the merge can de-duplicate.
            r.setdefault("record_id", "legacy-%d-%s" % (
                i, hashlib.sha256(_canonical({k: v for k, v in r.items()
                                              if k not in ("prev_hash", "record_hash")}).encode()).hexdigest()[:20]))
            r["migrated_from_legacy"] = True
            r.pop("prev_hash", None)
            r.pop("record_hash", None)
            self._chain(r)
        return records

    # -- public API ---------------------------------------------------------
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
        d = rec.to_dict()
        self._chain(d)
        self._records.append(d)
        print(
            f"  [AuthorityLedger]: Recorded authority exercise by '{stakeholder_id}' "
            f"({stakeholder_role}) — Decision: '{decision}'"
        )
        if self.path:
            # WRITE-THROUGH: with a path configured, the decision is durable immediately. Waiting
            # for a later save() meant a crash after the approval (and after the action it
            # authorised) left an action with no record of who approved it.
            self.save()
        return rec

    def get_records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def _payload(self) -> Dict[str, Any]:
        return {
            "ledger_type": "AUTHORITY_EXERCISE_LEDGER",
            "eu_ai_act_reference": "Articles 12–14: Human Oversight Evidence Chain",
            "total_records": len(self._records),
            "chain_head": self._last_hash,
            "records": self._records,
        }

    def save(self, filepath: Optional[str] = None) -> None:
        """
        Persist the ledger (JSON, optionally HMAC-signed).

        Under a file lock, this MERGES with whatever is already on disk: records written by other
        ledger instances or processes since this one loaded are kept, and this instance's new
        records are chained after them. Two writers can therefore never silently erase each
        other's records. (The lock covers processes on one host; several hosts need a database.)
        """
        target = filepath or self.path
        if not target:
            raise ValueError("save() needs a filepath (or construct the ledger with path=...)")
        directory = os.path.dirname(target)
        if directory:
            secure_makedirs(directory)

        with FileLock(target + ".lock", timeout=30):
            base: List[Dict[str, Any]] = []
            if os.path.exists(target):
                with open(target) as f:
                    base = self._migrate_legacy(json.load(f).get("records", []))
            base_ids = {r["record_id"] for r in base}
            mine_new = [r for r in self._records if r["record_id"] not in base_ids]
            self._records = list(base)
            self._last_hash = base[-1]["record_hash"] if base else GENESIS_HASH
            for r in mine_new:
                self._chain(r)
                self._records.append(r)

            payload = self._payload()
            if self.hmac_secret:
                payload["signature"] = hmac.new(
                    key=self.hmac_secret.encode("utf-8"),
                    msg=_canonical(payload).encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).hexdigest()
            secure_write_text(target, json.dumps(payload, indent=2, default=str))
        self._persisted_ids = {r["record_id"] for r in self._records}
        print(f"  [AuthorityLedger]: Ledger saved to: {target}")

    @staticmethod
    def verify(filepath: str, hmac_secret: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify a saved ledger: every ``record_hash`` and ``prev_hash`` link,
        ``total_records`` / ``chain_head``, and (with ``hmac_secret``) the file
        signature, using a constant-time comparison.
        """
        try:
            with open(filepath) as f:
                data = json.load(f)
            prev = GENESIS_HASH
            for i, r in enumerate(data.get("records", [])):
                if r.get("prev_hash") != prev:
                    return {"ok": False, "error": f"chain link broken at record {i}"}
                calc = AuthorityLedger._hash_record(prev, r)
                if not hmac.compare_digest(calc, r.get("record_hash", "")):
                    return {"ok": False, "error": f"record {i} modified"}
                prev = calc
            if data.get("total_records") != len(data.get("records", [])):
                return {"ok": False, "error": "total_records mismatch (records removed?)"}
            if data.get("chain_head") != prev:
                return {"ok": False, "error": "chain_head mismatch"}
            if hmac_secret:
                saved = data.get("signature")
                body = {k: v for k, v in data.items() if k != "signature"}
                want = hmac.new(hmac_secret.encode("utf-8"), _canonical(body).encode("utf-8"), hashlib.sha256).hexdigest()
                if not saved or not hmac.compare_digest(str(saved), want):
                    return {"ok": False, "error": "bad or missing signature"}
            return {"ok": True, "error": None, "records": len(data.get("records", []))}
        except (OSError, ValueError, KeyError) as e:
            return {"ok": False, "error": f"unreadable ledger: {e}"}
