"""ADR-0029: the compatibility layer, after the rename from gatekit (0.17.0).

Every contract the name is part of accepts both names; everything a user sees
and everything new projects get says gatebound; projects made by gatekit keep
working.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import (approval, contract, design, doctor, hosts, jobs, ledger,  # noqa: E402
                     migrate, names, paths, spec)
from gatebound.gates import bash as bash_gate  # noqa: E402
from gatebound.gates import prompt as prompt_gate  # noqa: E402
from gatebound.gates import question as question_gate  # noqa: E402
from gatebound.gates import spawn as spawn_gate  # noqa: E402
from gatebound.gates import stop as stop_gate  # noqa: E402
from gatebound.gates import write as write_gate  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "spec"
GATES = pathlib.Path(__file__).resolve().parents[1] / "gatebound" / "gates"
PY = sys.executable


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        self._env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    @contextlib.contextmanager
    def renamed(self):
        """Pin the released names: gatebound current, gatekit legacy."""
        saved = (names.CURRENT, names.FUTURE, names.LEGACY)
        names.CURRENT, names.FUTURE, names.LEGACY = "gatebound", "gatebound", ("gatekit",)
        try:
            yield
        finally:
            names.CURRENT, names.FUTURE, names.LEGACY = saved

    def fake_home(self) -> pathlib.Path:
        home = self.root / "_home"
        (home / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        os.environ["CODEX_HOME"] = str(home / ".codex")
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        return home


# ------------------------------------------------------------------ names
class TestNames(unittest.TestCase):
    def test_current_name_is_gatebound_and_gatekit_is_legacy(self) -> None:
        self.assertEqual(names.CURRENT, "gatebound")
        self.assertEqual(names.FUTURE, "gatebound")
        self.assertEqual(names.LEGACY, ("gatekit",))
        self.assertEqual(names.all_names(), ("gatebound", "gatekit"))

    def test_new_projects_get_the_new_names(self) -> None:
        self.assertEqual(names.state_dirname(), ".gatebound")
        self.assertEqual(names.state_dirnames(), (".gatebound", ".gatekit"))
        self.assertEqual(names.fence("task"), "gatebound-task")
        self.assertEqual(names.agents_markers()[1], "<!-- gatebound:end -->")
        self.assertEqual(names.launcher_names()[:2], ("gatebound.py", "gatebound"))

    def test_fence_aliases(self) -> None:
        self.assertEqual(set(names.fence_names("gatebound-task")),
                         {"gatebound-task", "gatekit-task"})
        self.assertEqual(set(names.fence_names("gatekit-scope")),
                         {"gatebound-scope", "gatekit-scope"})
        self.assertEqual(names.fence_names("python"), ("python",))
        self.assertEqual(names.fence("criterion"), "gatebound-criterion")

    def test_env_names_current_first(self) -> None:
        self.assertEqual(names.env_names("TASK_ID"), ("GATEBOUND_TASK_ID", "GATEKIT_TASK_ID"))


# ------------------------------------------------------------------ 1. fences
def _fenced(prefix: str, kind: str, body: dict) -> str:
    return "```%s-%s\n%s\n```\n" % (prefix, kind, json.dumps(body))


class TestFenceAliases(Temp):
    TASK = {"id": "t1", "title": "T", "write_scope": ["src/**"], "instruction": "x",
            "gates": [{"name": "g", "argv": [PY, "-c", "pass"]}], "depends_on": [], "round": 1}

    def test_spec_parse_fences_reads_both_prefixes(self) -> None:
        for prefix in ("gatebound", "gatekit"):
            text = _fenced(prefix, "task", self.TASK)
            self.assertEqual(spec.parse_fences(text, "gatebound-task"), [self.TASK], prefix)
            detailed = spec._parse_fences_detailed(text, "gatebound-discovery")
            self.assertEqual(detailed, [])
            disc = spec._parse_fences_detailed(_fenced(prefix, "discovery", {"a": 1}),
                                               "gatebound-discovery")
            self.assertEqual(disc[0][1], {"a": 1})

    def test_contract_derive_reads_gatekit_criterion_and_budget(self) -> None:
        (self.root / ".gatebound").mkdir()
        (self.root / "spec").mkdir()
        text = (_fenced("gatekit", "criterion", {"id": "c1", "argv": [PY, "-c", "pass"]})
                + _fenced("gatebound", "criterion", {"id": "c2", "argv": [PY, "-c", "pass"]})
                + _fenced("gatekit", "budget", {"total_budget_s": 60}))
        (self.root / "spec" / "05-gate.md").write_text(text, encoding="utf-8")
        derived = contract.derive(self.root)
        self.assertEqual([c["id"] for c in derived["criteria"]], ["c1", "c2"])

    def test_jobs_and_design_read_gatekit_tasks(self) -> None:
        (self.root / "spec").mkdir()
        (self.root / "spec" / "04-tasks.md").write_text(
            _fenced("gatekit", "task", self.TASK), encoding="utf-8")
        self.assertEqual([t["id"] for t in jobs.load_tasks(self.root)], ["t1"])
        self.assertEqual(contract.parse_fences(_fenced("gatekit", "task", self.TASK),
                                               "gatebound-task"), [self.TASK])

    def test_spawn_scope_fence_alias(self) -> None:
        body = '{"write_scope": ["src/**"], "stop_when": "done"}'
        for prefix in ("gatebound", "gatekit"):
            text = "do it\n```%s-scope\n%s\n```\n" % (prefix, body)
            self.assertEqual(spawn_gate.extract_fence(text).strip(), body, prefix)

    def test_spec_validate_same_verdict_with_either_prefix(self) -> None:
        old = self.root / "old"
        new = self.root / "new"
        shutil.copytree(FIXTURES / "valid-en", old)
        shutil.copytree(FIXTURES / "valid-en", new)
        for path in (new / "spec").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("```gatebound-", "```gatekit-"), encoding="utf-8")
        self.assertIn("```gatekit-task", (new / "spec" / "04-tasks.md").read_text(encoding="utf-8"))
        a, b = spec.validate(old), spec.validate(new)
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(sorted(f["message"] for f in a["findings"]),
                         sorted(f["message"] for f in b["findings"]))


# ------------------------------------------------------------------ 2. state dir
class TestStateDir(Temp):
    def test_neither_gives_current_name(self) -> None:
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_a_new_project_gets_gatebound_and_a_gatekit_one_keeps_its_dir(self) -> None:
        from gatebound import config
        config.save(self.root, config.load(self.root))  # what /gatebound:setup does
        self.assertTrue((self.root / ".gatebound" / "config.json").is_file())
        self.assertFalse((self.root / ".gatekit").exists())
        legacy = self.root / "legacy"
        (legacy / ".gatekit").mkdir(parents=True)
        config.save(legacy, config.load(legacy))
        self.assertTrue((legacy / ".gatekit" / "config.json").is_file())
        self.assertFalse((legacy / ".gatebound").exists())

    def test_current_only(self) -> None:
        (self.root / ".gatebound").mkdir()
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_legacy_only(self) -> None:
        (self.root / ".gatekit").mkdir()
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatekit")
        self.assertEqual(paths.approvals_file(self.root), self.root / ".gatekit" / "approvals.json")
        deep = self.root / "a" / "b"
        deep.mkdir(parents=True)
        self.assertEqual(paths.project_root(str(deep)), self.root)

    def test_both_prefers_the_current_name(self) -> None:
        # ADR-0029 amendment: a usable current-named dir always wins
        (self.root / ".gatebound").mkdir()
        (self.root / ".gatekit" / "runs").mkdir(parents=True)
        (self.root / ".gatekit" / "approvals.json").write_text("{}", encoding="utf-8")
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")
        (self.root / ".gatebound" / "approvals.json").write_text("{}", encoding="utf-8")
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_empty_second_dir_does_not_capture_state(self) -> None:
        # review: an agent writing .gatekit/config.json must not move the
        # hooks away from the ledgers in .gatebound/.
        (self.root / ".gatebound" / "runs").mkdir(parents=True)
        (self.root / ".gatekit").mkdir()
        (self.root / ".gatekit" / "config.json").write_text("{}", encoding="utf-8")
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_both_empty_prefers_current_name(self) -> None:
        (self.root / ".gatebound").mkdir()
        (self.root / ".gatekit").mkdir()
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_gatekit_project_is_governed(self) -> None:
        (self.root / ".gatekit").mkdir()
        event = {"session_id": "s", "cwd": str(self.root), "prompt": "/gatebound:build"}
        prompt_gate.handle(event)
        self.assertTrue((self.root / ".gatekit" / "runs" / "s.json").is_file())
        self.assertFalse((self.root / ".gatebound").exists())


class TestProtectedStateBothNames(Temp):
    def setUp(self) -> None:
        super().setUp()
        (self.root / ".gatekit").mkdir()
        (self.root / "spec").mkdir()

    def write(self, rel: str):
        return write_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Write",
                                  "tool_input": {"file_path": str(self.root / rel)}})

    def bash(self, command: str):
        return bash_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Bash",
                                 "tool_input": {"command": command}})

    def denied(self, result) -> bool:
        return bool(result) and result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_write_gate_protects_gatekit(self) -> None:
        for rel in (".gatekit/approvals.json", ".gatekit/contract.json",
                    ".gatekit/runs/s.json", ".gatebound/approvals.json"):
            self.assertTrue(self.denied(self.write(rel)), rel)
        for rel in (".gatekit/config.json", ".gatekit/eval/driver.py"):
            self.assertIsNone(self.write(rel), rel)

    def test_protected_state_reports_the_matched_dir(self) -> None:
        self.assertEqual(write_gate.protected_state(self.root, ".gatekit/approvals.json"),
                         ".gatekit/approvals.json")
        self.assertEqual(write_gate.protected_state(self.root, ".GATEBOUND/contract.json"),
                         ".gatebound/contract.json")

    def test_bash_gate_protects_gatekit(self) -> None:
        for command in ("echo {} > .gatekit/approvals.json", "rm -rf .gatekit",
                        "cp x.json .gatekit/", "eval \"$(cat x)\" .gatekit/contract.json"):
            self.assertTrue(self.denied(self.bash(command)), command)
        self.assertIsNone(self.bash("echo {} > .gatekit/config.json"))

    def test_spec_allowlist_covers_gatekit(self) -> None:
        self.assertTrue(write_gate.in_allowlist(".gatekit/config.json"))
        self.assertTrue(write_gate.in_allowlist(".gatebound/config.json"))

    def test_evaluator_scratch_under_gatekit(self) -> None:
        job = paths.jobs_dir(self.root) / "j1" / "evaluate"
        job.mkdir(parents=True)
        (job / "task.json").write_text(json.dumps({"id": "evaluate", "write_scope": "read-only"}),
                                       encoding="utf-8")
        os.environ["GATEKIT_TASK_ID"] = "evaluate"
        os.environ["GATEKIT_JOB_ID"] = "j1"
        os.environ.pop("GATEBOUND_TASK_ID", None)
        os.environ.pop("GATEBOUND_JOB_ID", None)
        self.assertIsNone(self.write(".gatekit/eval/shot.png"))
        self.assertTrue(self.denied(self.write("src/app.py")))


class TestMessagesNameTheDirInUse(Temp):
    """Review: messages hardcoded .gatebound/ and GATEBOUND_TASK_ID, so a
    gatekit project was told about a directory and a variable it lacks."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / ".gatekit").mkdir()
        (self.root / "spec").mkdir()

    def reason(self, result) -> str:
        return result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_write_gate_deny_names_gatekit(self) -> None:
        result = write_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Write",
                                    "tool_input": {"file_path": str(self.root / ".gatekit/approvals.json")}})
        reason = self.reason(result)
        self.assertIn("Everything under .gatekit/ except", reason)
        self.assertNotIn(".gatebound/", reason)

    def test_doctor_axis_5_names_gatekit(self) -> None:
        axis = doctor.axis_contract_freshness(self.root)
        self.assertIn(".gatekit/contract.json", axis["detail"])
        self.assertNotIn(".gatebound", axis["detail"])
        (self.root / "spec" / "05-gate.md").write_text(
            _fenced("gatekit", "criterion", {"id": "c1", "argv": [PY, "-c", "pass"]}),
            encoding="utf-8")
        contract.derive(self.root)
        axis = doctor.axis_contract_freshness(self.root)
        self.assertEqual(axis["verdict"], "ok")
        self.assertIn(".gatekit/contract.json", axis["detail"])

    def test_doctor_axis_3_names_gatekit(self) -> None:
        (self.root / ".gatekit" / "config.json").write_text("{broken", encoding="utf-8")
        axis = doctor.axis_project_state(self.root)
        self.assertNotIn(".gatebound", axis["detail"] + axis["fix"])

    def test_jobs_messages_name_gatekit(self) -> None:
        self.assertIn(".gatekit/jobs/", jobs.status(self.root)["detail"])

    def test_worker_approve_deny_names_the_variable_set(self) -> None:
        os.environ.pop("GATEBOUND_TASK_ID", None)
        os.environ["GATEKIT_TASK_ID"] = "t1"
        result = bash_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Bash",
                                   "tool_input": {"command": "python3 bin/gatebound.py approve spec/05-gate.md"}})
        reason = self.reason(result)
        self.assertIn("GATEKIT_TASK_ID=t1", reason)
        self.assertNotIn("GATEBOUND_TASK_ID", reason)


# ------------------------------------------------------------------ 3. argv aliases
class TestArgvAliases(Temp):
    def setUp(self) -> None:
        super().setUp()
        self.tokens = str(paths.plugin_root() / "gatebound" / "gates" / "tokens.py")
        self.launcher = str(paths.plugin_root() / "bin" / "gatebound.py")

    def old_checkout(self, *tail: str) -> str:
        # A deleted checkout under someone's home, built at run time so no
        # personal path is committed.
        return os.path.join(self.root.anchor, "Users", "someone", "Projects", "gatebound",
                            "plugin", *tail)

    def test_study_gallery_shapes(self) -> None:
        cases = {
            "${CLAUDE_PLUGIN_ROOT}/gatebound/gates/tokens.py": self.tokens,
            "${CLAUDE_PLUGIN_ROOT}/gatekit/gates/tokens.py": self.tokens,
            "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py": self.launcher,
            "${CLAUDE_PLUGIN_ROOT}/bin/gatekit.py": self.launcher,
            self.old_checkout("gatebound", "gates", "tokens.py"): self.tokens,
            self.old_checkout("gatekit", "gates", "tokens.py"): self.tokens,
            self.old_checkout("bin", "gatebound.py"): self.launcher,
            "C:\\Users\\someone\\cache\\gatebound\\0.16.5\\gatebound\\gates\\tokens.py": self.tokens,
            # what real gatekit projects carry: a gatekit checkout or plugin cache
            os.path.join(self.root.anchor, "Users", "someone", "Projects", "gatekit",
                         "plugin", "gatekit", "gates", "tokens.py"): self.tokens,
            os.path.join(self.root.anchor, "Users", "someone", "Projects", "gatekit",
                         "plugin", "bin", "gatekit.py"): self.launcher,
            "C:\\Users\\someone\\cache\\gatekit\\0.16.5\\gatekit\\gates\\tokens.py": self.tokens,
        }
        for raw, want in cases.items():
            if raw.startswith("C:") and os.name != "nt":
                continue
            out = paths.expand_argv(["python3", raw, "--lang", "ko", "src/**"])
            self.assertEqual(os.path.normcase(out[1]), os.path.normcase(want), raw)
            self.assertEqual(out[2:], ["--lang", "ko", "src/**"])

    def test_unknown_gate_or_existing_path_is_left_alone(self) -> None:
        missing = self.old_checkout("gatebound", "gates", "no_such_gate.py")
        self.assertEqual(paths.expand_argv(["python3", missing])[1], missing)
        real = self.root / "gatebound" / "gates" / "tokens.py"
        real.parent.mkdir(parents=True)
        real.write_text("print(1)\n", encoding="utf-8")
        self.assertEqual(paths.expand_argv(["python3", str(real)])[1], str(real))
        self.assertEqual(paths.expand_argv(["python3", "gatebound/gates/tokens.py"])[1],
                         "gatebound/gates/tokens.py")
        self.assertEqual(paths.expand_argv(["python3", self.old_checkout("tests", "x.py")])[1],
                         self.old_checkout("tests", "x.py"))

    def test_criterion_with_dead_checkout_path_runs(self) -> None:
        (self.root / ".gatebound").mkdir()
        (self.root / "spec").mkdir()
        dead = self.old_checkout("bin", "gatebound.py")
        crit = {"id": "cli", "argv": [PY, dead, "lang", "hello"], "timeout_s": 60}
        (self.root / "spec" / "05-gate.md").write_text(_fenced("gatebound", "criterion", crit),
                                                       encoding="utf-8")
        derived = contract.derive(self.root)
        self.assertEqual(derived["criteria"][0]["argv"][1], dead)  # pinned as written
        result = contract.execute(self.root)
        self.assertEqual(result["verdict"], "ok", result)


# ------------------------------------------------------------------ 4. env
class TestEnv(Temp):
    def test_task_id_reads_current_then_other(self) -> None:
        env = {"GATEKIT_TASK_ID": "b"}
        self.assertEqual(names.task_id(env), "b")
        env["GATEBOUND_TASK_ID"] = "k"
        self.assertEqual(names.task_id(env), "k")
        self.assertIsNone(names.job_id({}))
        self.assertEqual(names.job_id({"GATEKIT_JOB_ID": "j"}), "j")

    def test_worker_env_sets_both(self) -> None:
        self.assertEqual(names.worker_env("t", "j"), {
            "GATEBOUND_TASK_ID": "t", "GATEKIT_TASK_ID": "t",
            "GATEBOUND_JOB_ID": "j", "GATEKIT_JOB_ID": "j"})

    def test_spawned_worker_gets_both_and_no_leak(self) -> None:
        (self.root / ".gatebound").mkdir()
        (self.root / "spec").mkdir()
        probe = self.root / "probe.py"
        probe.write_text(
            "import os,sys\n"
            "ok = (os.environ.get('GATEBOUND_TASK_ID') == 't1' and os.environ.get('GATEKIT_TASK_ID') == 't1'\n"
            "      and os.environ.get('GATEKIT_JOB_ID') == os.environ.get('GATEBOUND_JOB_ID')\n"
            "      and 'GATEKIT_LEAK' not in os.environ and 'GATEBOUND_LEAK' not in os.environ)\n"
            "sys.exit(0 if ok else 3)\n", encoding="utf-8")
        cfg = {"worker": {"default": "fake",
                          "backends": {"fake": {"argv": [PY, str(probe)], "enabled": True}}},
               "build": {"max_retries": 0, "parallel": 1, "task_timeout_s": 60,
                         "execution": "worker"}}
        (self.root / ".gatebound" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        task = dict(TestFenceAliases.TASK, gates=[{"name": "g", "argv": [PY, "-c", "pass"]}])
        (self.root / "spec" / "04-tasks.md").write_text(_fenced("gatebound", "task", task),
                                                        encoding="utf-8")
        os.environ["GATEKIT_LEAK"] = "x"
        os.environ["GATEBOUND_LEAK"] = "x"
        job = jobs.start(self.root, no_preflight=True)
        status = json.loads((paths.jobs_dir(self.root) / job["job_id"] / "tasks" / "t1"
                             / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["exit"], 0, status)

    def test_worker_under_gatekit_env_never_approves(self) -> None:
        (self.root / ".gatebound").mkdir()
        os.environ.pop("GATEBOUND_TASK_ID", None)
        os.environ["GATEKIT_TASK_ID"] = "t1"
        with self.assertRaises(PermissionError) as caught:
            approval.approve(self.root, "spec/05-gate.md")
        self.assertIn("GATEKIT_TASK_ID=t1", str(caught.exception))


# ------------------------------------------------------------------ 5. approve guard / arming
class TestApproveAndArming(Temp):
    def test_approve_guard_recognises_gatekit_launcher(self) -> None:
        for command in ('python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatekit.py" approve spec/05-gate.md',
                        "gatekit approve spec/05-gate.md",
                        "python3 -m gatekit approve spec/05-gate.md",
                        "env -u GATEKIT_TASK_ID python3 bin/gatekit.py approve x",
                        "bash -c 'python3 gatekit.py approve x'",
                        "python3 gatebound.py approve spec/05-gate.md"):
            self.assertTrue(bash_gate.invokes_gatebound_approve(command), command)
        self.assertFalse(bash_gate.invokes_gatebound_approve("python3 bin/gatekit.py approve check x"))
        self.assertTrue(bash_gate._APPROVE_RE.search("x/gatekit.py' approve spec"))

    def test_bash_gate_denies_gatekit_approve_in_worker(self) -> None:
        (self.root / ".gatebound").mkdir()
        os.environ.pop("GATEBOUND_TASK_ID", None)
        os.environ["GATEKIT_TASK_ID"] = "t1"
        result = bash_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Bash",
                                   "tool_input": {"command": "python3 bin/gatekit.py approve spec/05-gate.md"}})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gatekit_commands_arm_the_stop_gate(self) -> None:
        for text in ("/gatekit:build", "<command-name>/gatekit:build</command-name>",
                     "# /gatekit:verify", "$gatekit-build go", "/gatebound:build"):
            self.assertIn(prompt_gate.detect_command(text), ("build", "verify"), text)
        self.assertEqual(prompt_gate.language_signal("$gatekit-build 시작해"), " 시작해")
        (self.root / ".gatebound").mkdir()
        prompt_gate.handle({"session_id": "s", "cwd": str(self.root),
                            "prompt": "<command-name>/gatekit:build</command-name>"})
        self.assertEqual(ledger.Ledger.load(self.root, "s").data["active_pipeline"], "build")


# ------------------------------------------------------------------ 6. AGENTS.md
class TestAgentsMarkers(Temp):
    def test_replaces_either_marker_pair(self) -> None:
        proot = paths.plugin_root()
        for name in ("gatebound", "gatekit"):
            begin, end = names.agents_markers(name)
            existing = "# Mine\n\n%s\nold block\n%s\n\ntail\n" % (begin, end)
            merged = hosts.merged_agents_md(existing, proot)
            self.assertNotIn("old block", merged, name)
            self.assertIn("# Mine", merged)
            self.assertIn("tail", merged)
            self.assertEqual(merged.count(":begin"), 1, name)
            self.assertIn(hosts.BLOCK_BEGIN, merged)
        self.assertEqual(hosts.BLOCK_BEGIN, names.agents_markers()[0])

    def test_blocks_under_both_names_collapse_to_one(self) -> None:
        new, old = names.agents_markers("gatebound"), names.agents_markers("gatekit")
        existing = "A\n%s\nx\n%s\nB\n%s\ny\n%s\nC\n" % (old[0], old[1], new[0], new[1])
        merged = hosts.merged_agents_md(existing, paths.plugin_root())
        self.assertEqual(merged.count(":begin"), 1)
        self.assertEqual(merged.count(":end -->"), 1)
        for keep in ("A\n", "B\n", "C\n"):
            self.assertIn(keep, merged)
        self.assertNotIn("\nx\n", merged)
        self.assertNotIn("\ny\n", merged)


# ------------------------------------------------------------------ 7. doctor
class TestDoctorBothNames(Temp):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.fake_home()
        (self.root / ".gatebound").mkdir()

    def install(self, *keys: str, enabled=None) -> None:
        table = {k: {"version": "0.1"} for k in keys}
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": table}), encoding="utf-8")
        enabled = keys if enabled is None else enabled
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {k: True for k in enabled}}), encoding="utf-8")

    def test_single_plugin_still_ok(self) -> None:
        self.install("gatebound@gatebound")
        self.assertEqual(doctor.axis_hooks_registered(self.root)["verdict"], "ok")

    def test_both_plugins_enabled_fails(self) -> None:
        self.install("gatebound@gatebound", "gatekit@gatekit")
        axis = doctor.axis_hooks_registered(self.root)
        self.assertEqual(axis["verdict"], "fail")
        self.assertIn("gatekit@gatekit", axis["detail"])
        self.assertIn("/plugin disable", axis["fix"])

    def test_both_enabled_fails_even_when_this_plugin_was_seen_running(self) -> None:
        # The new plugin's hooks run (ADR-0032 evidence), yet the old one gates
        # the same session too: that is still a failure, not "ok".
        self.install("gatebound@gatebound", "gatekit@gatekit")
        runs = self.root / ".gatebound" / "runs"
        runs.mkdir(parents=True)
        (runs / "s1.json").write_text(json.dumps({
            "session_id": "s1", "hook_root": str(paths.plugin_root()),
            "hook_seen_at": "2026-10-09T09:00:00+00:00"}), encoding="utf-8")
        axis = doctor.axis_hooks_registered(self.root)
        self.assertEqual(axis["verdict"], "fail")
        self.assertIn("/plugin disable gatekit@gatekit", axis["fix"])

    def test_both_enabled_in_project_settings_fails(self) -> None:
        self.install("gatebound@gatebound", "gatekit@gatekit", enabled=("gatebound@gatebound",))
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {"gatekit@gatekit": True}}), encoding="utf-8")
        self.assertEqual(doctor.axis_hooks_registered(self.root)["verdict"], "fail")

    def test_installed_but_disabled_second_plugin_is_not_a_conflict(self) -> None:
        self.install("gatebound@gatebound", "gatekit@gatekit", enabled=("gatebound@gatebound",))
        self.assertEqual(doctor.axis_hooks_registered(self.root)["verdict"], "ok")

    def test_both_in_codex_cache_fails(self) -> None:
        self.install("gatebound@gatebound")
        for name in ("gatebound", "gatekit"):
            (self.home / ".codex" / "plugins" / "cache" / name / name / "0.1" / "hooks").mkdir(parents=True)
        axis = doctor.axis_hooks_registered(self.root)
        self.assertEqual(axis["verdict"], "fail")
        self.assertIn("Codex", axis["detail"])

    def test_both_state_dirs_fail_axis_3(self) -> None:
        (self.root / ".gatekit").mkdir()
        axis = doctor.axis_project_state(self.root)
        self.assertEqual(axis["verdict"], "fail")
        self.assertIn(".gatekit", axis["detail"])
        self.assertIn("migrate", axis["fix"])

    def test_gatekit_dir_alone_is_ok(self) -> None:
        (self.root / ".gatebound").rmdir()
        (self.root / ".gatekit").mkdir()
        self.assertEqual(doctor.axis_project_state(self.root)["verdict"], "ok")


# ------------------------------------------------------------------ 8. coexistence
class TestCoexistence(Temp):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.fake_home()
        (self.root / ".gatekit").mkdir()
        (self.root / "spec").mkdir()
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"gatekit@gatekit": True, "gatebound@gatebound": True}}),
            encoding="utf-8")
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": {"gatekit@gatekit": {}, "gatebound@gatebound": {}}}),
            encoding="utf-8")
        # ADR-0029 amendment: the legacy plugin's cache directory must exist
        (self.home / ".claude" / "plugins" / "cache" / "gatekit" / "gatekit").mkdir(parents=True)
        crit = {"id": "bad", "argv": [PY, "-c", "raise SystemExit(1)"], "timeout_s": 20}
        (self.root / "spec" / "05-gate.md").write_text(_fenced("gatekit", "criterion", crit),
                                                       encoding="utf-8")
        contract.derive(self.root)
        approval.approve(self.root, "spec/05-gate.md")
        led = ledger.Ledger.load(self.root, "s")
        led.data["active_pipeline"] = "build"
        led.save()

    def stop(self):
        return stop_gate.handle({"session_id": "s", "cwd": str(self.root), "hook_event_name": "Stop"})

    def ask(self):
        return question_gate.handle({"session_id": "s", "cwd": str(self.root),
                                     "tool_name": "AskUserQuestion", "tool_input": {}})

    def test_inert_without_a_legacy_name(self) -> None:
        saved = names.LEGACY
        names.LEGACY = ()
        try:
            self.assertEqual(names.legacy_plugin_enabled(self.root), [])
        finally:
            names.LEGACY = saved

    def test_released_names_stand_down_without_pinning(self) -> None:
        self.assertEqual(names.legacy_plugin_enabled(self.root), ["gatekit@gatekit"])

    def test_after_rename_new_plugin_stands_down(self) -> None:
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), ["gatekit@gatekit"])
            # the snapshot is taken at the session's first prompt (amendment)
            out = prompt_gate.handle({"session_id": "s", "cwd": str(self.root), "prompt": "hi"})
            context = json.dumps(out)
            self.assertIn("gatekit@gatekit", context)
            self.assertIsNone(self.stop())
            before = ledger.Ledger.load(self.root, "s").data["questions"]["asked"]
            self.assertIsNone(self.ask())
            self.assertEqual(ledger.Ledger.load(self.root, "s").data["questions"]["asked"], before)
            again = json.dumps(prompt_gate.handle({"session_id": "s", "cwd": str(self.root),
                                                   "prompt": "hi"}))
            self.assertNotIn("gatekit@gatekit", again)  # once per session
            # write/bash keep running
            res = write_gate.handle({"session_id": "s", "cwd": str(self.root), "tool_name": "Write",
                                     "tool_input": {"file_path": str(self.root / ".gatekit/approvals.json")}})
            self.assertEqual(res["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_legacy_disabled_in_project_does_not_stand_down(self) -> None:
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"gatekit@gatekit": False}}), encoding="utf-8")
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), [])
            self.assertEqual(self.stop()["decision"], "block")

    def test_stale_enabled_key_without_install_does_not_stand_down(self) -> None:
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"version": 2, "plugins": {"gatebound@gatebound": {}}}), encoding="utf-8")
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), [])

    def test_migrated_project_keeps_new_gates(self) -> None:
        # The old plugin reads only .gatekit/; once state lives in .gatebound/
        # it stands down itself, so the new plugin must not.
        (self.root / ".gatekit").rename(self.root / ".gatebound")
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), [])
            self.assertEqual(self.stop()["decision"], "block")

    def test_claude_config_dir_is_honoured(self) -> None:
        alt = self.root / "_cfg"
        (alt / "plugins").mkdir(parents=True)
        shutil.move(str(self.home / ".claude" / "settings.json"), str(alt / "settings.json"))
        shutil.move(str(self.home / ".claude" / "plugins" / "installed_plugins.json"),
                    str(alt / "plugins" / "installed_plugins.json"))
        shutil.move(str(self.home / ".claude" / "plugins" / "cache"), str(alt / "plugins" / "cache"))
        os.environ["CLAUDE_CONFIG_DIR"] = str(alt)
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), ["gatekit@gatekit"])

    def test_unreadable_settings_never_raise(self) -> None:
        (self.home / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
        with self.renamed():
            self.assertEqual(names.legacy_plugin_enabled(self.root), [])


# ------------------------------------------------------------------ migrate
def _git(root, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)


class TestMigrate(Temp):
    def setUp(self) -> None:
        super().setUp()
        state = self.root / ".gatekit"
        (state / "runs").mkdir(parents=True)
        (state / "config.json").write_text("{}", encoding="utf-8")
        (state / "approvals.json").write_text('{"approvals": []}', encoding="utf-8")
        (self.root / "spec").mkdir()
        (self.root / "spec" / "05-gate.md").write_text("```gatekit-criterion\n{}\n```\n",
                                                       encoding="utf-8")
        (self.root / ".gitignore").write_text("node_modules/\n.gatekit/runs/\n/.gatekit/jobs/\n",
                                              encoding="utf-8")

    def run_cli(self, *args: str):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = migrate.run(["--root", str(self.root), *args])
        return code, out.getvalue()

    def test_default_target_is_gatebound(self) -> None:
        code, out = self.run_cli("--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["to"], ".gatebound")
        self.assertTrue(report["actions"])
        self.assertTrue((self.root / ".gatekit").is_dir())
        code, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / ".gatebound" / "approvals.json").is_file())
        self.assertFalse((self.root / ".gatekit").exists())
        code, out = self.run_cli("--apply", "--json")
        self.assertEqual(json.loads(out)["actions"], [])

    def test_dry_run_changes_nothing(self) -> None:
        code, out = self.run_cli("--to", "gatebound", "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertFalse(report["applied"])
        self.assertTrue(report["actions"])
        self.assertTrue((self.root / ".gatekit").is_dir())
        self.assertFalse((self.root / ".gatebound").exists())

    def test_apply_renames_and_is_idempotent(self) -> None:
        spec_before = (self.root / "spec" / "05-gate.md").read_bytes()
        code, _ = self.run_cli("--to", "gatebound", "--apply")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".gatekit").exists())
        self.assertTrue((self.root / ".gatebound" / "approvals.json").is_file())
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8"),
                         "node_modules/\n.gatebound/runs/\n/.gatebound/jobs/\n")
        self.assertEqual((self.root / "spec" / "05-gate.md").read_bytes(), spec_before)
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")
        code, out = self.run_cli("--to", "gatebound", "--apply", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["actions"], [])

    def test_refuses_when_both_exist(self) -> None:
        (self.root / ".gatebound").mkdir()
        code, out = self.run_cli("--to", "gatebound", "--apply", "--json")
        self.assertEqual(code, 1)
        self.assertIn("both", json.loads(out)["detail"])
        self.assertTrue((self.root / ".gatekit" / "approvals.json").is_file())

    def test_regenerates_agents_block_when_present(self) -> None:
        begin, end = names.agents_markers()
        (self.root / "AGENTS.md").write_text("# Mine\n\n%s\nstale\n%s\n" % (begin, end),
                                             encoding="utf-8")
        code, _ = self.run_cli("--to", "gatebound", "--apply")
        self.assertEqual(code, 0)
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("stale", text)
        self.assertIn("# Mine", text)

    @unittest.skipIf(shutil.which("git") is None, "git not available")
    def test_uses_git_mv_when_tracked(self) -> None:
        _git(self.root, "init", "-q")
        _git(self.root, "add", ".gatekit/config.json", ".gatekit/approvals.json")
        code, _ = self.run_cli("--to", "gatebound", "--apply")
        self.assertEqual(code, 0)
        staged = _git(self.root, "diff", "--cached", "--name-status").stdout
        self.assertIn(".gatebound/approvals.json", staged)
        self.assertTrue((self.root / ".gatebound" / "runs").is_dir())  # untracked moved too
        self.assertFalse((self.root / ".gatekit").exists())

    def test_registered_in_cli(self) -> None:
        from gatebound import cli
        self.assertIn("migrate", cli.SUBCOMMANDS)


# ------------------------------------------------------------------ hooks exit 0
class TestHooksExitZero(Temp):
    def test_gates_exit_zero_in_a_gatekit_project_with_broken_settings(self) -> None:
        home = self.fake_home()
        (home / ".claude" / "settings.json").write_text("{broken", encoding="utf-8")
        (self.root / ".gatekit").mkdir()
        (self.root / ".gatekit" / "approvals.json").write_text("{broken", encoding="utf-8")
        events = {
            "prompt.py": {"prompt": "/gatekit:build"},
            "stop.py": {"hook_event_name": "Stop"},
            "question.py": {"tool_name": "AskUserQuestion", "tool_input": {}},
            "write.py": {"tool_name": "Write", "tool_input": {"file_path": "x.py"}},
            "bash.py": {"tool_name": "Bash", "tool_input": {"command": "gatekit approve x"}},
        }
        for script, extra in events.items():
            event = dict({"session_id": "s", "cwd": str(self.root)}, **extra)
            proc = subprocess.run([PY, str(GATES / script)], input=json.dumps(event),
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, (script, proc.stderr[-300:]))


if __name__ == "__main__":
    unittest.main()
