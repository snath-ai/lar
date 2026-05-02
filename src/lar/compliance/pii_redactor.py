import hashlib
from typing import Any, Dict, List, Set, Union

class PIIRedactionEngine:
    """
    Strips or individually hashes sensitive state keys before the AuditLogger generates 
    the HMAC signature. Operationalises GDPR Art. 5(1)(c) Data Minimisation and 
    Art. 17 Right to Erasure in cryptographic logs.
    """
    def __init__(self, sensitive_keys: List[str] = None, mode: str = "REDACT"):
        """
        Args:
            sensitive_keys: List of dictionary keys that contain PII and should be redacted.
            mode: "REDACT" (replace with [REDACTED]) or "HASH" (replace with SHA-256 hash).
        """
        self.sensitive_keys: Set[str] = set(sensitive_keys or ["email", "ssn", "phone", "name", "address"])
        self.mode = mode.upper()

    def _process_value(self, value: Any) -> str:
        if self.mode == "HASH":
            return hashlib.sha256(str(value).encode('utf-8')).hexdigest()
        return "[REDACTED]"

    def process_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact PII from a dictionary."""
        result = {}
        for key, value in data.items():
            if key in self.sensitive_keys:
                result[key] = self._process_value(value)
            elif isinstance(value, dict):
                result[key] = self.process_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.process_dict(item) if isinstance(item, dict) else item 
                    for item in value
                ]
            else:
                result[key] = value
        return result
