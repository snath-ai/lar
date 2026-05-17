import os
import datetime
from typing import Dict, Any, List, Optional


# Trust levels — higher number = higher trust required to grant credential
_TRUST_LEVELS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class CredentialVault:
    """
    Just-in-Time (JIT) credential provisioning for agent tools.
    Operationalises EU AI Act Art. 15(4) and GDPR (NHI Governance / Least Privilege).

    v2.2.0 additions:
      - ``_audit_trail``: per-action NHI authorisation log (iterable for compliance export)
      - ``get_with_trust()``: dynamic trust-based privilege restriction — credential is only
        granted when the calling context's trust_level meets the credential's minimum
        threshold.  Enables deployers to restrict sensitive credentials to high-trust
        execution paths (e.g., only grant payment API key after HumanJuryNode approves).

    EU Reference: Art. 15(4) EU AI Act — Cybersecurity; NHI Governance / Least Privilege
    """

    EU_REFERENCE = "Art. 15(4) EU AI Act — Cybersecurity; NHI Governance / Least Privilege"

    def __init__(self, logger_callback=None):
        self._vault: Dict[str, str] = {}
        self._min_trust: Dict[str, str] = {}   # credential_key -> min trust level
        self.logger_callback = logger_callback   # callable(dict)
        self._audit_trail: List[Dict[str, Any]] = []

    # ── Registration ──────────────────────────────────────────────────────────

    def register_credential(self, key: str, value: str,
                            min_trust_level: str = "LOW") -> None:
        """
        Register a credential.

        Args:
            key: Credential identifier (e.g. ``"OPENAI_API_KEY"``).
            value: Credential value.
            min_trust_level: Minimum trust level required to retrieve this credential
                via ``get_with_trust()``.  One of ``LOW | MEDIUM | HIGH | CRITICAL``.
        """
        if min_trust_level not in _TRUST_LEVELS:
            raise ValueError(
                f"min_trust_level must be one of {list(_TRUST_LEVELS)}, "
                f"got '{min_trust_level}'"
            )
        self._vault[key] = value
        self._min_trust[key] = min_trust_level

    # ── Standard retrieval ────────────────────────────────────────────────────

    def get(self, tool_name: str, scope: str, credential_key: str) -> Optional[str]:
        """
        Retrieve a credential and log the NHI access.
        Falls back to environment variables if not registered manually.
        """
        cred = self._vault.get(credential_key) or os.environ.get(credential_key)
        if cred:
            self._log_access(tool_name, scope, credential_key, "GRANTED", trust_level=None)
        return cred

    # ── Trust-based retrieval (v2.2.0) ────────────────────────────────────────

    def get_with_trust(
        self,
        tool_name: str,
        scope: str,
        credential_key: str,
        trust_level: str,
    ) -> Optional[str]:
        """
        Retrieve a credential only when the calling context's ``trust_level``
        meets or exceeds the credential's registered minimum.

        Use this to gate sensitive credentials (e.g., payment API keys) behind
        a HumanJuryNode decision — set ``min_trust_level="HIGH"`` on the
        credential and pass ``trust_level="HIGH"`` only after jury approval.

        Args:
            trust_level: Context trust level. One of ``LOW | MEDIUM | HIGH | CRITICAL``.

        Returns:
            The credential string, or ``None`` if not found.

        Raises:
            PermissionError: If ``trust_level`` is below the credential minimum.
        """
        if trust_level not in _TRUST_LEVELS:
            raise ValueError(
                f"trust_level must be one of {list(_TRUST_LEVELS)}, got '{trust_level}'"
            )

        cred = self._vault.get(credential_key) or os.environ.get(credential_key)
        if not cred:
            self._log_access(tool_name, scope, credential_key, "NOT_FOUND", trust_level)
            return None

        min_level = self._min_trust.get(credential_key, "LOW")
        if _TRUST_LEVELS[trust_level] < _TRUST_LEVELS[min_level]:
            self._log_access(tool_name, scope, credential_key, "DENIED_TRUST", trust_level)
            raise PermissionError(
                f"[CredentialVault] Credential '{credential_key}' requires trust_level "
                f"'{min_level}' but calling context has '{trust_level}'. "
                f"Art. 15(4) privilege restriction active."
            )

        self._log_access(tool_name, scope, credential_key, "GRANTED", trust_level)
        return cred

    # ── Audit ─────────────────────────────────────────────────────────────────

    def _log_access(
        self,
        tool_name: str,
        scope: str,
        credential_key: str,
        outcome: str,
        trust_level: Optional[str],
    ) -> None:
        entry = {
            "type": "NHI_CREDENTIAL_ACCESS",
            "tool_name": tool_name,
            "scope": scope,
            "credential_key": credential_key,
            "outcome": outcome,
            "trust_level": trust_level,
            "timestamp": datetime.datetime.now().isoformat(),
            "eu_reference": self.EU_REFERENCE,
        }
        self._audit_trail.append(entry)
        status = "granted" if outcome == "GRANTED" else outcome.lower().replace("_", " ")
        print(
            f"  [CredentialVault]: NHI Auth {status} — "
            f"tool='{tool_name}' scope='{scope}' key='{credential_key}'"
        )
        if self.logger_callback:
            self.logger_callback(entry)

    def audit_log(self, tool_name: str, scope: str) -> None:
        """Legacy compatibility — retained for any code calling this directly."""
        self._log_access(tool_name, scope, "unknown", "GRANTED", None)

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Return a copy of the full NHI authorisation log."""
        return list(self._audit_trail)
