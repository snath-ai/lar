import json
import datetime
from typing import List, Dict, Any

class DriftReport:
    def __init__(self, drift_detected: bool, changed_keys: List[str], severity: str):
        self.drift_detected = drift_detected
        self.changed_keys = changed_keys
        self.severity = severity

class DriftDetector:
    """
    Detects structural drift between two runtime state snapshots.
    Operationalises EU AI Act Art. 3(23) (Substantial modification).
    """
    @staticmethod
    def compare(snapshot_a: Dict[str, Any], snapshot_b: Dict[str, Any]) -> DriftReport:
        changed_keys = []
        for key in ["tool_catalogue", "policy_bindings"]:
            if json.dumps(snapshot_a.get(key), sort_keys=True) != json.dumps(snapshot_b.get(key), sort_keys=True):
                changed_keys.append(key)
        
        schema_a = set(snapshot_a.get("state_schema_keys", []))
        schema_b = set(snapshot_b.get("state_schema_keys", []))
        if schema_a != schema_b:
            changed_keys.append("state_schema_keys")
            
        drift_detected = len(changed_keys) > 0
        severity = "HIGH" if "tool_catalogue" in changed_keys else ("MEDIUM" if drift_detected else "LOW")
        
        return DriftReport(drift_detected, changed_keys, severity)

class RuntimeStateVersioner:
    """
    Captures periodic snapshots of the agent's structural configuration (tools, schema, policies)
    to establish a baseline and monitor for substantial modification.
    """
    def __init__(self, conformity_baseline_id: str = "baseline_v1"):
        self.conformity_baseline_id = conformity_baseline_id
        self.snapshots: List[Dict[str, Any]] = []
        
    def snapshot(self, tool_catalogue: List[str], state_schema_keys: List[str], policy_bindings: Dict[str, Any]) -> Dict[str, Any]:
        snap = {
            "timestamp": datetime.datetime.now().isoformat(),
            "conformity_baseline_id": self.conformity_baseline_id,
            "tool_catalogue": tool_catalogue,
            "state_schema_keys": state_schema_keys,
            "policy_bindings": policy_bindings
        }
        
        if self.snapshots:
            baseline = self.snapshots[0]
            report = DriftDetector.compare(baseline, snap)
            if report.drift_detected:
                print(f"  [RuntimeStateVersioner] WARNING: Drift detected in keys: {report.changed_keys} (Severity: {report.severity})")
                snap["drift_report"] = {
                    "drift_detected": True,
                    "changed_keys": report.changed_keys,
                    "severity": report.severity
                }
        
        self.snapshots.append(snap)
        return snap
