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
from pathlib import Path
from typing import Any, Dict, Optional


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
    across a process restart — it is NOT a distributed store, has no
    locking, and is not safe for concurrent writers to the same case_id.
    For multi-instance deployments, implement this same four-method
    interface against a real database or object store.
    """

    def __init__(self, directory: str = "lar_checkpoints"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, case_id: str) -> Path:
        return self.directory / f"{case_id}.json"

    def save(self, checkpoint: Checkpoint) -> None:
        with open(self._path(checkpoint.case_id), "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

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
):
    """
    Resolves a ``HumanJuryNode`` checkpoint from OUTSIDE the process that
    created it — e.g. a decision submitted via a web form, API call, or
    Slack action, arbitrarily long after the pause and in a different
    process entirely.

    Loads the durable checkpoint, writes ``decision`` to the ``output_key``
    the paused node was configured with, records an Art. 12/14 authority
    record if a ledger is attached (so the audit trail is identical whether
    a decision was resolved in-process via blocking ``input()`` or
    out-of-process via this function), deletes the resolved checkpoint, and
    resumes execution from ``next_node`` onward. The paused ``HumanJuryNode``
    itself is never re-executed — only the state snapshot taken *before* the
    pause is used, so nothing computed here can be re-derived from state
    that drifted after the checkpoint was written.

    Yields the same per-step log entries as ``GraphExecutor.run_step_by_step``.
    """
    checkpoint = checkpoint_store.load(case_id)
    if checkpoint is None:
        raise ValueError(f"No pending checkpoint for case_id={case_id!r}.")

    output_key = checkpoint.metadata.get("output_key")
    if not output_key:
        raise ValueError(
            f"Checkpoint for case_id={case_id!r} has no recorded output_key; "
            f"it wasn't created by a checkpoint-enabled HumanJuryNode."
        )

    checkpoint.state[output_key] = decision

    if authority_ledger is not None:
        risk_score_key = checkpoint.metadata.get("risk_score_key")
        authority_ledger.record(
            action_description=checkpoint.metadata.get("action_description", checkpoint.reason),
            stakeholder_id=stakeholder_id,
            stakeholder_role=stakeholder_role,
            decision=decision,
            rationale=rationale or "Resolved via external resume (out-of-process).",
            context_snapshot={
                k: checkpoint.state.get(k) for k in checkpoint.metadata.get("context_keys", [])
            },
            risk_score=checkpoint.state.get(risk_score_key) if risk_score_key else None,
        )

    checkpoint_store.delete(case_id)

    yield from executor.resume_step_by_step(checkpoint, node_registry, max_steps=max_steps)
