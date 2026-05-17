import json
import os
import datetime
import hmac
import hashlib
from typing import List, Dict, Any, Optional
from .compliance.pii_redactor import PIIRedactionEngine
from .utils import compute_state_diff


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


class AuditLogger:
    """
    Handles audit trail logging and persistence for Lár graph executions.
    
    This class is responsible for recording execution history and saving
    it to JSON files for compliance and debugging purposes.
    """
    
    def __init__(self, log_dir: str = "lar_logs", hmac_secret: str = None, pii_redactor: Optional[PIIRedactionEngine] = None):
        """
        Initialize the AuditLogger.
        
        Args:
            log_dir (str): Directory where audit logs will be saved.
            hmac_secret (str, optional): Secret key for cryptographically signing the log.
            pii_redactor (PIIRedactionEngine, optional): Engine to redact PII before logging.
        """
        self.log_dir = log_dir
        self.hmac_secret = hmac_secret
        self.pii_redactor = pii_redactor
        self.history: List[Dict[str, Any]] = []
        
        # Create log directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
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

        # Sign the log if a secret is provided
        if self.hmac_secret:
            log_data["signature"] = self._generate_signature(log_data)

        try:
            with open(filename, "w") as f:
                json.dump(log_data, f, indent=2, cls=TensorSafeEncoder)
            print(f"\n[AuditLogger] Log saved to: {filename}")
        except Exception as e:
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
        self.history.append(entry)

    def _generate_signature(self, payload: dict) -> str:
        """
        Generates an HMAC-SHA256 signature for the given JSON payload.
        Keys are sorted to ensure canonical representation.
        """
        # Remove existing signature to avoid recursive hashing
        clean_payload = {k: v for k, v in payload.items() if k != "signature"}
        
        # Canonicalize JSON (sorted keys, no extra spaces)
        payload_str = json.dumps(clean_payload, sort_keys=True, separators=(',', ':'), cls=TensorSafeEncoder)
        
        mac = hmac.new(
            key=self.hmac_secret.encode('utf-8'),
            msg=payload_str.encode('utf-8'),
            digestmod=hashlib.sha256,
        )
        return mac.hexdigest()
