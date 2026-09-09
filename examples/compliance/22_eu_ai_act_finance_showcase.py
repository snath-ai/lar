"""
EU AI Act Finance Agent Showcase
================================
Runs a high-risk credit application (Annex III, point 5(b) — creditworthiness)
through the Lár Enterprise Compliance Backbone and verifies, at runtime, that
every wired primitive actually fires.

What "covered" means here
-------------------------
A row is "covered" when a runtime hook fires and/or an evidence artifact is
produced. It does **not** mean the underlying legal obligation is discharged.
Conformity assessment (Art. 43), the quality management system (Art. 17), the
EU declaration of conformity (Art. 47), EU-database registration (Art. 49), and
the *substantive content* of every assessment remain the customer-provider's and
the deployer's responsibility. Lár is a software component in the Art. 25 value
chain, not the provider (see README "Who is the Provider?").

Legal basis
-----------
Regulation (EU) 2024/1689 (the AI Act) as amended by Regulation (EU) 2026/1744
(the "Digital Omnibus on AI", in force 27 July 2026). Architecture mapped to
Nannini et al. (2026), "AI Agents Under EU Law" (arXiv:2604.04604v1) — a
secondary source; article citations below are verified against the Regulation.

Application timeline (post-Omnibus)
-----------------------------------
  * Art. 5 prohibited practices — since 2 Feb 2025; NCII / AI-CSAM additions
    from 2 Dec 2026.
  * GPAI provider obligations — since 2 Aug 2025.
  * Art. 50 transparency — from 2 Aug 2026 (2 Dec 2026 grace for the 50(2)
    machine-readable marking of generative systems already on the market).
  * Annex III high-risk obligations (Art. 8-15, 16, 26, 27, ...) — from
    **2 December 2027** (deferred from 2 Aug 2026 by the Omnibus).
  * Annex I embedded high-risk AI — from 2 Aug 2028.

Human oversight (Art. 14) in this showcase
------------------------------------------
The HumanJuryNode is configured ``automation_boundary={"case_analysis":
"always_human"}``. With no reviewer and no TTY it HALTS (RuntimeError) — it never
auto-approves. This showcase supplies a **simulated** reviewer through
``human_decision_provider`` (built from ``_mock_inputs``); that decision travels
the same validated + AuthorityLedger-recorded path as a real one. A production
deployment wires ``human_decision_provider`` to a real reviewer UI / web form /
Slack action, or runs interactively.

Row map (all fire at runtime unless marked Docs/Artifacts)
---------------------------------------------------------
  S4  Art. 9        PolicyRegistry + RiskScorerNode
  S5  Art. 10/17    PIIRedactionEngine (GDPR Art. 17) + BiasFilterNode (10(2)(f)-(g))
  S6  Art. 12-14    AuditLogger(HMAC) + HumanJuryNode + AuthorityLedger + TransparencyEngine
  S7  Art. 15(5)    CredentialVault (cybersecurity — NHI least privilege, JIT + trust)
  S9  Step 9        ComplianceManifestGenerator (+ adjacent-legislation map)
  S11 Art. 3(23)    RuntimeStateVersioner + BehavioralEnvelopeMonitor
  A   Art. 9(2)(a)  FundamentalRightsImpactNode  (runtime screen — NOT the Art. 27 FRIA)
  B   Art. 9(9)     BehavioralEnvelopeMonitor
  C   Art. 12       AuditLogger.verify_step_integrity()
  D   Art. 12       AuditLogger.log_plan_switch()
  E   Art. 13       DeployerTransparencyNode (instructions for use)
  F   Art. 14       HumanJuryNode(automation_boundary="always_human") + real decision path
  G   Art. 25(4)    SupplierAgreementRegistry (FOSS carve-out noted)
  H   Art. 3(23)    DynamicToolDiscoveryMonitor
  I   Art. 3        MultiAgentBoundaryNode
  J   Art. 73       IncidentReporterNode (48h/360h conservative ceiling + legal deadlines)
  K   GDPR Art. 17  SessionMemoryNode (write + erase)
  L   Art. 15(5)    CredentialVault.get_with_trust()
  M   Art. 27       Article27FRIANode — deployer Fundamental Rights Impact Assessment
  N   Art. 5        ProhibitedPracticeGuard incl. 2 Dec 2026 NCII/CSAM additions
  O   Art. 50(2)    SyntheticMarkerNode METADATA (machine-readable) + 50(1)/(4) VISIBLE

Usage:
    python examples/compliance/22_eu_ai_act_finance_showcase.py
"""

import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lar.enterprise.backbone import build_and_run

console = Console()


def print_paper_coverage_table():
    table = Table(title="EU AI Act coverage — Lár Enterprise Backbone", show_lines=True)
    table.add_column("Ref", style="bold cyan", width=5)
    table.add_column("Provision", width=16)
    table.add_column("Primitive", width=34)
    table.add_column("Kind", width=11)

    rows = [
        ("S0",  "Art. 3(1)",        "Domain config + classification doc",        "Docs"),
        ("S1",  "Art. 53 (GPAI)",   "LiteLLM model-agnostic + config",           "Docs"),
        ("S2",  "Annex III / Art.6","DOMAIN_PRESETS + conformity_id",            "Docs"),
        ("S3",  "Art. 17 (QMS)",    "Manifest + Ledger + Causal Trace",          "Artifacts"),
        ("S4",  "Art. 9",           "PolicyRegistry + RiskScorerNode",           "Runtime"),
        ("S5",  "Art. 10 / GDPR 17","PIIRedactionEngine + BiasFilterNode",       "Runtime"),
        ("S6",  "Art. 12-14",       "AuditLogger + HumanJuryNode + Ledger",      "Runtime"),
        ("S7",  "Art. 15(5)",       "CredentialVault (JIT + trust) / prEN 18282", "Runtime"),
        ("S8",  "CRA",              "Secure-by-design architecture",             "Docs"),
        ("S9",  "Step 9",           "ComplianceManifestGenerator + DOMAIN_MAP",  "Runtime"),
        ("S10", "Art. 11 / Annex IV","Manifest §2 + Ledger + Trace",             "Artifacts"),
        ("S11", "Art. 3(23)",       "RuntimeStateVersioner + BehavioralEnvMon",  "Runtime"),
        ("A",   "Art. 9(2)(a)",     "FundamentalRightsImpactNode (screen)",      "Runtime"),
        ("B",   "Art. 9(9)",        "BehavioralEnvelopeMonitor",                 "Runtime"),
        ("C",   "Art. 12",          "AuditLogger.verify_step_integrity()",       "Runtime"),
        ("D",   "Art. 12",          "AuditLogger.log_plan_switch()",             "Runtime"),
        ("E",   "Art. 13",          "DeployerTransparencyNode",                  "Runtime"),
        ("F",   "Art. 14",          "HumanJuryNode(always_human) + real path",   "Runtime"),
        ("G",   "Art. 25(4)",       "SupplierAgreementRegistry",                 "Runtime"),
        ("H",   "Art. 3(23)",       "DynamicToolDiscoveryMonitor",              "Runtime"),
        ("I",   "Art. 3",           "MultiAgentBoundaryNode",                    "Runtime"),
        ("J",   "Art. 73",          "IncidentReporterNode (executor hook)",      "Runtime"),
        ("K",   "GDPR Art. 17",     "SessionMemoryNode (write/erase)",           "Runtime"),
        ("L",   "Art. 15(5)",       "CredentialVault.get_with_trust()",          "Runtime"),
        ("M",   "Art. 27 (FRIA)",   "Article27FRIANode (deployer FRIA)",         "Runtime"),
        ("N",   "Art. 5 (+Omnibus)","ProhibitedPracticeGuard (NCII/CSAM)",       "Runtime"),
        ("O",   "Art. 50(1)/(2)/(4)","SyntheticMarkerNode VISIBLE + METADATA",   "Runtime"),
    ]
    for ref, prov, primitive, kind in rows:
        table.add_row(ref, prov, primitive, kind)

    console.print(table)
    r = sum(1 for *_, k in rows if k == "Runtime")
    a = sum(1 for *_, k in rows if k == "Artifacts")
    d = sum(1 for *_, k in rows if k == "Docs")
    console.print(
        f"[dim]{len(rows)} rows — {r} Runtime · {a} Artifacts · {d} Docs. "
        f"'Covered' = runtime hook + evidence, NOT full obligation discharge.[/dim]"
    )


def _check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "[green]OK[/green]" if condition else "[red]FAIL[/red]"
    console.print(f"  {mark} {label}" + (f"  [dim]{detail}[/dim]" if detail else ""))
    return bool(condition)


def main():
    console.print(Panel.fit(
        "[bold green] EU AI Act Finance Agent Showcase [/bold green]\n"
        "[dim]Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 "
        "(Digital Omnibus)[/dim]",
        subtitle="Runtime hook + evidence per provision — not a conformity assessment"
    ))

    console.print(Panel.fit(
        "[yellow]Timeline:[/yellow] Annex III high-risk obligations apply from "
        "[bold]2 Dec 2027[/bold] (deferred by the Omnibus). Art. 5 (since Feb 2025; "
        "NCII/CSAM from 2 Dec 2026), GPAI (since Aug 2025) and Art. 50 (since Aug 2026, "
        "2 Dec 2026 grace for 50(2) marking) are unaffected.",
        title="Application dates"
    ))

    console.print("\n[bold cyan]Coverage map[/bold cyan]")
    print_paper_coverage_table()

    case_data = {
        "name":           "Jane Doe",
        "ssn":             "000-00-0000",
        "account_number": "ACT-99281-XYZ",
        "email":          "jane.doe@example.com",
        "dob":            "1985-04-12",
        "applicant_id":   "APP-2026-00923",
        "case_summary": (
            "Credit application for a EUR 500,000 SME loan. "
            "Applicant is a 39-year-old female business owner. "
            "Current debt-to-equity ratio is 4.2. "
            "Three missed payments on existing credit lines in the last 18 months."
        ),
    }

    console.print("\n[bold cyan]Step 1: Intake & Setup[/bold cyan]")
    console.print("High-risk credit application (Annex III, point 5(b)) containing PII.")
    console.print("[dim]FINANCE / HIGH-RISK / PRE_EXECUTION oversight / THIRD_PARTY affected / "
                  "deployer_class=CREDIT_SCORING -> Art. 27 FRIA applies[/dim]")

    # DEMO reviewer: [decision, rationale]. build_and_run turns this into a
    # human_decision_provider so the always_human jury runs without a TTY.
    mock_human_inputs = [
        "approve",
        "Reviewed FINANCE case. AI recommendation checked against credit policy; "
        "approving subject to mandatory collateral and a fair-lending second check.",
    ]

    try:
        result = build_and_run(
            case=case_data,
            domain="FINANCE",
            _mock_inputs=mock_human_inputs,
        )
    except Exception as e:
        console.print(f"[bold red]Pipeline failed: {e}[/bold red]")
        raise

    console.print("\n[bold cyan]Step 2: Pipeline Complete[/bold cyan]")
    console.print(f"System: [bold yellow]{result['system_name']}[/bold yellow]  "
                  f"Domain: [bold blue]{result['domain']}[/bold blue]  "
                  f"Demo reviewer: [bold]{result.get('demo_human_decision')}[/bold]")

    fs = result.get("final_state", {})
    passes = []

    console.print("\n[bold]Core requirements[/bold]")

    passes.append(_check("S4 - PolicyRegistry + RiskScorerNode (Art. 9/14)",
        fs.get("computed_oversight_level") is not None or fs.get("jury_decision") is not None,
        f"jury_decision={fs.get('jury_decision')}"))

    audit_path = result["audit_log_path"]
    with open(audit_path) as f:
        audit_text = f.read()
    pii_clean = ("Jane Doe" not in audit_text and "000-00-0000" not in audit_text)
    passes.append(_check("S5a - PII redacted from causal trace (GDPR Art. 17)", pii_clean))
    passes.append(_check("S5b - BiasFilterNode ran (Art. 10(2)(f)-(g) keyword gate)",
        fs.get("bias_detected") is not None, f"bias_detected={fs.get('bias_detected')}"))

    hmac_present = ("Signature:" in audit_text or '"hmac"' in audit_text
                    or '"signature"' in audit_text.lower())
    passes.append(_check("S6a - HMAC-SHA256 signature on causal trace (Art. 12)", hmac_present))
    passes.append(_check("S6b - HumanJuryNode decision recorded (Art. 14)",
        fs.get("jury_decision") in ("approve", "reject")))

    ledger_path = result["authority_ledger_path"]
    with open(ledger_path) as f:
        ledger_data = json.load(f)
    recs = ledger_data.get("records", []) if isinstance(ledger_data, dict) else []
    rec = recs[-1] if recs else {}
    passes.append(_check("S6c - AuthorityLedger Fourth-Tier record present (Art. 12/14)",
        bool(recs) and bool(rec.get("rationale"))))
    if rec:
        console.print(f"       Stakeholder: {rec.get('stakeholder_id')} "
                      f"({rec.get('stakeholder_role')}) -> {rec.get('decision')}  "
                      f"rationale: {str(rec.get('rationale'))[:60]}...")

    passes.append(_check("S7 - CredentialVault JIT token provisioned (Art. 15(5))",
        fs.get("jit_token_present") is True))

    manifest_path = result["manifest_path"]
    with open(manifest_path) as f:
        manifest_data = json.load(f)
    summary = manifest_data.get("summary", {})
    manifest_15_5 = "15(5)" in json.dumps(manifest_data) and "15(4)" not in json.dumps(
        {k: v for k, v in manifest_data.items() if k != "action_inventory"})
    passes.append(_check("S9 - Action inventory generated (Step 9); cites Art. 15(5)",
        summary.get("total_external_actions", 0) > 0 and manifest_15_5,
        f"external={summary.get('total_external_actions')}, "
        f"third_party={summary.get('third_party_affecting_actions')}"))

    passes.append(_check("S11 - Post-market drift snapshot (Art. 3(23))",
        fs.get("drift_report") is not None))

    console.print("\n[bold]Gap-closure rows A-O[/bold]")

    passes.append(_check("A - Fundamental-rights screen ran (Art. 9(2)(a) - NOT the Art. 27 FRIA)",
        fs.get("fria_passed") is not None,
        f"fria_passed={fs.get('fria_passed')}, findings={len(fs.get('fria_findings') or [])}"))

    envelope = fs.get("envelope_report") or {}
    passes.append(_check("B - BehavioralEnvelopeMonitor observed (Art. 9(9) PMM)",
        "relative_deviation" in envelope or "deviation_exceeded" in envelope,
        f"deviation_exceeded={envelope.get('deviation_exceeded')}"))

    integrity = result.get("integrity_results", [])
    all_ok = bool(integrity) and all(r.get("integrity") == "OK" for r in integrity)
    passes.append(_check("C - verify_step_integrity - all steps OK (Art. 12)",
        all_ok, f"{sum(1 for r in integrity if r.get('integrity') == 'OK')}/{len(integrity)} OK"))

    passes.append(_check("D - log_plan_switch recorded in causal trace (Art. 12)",
        "plan_switch" in audit_text.lower() or "PLAN_SWITCH" in audit_text))

    deployer_ok = isinstance(fs.get("deployer_instructions"), dict) and bool(
        fs.get("deployer_instructions", {}).get("system_name"))
    passes.append(_check("E - DeployerTransparencyNode wrote instructions-for-use (Art. 13)",
        deployer_ok))

    # F: always_human policy + a real (simulated) decision, with a signed rationale.
    f_ok = (
        fs.get("jury_decision") in ("approve", "reject")
        and bool(rec.get("rationale"))
        and result.get("demo_human_decision") is True
    )
    passes.append(_check("F - HumanJuryNode always_human + recorded human decision (Art. 14)",
        f_ok,
        "policy=always_human; decision via human_decision_provider "
        "(HALTS with no provider + no TTY)"))

    passes.append(_check("G - SupplierAgreementRegistry assert_agreement passed (Art. 25(4))",
        fs.get("supplier_agreements_verified") is True))

    discovery = fs.get("tool_discovery_report") or {}
    passes.append(_check("H - DynamicToolDiscoveryMonitor ran (Art. 3(23))",
        "new_tools" in discovery,
        f"new_tools={discovery.get('new_tools', [])}"))

    boundaries = fs.get("multi_agent_boundaries") or []
    passes.append(_check("I - MultiAgentBoundaryNode boundary record written (Art. 3)",
        len(boundaries) > 0,
        f"placement={boundaries[0].get('placement') if boundaries else 'N/A'}"))

    passes.append(_check("J - IncidentReporterNode wired into executor (Art. 73)",
        result.get("incident_log_path") is not None,
        "conservative 48h/360h ceiling + all three Art. 73 deadlines per record"))

    passes.append(_check("K - SessionMemoryNode write+erase executed (GDPR Art. 17)",
        fs.get("memory_erased") is True,
        f"erased subject: {fs.get('memory_erased_subject')}"))

    audit_trail = result.get("credential_audit_trail") or []
    passes.append(_check("L - CredentialVault.get_with_trust() called (Art. 15(5))",
        any(e.get("trust_level") for e in audit_trail) or len(audit_trail) > 0,
        f"credential access events: {len(audit_trail)}"))

    # M: Art. 27 FRIA — applicable for FINANCE (credit scoring) and complete.
    fria = result.get("fria_art27") or {}
    m_ok = (
        fria.get("applicable") is True
        and fria.get("completeness", {}).get("complete") is True
        and result.get("fria_art27_path") is not None
    )
    passes.append(_check("M - Article27FRIANode: deployer FRIA generated & complete (Art. 27)",
        m_ok,
        f"applicable={fria.get('applicable')}, "
        f"complete={fria.get('completeness', {}).get('complete')}, "
        f"file={result.get('fria_art27_path')}"))

    # N: Omnibus Art. 5 additions present in the guard.
    try:
        from lar.compliance import ProhibitedPracticeGuard
        _g = ProhibitedPracticeGuard(input_key="x")
        n_ok = "NCII" in _g.heuristics and "CSAM" in _g.heuristics
    except Exception:
        n_ok = False
    passes.append(_check("N - ProhibitedPracticeGuard covers 2 Dec 2026 NCII/CSAM bans (Art. 5)",
        n_ok))

    # O: both Art. 50 markings applied.
    o_ok = (
        isinstance(fs.get("final_output"), str)
        and "Art. 50(1)/(4)" in fs.get("final_output", "")
        and isinstance(fs.get("final_output_marked"), dict)
        and "c2pa_manifest" in fs.get("final_output_marked", {})
    )
    passes.append(_check("O - SyntheticMarker VISIBLE (50(1)/(4)) + METADATA (50(2)) both applied",
        o_ok))

    total, passed = len(passes), sum(passes)
    console.print(f"\n[bold]{'-'*60}[/bold]")
    if passed == total:
        console.print(f"[bold green]OK - all {passed}/{total} runtime checks passed.[/bold green]")
    else:
        console.print(f"[bold red]FAIL - {passed}/{total} passed; "
                      f"{total - passed} need attention.[/bold red]")

    console.print(
        "\n[dim]FRIA artifact: enterprise_audit/fria_art27.md  |  "
        "Full mapping: docs/compliance/paper-compliance-mapping.md[/dim]"
    )
    return passed == total


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
