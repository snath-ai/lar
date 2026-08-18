# Changelog

All notable changes to Lár are documented here.

## [2.2.3] — 2026-08-18

### Fixed

- **`GraphExecutor`'s node-fatigue (loop) detection identified nodes by class name, not instance —
  a real default-active false positive.** `max_node_fatigue` (default 20) counts visits per node
  identity; absent an explicit `_node_id` (which is not referenced anywhere in the codebase, examples,
  or docs — nobody could have known to set it), identity fell back to `current_node.__class__.__name__`.
  A completely ordinary linear pipeline built from many distinct instances of the same reusable node
  type (e.g. 60 separate `AddValueNode` steps) had all 60 collide under the shared name `"AddValueNode"`,
  and the breaker fired at the 21st step even though nothing was looping. Found by actually running
  `examples/failure_modes/4_recursion_limit.py` against a genuine 60-step pipeline.
  - **Fix:** fatigue is now tracked per node *instance* by default (`id(current_node)`-based, assigned a
    stable, human-readable `ClassName#N` label for audit-log purposes). A genuine cycle — the same node
    object actually revisited — is still caught, since the same instance always resolves to the same
    label. Explicitly setting `_node_id` still works as an opt-in to *share* fatigue identity across
    multiple instances, for anyone who genuinely wants that.
  - `log_entry["node"]` (the audit-log display field) is unchanged — this only affects the internal
    fatigue-counting key, not logged output format.
  - No API changes. Existing graphs with genuine cycles behave identically; graphs that legitimately
    reuse the same node type many times no longer false-positive.

### Test suite

165 tests, 0 failures.

---

## [2.2.2] — 2026-08-17

### Fixed

- **Compliance-layer citations corrected against the verbatim text of Regulation (EU) 2024/1689**
  (full independent audit; these fixes were made and tested alongside the v2.2.1 work but were not
  yet included in a release):
  - `fria_node.py` — `FundamentalRightsImpactNode` was citing "Art. 9 FRIA" as its basis. Art. 9 is
    general risk management; the Act's actual standalone Fundamental Rights Impact Assessment is
    Art. 27 (confirmed via Art. 5(2)'s own cross-reference), which was never cited anywhere in the
    codebase. Retargeted to Art. 9(2)(a)'s actual scope with an explicit "this is not Art. 27" note.
  - `incident_reporter.py` — `IncidentReporterNode.DEADLINE_HOURS` had invented deadlines (24h/72h).
    Real Art. 73 figures are 48h (§3, widespread infringement), 240h (§4, death), 360h (§2, general
    default) — the old mapping also put "death" on a shorter deadline than its real one, inverting
    severity. Corrected to 48/240/360h with an explicit docstring caveat that this is a heuristic
    mapping onto real legal deadlines, not itself a legal determination.
  - `multi_agent_boundary_node.py` — removed a "Recital 12 — multi-actor AI system chains" citation;
    Recital 12 is actually about the definition of "AI system" and says nothing about multi-actor chains.
  - `manifest.py` — `BIOMETRIC` domain trigger cited Art. 5(1)(a) (subliminal/manipulative techniques);
    corrected to Art. 5(1)(e)/(g)/(h), the Act's actual biometric-specific prohibitions.

- **`LLMNode` prompt template rendering could still discard all substitutions — v2.2.1's fix was incomplete.**
  v2.2.1 patched `str.format_map()` with a dict that echoes back an unresolved `{key}` instead of raising
  `KeyError`. That protects against *missing keys*, but not against a different, equally common failure:
  a template embedding a literal JSON example whose braces contain a `:` — e.g.
  `{"verdict": "APPROVE" or "DENY", "reason": "..."}`. Python's `str.format()` mini-language treats text
  after a `:` inside braces as a **format spec** (as in `{value:.2f}`), and raises `ValueError` (not
  `KeyError`) when that text isn't a valid one — a case v2.2.1's fix did not catch, so it still fell back
  to the fully raw, unsubstituted template. Found by actually running `examples/compliance/5_context_contamination_test.py`
  and observing `{user_role}`, `{requested_action}`, `{justification}` sent to the model as literal,
  unfilled text.
  - **Fix:** stopped using `str.format()`/`format_map()` for prompt templates entirely. Replaced with
    `_render_template()`, a narrow regex substitution that can only ever match `{identifier}` or
    `{{identifier}}` (bare variable names) and passes every other character through unchanged, with
    `{{`/`}}` not wrapping an identifier collapsing to a literal single brace. Because no other syntax is
    ever recognized, no format-spec parsing happens and **no exception is possible** — a stray or malformed
    brace expression is simply left as literal text instead of aborting every other substitution in the
    same template.
  - Removes `_SafeFormatDict` and the `_JINJA_STYLE_VAR` regex from v2.2.1 (superseded).
  - No API changes. Existing well-formed templates render identically.

### Test suite

165 tests, 0 failures.

---

## [2.2.1] — 2026-08-17

### Fixed

- **`LLMNode` prompt template rendering could silently discard all substitutions.**
  `prompt_template.format(**state.get_all())` is all-or-nothing: a single unresolvable
  `{...}` anywhere in the template (e.g. a literal JSON/code example meant to show the
  model an output schema) raised `KeyError` and caused the *entire* prompt — including
  every otherwise-valid `{var}` substitution — to fall back to the raw, unfilled
  template. This failed silently (a `print()` warning, not an exception) and could
  produce plausible-looking but fabricated LLM output when real state values (customer
  data, request text, etc.) never reached the model.
  - Root cause: the prior `{{` → `{` normalization ran *before* `.format()`, defeating
    Python's own native double-brace escaping for literal braces.
  - Fix: only `{{identifier}}` pairs that look like an actual variable name are now
    collapsed for substitution; any other doubled braces are left to `str.format()`'s
    native literal-brace escaping. Rendering now uses `format_map()` with a dict that
    echoes back an unresolved `{key}` as literal text instead of raising — so one
    missing/malformed placeholder no longer discards every other valid substitution
    in the same template.
  - `AdaptiveNode`'s own internal `schema_instruction` (the JSON-schema example it
    appends to the graph-design prompt) was hitting this exact bug — its literal
    braces are now correctly doubled to render as intended.
  - No API changes. Existing well-formed templates render identically; malformed ones
    now degrade gracefully instead of discarding valid substitutions.

### Test suite

165 tests, 0 failures.

---

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
