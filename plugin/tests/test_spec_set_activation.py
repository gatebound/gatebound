"""ADR-0036: spec before code starts with gatebound's own spec files, not with
any `spec/` directory, so a globally installed plugin leaves an RSpec-shaped
project alone while a gatebound project stays guarded from its first spec file."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import approval, names, spec  # noqa: E402
from gatebound.gates import bash as bash_gate  # noqa: E402
from gatebound.gates import powershell as ps_gate  # noqa: E402
from gatebound.gates import write  # noqa: E402


class Project(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        self._env = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(names.env_prefixes())}

    def tearDown(self) -> None:
        for key in list(os.environ):
            if key.startswith(names.env_prefixes()):
                del os.environ[key]
        os.environ.update(self._env)
        self._tmp.cleanup()

    def put(self, rel: str, text: str = "x\n") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def event(self, tool: str, tool_input: dict) -> dict:
        return {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(self.root),
                "tool_name": tool, "tool_input": tool_input}

    def decisions(self, rel: str = "app/models/user.rb") -> dict:
        """The verdict of each gate on one write into *rel*."""
        out = {
            "Write": write.handle(self.event("Write", {"file_path": str(self.root / rel), "content": "x"})),
            "Bash": bash_gate.handle(self.event("Bash", {"command": "echo x > %s" % rel})),
            "PowerShell": ps_gate.handle(self.event("PowerShell", {"command": "Set-Content -Path %s -Value x" % rel})),
        }
        return {k: (v or {}).get("hookSpecificOutput", {}).get("permissionDecision", "allow") for k, v in out.items()}

    def assertAllAllowed(self, rel: str = "app/models/user.rb") -> None:  # noqa: N802
        self.assertEqual(self.decisions(rel), {"Write": "allow", "Bash": "allow", "PowerShell": "allow"})

    def assertAllDenied(self, rel: str = "app/models/user.rb") -> None:  # noqa: N802
        self.assertEqual(self.decisions(rel), {"Write": "deny", "Bash": "deny", "PowerShell": "deny"})


class TestUnmanagedSpecDirectory(Project):
    def test_an_rspec_project_is_left_alone(self) -> None:
        self.put("spec/models/user_spec.rb")
        self.put("spec/spec_helper.rb")
        self.assertFalse(write.spec_set_present(self.root))
        self.assertFalse(write.restrictions_active(self.root))
        self.assertAllAllowed()

    def test_an_empty_spec_directory_does_not_switch_rule_a_on(self) -> None:
        (self.root / "spec").mkdir()
        self.assertAllAllowed()

    def test_a_file_outside_the_spec_set_does_not_either(self) -> None:
        self.put("spec/notes.md")
        self.put("spec/01-prd.md.bak")
        self.assertAllAllowed()

    def test_a_spec_file_elsewhere_does_not_count(self) -> None:
        self.put("docs/spec/01-prd.md")
        self.put("01-prd.md")
        self.assertAllAllowed()


class TestGateboundSpecFiles(Project):
    def test_each_spec_file_switches_rule_a_on(self) -> None:
        self.assertIn("01-prd.md", spec.spec_files())
        for name in spec.spec_files():
            with self.subTest(name=name):
                for f in (self.root / "spec").glob("*"):
                    f.unlink()
                self.put("spec/" + name)
                self.assertTrue(write.spec_set_present(self.root))
                self.assertAllDenied()

    def test_approval_still_lifts_it(self) -> None:
        self.put("spec/01-prd.md")
        self.put("spec/05-gate.md", "# Gate\n")
        self.assertAllDenied()
        approval.approve(self.root, "spec/05-gate.md")
        self.assertAllAllowed()

    def test_the_allowlist_still_applies(self) -> None:
        self.put("spec/01-prd.md")
        self.assertAllAllowed("docs/notes.md")


class TestUnchangedRules(Project):
    def test_protected_state_holds_with_no_spec_file(self) -> None:
        (self.root / ".gatebound").mkdir()
        self.put(".gatebound/approvals.json", "{}")
        self.assertAllDenied(".gatebound/approvals.json")

    def test_task_scope_holds_with_no_spec_file(self) -> None:
        os.environ[names.env_prefixes()[0] + "TASK_ID"] = "t1"
        self.assertTrue(write.restrictions_active(self.root))
        self.assertEqual(self.decisions()["Write"], "deny")


if __name__ == "__main__":
    unittest.main()
