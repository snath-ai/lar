import os
import json
import glob
import datetime
from typing import List, Dict, Any, Optional

# IncidentReporterNode is imported lazily to avoid a circular import with lar.node
# (lar.node imports from lar.state; lar.compliance.incident_reporter is loaded by
#  lar.compliance.__init__ which is imported by lar.executor — always after lar.node).
try:
    from lar.node import BaseNode
    from lar.state import GraphState
    _NODE_AVAILABLE = True
except ImportError:
    _NODE_AVAILABLE = False

class IncidentReporter:
    """
    Aggregates runtime execution logs and Authority Ledger records to produce 
    a Post-Market Monitoring (PMM) report.
    
    Operationalises EU AI Act Art. 72 (Post-Market Monitoring) and provides 
    evidence for ISO 9001 Clause 9 (Performance Evaluation).
    """
    
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        
    def generate_report(self) -> str:
        """
        Scans the log directory and aggregates metrics into a Markdown report.
        """
        if not os.path.exists(self.log_dir):
            return "No logs found to generate Post-Market Monitoring report."
            
        run_files = glob.glob(os.path.join(self.log_dir, "run_*.json"))
        ledger_file = os.path.join(self.log_dir, "authority_ledger.json")
        
        total_runs = len(run_files)
        total_steps = 0
        critical_risk_count = 0
        trifecta_violations = 0
        high_severity_drifts = 0
        
        # 1. Scan Run Logs
        for rf in run_files:
            try:
                with open(rf, "r") as f:
                    run_data = json.load(f)
                    
                steps = run_data.get("steps", [])
                total_steps += len(steps)
                
                for step in steps:
                    state_diff = step.get("state_diff", {})
                    added = state_diff.get("added", {})
                    updated = state_diff.get("updated", {})
                    
                    # Check for CRITICAL risk
                    risk = added.get("risk_level") or updated.get("risk_level")
                    if risk == "CRITICAL":
                        critical_risk_count += 1
                        
                    # Check for Trifecta Guard violations
                    trifecta = added.get("_trifecta_check") or updated.get("_trifecta_check", {})
                    if isinstance(trifecta, dict) and trifecta.get("violation") is True:
                        trifecta_violations += 1
                        
                    # Check for High Severity Drift
                    drift = added.get("drift_report") or updated.get("drift_report", {})
                    if isinstance(drift, dict) and drift.get("severity") == "HIGH":
                        high_severity_drifts += 1
                        
            except Exception as e:
                print(f"Error parsing log {rf}: {e}")
                
        # 2. Scan Authority Ledger
        total_jury_decisions = 0
        rejections = 0
        approvals = 0
        
        if os.path.exists(ledger_file):
            try:
                with open(ledger_file, "r") as f:
                    ledger_data = json.load(f)
                records = ledger_data.get("records", [])
                total_jury_decisions = len(records)
                
                for rec in records:
                    decision = rec.get("decision", "").lower()
                    if decision == "reject":
                        rejections += 1
                    elif decision == "approve":
                        approvals += 1
            except Exception as e:
                print(f"Error parsing ledger: {e}")
                
        # 3. Format Report
        rejection_rate = (rejections / total_jury_decisions * 100) if total_jury_decisions > 0 else 0
        
        report = [
            "# Post-Market Monitoring (PMM) Incident Report",
            "**Regulatory Reference:** EU AI Act Art. 72 / ISO 9001 Clause 9",
            f"**Log Directory Scanned:** `{self.log_dir}`\n",
            "## 1. Volume Metrics",
            f"- **Total Executions Analyzed:** {total_runs}",
            f"- **Total Steps (Nodes) Executed:** {total_steps}\n",
            "## 2. Risk & Incident Metrics",
            f"- **CRITICAL Risk Scorer Events:** {critical_risk_count}",
            f"- **Lethal Trifecta Guard Violations:** {trifecta_violations}",
            f"- **HIGH Severity Structural Drifts (Art 3(23)):** {high_severity_drifts}\n",
            "## 3. Human Oversight (Authority Ledger)",
            f"- **Total Human Jury Decisions:** {total_jury_decisions}",
            f"- **Approvals:** {approvals}",
            f"- **Rejections:** {rejections} ({rejection_rate:.1f}% Rejection Rate)\n"
        ]
        
        # Alert thresholds
        if rejection_rate > 20:
            report.append("> [!WARNING]\n> **High Rejection Rate Alert:** Human reviewers are rejecting >20% of agent actions. Root cause analysis required.")
        if high_severity_drifts > 0:
            report.append("> [!CRITICAL]\n> **Substantial Modification Alert:** Structural graph drift detected. CE Marking may be invalidated. Immediate review required.")

        return "\n".join(report)


# ─────────────────────────────────────────────────────────────────────────────
# IncidentReporterNode — real-time Art. 73 incident detection
# ─────────────────────────────────────────────────────────────────────────────

class IncidentReporterNode:
    """
    Real-time incident detection and structured record creation for EU AI Act Art. 73-74.

    This class serves two roles:

    1. **As a graph node** (``BaseNode`` subclass via ``_make_node()``) — scans
       the graph state for harm signals after each LLM or Tool step.
    2. **As an executor hook** — called by ``GraphExecutor`` on unhandled
       exceptions via ``report_runtime_error()``.

    Incident records are written to ``incident_log_path`` as a JSON-Lines file.
    If a ``webhook_url`` is provided it is stored in each record so the deployer
    can POST to their CSIRT / ENISA pipeline.

    EU Reference: Art. 73 EU AI Act — Serious Incident Reporting obligations.

    Art. 73's actual deadlines are keyed by INCIDENT TYPE, not by an abstract
    severity score:
      Art. 73(3) — widespread infringement, or a serious incident as defined
                   in Art. 3, point (49)(b) — "not later than two days" (48 h)
      Art. 73(4) — an incident involving the death of a person —
                   "not later than 10 days" (240 h)
      Art. 73(2) — general default, whenever neither (3) nor (4) applies —
                   "not later than 15 days" (360 h)

    Lár has no way to automatically determine from a generic harm signal
    whether an incident is legally "widespread" or involved a death — that is
    a factual/legal determination, not a severity score.  DEADLINE_HOURS below
    is therefore a conservative HEURISTIC mapping from Lár's own internal
    severity tiers onto the real Art. 73 deadlines (fastest deadline for the
    most severe automated triggers, general 15-day default otherwise) — it is
    not itself a legal classification.  Confirm the applicable paragraph against
    the actual incident facts before relying on any deadline_by value produced
    here.

    DEADLINE_HOURS:
      CRITICAL → 48 h  (Art. 73(3) deadline, applied as a fail-safe ceiling for
                         Lár's most severe automated triggers)
      HIGH     → 240 h (Art. 73(4) deadline)
      MEDIUM   → 360 h (Art. 73(2) general default)
      LOW      → None  (below Lár's own reportability threshold — not an
                         Art. 73 category; not a claim that the Act itself
                         exempts these from reporting)
    """

    EU_REFERENCE = "Art. 73 EU AI Act — Serious Incident Reporting (heuristic severity mapping — see class docstring)"

    DEADLINE_HOURS: Dict[str, Optional[int]] = {
        "CRITICAL": 48,
        "HIGH": 240,
        "MEDIUM": 360,
        "LOW": None,
    }

    # Heuristic harm signals in graph state
    _HARM_KEYS = {
        "last_error": "RUNTIME_ERROR",
        "_prohibited_practice_flag": "PROHIBITED_PRACTICE",
        "_trifecta_check": "LETHAL_TRIFECTA",
        "fria_findings": "FRIA_VIOLATION",
        "bias_detected": "BIAS_DETECTED",
    }

    def __init__(
        self,
        severity_threshold: str = "HIGH",
        incident_log_path: str = "lar_logs/incidents.jsonl",
        webhook_url: Optional[str] = None,
        next_node: Optional["BaseNode"] = None,
    ):
        """
        Args:
            severity_threshold: Minimum severity to write an incident record.
                One of ``CRITICAL | HIGH | MEDIUM | LOW``.
            incident_log_path: JSON-Lines file path for incident records.
            webhook_url: Deployer-provided CSIRT webhook URL stored in each record
                (framework does **not** POST automatically — deployer wires this up).
            next_node: Next node when used as a graph node.
        """
        if severity_threshold not in self.DEADLINE_HOURS:
            raise ValueError(
                f"severity_threshold must be one of {list(self.DEADLINE_HOURS)}, "
                f"got '{severity_threshold}'"
            )
        self.severity_threshold = severity_threshold
        self.incident_log_path = incident_log_path
        self.webhook_url = webhook_url
        self.next_node = next_node
        os.makedirs(os.path.dirname(self.incident_log_path) or ".", exist_ok=True)

    # ── Graph node mode ───────────────────────────────────────────────────────

    def execute(self, state: "GraphState") -> Optional["BaseNode"]:
        """
        Scans the current graph state for harm signals and files an incident
        record for any that meet the severity threshold.
        """
        for state_key, harm_type in self._HARM_KEYS.items():
            val = state.get(state_key)
            if not val:
                continue
            # Skip empty lists / dicts
            if isinstance(val, (list, dict)) and not val:
                continue

            severity = self._classify_severity_from_harm(harm_type, val)
            levels = list(self.DEADLINE_HOURS)
            if levels.index(severity) <= levels.index(self.severity_threshold):
                self._write_incident(
                    {
                        "trigger": state_key,
                        "harm_type": harm_type,
                        "severity": severity,
                        "value_summary": str(val)[:300],
                        "run_id": state.get("__run_id"),
                    }
                )
        return self.next_node

    # ── Executor hook mode ────────────────────────────────────────────────────

    def report_runtime_error(
        self,
        node_name: str,
        error: Exception,
        state: "GraphState",
        run_id: str,
        step: int,
    ) -> None:
        """
        Called by ``GraphExecutor`` on an unhandled node exception.

        Classifies the error severity and writes a structured incident record.
        """
        severity = self._classify_severity(error, state)
        levels = list(self.DEADLINE_HOURS)
        if levels.index(severity) <= levels.index(self.severity_threshold):
            self._write_incident(
                {
                    "trigger": "unhandled_exception",
                    "harm_type": "RUNTIME_ERROR",
                    "severity": severity,
                    "node_name": node_name,
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:500],
                    "run_id": run_id,
                    "step": step,
                }
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _classify_severity(self, error: Exception, state: "GraphState") -> str:
        name = type(error).__name__
        if name in ("ProhibitedPracticeError", "LethalTrifectaError", "FRIAViolation"):
            return "CRITICAL"
        if name in ("SecurityError", "AgreementNotFoundError", "UndisclosedToolError"):
            return "HIGH"
        if state.get("_trifecta_check") or state.get("_prohibited_practice_flag"):
            return "HIGH"
        return "MEDIUM"

    def _classify_severity_from_harm(self, harm_type: str, val: Any) -> str:
        if harm_type in ("PROHIBITED_PRACTICE", "LETHAL_TRIFECTA", "FRIA_VIOLATION"):
            return "CRITICAL"
        if harm_type == "RUNTIME_ERROR":
            return "HIGH"
        if harm_type == "BIAS_DETECTED" and val is True:
            return "MEDIUM"
        return "LOW"

    def _write_incident(self, details: Dict) -> None:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        severity = details.get("severity", "MEDIUM")
        deadline_h = self.DEADLINE_HOURS.get(severity)
        record = {
            "schema": "lar-incident-v1",
            "eu_reference": self.EU_REFERENCE,
            "reported_at": now,
            "severity": severity,
            "reporting_deadline_hours": deadline_h,
            "deadline_by": (
                (datetime.datetime.utcnow() + datetime.timedelta(hours=deadline_h)).isoformat() + "Z"
                if deadline_h else None
            ),
            "webhook_url": self.webhook_url,
            **details,
        }
        with open(self.incident_log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        print(
            f"  [IncidentReporterNode] [{severity}] Incident recorded "
            f"(deadline: {deadline_h}h). → {self.incident_log_path}"
        )
