import json
import math
import datetime
import statistics
from typing import List, Dict, Any, Optional

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


class BehavioralEnvelopeMonitor:
    """
    Tracks stochastic output variance and flags when live outputs deviate from
    the conformity-assessed envelope.

    EU AI Act Relevance:
      - Art. 9 (Risk Management): providers must monitor AI system performance
        over time to detect accuracy drift or unexpected behaviour changes.
      - prEN 18229-1 (Trustworthiness): behavioural consistency is a core
        trustworthiness requirement.
      - Art. 3(23) (Substantial Modification): sustained output deviation may
        constitute a substantial modification of system performance.

    Usage::

        monitor = BehavioralEnvelopeMonitor(
            metric_key="risk_score",
            baseline_samples=[0.42, 0.38, 0.45, 0.40],
            deviation_threshold=0.25,   # 25% relative deviation from baseline mean
        )

        # After each run:
        flag = monitor.observe(current_value)
        if flag["deviation_exceeded"]:
            print(flag["message"])
    """

    EU_REFERENCE = (
        "Art. 9 EU AI Act — Risk Management (performance monitoring); "
        "prEN 18229-1 — Trustworthiness; Art. 3(23) — Substantial Modification"
    )

    def __init__(
        self,
        metric_key: str,
        baseline_samples: List[float],
        deviation_threshold: float = 0.20,
        window_size: int = 10,
    ):
        """
        Args:
            metric_key: Human-readable name of the metric being monitored
                (for logging — this class doesn't read state directly).
            baseline_samples: List of numeric output values observed during the
                conformity assessment period.  Used to compute the baseline mean
                and standard deviation.
            deviation_threshold: Maximum allowed relative deviation from the
                baseline mean before flagging.  E.g., 0.20 = 20%.
            window_size: Sliding window size for computing live statistics.
        """
        if not baseline_samples:
            raise ValueError("baseline_samples must be non-empty")
        self.metric_key = metric_key
        self.baseline_mean: float = statistics.mean(baseline_samples)
        self.baseline_stdev: float = (
            statistics.stdev(baseline_samples) if len(baseline_samples) > 1 else 0.0
        )
        self.deviation_threshold = deviation_threshold
        self.window_size = window_size
        self._observations: List[float] = []
        self._flags: List[Dict] = []

    def observe(self, value: float) -> Dict:
        """
        Record a new observation and check whether it deviates from the baseline.

        Returns a report dict::

            {
              "value": 0.71,
              "baseline_mean": 0.42,
              "relative_deviation": 0.69,
              "deviation_exceeded": True,
              "severity": "HIGH",
              "message": "...",
              "eu_reference": "...",
            }
        """
        self._observations.append(value)
        if len(self._observations) > self.window_size:
            self._observations = self._observations[-self.window_size:]

        # Relative deviation from baseline mean
        if self.baseline_mean != 0:
            rel_dev = abs(value - self.baseline_mean) / abs(self.baseline_mean)
        else:
            rel_dev = abs(value)

        exceeded = rel_dev > self.deviation_threshold
        severity = "HIGH" if rel_dev > self.deviation_threshold * 2 else (
            "MEDIUM" if exceeded else "LOW"
        )

        report: Dict = {
            "metric_key": self.metric_key,
            "observed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "value": value,
            "baseline_mean": self.baseline_mean,
            "baseline_stdev": self.baseline_stdev,
            "relative_deviation": round(rel_dev, 4),
            "threshold": self.deviation_threshold,
            "deviation_exceeded": exceeded,
            "severity": severity,
            "eu_reference": self.EU_REFERENCE,
        }

        if exceeded:
            report["message"] = (
                f"[BehavioralEnvelopeMonitor] [{severity}] Metric '{self.metric_key}' "
                f"deviated {rel_dev:.1%} from baseline mean "
                f"({self.baseline_mean:.4f}). Threshold: {self.deviation_threshold:.1%}. "
                f"Potential Art. 3(23) substantial modification or accuracy drift."
            )
            print(report["message"])
            self._flags.append(report)
        else:
            report["message"] = (
                f"  [BehavioralEnvelopeMonitor] '{self.metric_key}'={value:.4f} "
                f"within envelope ({rel_dev:.1%} deviation)."
            )

        return report

    def get_flags(self) -> List[Dict]:
        """Return all deviation flags raised so far."""
        return list(self._flags)

    def summary(self) -> Dict:
        """Return a summary of monitoring statistics."""
        obs = self._observations
        return {
            "metric_key": self.metric_key,
            "baseline_mean": self.baseline_mean,
            "baseline_stdev": self.baseline_stdev,
            "observations_count": len(obs),
            "live_mean": statistics.mean(obs) if obs else None,
            "live_stdev": statistics.stdev(obs) if len(obs) > 1 else None,
            "total_flags": len(self._flags),
            "eu_reference": self.EU_REFERENCE,
        }
