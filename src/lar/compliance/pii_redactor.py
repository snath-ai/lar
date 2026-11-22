import hashlib
import hmac
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set

# Built-in patterns for free text. They catch common, well-formed cases; they are
# NOT a complete PII detector (names, addresses and free-form IDs need the
# key-based and known-value mechanisms below, or an NER model).
# PHONE and CARD are opt-in: they also match ISO dates, epoch timestamps and long
# numeric IDs, which would corrupt the evidence an audit log exists to preserve.
_BUILTIN_PATTERNS = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "PHONE": re.compile(r"(?<!\d)\+?\d[\d ()-]{8,}\d(?!\d)"),
}


class PIIRedactionEngine:
    """
    Strips or individually pseudonymises sensitive data before the AuditLogger
    writes and signs a log entry. Operationalises GDPR Art. 5(1)(c) data
    minimisation.

    Three mechanisms (v2.4.1; before this only the first existed):

    1. **Key-based**: any dict key in ``sensitive_keys`` has its value replaced.
    2. **Known-value**: every value found under a sensitive key is ALSO removed
       wherever it appears inside other strings of the same record (for example a
       name that was substituted into a prompt or a free-text summary).
    3. **Pattern-based** (``redact_patterns=True``, default): e-mail, IBAN and
       US-SSN patterns inside any string are replaced. Add ``"PHONE"`` /
       ``"CARD"`` via ``patterns=`` if your data needs them and you accept that
       dates or long numeric IDs may be redacted too.

    Limits you should know: pattern matching is heuristic (it misses names and
    addresses that are not also stored under a sensitive key), and redaction
    protects what is *logged*; it does not change what the model or the state
    contains. Checkpoints hold full state and are not redacted.

    ``mode="HASH"`` replaces values with a **keyed** HMAC-SHA256 (``hash_key``)
    so low-entropy identifiers (SSNs, phone numbers) cannot be recovered by
    brute-forcing plain SHA-256. If no ``hash_key`` is given, a random per-process
    key is used: hashes then cannot be correlated across restarts.
    """

    MIN_KNOWN_VALUE_LEN = 3

    def __init__(self, sensitive_keys: List[str] = None, mode: str = "REDACT",
                 redact_patterns: bool = True, hash_key: Optional[str] = None,
                 patterns: Iterable[str] = ("EMAIL", "IBAN", "SSN")):
        """
        Args:
            sensitive_keys: Dictionary keys whose values are PII.
            mode: "REDACT" (replace with [REDACTED]) or "HASH" (keyed pseudonym).
            redact_patterns: Also scan every string for the selected patterns.
            hash_key: Secret for HASH mode (strongly recommended for HASH).
            patterns: Which built-in patterns to apply: any of EMAIL, IBAN, SSN, PHONE, CARD.
        """
        self.sensitive_keys: Set[str] = set(sensitive_keys or ["email", "ssn", "phone", "name", "address"])
        self.mode = mode.upper()
        if self.mode not in ("REDACT", "HASH"):
            raise ValueError("mode must be 'REDACT' or 'HASH'")
        self.redact_patterns = redact_patterns
        unknown = [n for n in patterns if n not in _BUILTIN_PATTERNS]
        if unknown:
            raise ValueError(f"unknown pattern(s) {unknown}; choose from {sorted(_BUILTIN_PATTERNS)}")
        self._patterns = {n: _BUILTIN_PATTERNS[n] for n in patterns}
        self._hash_key = (hash_key.encode("utf-8") if hash_key else os.urandom(32))

    def _process_value(self, value: Any) -> str:
        if self.mode == "HASH":
            return hmac.new(self._hash_key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()
        return "[REDACTED]"

    # -- internals ----------------------------------------------------------
    def _collect_known(self, data: Any, out: Set[str]) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                if k in self.sensitive_keys and isinstance(v, (str, int, float)):
                    sv = str(v)
                    if len(sv) >= self.MIN_KNOWN_VALUE_LEN and not sv.startswith("[REDACTED]"):
                        out.add(sv)
                else:
                    self._collect_known(v, out)
        elif isinstance(data, list):
            for item in data:
                self._collect_known(item, out)

    def _scrub_text(self, text: str, known: List[str]) -> str:
        for sv in known:                      # longest first (see process_dict)
            if sv in text:
                text = text.replace(sv, self._process_value(sv) if self.mode == "HASH" else "[REDACTED]")
        if self.redact_patterns:
            for label, pattern in self._patterns.items():
                text = pattern.sub("[REDACTED]" if self.mode == "REDACT" else f"[{label}]", text)
        return text

    def _walk(self, data: Any, known: List[str]) -> Any:
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key in self.sensitive_keys:
                    result[key] = self._process_value(value)
                else:
                    result[key] = self._walk(value, known)
            return result
        if isinstance(data, list):
            return [self._walk(item, known) for item in data]
        if isinstance(data, str):
            return self._scrub_text(data, known)
        return data

    def process_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact PII from a dictionary (keys, known values and patterns)."""
        known: Set[str] = set()
        self._collect_known(data, known)
        ordered = sorted(known, key=len, reverse=True)
        return self._walk(data, ordered)
