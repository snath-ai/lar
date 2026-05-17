"""
lar.compliance.manifest
=======================
ComplianceManifestGenerator — The Regulatory Map Builder.

EU AI Act Reference: Section 8, Step 9 — "Inventory all external actions, data flows,
connected systems, and affected persons."

The paper's core conclusion: "The provider's foundational compliance task is an exhaustive
inventory of the agent's actions, data flows, connected systems, and affected persons.
That inventory is the regulatory map."

This utility statically traverses a Lár graph starting from any node and produces a
structured, JSON-serializable manifest of every tool, model, and data flow — ready
for submission to a compliance officer or notified body.
"""

from __future__ import annotations

import json
import datetime
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ComplianceManifestGenerator:
    """
    Statically traverses a Lár graph and generates an exhaustive regulatory
    action inventory as required by EU AI Act Step 9.

    Usage::

        from lar.compliance import ComplianceManifestGenerator

        manifest = ComplianceManifestGenerator(
            start_node=entry_node,
            system_name="Credit Decision Agent",
            domain="FINANCE",
        )
        report = manifest.generate()
        manifest.save("compliance_manifest.json")
        print(manifest.as_markdown())
    """

    # ── Domain → Adjacent Legislation Map (v2.2.0) ───────────────────────────
    # Maps domain keywords (case-insensitive substring match on system_name /
    # action_type fields in the inventory) to the adjacent legislation that
    # activates alongside the EU AI Act in that sector.
    DOMAIN_TRIGGER_MAP: Dict[str, List[str]] = {
        "FINANCE":     ["MiFID II (investment advice)", "DORA (ICT risk)", "PSD2 (payment flows)"],
        "CREDIT":      ["CRD VI (creditworthiness)", "DORA (ICT risk)", "GDPR (scoring profiles)"],
        "HEALTH":      ["MDR 2017/745 (medical device)", "GDPR Art. 9 (special category data)"],
        "PHARMA":      ["GxP (data integrity)", "GDPR Art. 9 (health data)"],
        "HR":          ["GDPR Art. 22 (automated decisions)", "Anti-discrimination Directives"],
        "LEGAL":       ["Legal privilege obligations", "GDPR Art. 22 (automated decisions)"],
        "INSURANCE":   ["Solvency II", "GDPR Art. 22 (automated profiling)"],
        "ENERGY":      ["CER Directive (critical infrastructure)", "NIS2 Directive"],
        "TRANSPORT":   ["NIS2 Directive", "CER Directive"],
        "SOCIAL":      ["GDPR Art. 22 (automated decisions)", "DSA (platform obligations)"],
        "EMAIL":       ["ePrivacy Directive", "GDPR (data minimisation)"],
        "BIOMETRIC":   ["GDPR Art. 9 (special category)", "EU AI Act Art. 5(1)(a) (prohibited)"],
        "THIRD_PARTY": ["DSA (due diligence)", "Art. 50 EU AI Act (transparency)"],
    }

    def __init__(self, start_node: Any, system_name: str = "Unnamed Agent System",
                 domain: Optional[str] = None):
        """
        Args:
            start_node (BaseNode): The entry point node of the graph to analyze.
            system_name (str): A human-readable name for the agent system being inventoried.
            domain (str, optional): Explicit domain key for ``DOMAIN_TRIGGER_MAP``
                (e.g. ``"FINANCE"``).  If not provided, ``_auto_detect_regulatory_triggers()``
                infers triggered legislation from the inventory's action_type and
                affected_parties fields.
        """
        self.start_node = start_node
        self.system_name = system_name
        self.domain = domain
        self._visited: Set[int] = set()
        self._manifest: Optional[Dict] = None

    def _visit(self, node: Any) -> List[Dict]:
        """Recursively walks the node graph, extracting compliance-relevant metadata."""
        if node is None or id(node) in self._visited:
            return []
        self._visited.add(id(node))

        entries = []
        node_type = node.__class__.__name__

        # --- LLMNode ---
        if node_type == "LLMNode" or node_type == "ReduceNode":
            meta = getattr(node, "compliance_metadata", {})
            affected = meta.get("affected_parties", "USER_ONLY")
            is_external = meta.get("external_action", False)
            article = "Art. 12 (Logging), Art. 13 (Transparency)"
            note = "LLM inference. Prompt and output are logged to the Causal Audit Trail."
            if is_external and affected in ("THIRD_PARTY", "BOTH"):
                article += ", Art. 50 (Transparency to third parties)"
                note = meta.get("description", note) + " EXTERNAL ACTION — activates Art. 50 transparency obligations."
            entry = {
                "node_type": node_type,
                "model_name": getattr(node, "model_name", "unknown"),
                "output_key": getattr(node, "output_key", "unknown"),
                "prompt_template_preview": (getattr(node, "prompt_template", "") or "")[:120] + "...",
                "system_instruction": getattr(node, "system_instruction", None),
                "fallbacks": getattr(node, "fallbacks", None),
                "action_type": meta.get("action_type", "inference"),
                "affected_parties": affected,
                "external_action": is_external,
                "eu_act_relevance": {
                    "article": article,
                    "note": note,
                }
            }
            if node_type == "ReduceNode":
                entry["input_keys_reduced"] = getattr(node, "input_keys", [])
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))

        # --- ToolNode ---
        elif node_type == "ToolNode":
            tool_fn = getattr(node, "tool_function", None)
            action_type = getattr(node, "action_type", None)
            affected = getattr(node, "affected_parties", "USER_ONLY")
            vault = getattr(node, "credential_vault", None)

            entry = {
                "node_type": "ToolNode",
                "tool_function": getattr(tool_fn, "__name__", str(tool_fn)),
                "tool_module": getattr(tool_fn, "__module__", "unknown"),
                "input_keys": getattr(node, "input_keys", []),
                "output_key": getattr(node, "output_key", None),
                "action_type": action_type,
                "affected_parties": affected,
                "jit_credential_vault_attached": vault is not None,
                "credential_key": getattr(node, "credential_key", None),
                "eu_act_relevance": {
                    "article": "Art. 15(4) (Cybersecurity/Privilege), Art. 14 (Oversight)",
                    "note": (
                        "EXTERNAL ACTION — activates regulatory triggers. "
                        f"Affects: {affected}. "
                        + ("JIT CredentialVault provisioned." if vault else "WARNING: No CredentialVault attached.")
                    )
                }
            }
            if affected in ("THIRD_PARTY", "BOTH"):
                entry["eu_act_relevance"]["art_50_triggered"] = True
                entry["eu_act_relevance"]["article"] += ", Art. 50 (Transparency to third parties)"
            entries.append(entry)

            # Walk both next_node and error_node branches
            entries.extend(self._visit(getattr(node, "next_node", None)))
            entries.extend(self._visit(getattr(node, "error_node", None)))

        # --- RouterNode ---
        elif node_type == "RouterNode":
            path_map = getattr(node, "path_map", {})
            entry = {
                "node_type": "RouterNode",
                "decision_function": getattr(getattr(node, "decision_function", None), "__name__", "unknown"),
                "routes": list(path_map.keys()),
                "has_default_fallback": getattr(node, "default_node", None) is not None,
                "eu_act_relevance": {
                    "article": "Art. 14 (Human Oversight), Art. 9 (Risk Management)",
                    "note": "Branching logic. Ensure at least one route leads to HumanJuryNode for high-risk decisions."
                }
            }
            entries.append(entry)
            for child in path_map.values():
                entries.extend(self._visit(child))
            entries.extend(self._visit(getattr(node, "default_node", None)))

        # --- BatchNode ---
        elif node_type == "BatchNode":
            sub_nodes = getattr(node, "nodes", [])
            entry = {
                "node_type": "BatchNode",
                "parallel_branch_count": len(sub_nodes),
                "parallel_node_types": [n.__class__.__name__ for n in sub_nodes],
                "eu_act_relevance": {
                    "article": "Art. 9 (Risk Management), prEN 18229 (Trustworthiness)",
                    "note": (
                        f"Launches {len(sub_nodes)} isolated parallel sub-agents. "
                        "Each sub-agent runs in a cloned, isolated GraphState. "
                        "Results are merged via explicit reducer logic — no context bleed."
                    )
                }
            }
            entries.append(entry)
            for sub_node in sub_nodes:
                entries.extend(self._visit(sub_node))
            entries.extend(self._visit(getattr(node, "next_node", None)))

        # --- AdaptiveNode (formerly DynamicNode) ---
        elif node_type in ("AdaptiveNode", "DynamicNode"):
            entry = {
                "node_type": "AdaptiveNode",
                "eu_act_relevance": {
                    "article": "Art. 3(23) (Substantial Modification), Art. 12 (Logging), Art. 9 (Risk Management)",
                    "note": (
                        "RUNTIME GRAPH COMPOSITION — this node injects a validated subgraph at execution time. "
                        "TopologyValidator must be configured to enforce cycle detection, tool allowlist, and "
                        "structural integrity. Every injected spec is captured in the Causal Trace log for "
                        "Art. 3(23) substantial modification audit."
                    ),
                    "risk_level": "HIGH — Requires TopologyValidator guardrail."
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))

        # --- HumanJuryNode ---
        elif node_type == "HumanJuryNode":
            entry = {
                "node_type": "HumanJuryNode",
                "eu_act_relevance": {
                    "article": "Art. 14 (Human Oversight)",
                    "note": "Explicit human-in-the-loop interrupt. Satisfies Art. 14 automation boundary requirement."
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))
            entries.extend(self._visit(getattr(node, "reject_node", None)))

        # --- RiskScorerNode ---
        elif node_type == "RiskScorerNode":
            entry = {
                "node_type": "RiskScorerNode",
                "eu_act_relevance": {
                    "article": "Art. 9, 14 (Risk Management & Oversight)",
                    "note": "Pre-execution risk scoring gate. Scores risk tier and routes to HumanJury if threshold exceeded."
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))
            entries.extend(self._visit(getattr(node, "human_node", None)))

        # --- BiasFilterNode ---
        elif node_type == "BiasFilterNode":
            entry = {
                "node_type": "BiasFilterNode",
                "eu_act_relevance": {
                    "article": "prEN 18283 (Bias Management), Art. 10(2)(f-g)",
                    "note": "Bias heuristic check before output. Escalates to HumanJury if bias detected."
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))

        # --- SyntheticMarkerNode ---
        elif node_type == "SyntheticMarkerNode":
            entry = {
                "node_type": "SyntheticMarkerNode",
                "eu_act_relevance": {
                    "article": "Art. 50(2) (Synthetic Content Marking)",
                    "note": "Injects AI-generated content disclaimer before final output delivery."
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))

        # --- Generic / Unknown Node (FunctionalNode, etc.) ---
        else:
            meta = getattr(node, "compliance_metadata", {})
            affected = meta.get("affected_parties", "USER_ONLY")
            is_external = meta.get("external_action", False)
            if is_external:
                article = "Art. 15(4) (Cybersecurity/Privilege), Art. 14 (Oversight)"
                if affected in ("THIRD_PARTY", "BOTH"):
                    article += ", Art. 50 (Transparency to third parties)"
                note = meta.get("description", f"External action node '{node_type}'.")
            else:
                article = "Review required"
                note = f"Custom node type '{node_type}'. Manual review needed to determine regulatory triggers."
            entry = {
                "node_type": node_type,
                "action_type": meta.get("action_type", "internal"),
                "affected_parties": affected,
                "external_action": is_external,
                "eu_act_relevance": {
                    "article": article,
                    "note": note,
                }
            }
            entries.append(entry)
            entries.extend(self._visit(getattr(node, "next_node", None)))

        return entries

    # ── Regulatory trigger auto-detection (v2.2.0) ────────────────────────────

    def _auto_detect_regulatory_triggers(self, inventory: List[Dict]) -> Dict[str, List[str]]:
        """
        Infers which adjacent legislation is triggered based on:
        1. An explicit ``domain`` passed to the constructor.
        2. ``action_type``, ``affected_parties``, and node types found in the inventory.

        Returns a dict mapping legislation name to the list of inventory entries
        that triggered it, for full traceability.
        """
        triggered: Dict[str, List[str]] = {}

        def _add(leg: str, reason: str) -> None:
            triggered.setdefault(leg, [])
            if reason not in triggered[leg]:
                triggered[leg].append(reason)

        # 1. Explicit domain override
        if self.domain:
            for key, laws in self.DOMAIN_TRIGGER_MAP.items():
                if key in self.domain.upper():
                    for law in laws:
                        _add(law, f"explicit domain='{self.domain}'")

        # 2. System name substring match
        name_upper = self.system_name.upper()
        for key, laws in self.DOMAIN_TRIGGER_MAP.items():
            if key in name_upper:
                for law in laws:
                    _add(law, f"system_name contains '{key}'")

        # 3. Inventory signals
        for entry in inventory:
            at = str(entry.get("action_type") or "").upper()
            ap = str(entry.get("affected_parties") or "").upper()
            nt = str(entry.get("node_type") or "").upper()

            if "EMAIL" in at:
                _add("ePrivacy Directive", f"action_type={at}")
            if ap in ("THIRD_PARTY", "BOTH"):
                _add("DSA (due diligence)", f"affected_parties={ap}")
                _add("Art. 50 EU AI Act (transparency)", f"affected_parties={ap}")
            if "PAYMENT" in at or "FINANCIAL" in at:
                _add("PSD2 (payment flows)", f"action_type={at}")
                _add("DORA (ICT risk)", f"action_type={at}")
            if "BIOMETRIC" in at:
                _add("GDPR Art. 9 (special category)", f"action_type={at}")
                _add("EU AI Act Art. 5(1)(a) (prohibited biometric use)", f"action_type={at}")
            if "HEALTH" in at or "MEDICAL" in at:
                _add("MDR 2017/745 (medical device)", f"action_type={at}")
                _add("GDPR Art. 9 (special category data)", f"action_type={at}")
            if "CREDIT" in at or "SCORE" in at:
                _add("CRD VI (creditworthiness)", f"action_type={at}")
                _add("GDPR (scoring profiles)", f"action_type={at}")

        return triggered

    def generate(self) -> Dict:
        """
        Traverses the graph and returns the full compliance manifest as a dict.
        """
        self._visited.clear()
        inventory = self._visit(self.start_node)

        # Summarize node types
        node_type_counts: Dict[str, int] = {}
        for entry in inventory:
            nt = entry.get("node_type", "unknown")
            node_type_counts[nt] = node_type_counts.get(nt, 0) + 1

        # All external actions — ToolNode OR any node tagged with external_action=True
        tool_nodes = [e for e in inventory if e.get("node_type") == "ToolNode" or e.get("external_action") is True]
        third_party_tools = [e for e in tool_nodes if e.get("affected_parties") in ("THIRD_PARTY", "BOTH")]
        unvaulted_tools = [e for e in inventory if e.get("node_type") == "ToolNode" and not e.get("jit_credential_vault_attached")]
        dynamic_nodes = [e for e in inventory if e.get("node_type") in ("AdaptiveNode", "DynamicNode")]
        llm_nodes = [e for e in inventory if e.get("node_type") in ("LLMNode", "ReduceNode")]

        # v2.2.0: auto-detect adjacent legislation
        regulatory_triggers = self._auto_detect_regulatory_triggers(inventory)

        self._manifest = {
            "manifest_version": "2.0",
            "system_name": self.system_name,
            "domain": self.domain,
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "eu_ai_act_reference": "Step 9 — External Action Inventory (Section 8.1, Nannini et al., 2026)",
            "summary": {
                "total_nodes_inventoried": len(inventory),
                "node_type_breakdown": node_type_counts,
                "total_external_actions": len(tool_nodes),
                "third_party_affecting_actions": len(third_party_tools),
                "tools_without_credential_vault": len(unvaulted_tools),
                "dynamic_topology_nodes": len(dynamic_nodes),
                "llm_inference_nodes": len(llm_nodes),
            },
            "adjacent_legislation_triggered": regulatory_triggers,
            "risk_flags": self._compute_risk_flags(
                unvaulted_tools, dynamic_nodes, third_party_tools
            ),
            "action_inventory": inventory,
        }
        return self._manifest

    def _compute_risk_flags(
        self,
        unvaulted_tools: List[Dict],
        dynamic_nodes: List[Dict],
        third_party_tools: List[Dict],
    ) -> List[Dict]:
        flags = []
        if unvaulted_tools:
            flags.append({
                "severity": "HIGH",
                "article": "Art. 15(4) / prEN 18282",
                "message": (
                    f"{len(unvaulted_tools)} ToolNode(s) execute without a CredentialVault. "
                    "This violates the privilege minimization requirement. "
                    f"Affected tools: {[t.get('tool_function') or t.get('output_key') or t.get('node_type') for t in unvaulted_tools]}"
                )
            })
        if dynamic_nodes:
            flags.append({
                "severity": "HIGH",
                "article": "Art. 3(23)",
                "message": (
                    f"{len(dynamic_nodes)} AdaptiveNode(s) found. Runtime graph composition "
                    "constitutes a potential 'Substantial Modification' under Art. 3(23). Ensure TopologyValidator is active "
                    "and all generated specs are captured in the Causal Trace log."
                )
            })
        if third_party_tools:
            def _tool_label(t: Dict) -> str:
                return (
                    t.get("tool_function")
                    or t.get("output_key")
                    or t.get("action_type")
                    or t.get("node_type", "unknown")
                )
            flags.append({
                "severity": "MEDIUM",
                "article": "Art. 50",
                "message": (
                    f"{len(third_party_tools)} tool(s) affect third parties and trigger Art. 50 transparency obligations. "
                    f"Verify TransparencyEngine is attached. Tools: {[_tool_label(t) for t in third_party_tools]}"
                )
            })
        if not flags:
            flags.append({
                "severity": "INFO",
                "message": "No critical risk flags detected. Proceed to manual review of action_inventory."
            })
        return flags

    def save(self, filepath: str) -> None:
        """Saves the manifest to a JSON file."""
        if self._manifest is None:
            self.generate()
        with open(filepath, "w") as f:
            json.dump(self._manifest, f, indent=2)
        print(f"[ComplianceManifest] Regulatory map saved to: {filepath}")

    def as_markdown(self) -> str:
        """Returns the manifest as a human-readable Markdown string for auditors."""
        if self._manifest is None:
            self.generate()

        m = self._manifest
        summary = m["summary"]
        lines = [
            f"# Compliance Manifest: {m['system_name']}",
            f"**Generated:** {m['generated_at']}",
            f"**Reference:** {m['eu_ai_act_reference']}",
            "",
            "## Summary",
            f"| Metric | Value |",
            f"| :--- | :--- |",
            f"| Total Nodes Inventoried | {summary['total_nodes_inventoried']} |",
            f"| External Tool Actions | {summary['total_external_actions']} |",
            f"| Third-Party Affecting Actions | {summary['third_party_affecting_actions']} |",
            f"| Tools Without CredentialVault | **{summary['tools_without_credential_vault']}** |",
            f"| Dynamic Topology Nodes | {summary['dynamic_topology_nodes']} |",
            f"| LLM Inference Nodes | {summary['llm_inference_nodes']} |",
            "",
            "## Risk Flags",
        ]
        for flag in m["risk_flags"]:
            sev = flag.get("severity", "INFO")
            art = flag.get("article", "")
            lines.append(f"- **[{sev}]** `{art}` — {flag['message']}")

        lines += ["", "## Action Inventory", ""]
        for i, entry in enumerate(m["action_inventory"], 1):
            node_type = entry.get("node_type", "?")
            rel = entry.get("eu_act_relevance", {})
            lines.append(f"### {i}. `{node_type}`")
            for k, v in entry.items():
                if k not in ("node_type", "eu_act_relevance"):
                    lines.append(f"- **{k}:** `{v}`")
            lines.append(f"- **EU/AI Act Article:** {rel.get('article', 'N/A')}")
            lines.append(f"- **Compliance Note:** {rel.get('note', '')}")
            lines.append("")

        return "\n".join(lines)
