"""
lar.compliance.supplier_agreement_registry
==========================================
SupplierAgreementRegistry — Art. 25(4) Written Agreement Enforcement.

EU AI Act Art. 25(4): Where a deployer uses an AI system provided by a provider,
the parties must define by written agreement which obligations fall on whom.
Before a ToolNode executes a third-party tool, the registry verifies that a
current, unexpired written agreement exists.

Wire this into ToolNode via the ``pre_execute_hook`` pattern, or call
``registry.assert_agreement(tool_name)`` directly from tool functions.

Usage::

    from lar.compliance import SupplierAgreementRegistry

    registry = SupplierAgreementRegistry(registry_path="agreements.json")
    registry.register(
        tool_name="send_email",
        supplier_name="Acme Email SaaS Ltd",
        agreement_id="AGR-2026-001",
        signed_date="2026-01-15",
        expiry_date="2027-01-15",
        obligations={"provider": "Art. 9 risk docs", "deployer": "Art. 26 monitoring"},
    )

    # In ToolNode or tool function:
    registry.assert_agreement("send_email")   # raises if missing/expired
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional


class AgreementNotFoundError(Exception):
    """Raised when no current, unexpired supplier agreement exists for a tool."""
    pass


class SupplierAgreementRegistry:
    """
    Art. 25(4) Written Agreement Registry.

    Maintains a ledger of signed agreements between provider/deployer and each
    tool supplier.  Two enforcement points are available:

    1. **Explicit check** — call ``assert_agreement(tool_name)`` from a ToolNode
       or wrapper function before the external call.
    2. **Manifest integration** — pass the registry to ``ComplianceManifestGenerator``
       so the action inventory includes agreement status per tool.

    EU Reference: Art. 25(4) EU AI Act — Written Agreement between Provider and Deployer
    """

    EU_REFERENCE = "Art. 25(4) EU AI Act — Written Agreement between Provider and Deployer"

    def __init__(
        self,
        registry_path: Optional[str] = None,
        block_on_missing: bool = True,
    ):
        """
        Args:
            registry_path: JSON file to persist/load agreements.
                           ``None`` = in-memory only (useful for tests).
            block_on_missing: ``True`` (default) raises ``AgreementNotFoundError``
                              when no valid agreement exists.
                              ``False`` logs a warning and allows execution.
        """
        self.block_on_missing = block_on_missing
        self.registry_path = registry_path
        self._agreements: Dict[str, Dict] = {}

        if registry_path and os.path.exists(registry_path):
            with open(registry_path) as f:
                self._agreements = json.load(f)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        tool_name: str,
        supplier_name: str,
        agreement_id: str,
        signed_date: str,
        expiry_date: Optional[str] = None,
        obligations: Optional[Dict[str, str]] = None,
        contact_email: Optional[str] = None,
    ) -> None:
        """
        Register a written agreement for a tool supplier.

        Args:
            tool_name: Python function ``__name__`` as exposed by ToolNode,
                       or an explicit alias.
            supplier_name: Legal name of the tool/service supplier.
            agreement_id: Internal reference number (e.g. ``"AGR-2026-001"``).
            signed_date: ISO date string (e.g. ``"2026-01-15"``).
            expiry_date: ISO date string, or ``None`` for no expiry.
            obligations: Dict mapping ``{"provider": "...", "deployer": "..."}``
                         per Art. 25(4) obligation split.
            contact_email: Supplier DPA / compliance contact.
        """
        self._agreements[tool_name] = {
            "tool_name": tool_name,
            "supplier_name": supplier_name,
            "agreement_id": agreement_id,
            "signed_date": signed_date,
            "expiry_date": expiry_date,
            "obligations": obligations or {},
            "contact_email": contact_email,
            "registered_at": datetime.datetime.utcnow().isoformat(),
            "eu_reference": self.EU_REFERENCE,
        }
        if self.registry_path:
            os.makedirs(os.path.dirname(self.registry_path) or ".", exist_ok=True)
            with open(self.registry_path, "w") as f:
                json.dump(self._agreements, f, indent=2)

    # ── Enforcement ───────────────────────────────────────────────────────────

    def assert_agreement(self, tool_name: str) -> Dict:
        """
        Verify that a current, unexpired agreement exists for this tool.

        Returns the agreement dict on success.
        Raises ``AgreementNotFoundError`` if missing or expired and
        ``block_on_missing=True``.
        """
        agreement = self._agreements.get(tool_name)

        if not agreement:
            msg = (
                f"[SupplierAgreementRegistry] No Art. 25(4) agreement registered "
                f"for tool '{tool_name}'. {self.EU_REFERENCE}"
            )
            print(f"\n{'!' * 60}\n{msg}\n{'!' * 60}\n")
            if self.block_on_missing:
                raise AgreementNotFoundError(msg)
            return {}

        # Expiry check
        if agreement.get("expiry_date"):
            expiry = datetime.date.fromisoformat(agreement["expiry_date"])
            if datetime.date.today() > expiry:
                msg = (
                    f"[SupplierAgreementRegistry] Agreement '{agreement['agreement_id']}' "
                    f"for tool '{tool_name}' expired on {agreement['expiry_date']}. "
                    f"Renew before execution."
                )
                print(f"\n{'!' * 60}\n{msg}\n{'!' * 60}\n")
                if self.block_on_missing:
                    raise AgreementNotFoundError(msg)
                return {}

        print(
            f"  [SupplierAgreementRegistry] Agreement verified for '{tool_name}' "
            f"(ID: {agreement['agreement_id']}, Supplier: {agreement['supplier_name']})"
        )
        return agreement

    def get_agreement(self, tool_name: str) -> Optional[Dict]:
        """Return agreement dict or None (no blocking)."""
        return self._agreements.get(tool_name)

    def list_agreements(self) -> List[Dict]:
        """Return all registered agreements."""
        return list(self._agreements.values())

    def as_summary(self) -> str:
        """Markdown table of all agreements for compliance manifest."""
        lines = [
            f"## Supplier Agreement Registry — {self.EU_REFERENCE}",
            "| Tool | Supplier | Agreement ID | Signed | Expiry |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for a in self._agreements.values():
            lines.append(
                f"| {a['tool_name']} | {a['supplier_name']} | "
                f"{a['agreement_id']} | {a['signed_date']} | {a.get('expiry_date', '—')} |"
            )
        return "\n".join(lines)
