"""Tests for gates/spawn.py — declared write scopes for subagents."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import ledger, paths  # noqa: E402
from gatebound.gates import spawn as spawn_gate  # noqa: E402

GATE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "gatebound" / "gates" / "spawn.py"


def scope_fence(obj) -> str:
    body = obj if isinstance(obj, str) else json.dumps(obj)
    return "```gatebound-scope\n" + body + "\n```"


class SpawnProject(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / ".gatebound").mkdir()
        self.session = "sess-spawn"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def event(self, prompt: str, description: str = "") -> dict:
        tool_input = {"prompt": prompt}
        if description:
            tool_input["description"] = description
        return {
            "session_id": self.session,
            "hook_event_name": "PreToolUse",
            "cwd": str(self.root),
            "tool_name": "Task",
            "tool_input": tool_input,
        }

    def led(self) -> ledger.Ledger:
        return ledger.Ledger.load(self.root, self.session)

    def is_deny(self, result) -> bool:
        return (
            result is not None
            and result["hookSpecificOutput"]["permissionDecision"] == "deny"
        )


class TestAllow(SpawnProject):
    def test_valid_fence_allows_and_records_scope(self) -> None:
        prompt = "Do the auth work.\n" + scope_fence(
            {"write_scope": ["src/auth/**"], "stop_when": "tests pass", "tools": "inherit"}
        )
        self.assertIsNone(spawn_gate.handle(self.event(prompt, description="auth-agent")))
        scopes = self.led().data["scopes"]
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0]["write_scope"], ["src/auth/**"])
        self.assertEqual(scopes[0]["owner"], "auth-agent")

    def test_owner_falls_back_to_prompt_hash(self) -> None:
        prompt = "work\n" + scope_fence({"write_scope": ["src/a/**"], "stop_when": "x"})
        spawn_gate.handle(self.event(prompt))
        owner = self.led().data["scopes"][0]["owner"]
        expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        self.assertEqual(owner, expected)
        self.assertEqual(len(owner), 12)

    def test_read_only_scope_allowed(self) -> None:
        prompt = "review only\n" + scope_fence(
            {"write_scope": "read-only", "stop_when": "review posted"}
        )
        self.assertIsNone(spawn_gate.handle(self.event(prompt)))
        self.assertEqual(self.led().data["scopes"][0]["write_scope"], "read-only")

    def test_two_read_only_agents_do_not_conflict(self) -> None:
        prompt = "r\n" + scope_fence({"write_scope": "read-only", "stop_when": "x"})
        self.assertIsNone(spawn_gate.handle(self.event(prompt, description="a")))
        self.assertIsNone(spawn_gate.handle(self.event(prompt, description="b")))

    def test_disjoint_scopes_both_allowed(self) -> None:
        first = "a\n" + scope_fence({"write_scope": ["src/auth/**"], "stop_when": "x"})
        second = "b\n" + scope_fence({"write_scope": ["src/billing/**"], "stop_when": "x"})
        self.assertIsNone(spawn_gate.handle(self.event(first, description="a")))
        self.assertIsNone(spawn_gate.handle(self.event(second, description="b")))
        self.assertEqual(len(self.led().data["scopes"]), 2)

    def test_fence_with_surrounding_prose(self) -> None:
        prompt = (
            "# Task\nSome instructions.\n\n"
            + scope_fence({"write_scope": ["src/x/**"], "stop_when": "done"})
            + "\n\nMore prose afterwards.\n"
        )
        self.assertIsNone(spawn_gate.handle(self.event(prompt)))

    def test_event_is_recorded(self) -> None:
        prompt = "a\n" + scope_fence({"write_scope": ["src/a/**"], "stop_when": "x"})
        spawn_gate.handle(self.event(prompt))
        kinds = [e["kind"] for e in self.led().data["events"]]
        self.assertIn("scope_declared", kinds)


class TestDeny(SpawnProject):
    def test_missing_fence_denies(self) -> None:
        self.assertTrue(self.is_deny(spawn_gate.handle(self.event("just do the thing"))))

    def test_empty_prompt_denies(self) -> None:
        self.assertTrue(self.is_deny(spawn_gate.handle(self.event(""))))

    def test_invalid_json_denies(self) -> None:
        self.assertTrue(
            self.is_deny(spawn_gate.handle(self.event("x\n" + scope_fence("{not json"))))
        )

    def test_non_object_json_denies(self) -> None:
        self.assertTrue(
            self.is_deny(spawn_gate.handle(self.event("x\n" + scope_fence("[1,2,3]"))))
        )

    def test_missing_write_scope_key_denies(self) -> None:
        self.assertTrue(
            self.is_deny(spawn_gate.handle(self.event("x\n" + scope_fence({"stop_when": "x"}))))
        )

    def test_missing_stop_when_denies(self) -> None:
        self.assertTrue(
            self.is_deny(
                spawn_gate.handle(self.event("x\n" + scope_fence({"write_scope": ["a/**"]})))
            )
        )

    def test_empty_write_scope_list_denies(self) -> None:
        self.assertTrue(
            self.is_deny(
                spawn_gate.handle(
                    self.event("x\n" + scope_fence({"write_scope": [], "stop_when": "x"}))
                )
            )
        )

    def test_bad_write_scope_type_denies(self) -> None:
        self.assertTrue(
            self.is_deny(
                spawn_gate.handle(
                    self.event("x\n" + scope_fence({"write_scope": 42, "stop_when": "x"}))
                )
            )
        )

    def test_unknown_write_scope_string_denies(self) -> None:
        # only the literal "read-only" is a valid string form
        self.assertTrue(
            self.is_deny(
                spawn_gate.handle(
                    self.event("x\n" + scope_fence({"write_scope": "anything", "stop_when": "x"}))
                )
            )
        )

    def test_conflicting_scope_denies(self) -> None:
        first = "a\n" + scope_fence({"write_scope": ["src/auth/**"], "stop_when": "x"})
        spawn_gate.handle(self.event(first, description="a"))
        second = "b\n" + scope_fence({"write_scope": ["src/auth/token.ts"], "stop_when": "x"})
        result = spawn_gate.handle(self.event(second, description="b"))
        self.assertTrue(self.is_deny(result))
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("a", reason)

    def test_conflicting_scope_is_not_recorded(self) -> None:
        first = "a\n" + scope_fence({"write_scope": ["src/auth/**"], "stop_when": "x"})
        spawn_gate.handle(self.event(first, description="a"))
        second = "b\n" + scope_fence({"write_scope": ["src/auth/**"], "stop_when": "x"})
        spawn_gate.handle(self.event(second, description="b"))
        self.assertEqual(len(self.led().data["scopes"]), 1)

    def test_denial_is_recorded_as_event(self) -> None:
        spawn_gate.handle(self.event("no fence here"))
        kinds = [e["kind"] for e in self.led().data["events"]]
        self.assertIn("spawn_denied", kinds)

    def test_no_regex_over_prose(self) -> None:
        """Prose merely mentioning write_scope must not satisfy the gate."""
        prompt = 'Please use write_scope: ["src/**"] and stop_when: "done".'
        self.assertTrue(self.is_deny(spawn_gate.handle(self.event(prompt))))

    def test_korean_reason_when_ledger_says_ko(self) -> None:
        led = self.led()
        led.set_output_lang("ko")
        led.save()
        result = spawn_gate.handle(self.event("no fence"))
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertTrue(any("가" <= ch <= "힣" for ch in reason), reason)


class TestSubprocess(SpawnProject):
    def _run(self, event: dict) -> "tuple[int, str, str]":
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run(
            [sys.executable, str(GATE_SCRIPT)],
            input=json.dumps(event),
            capture_output=True,
            text=True, encoding="utf-8",
            env=env,
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_allow_via_subprocess(self) -> None:
        prompt = "a\n" + scope_fence({"write_scope": ["src/a/**"], "stop_when": "x"})
        code, out, err = self._run(self.event(prompt))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "")

    def test_deny_via_subprocess(self) -> None:
        code, out, err = self._run(self.event("no fence"))
        self.assertEqual(code, 0, err)
        self.assertEqual(
            json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_internal_error_exits_zero_and_logs(self) -> None:
        runs = self.root / ".gatebound" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{self.session}.json").mkdir()  # unwritable ledger path
        prompt = "a\n" + scope_fence({"write_scope": ["src/a/**"], "stop_when": "x"})
        code, _, err = self._run(self.event(prompt))
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        log = runs / "hook-errors.log"
        self.assertTrue(log.is_file())
        self.assertIn("PreToolUse", log.read_text(encoding="utf-8"))

    def test_malformed_stdin_exits_zero(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run(
            [sys.executable, str(GATE_SCRIPT)],
            input="{oops",
            capture_output=True,
            text=True, encoding="utf-8",
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TestCodexSpawnTool(unittest.TestCase):
    """Codex's collaborationspawn_agent hides the prompt; the gate allows and
    records that the subagent is unscoped instead of denying every spawn."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / ".gatebound").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_codex_spawn_without_prompt_is_allowed_and_recorded(self) -> None:
        event = {
            "session_id": "cx", "hook_event_name": "PreToolUse", "cwd": str(self.root),
            "tool_name": "collaborationspawn_agent",
            "tool_input": {"task_name": "folder_summary", "message": "gAAAA-encrypted"},
        }
        self.assertIsNone(spawn_gate.handle(event))
        led = ledger.Ledger.load(self.root, "cx")
        kinds = [e["kind"] for e in led.data["events"]]
        self.assertIn("spawn_unscoped", kinds)
        self.assertEqual(led.data["scopes"], [])

    def test_codex_spawn_with_prompt_is_still_checked(self) -> None:
        event = {
            "session_id": "cx", "hook_event_name": "PreToolUse", "cwd": str(self.root),
            "tool_name": "collaborationspawn_agent",
            "tool_input": {"prompt": "no fence here"},
        }
        self.assertIsNotNone(spawn_gate.handle(event))


class TestUnmanagedProject(unittest.TestCase):
    """A project gatebound does not manage is none of the gate's business.

    The plugin installs globally, so this hook fires in every project the
    user opens. Denying a spawn there blocks work gatebound was never asked
    to govern; the scope fence only means something once `.gatebound/` exists.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / ".git").mkdir()  # a git repo, but not a gatebound project

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def event(self, prompt: str) -> dict:
        return {
            "session_id": "unmanaged", "hook_event_name": "PreToolUse",
            "cwd": str(self.root), "tool_name": "Agent",
            "tool_input": {"prompt": prompt, "description": "Locate harness"},
        }

    def test_fenceless_spawn_is_allowed(self) -> None:
        self.assertIsNone(spawn_gate.handle(self.event("find the harness project")))

    def test_invalid_fence_is_allowed(self) -> None:
        bad = scope_fence({"write_scope": [], "stop_when": "done"})
        self.assertIsNone(spawn_gate.handle(self.event(bad)))

    def test_nothing_is_written_to_an_unmanaged_project(self) -> None:
        spawn_gate.handle(self.event("find the harness project"))
        self.assertFalse((self.root / ".gatebound").exists())

    def test_managed_project_still_denies(self) -> None:
        (self.root / ".gatebound").mkdir()
        self.assertIsNotNone(spawn_gate.handle(self.event("no fence here")))


class TestScopeRelease(SpawnProject):
    """A finished subagent's scope is released (found in the 2026-10-09 timed
    trial: round 3 of a build could not be delegated because round 2's
    finished agents still held overlapping scopes)."""

    SCOPE = {"write_scope": ["src/**"], "stop_when": "tests pass", "tools": "inherit"}

    def pre(self, tool_use_id: str, background: bool = False) -> dict:
        ev = self.event("Work.\n" + scope_fence(self.SCOPE), description="worker " + tool_use_id)
        ev["tool_use_id"] = tool_use_id
        ev["tool_input"]["run_in_background"] = background
        return ev

    def post(self, tool_use_id: str, response: dict) -> dict:
        return {
            "session_id": self.session,
            "hook_event_name": "PostToolUse",
            "cwd": str(self.root),
            "tool_name": "Task",
            "tool_use_id": tool_use_id,
            "tool_input": {"prompt": "x"},
            "tool_response": response,
        }

    def subagent_stop(self, agent_id: str) -> dict:
        return {
            "session_id": self.session,
            "hook_event_name": "SubagentStop",
            "cwd": str(self.root),
            "agent_id": agent_id,
        }

    def test_foreground_agent_releases_on_completion(self) -> None:
        self.assertFalse(self.is_deny(spawn_gate.handle(self.pre("t1"))))
        self.assertTrue(self.is_deny(spawn_gate.handle(self.pre("t2"))))
        self.assertIsNone(spawn_gate.handle(self.post("t1", {"status": "completed", "agentId": "a1"})))
        self.assertEqual(self.led().data["scopes"], [])
        self.assertFalse(self.is_deny(spawn_gate.handle(self.pre("t3"))))

    def test_background_agent_holds_until_subagent_stop(self) -> None:
        spawn_gate.handle(self.pre("t1", background=True))
        spawn_gate.handle(self.post("t1", {"status": "async_launched", "isAsync": True, "agentId": "a1"}))
        self.assertTrue(self.is_deny(spawn_gate.handle(self.pre("t2"))))
        self.assertEqual(self.led().data["scopes"][0].get("agent_id"), "a1")
        self.assertIsNone(spawn_gate.handle(self.subagent_stop("a1")))
        self.assertFalse(self.is_deny(spawn_gate.handle(self.pre("t3"))))

    def test_unknown_ids_change_nothing(self) -> None:
        spawn_gate.handle(self.pre("t1"))
        spawn_gate.handle(self.post("other", {"status": "completed"}))
        spawn_gate.handle(self.subagent_stop("nobody"))
        self.assertEqual(len(self.led().data["scopes"]), 1)

    def test_entry_without_tool_use_id_is_kept(self) -> None:
        ev = self.pre("t1")
        del ev["tool_use_id"]
        spawn_gate.handle(ev)
        spawn_gate.handle(self.post("t1", {"status": "completed"}))
        self.assertEqual(len(self.led().data["scopes"]), 1)

    def test_release_is_recorded_as_an_event(self) -> None:
        spawn_gate.handle(self.pre("t1"))
        spawn_gate.handle(self.post("t1", {"status": "completed"}))
        kinds = [e["kind"] for e in self.led().data["events"]]
        self.assertIn("scope_released", kinds)

    def test_unmanaged_project_creates_no_state(self) -> None:
        state = paths.state_dir(self.root)
        state.rmdir()
        self.assertIsNone(spawn_gate.handle(self.post("t1", {"status": "completed"})))
        self.assertIsNone(spawn_gate.handle(self.subagent_stop("a1")))
        self.assertFalse(state.exists())

    def test_post_and_subagent_stop_run_as_a_script(self) -> None:
        spawn_gate.handle(self.pre("t1"))
        for ev in (self.post("t1", {"status": "completed"}), self.subagent_stop("a9")):
            proc = subprocess.run([sys.executable, str(GATE_SCRIPT)], input=json.dumps(ev),
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.led().data["scopes"], [])


class TestHooksRegisterScopeRelease(unittest.TestCase):
    def test_post_tool_use_and_subagent_stop_reach_the_spawn_gate(self) -> None:
        hooks = json.loads((pathlib.Path(__file__).resolve().parents[1] / "hooks" / "hooks.json")
                           .read_text(encoding="utf-8"))["hooks"]
        post = [e for e in hooks.get("PostToolUse", []) if "Agent" in (e.get("matcher") or "")]
        self.assertTrue(post and "gates/spawn.py" in post[0]["hooks"][0]["command"])
        stop = hooks.get("SubagentStop", [])
        self.assertTrue(stop and "gates/spawn.py" in stop[0]["hooks"][0]["command"])


class TestScopeReleaseReview(TestScopeRelease):
    """ADR-0040 review: a SubagentStop that arrives before its spawn call's
    async PostToolUse still releases the scope."""

    def test_stop_before_attach_still_releases(self) -> None:
        spawn_gate.handle(self.pre("t1", background=True))
        spawn_gate.handle(self.subagent_stop("a1"))
        spawn_gate.handle(self.post("t1", {"status": "async_launched", "isAsync": True, "agentId": "a1"}))
        self.assertEqual(self.led().data["scopes"], [])

    def test_failed_or_interrupted_call_releases(self) -> None:
        spawn_gate.handle(self.pre("t1"))
        ev = self.post("t1", {})
        ev["hook_event_name"] = "PostToolUseFailure"
        ev["error"] = "interrupted"
        ev["is_interrupt"] = True
        self.assertIsNone(spawn_gate.handle(ev))
        self.assertEqual(self.led().data["scopes"], [])

    def test_post_tool_use_failure_reaches_the_spawn_gate(self) -> None:
        hooks = json.loads((pathlib.Path(__file__).resolve().parents[1] / "hooks" / "hooks.json")
                           .read_text(encoding="utf-8"))["hooks"]
        failure = [e for e in hooks.get("PostToolUseFailure", []) if "Agent" in (e.get("matcher") or "")]
        self.assertTrue(failure and "gates/spawn.py" in failure[0]["hooks"][0]["command"])
