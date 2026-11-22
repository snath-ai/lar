"""
lar.compliance.session_memory_node
===================================
SessionMemoryNode — GDPR Art. 17 erasable, compartmentalised per-subject memory.

Provides:
  - Per-subject memory compartments (no cross-subject bleed)
  - Configurable retention periods with automatic TTL expiry
  - Erasure-on-request implementing GDPR Art. 17 right to be forgotten
  - Immutable access audit log per subject

Modes:
  ``write`` — capture current state keys into subject's compartment
  ``read``  — load subject's latest memory back into graph state
  ``erase`` — delete all memory for a subject (right to erasure)
  ``audit`` — write the access audit trail to ``state['memory_audit']``
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from lar.node import BaseNode
from lar.state import GraphState
from lar._security import secure_makedirs, secure_write_text


class SessionMemoryNode(BaseNode):
    """
    GDPR Art. 17 compliant session memory with per-subject compartmentalisation.

    Each subject's memory is stored in a dedicated JSON file under ``memory_dir``.
    On every write, expired entries (older than ``retention_days``) are pruned
    automatically before writing the new payload.

    EU References:
      - GDPR Art. 5(1)(e) — Storage limitation
      - GDPR Art. 17    — Right to erasure
      - GDPR Art. 15    — Right of access (``audit`` mode)

    Usage::

        from lar.compliance import SessionMemoryNode

        # Store after each interaction
        mem_write = SessionMemoryNode(
            mode="write",
            subject_key="applicant_id",
            memory_keys=["recommendation", "risk_score"],
            next_node=output_node,
        )

        # Erase on explicit request
        mem_erase = SessionMemoryNode(
            mode="erase",
            subject_key="applicant_id",
            next_node=confirm_node,
        )
    """

    EU_REFERENCE = (
        "GDPR Art. 17 (Right to Erasure), "
        "Art. 5(1)(e) (Storage Limitation), "
        "Art. 15 (Right of Access)"
    )

    _VALID_MODES = ("write", "read", "erase", "audit")

    def __init__(
        self,
        mode: str,
        subject_key: str,
        memory_keys: Optional[List[str]] = None,
        retention_days: int = 90,
        memory_dir: str = "lar_logs/session_memory",
        next_node: Optional[BaseNode] = None,
        sweep_interval_seconds: int = 3600,
    ):
        """
        Args:
            mode: One of ``write | read | erase | audit``.
            subject_key: State key holding the data-subject identifier (e.g. ``user_id``).
            memory_keys: Keys to capture into memory (required for ``write`` mode).
            retention_days: Entries older than this are automatically expired.
            memory_dir: Directory for per-subject JSON files.
            next_node: Next node after execution.
            sweep_interval_seconds: How often this node sweeps the WHOLE directory and
                removes expired entries for every subject (default hourly). Without the
                sweep, retention would only be enforced when the same subject is touched
                again, so a stale file could outlive its retention period indefinitely.
        """
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"SessionMemoryNode mode must be one of {self._VALID_MODES}, got '{mode}'"
            )
        self.mode = mode
        self.subject_key = subject_key
        self.memory_keys: List[str] = memory_keys or []
        self.retention_days = retention_days
        self.memory_dir = memory_dir
        self.next_node = next_node
        self.sweep_interval_seconds = sweep_interval_seconds
        self._last_sweep = 0.0
        secure_makedirs(self.memory_dir)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _subject_path(self, subject_id: str) -> str:
        # Readable prefix + hash of the ORIGINAL id. The prefix alone is lossy
        # ("alice@bank.com" and "alice_bank.com" would collide and one subject
        # would read the other's memory); the hash makes every id map to its own file.
        sid = str(subject_id)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:48] or "subject"
        digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.memory_dir, f"{safe}-{digest}.json")

    def _load(self, subject_id: str) -> Dict:
        path = self._subject_path(subject_id)
        if not os.path.exists(path):
            return {"subject_id": subject_id, "entries": [], "access_log": []}
        with open(path) as f:
            return json.load(f)

    def _save(self, subject_id: str, data: Dict) -> None:
        secure_write_text(self._subject_path(subject_id), json.dumps(data, indent=2, default=str))

    def sweep_expired(self) -> int:
        """Remove expired entries for every subject; delete files left empty. Returns files touched."""
        touched = 0
        for name in os.listdir(self.memory_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.memory_dir, name)
            try:
                with open(path) as f:
                    data = json.load(f)
                before = len(data.get("entries", []))
                data = self._expire(data)
                if not data["entries"]:
                    os.remove(path)
                    touched += 1
                elif len(data["entries"]) != before:
                    secure_write_text(path, json.dumps(data, indent=2, default=str))
                    touched += 1
            except (OSError, ValueError, KeyError):
                continue
        return touched

    def _expire(self, data: Dict) -> Dict:
        """Prune entries older than retention_days."""
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=self.retention_days)
        data["entries"] = [
            e for e in data.get("entries", [])
            if datetime.datetime.fromisoformat(e["stored_at"]) >= cutoff
        ]
        return data

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, state: GraphState) -> Optional[BaseNode]:
        if time.time() - self._last_sweep >= self.sweep_interval_seconds:
            self.sweep_expired()
            self._last_sweep = time.time()
        subject_id = state.get(self.subject_key) or "anonymous"
        now = datetime.datetime.utcnow().isoformat()
        data = self._load(subject_id)
        data = self._expire(data)

        if self.mode == "write":
            payload = {k: state.get(k) for k in self.memory_keys if state.get(k) is not None}
            data["entries"].append({"stored_at": now, "payload": payload})
            data["access_log"].append(
                {"event": "write", "timestamp": now, "keys": self.memory_keys}
            )
            self._save(subject_id, data)
            print(
                f"  [SessionMemoryNode] Wrote {len(payload)} key(s) "
                f"for subject '{subject_id}' (expires after {self.retention_days} days)."
            )

        elif self.mode == "read":
            if data["entries"]:
                latest = data["entries"][-1]["payload"]
                for k, v in latest.items():
                    state.set(k, v)
                print(
                    f"  [SessionMemoryNode] Loaded {len(latest)} key(s) "
                    f"for subject '{subject_id}'."
                )
            else:
                print(f"  [SessionMemoryNode] No memory found for subject '{subject_id}'.")
            data["access_log"].append({"event": "read", "timestamp": now})
            self._save(subject_id, data)

        elif self.mode == "erase":
            path = self._subject_path(subject_id)
            if os.path.exists(path):
                os.remove(path)
            state.set("memory_erased", True)
            state.set("memory_erased_subject", subject_id)
            state.set("memory_erasure_scope", "session_memory_only")
            print(
                f"  [SessionMemoryNode] ERASED session memory for subject '{subject_id}'. "
                f"NOTE: this does not remove copies held elsewhere (audit logs, checkpoints, "
                f"authority ledger, model-provider logs). Art. 17 needs a process covering those too."
            )

        elif self.mode == "audit":
            state.set("memory_audit", data.get("access_log", []))
            print(
                f"  [SessionMemoryNode] Access audit trail for "
                f"'{subject_id}' written to state['memory_audit']."
            )

        return self.next_node
