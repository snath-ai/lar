# BranchTriageNode API Reference

## Overview

`BranchTriageNode` is a compliance primitive for **fractal and parallel agent architectures**. Place it immediately after a `BatchNode` whose branches each produce a risk assessment. It does two things before `ReduceNode` compresses those results away:

1. Builds `branch_findings_summary` — a per-dimension breakdown the `HumanJuryNode` can surface to a human reviewer, so they see individual branch findings alongside the consolidated output.
2. Sets `branch_critical` — a boolean flag read by a `RouterNode` to trigger an early-exit `HumanJuryNode` if any branch breached the risk threshold, *before consolidation discards the evidence*.

**Why this matters for Art. 14:** Without `BranchTriageNode`, a reviewer approving a consolidated score has no visibility into which individual dimension triggered a HIGH or CRITICAL flag. The PI sees "MEDIUM overall" but the safety branch said "CRITICAL". That is not meaningful oversight. `BranchTriageNode` preserves the evidence before `ReduceNode` destroys it.

## Class Signature

```python
class BranchTriageNode(BaseNode):
    def __init__(
        self,
        branch_output_keys: List[str],
        risk_level_key: str = "risk_level",
        finding_key: str = "finding",
        critical_threshold: str = "CRITICAL",
        summary_state_key: str = "branch_findings_summary",
        critical_flag_key: str = "branch_critical",
        next_node: Optional[BaseNode] = None,
    )
```

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `branch_output_keys` | `List[str]` | Yes | — | State keys written by each `BatchNode` branch. Each value should be a JSON string containing at minimum `risk_level_key` and `finding_key`. |
| `risk_level_key` | `str` | No | `"risk_level"` | The JSON field inside each branch output that holds the risk level. Expected values: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `finding_key` | `str` | No | `"finding"` | The JSON field inside each branch output that holds the 1-sentence finding. |
| `critical_threshold` | `str` | No | `"CRITICAL"` | The risk level at or above which `branch_critical` is set to `True`. Set to `"HIGH"` for stricter earlier escalation. |
| `summary_state_key` | `str` | No | `"branch_findings_summary"` | State key where the formatted per-dimension summary is written. Include this in `HumanJuryNode.context_keys`. |
| `critical_flag_key` | `str` | No | `"branch_critical"` | State key where the boolean escalation flag is written. `RouterNode.decision_function` reads this key. |
| `next_node` | `BaseNode` | No | `None` | Typically a `RouterNode` that branches on `branch_critical`. |

## State Outputs

| Key | Type | Description |
|-----|------|-------------|
| `branch_findings_summary` | `str` | Formatted multi-line string: one row per branch showing dimension label, risk level, and finding. Survives `ReduceNode` compression because it is written to state before `ReduceNode` runs. |
| `branch_critical` | `bool` | `True` if any branch's `risk_level` was at or above `critical_threshold`. |

## Standard Wiring Pattern

`BranchTriageNode` is always the bridge between `BatchNode` and `RouterNode`. The `RouterNode` must be created after `BranchTriageNode` so it can reference the jury and reduce nodes:

```python
from lar.compliance import BranchTriageNode
from lar import BatchNode, ReduceNode, RouterNode, HumanJuryNode

# 1. Define downstream nodes first (reverse definition order)
node_reduce = ReduceNode(...)
node_jury_early = HumanJuryNode(
    prompt="CRITICAL branch detected. Review before consolidation.",
    context_keys=["branch_findings_summary"],
    output_key="jury_early_decision",
    next_node=node_reduce,   # After early approval, still consolidate
    ...
)
node_jury_final = HumanJuryNode(
    prompt="Consolidated assessment ready. Approve?",
    context_keys=["risk_level", "recommendation", "branch_findings_summary"],
    output_key="jury_decision",
    ...
)

# 2. Triage node — parses branch outputs, sets branch_critical
node_triage = BranchTriageNode(
    branch_output_keys=["safety_analysis", "efficacy_analysis", "regulatory_analysis"],
    critical_threshold="CRITICAL",
    next_node=None,  # wired to router below
)

# 3. Router — created after jury nodes exist (path_map requires live BaseNode instances)
node_router = RouterNode(
    decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
    path_map={
        "critical": node_jury_early,   # Early-exit before ReduceNode
        "ok":       node_reduce,       # Straight to consolidation
    },
)
node_triage.next_node = node_router

# 4. BatchNode wires to triage
node_batch = BatchNode(
    nodes=[node_safety, node_efficacy, node_regulatory],
    next_node=node_triage,
)
```

**Graph flow:**

```
BatchNode → BranchTriageNode → RouterNode
                                    ↓ "critical" → HumanJuryNode (early gate)
                                    │                   ↓
                                    └── "ok" ───→ ReduceNode → parse → HumanJuryNode (final gate)
```

## Risk Level Ordering

The threshold comparison uses a fixed ordinal scale:

| Level | Rank |
|-------|------|
| `LOW` | 0 |
| `MEDIUM` | 1 |
| `HIGH` | 2 |
| `CRITICAL` | 3 |

Setting `critical_threshold="HIGH"` means any branch returning `HIGH` or `CRITICAL` triggers escalation. `UNKNOWN` branch outputs (malformed JSON, empty response) are treated as rank `-1` and never trigger escalation — but they are still included in `branch_findings_summary` so the reviewer sees that a branch failed to produce a parseable result.

## branch_findings_summary Format

```
Branch findings (threshold: CRITICAL):
  SAFETY        : CRITICAL — Compound ZX-412: Grade 4 hepatotoxicity, 3 confirmed deaths.
  EFFICACY      : MEDIUM   — PFS improved 8.4 vs 5.1 months (HR 0.61, p<0.001).
  REGULATORY    : MEDIUM   — Two protocol deviations; no critical GCP findings.
```

The label is derived from the branch output key by stripping `_analysis` and uppercasing. Override `summary_state_key` if you need the summary under a different key name.

## Compliance Notes

**Regulatory basis:**
- **Art. 14 EU AI Act** — Human oversight must be *meaningful*. Showing a human only the consolidated output (after `ReduceNode`) hides the per-dimension evidence they need to exercise informed oversight. `BranchTriageNode` preserves that evidence and surfaces it in the jury context.
- **Art. 3(23) EU AI Act** — In fractal agents, individual branch outcomes may constitute substantial modification evidence. `BranchTriageNode` ensures those outcomes are captured in the causal trace before compression.
- **Nannini et al. (2026), §6.2** — The "Fourth Tier" of human oversight requires that authority exercise records contain sufficient rationale. A rationale tied to a consolidated score is weaker than one tied to per-dimension findings the reviewer actually saw.

**Audit trail:** `BranchTriageNode` is logged as a named step in the HMAC-signed causal trace. The `branch_findings_summary` and `branch_critical` values appear in `state_diff.added`, reconstructible by an auditor independently.

## Example: PHARMA Fractal Agent

Full working implementation with CRITICAL early-exit firing, two authority ledger records, and 13 HMAC-signed steps:

```bash
python examples/compliance/23_fractal_compliance_showcase.py
```

Expected verification output when safety branch returns CRITICAL:

```
Branch triage          : ✅ CRITICAL detected
Early-exit jury        : ✅ FIRED (pre-consolidation safety gate)
Branch findings in jury: ✅ YES (PI saw dimension breakdown)
```

## See Also

- [BatchNode API](batchnode.md) — parallel fan-out
- [HumanJuryNode API](humanjurynode.md) — the blocking Art. 14 interrupt
- [RouterNode API](routernode.md) — conditional routing on `branch_critical`
- [Fractal Agency — Art. 14 in parallel agents](../core-concepts/11-fractal-agency.md)
- [Build a Compliant Agent from Scratch](../guides/build-compliant-agent.md)
- [EU AI Act Deep Dive](../compliance/eu-ai-act-deep-dive.md)
