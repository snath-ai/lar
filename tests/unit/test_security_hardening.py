"""
Regression tests for the November 2026 security audit.

Each test pins a behaviour that the audit proved was broken. Finding ids (H1..M3,
L1) refer to reports/LAR_SECURITY_AUDIT_2026-11-21.md.
"""
import contextlib
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import textwrap

import pytest

from lar import GraphExecutor, FunctionalNode, ToolNode
from lar.node import HumanJuryNode, LLMNode, BaseNode
from lar.state import GraphState
from lar.logger import AuditLogger, AuditWriteError
from lar.checkpoint import FileCheckpointStore, Checkpoint, resume_human_decision
from lar.compliance import (
    AuthorityLedger, BiasFilterNode, CredentialVault, LethalTrifectaGuard,
    LethalTrifectaError, PIIRedactionEngine, SessionMemoryNode,
    PolicyRegistry, ActionPolicy, RiskScorerNode,
)
from lar.spec.registry import AgentRegistry

# `lar.node` is shadowed by the `node` decorator re-exported in lar/__init__.py,
# so fetch the real module object explicitly when patching its globals.
node_mod = importlib.import_module("lar.node")


@pytest.fixture(autouse=True)
def _headless(monkeypatch):
    """Simulate a server/CI process: stdin is not a terminal."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)


def run(node, state=None, **executor_kwargs):
    ex = GraphExecutor(**executor_kwargs)
    return list(ex.run_step_by_step(node, dict(state or {})))


# ───────────────────────────── H1: fail closed ─────────────────────────────

class TestH1HeadlessJuryFailsClosed:
    def test_unconfigured_headless_jury_does_not_auto_approve(self, tmp_path):
        after = FunctionalNode(lambda s: s.set("executed", True))
        jury = HumanJuryNode(prompt="Approve?", choices=["approve", "reject"],
                             output_key="decision", next_node=after)
        steps = run(jury, log_dir=str(tmp_path))
        final = steps[-1]["state_after"]
        assert "decision" not in final           # no decision was fabricated
        assert "executed" not in final            # the gated action never ran
        assert steps[0]["outcome"] == "error"

    def test_always_human_still_halts(self, tmp_path):
        jury = HumanJuryNode(prompt="?", choices=["approve", "reject"], output_key="d",
                             decision_type="CREDIT", automation_boundary={"CREDIT": "always_human"})
        steps = run(jury, log_dir=str(tmp_path))
        assert steps[0]["outcome"] == "error"

    def test_explicit_opt_in_auto_first_choice_still_works(self, tmp_path):
        jury = HumanJuryNode(prompt="?", choices=["approve", "reject"], output_key="d",
                             decision_type="LOW", automation_boundary={"LOW": "auto_first_choice"})
        steps = run(jury, log_dir=str(tmp_path))
        assert steps[0]["state_after"]["d"] == "approve"

    def test_unknown_policy_name_is_rejected(self, tmp_path):
        jury = HumanJuryNode(prompt="?", choices=["a", "b"], output_key="d",
                             decision_type="X", automation_boundary={"X": "typo_policy"})
        steps = run(jury, log_dir=str(tmp_path))
        assert steps[0]["outcome"] == "error"


# ───────────────────── H2: a reject must stop the approval path ─────────────────────

class TestH2RejectIsEnforced:
    def _graph(self, routes):
        effect = FunctionalNode(lambda s: s.set("side_effect", True))
        jury = HumanJuryNode(
            prompt="?", choices=["approve", "reject"], output_key="d", next_node=effect,
            human_decision_provider=lambda ctx: ("reject", "not acceptable"),
            decision_routes=routes,
        )
        return jury, effect

    def test_reject_with_route_none_stops_the_run(self, tmp_path):
        jury, _ = self._graph({"reject": None})
        steps = run(jury, log_dir=str(tmp_path))
        assert steps[-1]["state_after"]["d"] == "reject"
        assert "side_effect" not in steps[-1]["state_after"]
        assert len(steps) == 1

    def test_reject_can_route_to_a_cleanup_node(self, tmp_path):
        cleanup = FunctionalNode(lambda s: s.set("cleaned", True))
        jury, _ = self._graph({"reject": cleanup})
        steps = run(jury, log_dir=str(tmp_path))
        final = steps[-1]["state_after"]
        assert final.get("cleaned") is True and "side_effect" not in final

    def test_approve_still_continues(self, tmp_path):
        effect = FunctionalNode(lambda s: s.set("side_effect", True))
        jury = HumanJuryNode(prompt="?", choices=["approve", "reject"], output_key="d", next_node=effect,
                             human_decision_provider=lambda ctx: ("approve", "ok"),
                             decision_routes={"reject": None})
        steps = run(jury, log_dir=str(tmp_path))
        assert steps[-1]["state_after"].get("side_effect") is True

    def test_routes_must_use_known_choices(self):
        with pytest.raises(ValueError):
            HumanJuryNode(prompt="?", choices=["approve", "reject"], output_key="d",
                          decision_routes={"maybe": None})

    def test_trifecta_guard_does_not_accept_a_reject_as_approval(self):
        g = LethalTrifectaGuard(lambda s: True, lambda s: True, lambda s: True)
        with pytest.raises(LethalTrifectaError):
            g.check(GraphState({"jury_decision": "reject"}), "external_write")

    def test_trifecta_guard_accepts_approve(self):
        g = LethalTrifectaGuard(lambda s: True, lambda s: True, lambda s: True)
        assert g.check(GraphState({"jury_decision": "Approve"}), "x")["violation"] is False


# ───────────────────── H3: secrets never reach state or logs ─────────────────────

class TestH3CredentialNotLogged:
    def test_secret_absent_from_audit_log_and_state_but_tool_receives_it(self, tmp_path):
        vault = CredentialVault()
        vault.register_credential("API_KEY", "sk-SECRET-12345")
        seen = {}

        def tool(state):
            seen["key"] = state.get("API_KEY")
            return "done"

        end = FunctionalNode(lambda s: None)
        node = ToolNode(tool_function=tool, input_keys=["__state__"], output_key="out",
                        next_node=end, action_type="read",
                        credential_vault=vault, credential_key="API_KEY")
        steps = run(node, log_dir=str(tmp_path), hmac_secret="k")
        assert seen["key"] == "sk-SECRET-12345"              # the tool could use it
        for f in os.listdir(tmp_path):                        # ...but it was never written down
            assert "sk-SECRET-12345" not in (tmp_path / f).read_text()
        assert "API_KEY" not in steps[-1]["state_after"]

    def test_pre_existing_state_value_is_restored(self, tmp_path):
        vault = CredentialVault()
        vault.register_credential("API_KEY", "vault-value")
        node = ToolNode(tool_function=lambda: 1, input_keys=[], output_key="o",
                        next_node=FunctionalNode(lambda s: None),
                        credential_vault=vault, credential_key="API_KEY")
        state = GraphState({"API_KEY": "caller-value"})
        node.execute(state)
        assert state.get("API_KEY") == "caller-value"


# ───────────────────── H4: resume is validated, authorised, exactly-once ─────────────────────

def _paused_case(tmp_path, routes=None, case="C1"):
    """Run a checkpoint-enabled jury until it pauses; return (store, registry, executor, after)."""
    store = FileCheckpointStore(str(tmp_path / "cp"))
    after = FunctionalNode(lambda s: s.set("executed", True))
    after._node_id = "after"
    routed = {}
    if routes == "reject_stops":
        routed = {"reject": None}
    elif routes == "reject_cleanup":
        cleanup = FunctionalNode(lambda s: s.set("cleaned", True))
        cleanup._node_id = "cleanup"
        routed = {"reject": cleanup}
    jury = HumanJuryNode(
        prompt="ok?", choices=["approve", "reject"], output_key="d", context_keys=[],
        next_node=after, checkpoint_store=store, case_id_key="case_id",
        decision_type="CREDIT", automation_boundary={"CREDIT": "always_human"},
        decision_routes=routed or None,
    )
    ex = GraphExecutor(log_dir=str(tmp_path / "logs"))
    list(ex.run_step_by_step(jury, {"case_id": case}))     # pauses (always_human, no human)
    registry = {"after": after}
    if routes == "reject_cleanup":
        registry["cleanup"] = cleanup
    return store, registry, ex, after


class TestH4ResumeSafety:
    def test_pause_writes_a_checkpoint_with_choices(self, tmp_path):
        store, *_ = _paused_case(tmp_path)
        cp = store.load("C1")
        assert cp is not None and cp.metadata["choices"] == ["approve", "reject"]

    def test_invalid_decision_is_rejected_and_checkpoint_stays_pending(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        with pytest.raises(ValueError, match="Invalid decision"):
            list(resume_human_decision(store, "C1", "banana", ex, reg))
        assert store.exists("C1")

    def test_unauthorised_stakeholder_is_refused(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        with pytest.raises(PermissionError):
            list(resume_human_decision(store, "C1", "approve", ex, reg,
                                       stakeholder_id="mallory", authorize=lambda who, meta: who == "alice"))
        assert store.exists("C1")

    def test_anonymous_reviewer_refused_when_ledger_attached(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        with pytest.raises(PermissionError):
            list(resume_human_decision(store, "C1", "approve", ex, reg,
                                       authority_ledger=AuthorityLedger()))

    def test_valid_resume_runs_next_node_then_clears_checkpoint(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        steps = list(resume_human_decision(store, "C1", "APPROVE ", ex, reg,
                                           stakeholder_id="alice", authorize=lambda w, m: True))
        assert steps[-1]["state_after"]["executed"] is True
        assert not store.exists("C1")

    def test_second_resume_of_same_case_is_refused(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        list(resume_human_decision(store, "C1", "approve", ex, reg))
        with pytest.raises(ValueError):
            list(resume_human_decision(store, "C1", "approve", ex, reg))

    def test_claim_is_exactly_once(self, tmp_path):
        store, *_ = _paused_case(tmp_path)
        assert store.claim("C1") is not None
        assert store.claim("C1") is None

    def test_interrupted_resume_releases_the_checkpoint(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        gen = resume_human_decision(store, "C1", "approve", ex, reg)
        next(gen)            # run started: checkpoint is claimed
        gen.close()          # consumer abandons it before it finishes
        assert store.exists("C1")                 # decision/case not lost
        assert store.claim("C1") is not None      # and can be resolved again

    def test_resumed_reject_follows_the_route_and_skips_approval_path(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path, routes="reject_cleanup")
        steps = list(resume_human_decision(store, "C1", "reject", ex, reg))
        final = steps[-1]["state_after"]
        assert final.get("cleaned") is True and "executed" not in final

    def test_resumed_reject_with_stop_route_runs_nothing(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path, routes="reject_stops")
        steps = list(resume_human_decision(store, "C1", "reject", ex, reg))
        assert steps == []
        assert not store.exists("C1")


# ───────────────────── H5: audit trail integrity ─────────────────────

class TestH5AuditTrail:
    def _two_step_run(self, tmp_path, secret="k"):
        s2 = FunctionalNode(lambda s: s.set("b", 2))
        s1 = FunctionalNode(lambda s: s.set("a", 1), next_node=s2)
        run(s1, log_dir=str(tmp_path), hmac_secret=secret)
        chain = next(f for f in os.listdir(tmp_path) if f.endswith(".chain.jsonl"))
        summary = next(f for f in os.listdir(tmp_path) if f.endswith(".json"))
        return tmp_path / chain, tmp_path / summary

    def test_chain_is_written_and_verifies(self, tmp_path):
        chain, summary = self._two_step_run(tmp_path)
        data = json.loads(summary.read_text())
        res = AuditLogger.verify_chain(str(chain), hmac_secret="k", expected_head=data["chain"]["head"])
        assert res["ok"] and res["entries"] == 2

    def test_editing_an_entry_is_detected(self, tmp_path):
        chain, _ = self._two_step_run(tmp_path)
        lines = chain.read_text().splitlines()
        rec = json.loads(lines[0]); rec["entry"]["node"] = "forged"
        lines[0] = json.dumps(rec, sort_keys=True)
        chain.write_text("\n".join(lines) + "\n")
        assert AuditLogger.verify_chain(str(chain))["ok"] is False

    def test_truncation_is_detected_with_expected_head(self, tmp_path):
        chain, summary = self._two_step_run(tmp_path)
        head = json.loads(summary.read_text())["chain"]["head"]
        chain.write_text(chain.read_text().splitlines()[0] + "\n")
        assert AuditLogger.verify_chain(str(chain), expected_head=head)["ok"] is False

    def test_wrong_key_fails_mac_check(self, tmp_path):
        chain, _ = self._two_step_run(tmp_path, secret="right")
        assert AuditLogger.verify_chain(str(chain), hmac_secret="wrong")["ok"] is False

    def test_summary_signature_verifies_and_detects_tampering(self, tmp_path):
        _, summary = self._two_step_run(tmp_path)
        assert AuditLogger.verify_signature(str(summary), "k") is True
        assert AuditLogger.verify_signature(str(summary), "other") is False
        data = json.loads(summary.read_text()); data["summary"]["total_steps"] = 99
        assert AuditLogger.verify_signature(data, "k") is False

    def test_completed_steps_survive_a_hard_crash(self, tmp_path):
        script = textwrap.dedent("""
            import os
            from lar import GraphExecutor, FunctionalNode
            crash = FunctionalNode(lambda s: os._exit(1))
            s2 = FunctionalNode(lambda s: s.set("side_effect_done", True), next_node=crash)
            s1 = FunctionalNode(lambda s: s.set("step1", True), next_node=s2)
            list(GraphExecutor(log_dir="logs", hmac_secret="k").run_step_by_step(s1, {}))
        """)
        subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True)
        chains = [f for f in os.listdir(tmp_path / "logs") if f.endswith(".chain.jsonl")]
        assert chains, "no per-step log survived the crash"
        res = AuditLogger.verify_chain(str(tmp_path / "logs" / chains[0]), hmac_secret="k")
        assert res["ok"] and res["entries"] == 2          # both completed steps are on disk

    def test_failed_summary_write_raises_in_strict_mode(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path / "L"), hmac_secret="k")
        lg.log_dir = str(tmp_path / "does" / "not" / "exist")
        with pytest.raises(AuditWriteError):
            lg.save_to_file("rid")

    def test_failed_summary_write_can_be_opted_back_to_legacy(self, tmp_path, capsys):
        lg = AuditLogger(log_dir=str(tmp_path / "L"), strict=False)
        lg.log_dir = str(tmp_path / "does" / "not" / "exist")
        lg.save_to_file("rid")                     # prints, does not raise
        assert "Failed to save log" in capsys.readouterr().out

    def test_failed_step_write_fails_closed(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path / "L"))
        lg.begin_run("r1")
        lg._chain_path = str(tmp_path / "missing" / "dir" / "x.chain.jsonl")
        with pytest.raises(AuditWriteError):
            lg.log_step({"step": 0})


class TestH5Ledger:
    def _rec(self, led, who="a"):
        led.record("act", who, "role", "approve", "why", context_snapshot={"k": "v"})

    def test_second_run_does_not_erase_first_runs_records(self, tmp_path):
        path = str(tmp_path / "led.json")
        l1 = AuthorityLedger(hmac_secret="k"); self._rec(l1, "u1"); l1.save(path)
        l2 = AuthorityLedger(hmac_secret="k"); self._rec(l2, "u2"); l2.save(path)
        data = json.loads(open(path).read())
        assert data["total_records"] == 2
        assert [r["stakeholder_id"] for r in data["records"]] == ["u1", "u2"]
        assert AuthorityLedger.verify(path, "k")["ok"]

    def test_path_constructor_appends_across_instances(self, tmp_path):
        path = str(tmp_path / "led.json")
        for who in ("u1", "u2", "u3"):
            l = AuthorityLedger(hmac_secret="k", path=path); self._rec(l, who); l.save()
        assert json.loads(open(path).read())["total_records"] == 3
        assert AuthorityLedger.verify(path, "k")["ok"]

    def test_removed_record_is_detected(self, tmp_path):
        path = str(tmp_path / "led.json")
        l = AuthorityLedger(hmac_secret="k", path=path)
        for who in ("u1", "u2"): self._rec(l, who)
        l.save()
        data = json.loads(open(path).read()); data["records"].pop(0)
        open(path, "w").write(json.dumps(data))
        assert AuthorityLedger.verify(path, "k")["ok"] is False

    def test_edited_record_is_detected(self, tmp_path):
        path = str(tmp_path / "led.json")
        l = AuthorityLedger(hmac_secret="k", path=path); self._rec(l); l.save()
        data = json.loads(open(path).read()); data["records"][0]["decision"] = "reject"
        open(path, "w").write(json.dumps(data))
        assert AuthorityLedger.verify(path)["ok"] is False

    def test_record_attests_the_context_the_reviewer_saw(self):
        l = AuthorityLedger()
        rec = l.record("a", "u", "r", "approve", "why", context_snapshot={"amount": 500})
        expected = hashlib.sha256(json.dumps({"amount": 500}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert rec.to_dict()["context_sha256"] == expected

    def test_legacy_ledger_without_hashes_is_migrated_not_crashed(self, tmp_path):
        path = tmp_path / "old.json"
        path.write_text(json.dumps({"ledger_type": "AUTHORITY_EXERCISE_LEDGER", "total_records": 1,
                                    "records": [{"record_type": "AUTHORITY_EXERCISE", "stakeholder_id": "legacy",
                                                 "decision": "approve"}]}))
        l = AuthorityLedger(hmac_secret="k", path=str(path)); self._rec(l, "new"); l.save()
        data = json.loads(path.read_text())
        assert data["total_records"] == 2 and data["records"][0]["migrated_from_legacy"] is True
        assert AuthorityLedger.verify(str(path), "k")["ok"]


# ───────────────────── H6: identifiers cannot escape their directory ─────────────────────

class TestH6PathTraversal:
    @pytest.mark.parametrize("bad", ["../evil", "../../outside/evil", "a/b", "/abs/path", "..", ".hidden", "x" * 200])
    def test_checkpoint_store_rejects_unsafe_case_ids(self, tmp_path, bad):
        store = FileCheckpointStore(str(tmp_path / "cp"))
        with pytest.raises(ValueError):
            store.save(Checkpoint(case_id=bad, resume_node_id="n", state={}))
        assert not (tmp_path / "evil.json").exists()
        assert not (tmp_path / "outside").exists()

    def test_checkpoint_store_unsafe_load_and_delete_also_rejected(self, tmp_path):
        store = FileCheckpointStore(str(tmp_path / "cp"))
        for op in (store.load, store.delete, store.exists, store.claim):
            with pytest.raises(ValueError):
                op("../../etc/passwd")

    def test_normal_case_ids_still_work(self, tmp_path):
        store = FileCheckpointStore(str(tmp_path / "cp"))
        store.save(Checkpoint(case_id="CASE-2026_11.A", resume_node_id="n", state={"x": 1}))
        assert store.load("CASE-2026_11.A").state == {"x": 1}

    def test_agent_registry_rejects_traversal(self, tmp_path):
        reg = AgentRegistry(str(tmp_path / "agents"))
        with pytest.raises(ValueError):
            reg.load_agent("../../etc/passwd", "1.0.0")
        with pytest.raises(ValueError):
            reg.list_versions("../x")


# ───────────────────── M1: personal data ─────────────────────

class TestM1PersonalData:
    def test_known_values_are_scrubbed_from_free_text(self):
        eng = PIIRedactionEngine(sensitive_keys=["name"])
        out = eng.process_dict({"name": "John Smith", "prompt": "Assess a loan for John Smith today"})
        assert "John Smith" not in json.dumps(out)

    def test_email_iban_ssn_patterns_in_free_text(self):
        eng = PIIRedactionEngine(sensitive_keys=[])
        out = eng.process_dict({"t": "mail a@b.com iban IE29 AIBK 9311 5212 3456 78 ssn 123-45-6789"})
        assert "a@b.com" not in out["t"] and "123-45-6789" not in out["t"] and "9311" not in out["t"]

    def test_dates_and_long_ids_are_not_mangled_by_default(self):
        eng = PIIRedactionEngine(sensitive_keys=[])
        data = {"timestamp": "2026-11-21T10:00:00", "epoch": "1763719200000", "run": "run_b72ca249"}
        assert eng.process_dict(data) == data

    def test_logger_redacts_prompt_text_end_to_end(self, tmp_path):
        red = PIIRedactionEngine(sensitive_keys=["name"])
        lg = AuditLogger(log_dir=str(tmp_path), hmac_secret="k", pii_redactor=red)

        def w(s):
            s.set("name", "John Smith")
            s.set("__last_prompt", "Assess loan for John Smith")
        list(GraphExecutor(log_dir=str(tmp_path), logger=lg, hmac_secret="k")
             .run_step_by_step(FunctionalNode(w), {}))
        assert "John Smith" not in json.dumps(lg.get_history())
        for f in os.listdir(tmp_path):
            assert "John Smith" not in (tmp_path / f).read_text()

    def test_hash_mode_is_keyed_not_plain_sha256(self):
        plain = hashlib.sha256(b"123-45-6789").hexdigest()
        a = PIIRedactionEngine(["ssn"], mode="HASH", hash_key="k1").process_dict({"ssn": "123-45-6789"})["ssn"]
        b = PIIRedactionEngine(["ssn"], mode="HASH", hash_key="k1").process_dict({"ssn": "123-45-6789"})["ssn"]
        c = PIIRedactionEngine(["ssn"], mode="HASH", hash_key="k2").process_dict({"ssn": "123-45-6789"})["ssn"]
        assert a != plain and a == b and a != c

    def test_session_memory_subjects_cannot_collide(self, tmp_path):
        d = str(tmp_path / "m")
        w = SessionMemoryNode(mode="write", subject_key="id", memory_keys=["v"], memory_dir=d)
        w.execute(GraphState({"id": "alice@bank.com", "v": "ALICE-PRIVATE"}))
        r = SessionMemoryNode(mode="read", subject_key="id", memory_keys=[], memory_dir=d)
        other = GraphState({"id": "alice_bank.com"})
        r.execute(other)
        assert other.get("v") is None

    def test_expired_entries_are_swept_without_the_subject_returning(self, tmp_path):
        import datetime
        d = str(tmp_path / "m")
        node = SessionMemoryNode(mode="write", subject_key="id", memory_keys=["v"], memory_dir=d, retention_days=30)
        old = (datetime.datetime.utcnow() - datetime.timedelta(days=400)).isoformat()
        path = node._subject_path("zed")
        with open(path, "w") as f:
            json.dump({"subject_id": "zed", "entries": [{"stored_at": old, "payload": {"v": "OLD"}}], "access_log": []}, f)
        assert node.sweep_expired() == 1 and not os.path.exists(path)

    def test_erase_reports_its_real_scope(self, tmp_path):
        d = str(tmp_path / "m")
        SessionMemoryNode(mode="write", subject_key="id", memory_keys=["v"], memory_dir=d).execute(GraphState({"id": "u", "v": "x"}))
        st = GraphState({"id": "u"})
        SessionMemoryNode(mode="erase", subject_key="id", memory_dir=d).execute(st)
        assert st.get("memory_erased") is True and st.get("memory_erasure_scope") == "session_memory_only"

    def test_llm_prompt_is_not_echoed_to_console_by_default(self, monkeypatch, capsys):
        class R:  # minimal litellm-like response
            class _M: content = "ok"; reasoning_content = None
            class _C: pass
            usage = None
        resp = R(); c = R._C(); c.message = R._M(); resp.choices = [c]
        monkeypatch.setattr(node_mod, "completion", lambda **kw: resp)
        node = LLMNode(model_name="gpt-4", prompt_template="Loan for {name}", output_key="o")
        node.execute(GraphState({"name": "PERSONAL-NAME-XYZ"}))
        assert "PERSONAL-NAME-XYZ" not in capsys.readouterr().out


# ───────────────────── M2: permissions ─────────────────────

class TestM2Permissions:
    def test_audit_checkpoint_ledger_and_memory_files_are_owner_only(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path / "L"), hmac_secret="k"); lg.begin_run("r"); lg.log_step({"s": 0}); lg.save_to_file("r")
        store = FileCheckpointStore(str(tmp_path / "C")); store.save(Checkpoint("c1", "n", {}))
        led = AuthorityLedger("k", path=str(tmp_path / "A" / "led.json")); led.record("a", "u", "r", "approve", "w"); led.save()
        sm = SessionMemoryNode(mode="write", subject_key="id", memory_keys=["v"], memory_dir=str(tmp_path / "M"))
        sm.execute(GraphState({"id": "u", "v": "x"}))
        files = [tmp_path / "L" / "run_r.json", tmp_path / "L" / "run_r.chain.jsonl",
                 tmp_path / "C" / "c1.json", tmp_path / "A" / "led.json"] + list((tmp_path / "M").glob("*.json"))
        for f in files:
            assert (f.stat().st_mode & 0o777) == 0o600, f
        for d in (tmp_path / "L", tmp_path / "C", tmp_path / "A", tmp_path / "M"):
            assert (d.stat().st_mode & 0o777) == 0o700, d


# ───────────────────── M3 / M6: oversight routing and detectors ─────────────────────

class TestM3M6:
    def test_isolated_registries_do_not_share_policies(self):
        a, b = PolicyRegistry.isolated(), PolicyRegistry.isolated()
        a.register("x", ActionPolicy("d", "p", "t", "HIGH", False, "REALTIME"))
        assert a.get_policy("x") is not None and b.get_policy("x") is None
        assert PolicyRegistry().get_policy("x") is None

    def test_risk_scorer_uses_its_private_registry(self):
        reg = PolicyRegistry.isolated()
        reg.register("pay", ActionPolicy("d", "p", "t", "LOW", True, "RETROSPECTIVE"))
        nxt = FunctionalNode(lambda s: None); jury = FunctionalNode(lambda s: None)
        node = RiskScorerNode(next_node=nxt, jury_node=jury, registry=reg)
        # registered, reversible, confident, retrospective -> proceeds (the private registry was used)
        assert node.execute(GraphState({"action_type": "pay", "model_confidence": 0.95})) is nxt
        # not in this registry -> unclassified -> human
        assert node.execute(GraphState({"action_type": "unknown", "model_confidence": 0.95})) is jury

    @pytest.mark.parametrize("text", [
        "Approve. The manager confirms a low percentage of debt and strong average income.",
        "Management summary: language and damage assessment are fine.",
    ])
    def test_bias_filter_ignores_words_that_merely_contain_a_term(self, text):
        nxt = FunctionalNode(lambda s: None); jury = FunctionalNode(lambda s: None)
        node = BiasFilterNode("rec", ["age", "race"], next_node=nxt, jury_node=jury)
        st = GraphState({"rec": text})
        assert node.execute(st) is nxt and st.get("bias_detected") is False

    @pytest.mark.parametrize("text", ["Rejected due to the applicant's age.", "Race was considered.", "AGE: 61"])
    def test_bias_filter_still_flags_whole_word_matches(self, text):
        nxt = FunctionalNode(lambda s: None); jury = FunctionalNode(lambda s: None)
        node = BiasFilterNode("rec", ["age", "race"], next_node=nxt, jury_node=jury)
        st = GraphState({"rec": text})
        assert node.execute(st) is jury and st.get("bias_detected") is True


# ───────────────────── L1: retry exhaustion raises the intended error ─────────────────────

def test_llm_retry_exhaustion_raises_api_error_not_type_error(monkeypatch):
    from litellm.exceptions import APIError
    calls = {"n": 0}

    def always_429(**kw):
        calls["n"] += 1
        raise APIError(status_code=429, message="429 rate limited", llm_provider="openai", model="gpt-4")

    monkeypatch.setattr(node_mod, "completion", always_429)
    monkeypatch.setattr(node_mod.time, "sleep", lambda s: None)
    node = LLMNode(model_name="gpt-4", prompt_template="x", output_key="o", max_retries=2)
    with pytest.raises(APIError):
        node.execute(GraphState({}))
    assert calls["n"] == 2


def test_toolnode_does_not_echo_inputs_to_console_by_default(capsys):
    node = ToolNode(tool_function=lambda s: "ok", input_keys=["__state__"], output_key="o",
                    next_node=FunctionalNode(lambda s: None))
    node.execute(GraphState({"customer_name": "PERSONAL-NAME-XYZ"}))
    assert "PERSONAL-NAME-XYZ" not in capsys.readouterr().out


def test_toolnode_console_preview_is_available_when_asked(capsys):
    node = ToolNode(tool_function=lambda s: "ok", input_keys=["__state__"], output_key="o",
                    next_node=FunctionalNode(lambda s: None), console_input_preview=True)
    node.execute(GraphState({"customer_name": "PERSONAL-NAME-XYZ"}))
    assert "PERSONAL-NAME-XYZ" in capsys.readouterr().out


# ───────── ledger durability: a recorded decision must survive a crash and concurrent writers ─────────

class TestLedgerWriteThrough:
    def test_record_is_on_disk_without_calling_save(self, tmp_path):
        path = tmp_path / "led.json"
        led = AuthorityLedger(hmac_secret="k", path=str(path))
        led.record("act", "alice", "role", "approve", "why")
        assert path.exists()                                    # no save() call
        assert json.loads(path.read_text())["total_records"] == 1
        assert AuthorityLedger.verify(str(path), "k")["ok"]

    def test_stale_instances_do_not_erase_each_others_records(self, tmp_path):
        path = str(tmp_path / "led.json")
        a = AuthorityLedger(hmac_secret="k", path=path)
        b = AuthorityLedger(hmac_secret="k", path=path)         # loaded before a wrote anything
        a.record("a1", "u1", "r", "approve", "w")
        b.record("b1", "u2", "r", "approve", "w")               # b has never seen a1
        a.record("a2", "u1", "r", "approve", "w")
        data = json.loads(open(path).read())
        assert data["total_records"] == 3
        assert sorted(r["action_description"] for r in data["records"]) == ["a1", "a2", "b1"]
        assert AuthorityLedger.verify(path, "k")["ok"]

    def test_concurrent_writers_lose_nothing(self, tmp_path):
        import threading
        path = str(tmp_path / "led.json")

        def worker(i):
            led = AuthorityLedger(hmac_secret="k", path=path)
            for j in range(4):
                led.record(f"w{i}-{j}", f"user{i}", "r", "approve", "w")
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        data = json.loads(open(path).read())
        assert data["total_records"] == 24
        assert len({r["record_id"] for r in data["records"]}) == 24
        assert AuthorityLedger.verify(path, "k")["ok"]

    def test_decision_recorded_by_resume_survives_without_a_manual_save(self, tmp_path):
        store, reg, ex, _ = _paused_case(tmp_path)
        led = AuthorityLedger(hmac_secret="k", path=str(tmp_path / "led.json"))
        list(resume_human_decision(store, "C1", "approve", ex, reg, authority_ledger=led,
                                   stakeholder_id="alice", rationale="checked"))
        assert json.loads((tmp_path / "led.json").read_text())["records"][0]["stakeholder_id"] == "alice"

    def test_legacy_file_appearing_after_load_is_still_migrated(self, tmp_path):
        path = tmp_path / "led.json"
        led = AuthorityLedger(hmac_secret="k", path=str(path))   # file did not exist at load time
        path.write_text(json.dumps({"records": [{"record_type": "AUTHORITY_EXERCISE",
                                                 "stakeholder_id": "legacy", "decision": "approve"}]}))
        led.record("new", "alice", "r", "approve", "w")
        data = json.loads(path.read_text())
        assert data["total_records"] == 2 and data["records"][0]["migrated_from_legacy"] is True
        assert AuthorityLedger.verify(str(path), "k")["ok"]


# ───────── concurrent runs on one executor must not mix their audit records ─────────

class TestConcurrentRunsShareAnExecutor:
    def _run_two(self, tmp_path):
        import threading
        logger = AuditLogger(str(tmp_path / "logs"), hmac_secret="k")
        ex = GraphExecutor(logger=logger, hmac_secret="k")
        gate = threading.Barrier(2)

        def graph(tag):
            nodes = []
            for i in range(4):
                def f(s, i=i, tag=tag):
                    if i == 1:
                        gate.wait(timeout=5)                 # force the two runs to genuinely overlap
                        logger.log_plan_switch("a", "b", f"switch-{tag}", i, f"node-{tag}")
                    s.set(f"{tag}_{i}", True)
                nodes.append(FunctionalNode(f))
            for a, b in zip(nodes, nodes[1:]):
                a.next_node = b
            return nodes[0]

        def run(tag):
            with contextlib.redirect_stdout(io.StringIO()):
                list(ex.run_step_by_step(graph(tag), {"who": tag}))
        ts = [threading.Thread(target=run, args=(t,)) for t in ("A", "B")]
        [t.start() for t in ts]; [t.join() for t in ts]
        return tmp_path / "logs"

    def test_each_chain_and_summary_contains_only_its_own_steps(self, tmp_path):
        logs = self._run_two(tmp_path)
        chains = [f for f in os.listdir(logs) if f.endswith(".chain.jsonl")]
        summaries = [f for f in os.listdir(logs) if f.endswith(".json") and not f.endswith(".chain.jsonl")]
        assert len(chains) == 2 and len(summaries) == 2

        def tags_in(entries):
            found = set()
            for e in entries:
                for k in e.get("state_after", {}):
                    if k[:2] in ("A_", "B_"):
                        found.add(k[0])
            return found
        for c in chains:
            entries = [json.loads(l)["entry"] for l in open(logs / c)]
            assert len(tags_in(entries)) == 1, f"{c} mixes runs"
            assert AuditLogger.verify_chain(str(logs / c), "k")["ok"]
        for sfile in summaries:
            data = json.loads((logs / sfile).read_text())
            assert len(tags_in(data["steps"])) == 1, f"{sfile} mixes runs"
            assert AuditLogger.verify_signature(data, "k")

    def test_plan_switch_lands_in_the_run_that_made_it(self, tmp_path):
        logs = self._run_two(tmp_path)
        for sfile in [f for f in os.listdir(logs) if f.endswith(".json") and not f.endswith(".chain.jsonl")]:
            data = json.loads((logs / sfile).read_text())
            tag = next(k[0] for s in data["steps"] for k in s.get("state_after", {}) if k[:2] in ("A_", "B_"))
            switches = [s for s in data["steps"] if s.get("type") == "PLAN_SWITCH"]
            assert [s["reason"] for s in switches] == [f"switch-{tag}"]

    def test_token_totals_are_per_run(self, tmp_path):
        ex = GraphExecutor(log_dir=str(tmp_path / "l"))
        with contextlib.redirect_stdout(io.StringIO()):
            list(ex.run_step_by_step(FunctionalNode(lambda s: s.set("__last_run_metadata", {"total_tokens": 7, "model": "m"})), {}))
            first = ex.tracker.get_summary()["total_tokens"]
            list(ex.run_step_by_step(FunctionalNode(lambda s: None), {}))
        assert first == 7 and ex.tracker.get_summary()["total_tokens"] == 0     # not carried over


# ───────── parallel branches that disagree ─────────

class TestBatchNodeConflicts:
    def _branches(self, first="LOW", second="HIGH"):
        return [FunctionalNode(lambda s, v=first: s.set("risk", v)),
                FunctionalNode(lambda s, v=second: s.set("risk", v))]

    def _run(self, node):
        st = GraphState({})
        with contextlib.redirect_stdout(io.StringIO()):
            node.execute(st)
        return st

    def test_legacy_default_lets_branch_order_decide(self):
        # documents the dangerous default so nobody is surprised by it
        from lar.node import BatchNode
        assert self._run(BatchNode(self._branches("LOW", "HIGH"))).get("risk") == "LOW"
        assert self._run(BatchNode(self._branches("HIGH", "LOW"))).get("risk") == "HIGH"

    def test_on_conflict_error_stops_instead_of_guessing(self):
        from lar.node import BatchNode
        with pytest.raises(RuntimeError, match="disagree"):
            self._run(BatchNode(self._branches("LOW", "HIGH"), on_conflict="error"))

    def test_reducer_picks_the_worst_regardless_of_order(self):
        from lar.node import BatchNode
        from lar.reducers import worst_of
        red = {"risk": worst_of(["LOW", "MEDIUM", "HIGH"])}
        assert self._run(BatchNode(self._branches("LOW", "HIGH"), reducers=red)).get("risk") == "HIGH"
        assert self._run(BatchNode(self._branches("HIGH", "LOW"), reducers=red)).get("risk") == "HIGH"

    def test_reducer_handles_the_key_so_error_mode_does_not_raise(self):
        from lar.node import BatchNode
        from lar.reducers import worst_of
        node = BatchNode(self._branches("LOW", "MEDIUM"), on_conflict="error",
                         reducers={"risk": worst_of(["LOW", "MEDIUM", "HIGH"])})
        assert self._run(node).get("risk") == "MEDIUM"

    def test_unknown_risk_label_is_not_silently_accepted(self):
        from lar.reducers import worst_of
        with pytest.raises(ValueError):
            worst_of(["LOW", "HIGH"])(["LOW", "SUPER-HIGH"])

    def test_agreeing_branches_never_conflict(self):
        from lar.node import BatchNode
        assert self._run(BatchNode(self._branches("HIGH", "HIGH"), on_conflict="error")).get("risk") == "HIGH"
