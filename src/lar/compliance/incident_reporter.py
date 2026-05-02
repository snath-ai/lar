import os
import json
import glob
from typing import List, Dict, Any

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
