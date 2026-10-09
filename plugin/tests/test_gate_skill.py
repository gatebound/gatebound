"""Tests for gates/skill.py — a gatebound skill may arm the Stop gate (ADR-0032)."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import ledger  # noqa: E402
from gatebound.gates import skill as skill_gate  # noqa: E402

GATE_SCRIPT = pathlib.Path(skill_gate.__file__)
HOOKS_JSON = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "hooks.json"


class SkillProject(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / ".gatebound").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def event(self, skill) -> dict:
        return {"session_id": "s1", "cwd": str(self.root), "hook_event_name": "PreToolUse",
                "tool_name": "Skill", "tool_input": {"skill": skill}}

    def led(self) -> ledger.Ledger:
        return ledger.Ledger.load(self.root, "s1")

    def start(self, pipeline: str, block_count: int = 0) -> None:
        led = self.led()
        led.set_pipeline(pipeline)
        led.data["stop"]["block_count"] = block_count
        led.save()


class TestArming(SkillProject):
    def test_a_verify_skill_arms_the_stop_gate(self) -> None:
        # Observed on the first host run: verify started through the Skill
        # tool left active_pipeline at `gate` and the Stop gate idle.
        self.start("gate", block_count=2)
        self.assertIsNone(skill_gate.handle(self.event("gatebound:verify")))
        data = self.led().data
        self.assertEqual(data["active_pipeline"], "verify")
        self.assertEqual(data["stop"]["block_count"], 0)
        kinds = [(e["kind"], e["detail"].get("source")) for e in data["events"]]
        self.assertIn(("pipeline_set", "skill"), kinds)
        self.assertIn("stop_rearmed", [k for k, _ in kinds])

    def test_a_trigger_skill_counts_as_its_command(self) -> None:
        self.assertIsNone(skill_gate.handle(self.event("gatebound:gatebound-build")))
        self.assertEqual(self.led().data["active_pipeline"], "build")

    def test_the_command_name_is_read_from_every_spelling(self) -> None:
        for raw, name in (("gatebound:verify", "verify"), ("gatebound:gatebound-build", "build"),
                          ("gatekit:verify", "verify"), ("GATEBOUND:Verify", "verify"),
                          ("other:verify", None), ("verify", None), ("", None), (None, None)):
            with self.subTest(raw=raw):
                self.assertEqual(skill_gate.skill_command(raw), name)


class TestNeverDisarms(SkillProject):
    def test_other_gatebound_skills_leave_a_running_build_alone(self) -> None:
        # A model must not end a build's judging early through a skill.
        self.start("build", block_count=1)
        for skill in ("gatebound:doctor", "gatebound:setup", "gatebound:gatebound-interview",
                      "gatebound:tasks", "gatebound:gate"):
            with self.subTest(skill=skill):
                self.assertIsNone(skill_gate.handle(self.event(skill)))
                data = self.led().data
                self.assertEqual(data["active_pipeline"], "build")
                self.assertEqual(data["stop"]["block_count"], 1)

    def test_other_plugins_skills_are_ignored(self) -> None:
        self.start("build")
        skill_gate.handle(self.event("data:analyze"))
        self.assertEqual(self.led().data["active_pipeline"], "build")


class TestQuietWhereNotGoverned(unittest.TestCase):
    def test_a_project_without_gatebound_state_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = {"session_id": "s1", "cwd": tmp, "tool_name": "Skill",
                     "tool_input": {"skill": "gatebound:verify"}}
            self.assertIsNone(skill_gate.handle(event))
            self.assertFalse((pathlib.Path(tmp) / ".gatebound").exists())


class TestHookContract(SkillProject):
    def run_script(self, stdin: bytes) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return subprocess.run([sys.executable, str(GATE_SCRIPT)], input=stdin,
                              capture_output=True, env=env, timeout=30)

    def test_it_exits_zero_and_allows(self) -> None:
        for stdin in (json.dumps(self.event("gatebound:verify")).encode("utf-8"),
                      b"not json", b"", json.dumps({"tool_input": 5}).encode("utf-8")):
            with self.subTest(stdin=stdin[:20]):
                proc = self.run_script(stdin)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertNotIn(b"deny", proc.stdout)

    def test_hooks_json_registers_it_for_the_skill_tool(self) -> None:
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        entries = [h for h in hooks if h.get("matcher") == "Skill"]
        self.assertEqual(len(entries), 1)
        command = entries[0]["hooks"][0]["command"]
        self.assertIn("gates/skill.py", command)
        self.assertIn("py -3", command)  # ADR-0019 interpreter chain


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
