import os
import datetime
from typing import Dict, Any, Optional

class CredentialVault:
    """
    Just-in-Time (JIT) credential provisioning for agent tools.
    Operationalises EU AI Act Art. 15(4) and GDPR (NHI Governance / Least Privilege).
    """
    def __init__(self, logger_callback=None):
        self._vault: Dict[str, str] = {}
        self.logger_callback = logger_callback  # Should be a callable that takes a dict

    def register_credential(self, key: str, value: str):
        """Register a credential manually (e.g., for testing or programmatic injection)."""
        self._vault[key] = value

    def get(self, tool_name: str, scope: str, credential_key: str) -> Optional[str]:
        """
        Retrieves a credential. Logs the access.
        Default implementation falls back to environment variables if not registered manually.
        """
        cred = self._vault.get(credential_key) or os.environ.get(credential_key)
        
        if cred:
            self.audit_log(tool_name, scope)
            
        return cred

    def audit_log(self, tool_name: str, scope: str):
        """Log that an NHI (Non-Human Identity) accessed a credential."""
        log_entry = {
            "type": "NHI_CREDENTIAL_ACCESS",
            "tool_name": tool_name,
            "scope": scope,
            "timestamp": datetime.datetime.now().isoformat()
        }
        print(f"  [CredentialVault]: NHI Auth granted to '{tool_name}' for scope '{scope}'")
        if self.logger_callback:
            self.logger_callback(log_entry)
