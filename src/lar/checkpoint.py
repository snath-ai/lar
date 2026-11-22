# src/lar/checkpoint.py
"""
Durable pause/resume for Lár graphs.

Lár is a state machine: ``GraphState`` is already a plain, JSON-serializable
dict, and ``GraphExecutor.run_step_by_step`` is a generator over discrete
node steps. Previously, "resuming" a graph meant a developer hand-serializing
that dict and hardcoding which node to resume at (see the correction in
``examples/patterns/10_resumable_cost_demo.py``). That's fine for a crash-
and-retry demo, but it does not survive the process that was blocked on
``HumanJuryNode``'s ``input()`` call actually dying — nothing was written to
disk until *after* a decision arrived, and the resume node was never
recorded anywhere the framework could find on its own.

This module makes the pause itself durable and the resume position
automatic:

    - ``Checkpoint``: a serializable snapshot of a paused run — the state
      dict, which node to resume at (by ``_node_id``, not a Python
      reference), and enough metadata to resolve a pending human decision
      without re-deriving it.
    - ``FileCheckpointStore``: the default store (one JSON file per
      ``case_id``). Swap in a database-backed store in production by
      implementing the same ``save``/``load``/``delete``/``exists`` methods
      — nothing else in this module or in ``HumanJuryNode`` depends on the
      file-based implementation.
    - ``resume_human_decision``: resolves a checkpoint from *outside* the
      original process — a decision submitted via a web form, API call, or
      Slack action, possibly hours or days later — and continues execution
      from ``next_node`` onward. The paused node itself is never re-run.

Node identity for resume is a plain string: the node's ``_node_id``
attribute, the same convention ``GraphExecutor`` already uses for fatigue-
log labelling (see ``executor.py``). A checkpoint's ``resume_node_id`` is
resolved against a ``node_registry`` dict the caller supplies — the same
graph object definitions used for the original run, exactly as LangGraph's
own resume path needs the same compiled graph, not a magically
reconstructed one. This module does not attempt to serialize graph
*topology*, only graph *position* — that would require rebuilding Python
node objects from data, which is a much larger and different problem.
"""
import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ._security import safe_id, secure_makedirs, secure_write_text


class Checkpoint:
    """A durable snapshot of a paused graph run."""

    def __init__(
        self,
        case_id: str,
        resume_node_id: str,
        state: dict,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ):
        if not case_id:
            raise ValueError("case_id must be a non-empty string")
        if not resume_node_id:
            raise ValueError("resume_node_id must be a non-empty string")
        self.case_id = case_id
        self.resume_node_id = resume_node_id
        self.state = state
        self.reason = reason
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "resume_node_id": self.resume_node_id,
            "state": self.state,
            "reason": self.reason,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(
            case_id=d["case_id"],
            resume_node_id=d["resume_node_id"],
            state=d["state"],
            reason=d.get("reason", ""),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at"),
        )

    def __repr__(self):
        return (
            f"Checkpoint(case_id={self.case_id!r}, resume_node_id={self.resume_node_id!r}, "
            f"reason={self.reason!r}, created_at={self.created_at!r})"
        )


class FileCheckpointStore:
    """
    Default checkpoint store: one JSON file per ``case_id`` on local disk.

    This is deliberately the simplest thing that is still genuinely durable
    across a process restart. It is NOT a distributed store: the atomic
    ``claim`` below stops two resumers on the SAME host from both resolving
    one case, but multi-instance deployments must implement this same
    interface (``save``/``load``/``delete``/``exists`` plus ``claim``/
    ``commit``/``release``) against a real database with compare-and-set.

    Security properties (v2.4.1):
      - ``case_id`` is validated (``lar._security.safe_id``): it can never
        contain a path separator or ``..``, so it cannot address a file
        outside ``directory``.
      - Files are created ``0600`` and the directory ``0700``.
      - Checkpoints hold the FULL run state in clear text. Treat the
        directory like a database of the data your graph handles.
    """

    def __init__(self, directory: str = "lar_checkpoints"):
        self.directory = Path(directory)
        secure_makedirs(self.directory)

    def _path(self, case_id: str) -> Path:
        return self.directory / f"{safe_id(case_id, 'case_id')}.json"

    def _claimed_path(self, case_id: str) -> Path:
        return self.directory / f"{safe_id(case_id, 'case_id')}.json.claimed"

    def save(self, checkpoint: Checkpoint) -> None:
        secure_write_text(self._path(checkpoint.case_id), json.dumps(checkpoint.to_dict(), indent=2))

    def load(self, case_id: str) -> Optional[Checkpoint]:
        path = self._path(case_id)
        if not path.exists():
            return None
        with open(path) as f:
            return Checkpoint.from_dict(json.load(f))

    def delete(self, case_id: str) -> None:
        path = self._path(case_id)
        if path.exists():
            path.unlink()

    def exists(self, case_id: str) -> bool:
        return self._path(case_id).exists()

    # -- exactly-once resolution -------------------------------------------
    def claim(self, case_id: str) -> Optional[Checkpoint]:
        """
        Atomically take ownership of a pending checkpoint. Returns ``None`` if
        there is nothing pending or another resumer already claimed it.
        ``os.replace`` is atomic on POSIX, so only one caller wins.
        """
        src, dst = self._path(case_id), self._claimed_path(case_id)
        try:
            os.replace(src, dst)
        except FileNotFoundError:
            return None
        with open(dst) as f:
            return Checkpoint.from_dict(json.load(f))

    def commit(self, case_id: str) -> None:
        """The claimed case was resolved successfully: remove it for good."""
        dst = self._claimed_path(case_id)
        if dst.exists():
            dst.unlink()

    def release(self, case_id: str) -> None:
        """Resolution did not complete: put the checkpoint back so nothing is lost."""
        dst = self._claimed_path(case_id)
        if dst.exists():
            os.replace(dst, self._path(case_id))


def resume_human_decision(
    checkpoint_store,
    case_id: str,
    decision: str,
    executor,
    node_registry: Dict[str, Any],
    authority_ledger=None,
    stakeholder_id: str = "UNKNOWN",
    stakeholder_role: str = "REVIEWER",
    rationale: str = "",
    max_steps: int = 100,
    authorize: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
):
    """
    Resolves a ``HumanJuryNode`` checkpoint from OUTSIDE the process that
    created it -- e.g. a decision submitted via a web form, API call, or
    Slack action, arbitrarily long after the pause and in a different
    process entirely.

    Safety properties (v2.4.1):
      - The decision is validated against the ``choices`` the paused node was
        configured with (recorded in the checkpoint). Anything else raises
        ``ValueError`` and the checkpoint stays pending.
      - ``authorize(stakeholder_id, checkpoint_metadata) -> bool`` lets the
        caller bind the decision to an authenticated, authorised identity.
        A falsy result raises ``PermissionError``. When an ``authority_ledger``
        is attached, an anonymous ``stakeholder_id`` ("UNKNOWN"/empty) is refused.
        Lár does not authenticate anyone itself: the caller must pass the
        identity its own auth layer verified.
      - The checkpoint is *claimed* atomically (exactly one resolver wins) and
        only deleted after the resumed run finishes. If the run is interrupted
        before finishing, the checkpoint is released back to pending, so the
        case is never lost. Custom stores without ``claim`` fall back to the
        old load-then-delete behaviour.
      - If the paused node declared ``decision_routes``, the run resumes at the
        node routed for this decision (or stops, for a route of ``None``) --
        a "reject" can no longer fall through to the approval path.

    Yields the same per-step log entries as ``GraphExecutor.run_step_by_step``.
    """
    pending = checkpoint_store.load(case_id)
    if pending is None:
        raise ValueError(f"No pending checkpoint for case_id={case_id!r}.")

    meta = pending.metadata
    output_key = meta.get("output_key")
    if not output_key:
        raise ValueError(
            f"Checkpoint for case_id={case_id!r} has no recorded output_key; "
            f"it wasn't created by a checkpoint-enabled HumanJuryNode."
        )

    choices = meta.get("choices")
    if not choices:
        raise ValueError(
            f"Checkpoint for case_id={case_id!r} records no valid choices, so the "
            f"decision cannot be validated. Re-run the paused node to recreate it."
        )
    decision = str(decision).strip().lower()
    if decision not in choices:
        raise ValueError(
            f"Invalid decision {decision!r} for case_id={case_id!r}; allowed: {choices}."
        )

    if authority_ledger is not None and (not stakeholder_id or stakeholder_id == "UNKNOWN"):
        raise PermissionError(
            "An identified stakeholder_id is required to resolve a case when an "
            "authority_ledger is attached (got an anonymous reviewer)."
        )
    if authorize is not None and not authorize(stakeholder_id, dict(meta)):
        raise PermissionError(
            f"stakeholder {stakeholder_id!r} is not authorised to resolve case_id={case_id!r}."
        )

    claim = getattr(checkpoint_store, "claim", None)
    if claim is not None:
        checkpoint = claim(case_id)
        if checkpoint is None:
            raise ValueError(
                f"case_id={case_id!r} is no longer pending (already resolved or being resolved)."
            )
    else:
        checkpoint = pending

    completed = False
    try:
        checkpoint.state[output_key] = decision

        if authority_ledger is not None:
            risk_score_key = meta.get("risk_score_key")
            authority_ledger.record(
                action_description=meta.get("action_description", checkpoint.reason),
                stakeholder_id=stakeholder_id,
                stakeholder_role=stakeholder_role,
                decision=decision,
                rationale=rationale or "Resolved via external resume (out-of-process).",
                context_snapshot={k: checkpoint.state.get(k) for k in meta.get("context_keys", [])},
                risk_score=checkpoint.state.get(risk_score_key) if risk_score_key else None,
            )

        routes = meta.get("decision_routes") or {}
        if decision in routes:
            resume_id = routes[decision]
            if resume_id is None:
                completed = True      # routed to "stop": nothing further runs
                return
            checkpoint.resume_node_id = resume_id

        yield from executor.resume_step_by_step(checkpoint, node_registry, max_steps=max_steps)
        completed = True
    finally:
        if claim is not None:
            if completed:
                checkpoint_store.commit(case_id)
            else:
                checkpoint_store.release(case_id)
        elif completed:
            checkpoint_store.delete(case_id)
