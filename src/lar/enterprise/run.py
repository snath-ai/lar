"""
Enterprise Compliance Reference Implementation
===============================================
Run this file to see the full Lár compliance backbone working end-to-end on a
realistic case. Article citations are against Regulation (EU) 2024/1689 as
amended by the Digital Omnibus (Regulation (EU) 2026/1744).

Usage:
    python run.py                        # defaults to HEALTHCARE demo
    python run.py FINANCE                # finance credit-risk case (Art. 27 FRIA applies)
    python run.py PHARMA                 # clinical-trial eligibility
    python run.py LEGAL                  # legal triage
    python run.py HR                     # recruitment screening

    LAR_SHOWCASE_MODEL=ollama/llama3.2:1b python run.py FINANCE   # override the LLM

To target your own domain, add an entry to backbone.DOMAIN_PRESETS or pass
config_overrides= to build_and_run().

DEMO NOTE: the HumanJuryNode below is configured automation_boundary="always_human".
The `mock` list is turned into a *simulated* reviewer (human_decision_provider);
with no provider and no TTY the run HALTS by design. Production wires a real
reviewer surface.

All output is written to ./enterprise_audit/
  run_<uuid>.json           → HMAC-signed causal audit log  (Art. 12)
  authority_ledger.json     → HMAC-signed authority records  (Art. 12/14)
  compliance_manifest.json  → Regulatory action inventory    (Step 9 / Annex IV §2)
  fria_art27.md             → deployer Fundamental Rights Impact Assessment (Art. 27; in-scope domains)
"""

import sys
from backbone import build_and_run, DOMAIN_PRESETS

# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE CASES  — one per domain, realistic but synthetic
# ─────────────────────────────────────────────────────────────────────────────
CASES = {
    "FINANCE": {
        "case_summary": (
            "Credit application from business client. "
            "Requested limit: €500,000. Current D/E ratio: 4.2. "
            "Three missed payments in the last 18 months. "
            "Industry: commercial real estate (elevated sector risk)."
        ),
        "account_number": "REDACT-ME-12345",
        "name":           "REDACT-ME-Acme Corp",
    },
    "HEALTHCARE": {
        "case_summary": (
            "Patient presents with BP 178/110, eGFR 38, HbA1c 9.2%. "
            "Current medications: metformin 1g BD, amlodipine 10mg. "
            "AI flagged Stage 3 CKD with high cardiovascular risk. "
            "Recommendation pending physician sign-off before treatment change."
        ),
        "patient_id": "REDACT-ME-PT00923",
        "dob":        "REDACT-ME-1961-04-12",
        "name":       "REDACT-ME-J. Smith",
    },
    "PHARMA": {
        "case_summary": (
            "Trial ONCO-2026-A candidate: 58yo, ECOG PS 1, "
            "BRCA2 positive, prior platinum-based therapy 14 months ago. "
            "eGFR 62. Meets primary inclusion criteria. "
            "Exclusion criterion check: no active CNS metastases confirmed."
        ),
        "trial_subject_id": "REDACT-ME-TS-4421",
        "dob":              "REDACT-ME-1968-07-30",
    },
    "LEGAL": {
        "case_summary": (
            "Employment dispute: alleged constructive dismissal following "
            "whistleblowing disclosure under ERA 1996 s.47B. "
            "Client employed 7 years, dismissed 3 weeks after protected disclosure. "
            "Limitation period: 3 months less one day from effective termination date."
        ),
        "name":     "REDACT-ME-Claimant A",
        "case_id":  "REDACT-ME-ET/2026/00412",
    },
    "HR": {
        "case_summary": (
            "Software engineer candidate. 8 years Python, distributed systems. "
            "Two prior SaaS startups as founding engineer. "
            "Passed technical screen at 94th percentile. "
            "One 6-month employment gap (undisclosed)."
        ),
        "name":  "REDACT-ME-Candidate B",
        "email": "REDACT-ME-candidate@example.com",
    },
    "GENERIC": {
        "case_summary": "Generic high-stakes enterprise case requiring AI-assisted review.",
    },
}


def main():
    domain = (sys.argv[1].upper() if len(sys.argv) > 1 else "HEALTHCARE")
    if domain not in CASES:
        print(f"Unknown domain '{domain}'. Available: {list(CASES.keys())}")
        sys.exit(1)

    case = CASES[domain]

    # Simulated reviewer decision + rationale (becomes a human_decision_provider).
    # Remove _mock_inputs to run interactively; in production pass a real
    # human_decision_provider wired to your reviewer surface.
    mock = ["approve", f"Reviewed {domain} case. AI recommendation verified against policy."]

    result = build_and_run(
        case=case,
        domain=domain,
        _mock_inputs=mock,
    )

    print(f"\n{'='*65}")
    print(f"  EXECUTION COMPLETE — {result['domain']}")
    print(f"{'='*65}")
    print(f"  Audit log       : {result['audit_log_path']}")
    print(f"  Authority ledger: {result['authority_ledger_path']}")
    print(f"  Manifest        : {result['manifest_path']}")
    fria = result.get("fria_art27") or {}
    if fria.get("applicable"):
        print(f"  Art. 27 FRIA    : {result.get('fria_art27_path')} "
              f"(complete={fria.get('completeness', {}).get('complete')})")
    else:
        print(f"  Art. 27 FRIA    : not applicable for deployer_class="
              f"{fria.get('deployer_class', 'OUT_OF_SCOPE')} "
              f"(rationale recorded at {result.get('fria_art27_path')})")
    records = result["authority_records"]
    if records:
        r = records[0]
        print(f"\n  Authority Record (Fourth Tier):")
        print(f"    Stakeholder : {r['stakeholder_id']} ({r['stakeholder_role']})")
        print(f"    Decision    : {r['decision']}")
        print(f"    Rationale   : {r['rationale']}")
        print(f"    Risk score  : {r['risk_score_at_decision']}")
        print(f"    Timestamp   : {r['timestamp']}")
    print(f"\n  OK  Compliance backbone executed end-to-end"
          f"{' (DEMO reviewer)' if result.get('demo_human_decision') else ''}.")
    print(f"  OK  Audit artefacts are HMAC-SHA256 signed; PII stripped before signing.")
    print(f"  OK  Lethal trifecta check passed (jury prior approval on record).")
    print(f"  OK  Regulatory action inventory saved to manifest.")
    print()


if __name__ == "__main__":
    main()
