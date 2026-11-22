import contextvars
import copy
import json
import os
import datetime
import hmac
import hashlib
from typing import List, Dict, Any, Optional
from .compliance.pii_redactor import PIIRedactionEngine
from .utils import compute_state_diff
from ._security import secure_makedirs, secure_write_text, secure_append_text

GENESIS_HASH = "0" * 64

# The logger of the run whose node is executing right now. Lets code that holds the *original*
# logger (e.g. a node calling ``audit_logger.log_plan_switch``) write into the correct run even
# when many runs share one executor.
_CURRENT_RUN_LOGGER: "contextvars.ContextVar" = contextvars.ContextVar("lar_current_run_logger", default=None)


class AuditWriteError(RuntimeError):
    """Raised when an audit record cannot be durably written. The run must not
    continue silently without its evidence (fail closed)."""


class TensorSafeEncoder(json.JSONEncoder):
    """
    Serializes objects safely, specifically converting PyTorch Tensors
    to metadata instead of crashing.
    """
    def default(self, obj):
        if type(obj).__name__ == "Tensor" and type(obj).__module__ == "torch":
            return {
                "__type__": "Tensor",
                "shape": list(obj.shape)
            }
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), cls=TensorSafeEncoder)


class AuditLogger:
    """
    Handles audit trail logging and persistence for Lár graph executions.

    Two artifacts are produced per run:

    1. ``run_<id>.chain.jsonl`` -- written ONE LINE PER STEP, as each step
       completes, with ``fsync``. Every line carries ``prev_hash`` and
       ``entry_hash`` (SHA-256 over the previous hash and the entry), and an
       HMAC of the hash when a secret is set. Editing, deleting or reordering a
       line breaks the chain. A hard crash mid-run still leaves every
       completed step on disk, and a failed write raises ``AuditWriteError``
       instead of letting the run continue unrecorded (fail closed).
    2. ``run_<id>.json`` -- the end-of-run summary, signed with HMAC-SHA256 and
       bound to the chain via ``chain.head``.

    What this does NOT give you: the HMAC key is symmetric and lives in the
    audited process, so someone who controls that process (or has the key) can
    rewrite and re-sign history. For stronger guarantees ship the chain head to
    an external write-once store, or sign with an asymmetric key held in a
    KMS/HSM. See ``verify_chain`` / ``verify_signature`` for checking.
    """
    
    def __init__(self, log_dir: str = "lar_logs", hmac_secret: str = None,
                 pii_redactor: Optional[PIIRedactionEngine] = None,
                 strict: bool = True, chain: bool = True):
        """
        Initialize the AuditLogger.
        
        Args:
            log_dir (str): Directory where audit logs will be saved (created 0700; files 0600).
            hmac_secret (str, optional): Secret key for cryptographically signing the log.
            pii_redactor (PIIRedactionEngine, optional): Engine to redact PII before logging.
            strict (bool): If True (default) a failed end-of-run write raises
                ``AuditWriteError``. If False the failure is printed and swallowed
                (legacy behaviour; not recommended for regulated use).
            chain (bool): Write the per-step hash-chained ``.chain.jsonl`` (default True).
        """
        self.log_dir = log_dir
        self.hmac_secret = hmac_secret
        self.pii_redactor = pii_redactor
        self.strict = strict
        self.chain = chain
        self.history: List[Dict[str, Any]] = []
        self._run_id: Optional[str] = None
        self._chain_path: Optional[str] = None
        self._chain_prev = GENESIS_HASH
        self._chain_len = 0
        
        # Create log directory if it doesn't exist
        secure_makedirs(self.log_dir)

    def fork(self) -> "AuditLogger":
        """
        A per-run copy: same configuration (directory, key, redactor, strictness), but its OWN
        history and hash chain. ``GraphExecutor`` forks one logger per run so that two runs
        sharing an executor (a web service handling concurrent requests) can never write steps
        into each other's audit record. Before this, they did.
        """
        c = copy.copy(self)
        c.history = []
        c._run_id = None
        c._chain_path = None
        c._chain_prev = GENESIS_HASH
        c._chain_len = 0
        return c

    def begin_run(self, run_id: str) -> None:
        """Called by ``GraphExecutor`` at the start of a run: opens a fresh chain."""
        self._run_id = run_id
        self._chain_prev = GENESIS_HASH
        self._chain_len = 0
        self._chain_path = os.path.join(self.log_dir, f"run_{run_id}.chain.jsonl") if self.chain else None

    def _mac(self, text: str) -> Optional[str]:
        if not self.hmac_secret:
            return None
        return hmac.new(self.hmac_secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()

    def _append_to_chain(self, step_data: dict) -> None:
        body = _canonical(step_data)
        entry_hash = hashlib.sha256((self._chain_prev + body).encode("utf-8")).hexdigest()
        record = {
            "seq": self._chain_len,
            "prev_hash": self._chain_prev,
            "entry_hash": entry_hash,
            "mac": self._mac(entry_hash),
            "entry": json.loads(body),
        }
        try:
            secure_append_text(self._chain_path, json.dumps(record, sort_keys=True) + "\n")
        except OSError as e:
            raise AuditWriteError(
                f"Could not append step {self._chain_len} to {self._chain_path}: {e}. "
                f"Refusing to continue without a durable audit record."
            ) from e
        self._chain_prev = entry_hash
        self._chain_len += 1
    
    def log_step(self, step_data: dict) -> None:
        """
        Record a single step execution.
        
        Args:
            step_data (dict): The execution data for this step, including:
                - step (int): Step index
                - timestamp (str): ISO format timestamp
                - node (str): Node class name
                - state_before (dict): State snapshot before execution
                - state_diff (dict): What changed in this step
                - run_metadata (dict): Token usage and model info
                - reasoning_trace (str): Causal relationship metadata (Art 12)
                - outcome (str): "success" or "error"
        """
        if self.pii_redactor:
            step_data = self.pii_redactor.process_dict(step_data)
        self.history.append(step_data)
        if self._chain_path:
            self._append_to_chain(step_data)
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get the complete execution history.
        
        Returns:
            List[Dict[str, Any]]: All logged steps
        """
        return self.history.copy()
    
    def save_to_file(self, run_id: str, user_id: Optional[str] = None, 
                     summary: Optional[Dict[str, Any]] = None) -> None:
        """
        Persist the audit log to a JSON file.
        
        Args:
            run_id (str): Unique identifier for this run (UUIDv4)
            user_id (str, optional): User identifier for multi-tenant systems
            summary (dict, optional): Aggregated summary data (tokens, steps, etc.)
        """
        filename = f"{self.log_dir}/run_{run_id}.json"
        
        log_data = {
            "run_id": run_id,
            "user_id": user_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "steps": self.history,
            "summary": summary or {}
        }
        if self._chain_path and self._run_id == run_id:
            log_data["chain"] = {
                "file": os.path.basename(self._chain_path),
                "entries": self._chain_len,
                "head": self._chain_prev,
            }

        # Sign the log if a secret is provided
        if self.hmac_secret:
            log_data["signature"] = self._generate_signature(log_data)

        try:
            secure_write_text(filename, json.dumps(log_data, indent=2, cls=TensorSafeEncoder))
            print(f"\n[AuditLogger] Log saved to: {filename}")
        except Exception as e:
            if self.strict:
                raise AuditWriteError(f"Failed to save audit log {filename}: {e}") from e
            print(f"\n[AuditLogger] Failed to save log: {e}")
    
    def clear_history(self) -> None:
        """Clear the current execution history (useful for reusing the logger)."""
        self.history = []

    # ── Phase 4: Per-step integrity verification (v2.2.0) ─────────────────────

    def verify_step_integrity(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recomputes the state diff for a given step from its recorded ``state_before``
        and ``state_after`` fields and compares it against the logged ``state_diff``.

        This per-step check is **independent of the file-level HMAC** — it catches
        post-hoc tampering with individual step entries (e.g., an attacker who edits
        one step's diff but leaves the HMAC intact because they also re-signed the file).

        Returns a verification report dict::

            {
              "step": 3,
              "node": "LLMNode",
              "integrity": "OK" | "MISMATCH",
              "discrepancies": ["key_x was added in state_diff but absent in recomputed diff"],
            }
        """
        before = step.get("state_before") or {}
        after = step.get("state_after") or {}
        logged_diff = step.get("state_diff") or {}

        # Recompute the diff from state snapshots
        recomputed = compute_state_diff(before, after)

        discrepancies = []

        for section in ("added", "updated", "removed"):
            logged_keys = set(logged_diff.get(section, {}).keys())
            recomputed_keys = set(recomputed.get(section, {}).keys())
            extra = logged_keys - recomputed_keys
            missing = recomputed_keys - logged_keys
            if extra:
                discrepancies.append(
                    f"[{section}] keys in log but not in recomputed diff: {sorted(extra)}"
                )
            if missing:
                discrepancies.append(
                    f"[{section}] keys in recomputed diff but missing from log: {sorted(missing)}"
                )

        return {
            "step": step.get("step"),
            "node": step.get("node"),
            "integrity": "OK" if not discrepancies else "MISMATCH",
            "discrepancies": discrepancies,
        }

    def verify_all_steps(self) -> List[Dict[str, Any]]:
        """
        Run ``verify_step_integrity`` over every logged step.
        Returns a list of verification reports — one per step.
        """
        return [self.verify_step_integrity(s) for s in self.history]

    def log_plan_switch(self, from_branch: str, to_branch: str, reason: str,
                        step: int, node: str) -> None:
        """
        Record a RouterNode plan-switch event — when the router takes an unexpected
        or fallback branch.  These events are injected into the audit trail as a
        special step type so they appear in the causal chain.

        Args:
            from_branch: The branch that was expected / last taken.
            to_branch: The branch actually taken.
            reason: Explanation from the decision_function (if available).
            step: Current step index.
            node: Node name of the RouterNode.
        """
        entry = {
            "type": "PLAN_SWITCH",
            "step": step,
            "node": node,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "reason": reason,
            "timestamp": datetime.datetime.now().isoformat(),
            "eu_reference": "Art. 12 EU AI Act — Causal Audit Trail (plan-switch event)",
        }
        target = _CURRENT_RUN_LOGGER.get() or self      # the run that is executing, not whichever shares the object
        target.history.append(entry)
        if target._chain_path:
            target._append_to_chain(entry)

    def _generate_signature(self, payload: dict) -> str:
        """
        Generates an HMAC-SHA256 signature for the given JSON payload.
        Keys are sorted to ensure canonical representation.
        """
        return AuditLogger._signature_for(payload, self.hmac_secret)

    @staticmethod
    def _signature_for(payload: dict, secret: str) -> str:
        # Remove existing signature to avoid recursive hashing
        clean_payload = {k: v for k, v in payload.items() if k != "signature"}
        mac = hmac.new(
            key=secret.encode('utf-8'),
            msg=_canonical(clean_payload).encode('utf-8'),
            digestmod=hashlib.sha256,
        )
        return mac.hexdigest()

    # ── Verification (constant-time) ──────────────────────────────────────────

    @staticmethod
    def verify_signature(log: Any, hmac_secret: str) -> bool:
        """
        Verify the end-of-run signature of a log (a path to ``run_*.json`` or the
        loaded dict). Uses ``hmac.compare_digest`` (constant time). Returns False
        for a missing or wrong signature.
        """
        if isinstance(log, (str, os.PathLike)):
            with open(log) as f:
                log = json.load(f)
        saved = log.get("signature")
        if not saved or not hmac_secret:
            return False
        expected = AuditLogger._signature_for(log, hmac_secret)
        return hmac.compare_digest(str(saved), expected)

    @staticmethod
    def verify_chain(chain_path: str, hmac_secret: Optional[str] = None,
                     expected_head: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify a ``run_*.chain.jsonl`` file: sequence numbers, hash links, each
        entry hash, and (when ``hmac_secret`` is given) each HMAC. Pass
        ``expected_head`` (from the signed run file or an external store) to also
        detect truncation. Returns ``{"ok": bool, "entries": int, "head": str,
        "error": str|None}``.
        """
        prev = GENESIS_HASH
        n = 0
        try:
            with open(chain_path) as f:
                for line in f:
                    rec = json.loads(line)
                    if rec["seq"] != n:
                        return {"ok": False, "entries": n, "head": prev, "error": f"sequence break at line {n}"}
                    if rec["prev_hash"] != prev:
                        return {"ok": False, "entries": n, "head": prev, "error": f"hash link broken at seq {n}"}
                    calc = hashlib.sha256((prev + _canonical(rec["entry"])).encode("utf-8")).hexdigest()
                    if not hmac.compare_digest(calc, rec["entry_hash"]):
                        return {"ok": False, "entries": n, "head": prev, "error": f"entry modified at seq {n}"}
                    if hmac_secret:
                        want = hmac.new(hmac_secret.encode("utf-8"), calc.encode("utf-8"), hashlib.sha256).hexdigest()
                        if not rec.get("mac") or not hmac.compare_digest(want, rec["mac"]):
                            return {"ok": False, "entries": n, "head": prev, "error": f"bad MAC at seq {n}"}
                    prev = calc
                    n += 1
        except (OSError, ValueError, KeyError) as e:
            return {"ok": False, "entries": n, "head": prev, "error": f"unreadable chain: {e}"}
        if expected_head is not None and not hmac.compare_digest(prev, expected_head):
            return {"ok": False, "entries": n, "head": prev, "error": "head mismatch (chain truncated or replaced)"}
        return {"ok": True, "entries": n, "head": prev, "error": None}
