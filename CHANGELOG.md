# Changelog

All notable changes to Lár are documented here.

## [2.1.0] — 2026-05-10

### Added

- **`BranchTriageNode`** — new first-class compliance primitive in `lar.compliance`.
  Post-`BatchNode` node that parses all parallel branch outputs, builds `branch_findings_summary`
  (per-dimension evidence for the human jury), and sets `branch_critical` flag before `ReduceNode`
  compresses results away. Operationalises EU AI Act Art. 14 meaningful oversight in fractal agents.
  Import via `from lar.compliance import BranchTriageNode`.

- **Early-exit HITL pattern** — `BatchNode → BranchTriageNode → RouterNode → [critical: HumanJuryNode → ReduceNode] / [ok: ReduceNode]`.
  Without this pattern, a human reviewer approving a consolidated score has no visibility into which
  individual branch triggered a CRITICAL flag. `BranchTriageNode` preserves that evidence before
  `ReduceNode` destroys it.

- **Full API reference** — `docs/api-reference/branchTriageNode.md` with class signature, parameter
  table, risk level ordering, summary format, standard wiring pattern, and compliance notes
  (Art. 14, Art. 3(23), Nannini et al. §6.2).

- **Fractal compliance showcase** — `examples/compliance/23_fractal_compliance_showcase.py`:
  end-to-end PHARMA fractal agent with `CredentialVault → BatchNode[3 AdaptiveNodes] →
  BranchTriageNode → RouterNode → [early jury / reduce] → BiasFilter → RiskScorer → jury →
  ProhibitedPracticeGuard → SyntheticMarker`. Produces two `AuthorityLedger` records and
  13 HMAC-signed causal trace steps.

- **88 new unit tests** — `tests/unit/test_compliance_primitives.py` brings every compliance
  primitive from zero coverage to production-ready:
  `PIIRedactionEngine`, `CredentialVault`, `AuthorityRecord`, `AuthorityLedger`,
  `PolicyRegistry`, `ActionPolicy`, `RiskScorerNode`, `BiasFilterNode`,
  `LethalTrifectaGuard`, `SyntheticMarkerNode`, `ProhibitedPracticeGuard`,
  `TransparencyEngine`, `RuntimeStateVersioner`, `DriftDetector`,
  `ComplianceManifestGenerator`, `IncidentReporter`.

- **28 unit tests** — `tests/unit/test_branch_triage.py` covering all `BranchTriageNode`
  behaviour: threshold routing at every risk level, custom thresholds, malformed/missing/prose-wrapped
  JSON inputs, custom state key names, `RouterNode` integration, and downstream state survival.

### Changed

- `lar.compliance.__all__` and `lar.__init__` export `BranchTriageNode` alongside existing primitives.
- `mkdocs.yml` nav updated with `BranchTriageNode` API reference entry.
- `README.md` compliance primitives table updated; open-core/enterprise boundary clarified.
- IDE master prompt and integration prompt updated with `BranchTriageNode` wiring pattern and
  pointer to `docs/guides/build-compliant-agent.md`.
- `docs/core-concepts/11-fractal-agency.md` — new "Art. 14 and Meaningful Oversight in Fractal
  Agents" section with full wiring pattern.
- `docs/guides/build-compliant-agent.md` — Step 17 (Advanced): Fractal Agents section added.
- `docs/compliance/eu-ai-act-deep-dive.md` — `BranchTriageNode` added to Art. 14 section.

### Test suite

124 tests, 0 failures.

---

## [2.0.0] — prior release

Initial public release of Lár v2 with the 9-primitive graph engine, HMAC-signed causal trace,
EU AI Act compliance backbone, and LiteLLM universal model support.
