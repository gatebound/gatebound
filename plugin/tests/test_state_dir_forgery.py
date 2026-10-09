"""A forged state directory must never become the one the hooks read.

Review finding (2026-10-04): with restrictions off, PowerShell could create
``.gatekit`` as a link or by renaming a directory the model had filled, and
``names.resolve_state_dir`` then picked it on a rank tie (newest name). Four
layers close it (ADR-0028 / ADR-0029 amendments):

a. the PowerShell reader records renames and links as copies into the new
   name, so the Bash gate's copy rule judges them;
b. any write, link, rename or copy whose final segment is a state directory
   name is gatebound's alone — only a plain ``mkdir`` of the current name, while
   no other state directory exists, is left to the model;
c. ``resolve_state_dir`` ignores a link (or a directory resolving outside the
   project) and prefers the current name on a tie;
d. the Stop gate refuses to judge while both directories hold approvals.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import approval, config, contract, ledger, names, paths  # noqa: E402
from gatebound.gates import bash as bash_gate  # noqa: E402
from gatebound.gates import powershell as ps_gate  # noqa: E402
from tests._stubs import symlink_or_skip  # noqa: E402
from gatebound.gates import stop as stop_gate  # noqa: E402
from gatebound.gates import write as write_gate  # noqa: E402

PY = sys.executable


class Project(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name)) / "proj"
        (self.root / ".gatebound").mkdir(parents=True)
        (self.root / "spec").mkdir()
        (self.root / "spec" / "05-gate.md").write_text(
            "```gatebound-criterion\n"
            + json.dumps({"id": "c", "argv": [PY, "-c", "raise SystemExit(1)"], "timeout_s": 20})
            + "\n```\n", encoding="utf-8")
        contract.derive(self.root)
        self.forged = self.root.parent / "forged"
        self.forged.mkdir()
        (self.forged / "approvals.json").write_text('{"version": 1, "approvals": {}}',
                                                    encoding="utf-8")
        self._env = {k: os.environ.pop(k) for k in list(os.environ)
                     if k.startswith(names.env_prefixes())}

    def tearDown(self) -> None:
        for key in list(os.environ):
            if key.startswith(names.env_prefixes()):
                del os.environ[key]
        os.environ.update(self._env)
        self._tmp.cleanup()

    def approve(self) -> None:
        approval.approve(self.root, "spec/05-gate.md")

    def tool(self, name: str, tool_input: dict) -> dict:
        return {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": name,
                "tool_input": tool_input, "cwd": str(self.root)}

    def ps(self, command: str):
        return ps_gate.handle(self.tool("PowerShell", {"command": command}))

    def bash(self, command: str):
        return bash_gate.handle(self.tool("Bash", {"command": command}))

    def assertProtected(self, result, command: str) -> None:  # noqa: N802
        self.assertIsNotNone(result, command)
        out = result["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny", command)
        self.assertIn("ADR-0027", out["permissionDecisionReason"], command)


class TestPowerShellCannotForgeTheStateDir(Project):
    FORMS = (
        "New-Item -ItemType SymbolicLink -Path .gatekit -Target C:\\tmp\\forged",
        "New-Item -ItemType Junction -Path .gatekit -Value C:\\tmp\\forged",
        "New-Item -ItemType SymbolicLink -Path .gatekit -Target ..\\forged",
        "New-Item -ItemType SymbolicLink -Name .gatekit -Target ..\\forged",
        "ni -ItemType SymbolicLink .GATEKIT -Value ..\\forged",
        "New-Item -ItemType HardLink -Path .gatekit -Value x.json",
        "Rename-Item ..\\forged -NewName .gatekit",
        "Rename-Item C:\\tmp\\forged -NewName .gatekit",
        "Rename-Item -Path forged -NewName .GateKit",
        "ren forged .gatekit",
        "Move-Item ..\\forged .gatekit",
        "Move-Item -Path C:\\tmp\\forged -Destination .gatekit",
        "Copy-Item -Recurse ..\\forged .gatekit",
        "New-Item -ItemType Directory .gatekit",
        "mkdir .gatekit",
        "Set-Content .gatekit x",
        "Move-Item eval .gatekit", "Copy-Item -Recurse .gatebound\\eval .gatekit",
        "[IO.Directory]::Move('forged', '.gatekit')",
        "[IO.Directory]::CreateDirectory('.gatekit')",
        "New-Item -Path .gatekit\\eval -ItemType Directory -Force",
    )

    def test_every_form_is_denied_before_and_after_approval(self) -> None:
        for approved in (False, True):
            if approved:
                self.approve()
            for command in self.FORMS:
                with self.subTest(approved=approved, command=command):
                    self.assertProtected(self.ps(command), command)

    def test_reader_records_renames_and_links_as_copies(self) -> None:
        from gatebound import pwsh
        for command in ("Rename-Item forged -NewName .gatekit",
                        "New-Item -ItemType SymbolicLink -Path .gatekit -Target forged",
                        "New-Item -ItemType Junction -Path .gatekit -Value C:\\tmp\\forged"):
            with self.subTest(command=command):
                found = pwsh.read(command, "/proj")
                self.assertTrue(any(dest.endswith("/.gatekit") for _, dest, _ in found.copies),
                                found.copies)

    def test_rename_also_removes_the_source(self) -> None:
        from gatebound import pwsh
        found = pwsh.read("Rename-Item forged -NewName .gatekit", "/proj")
        self.assertIn("/proj/forged", found.removed)

    def test_normal_directory_work_stays_allowed(self) -> None:
        self.approve()
        for command in ("New-Item -ItemType Directory .gatebound",
                        "mkdir .gatebound",
                        "New-Item -ItemType Directory -Force .gatebound\\eval",
                        "New-Item -ItemType SymbolicLink -Path latest -Target build",
                        "Rename-Item old.ts new.ts",
                        "Move-Item a b"):
            with self.subTest(command=command):
                self.assertIsNone(self.ps(command), command)


class TestBashCannotForgeTheStateDir(Project):
    FORMS = (
        "ln -s /tmp/forged .gatekit", "ln -sfn ../forged .gatekit",
        "mv ../forged .gatekit", "mv ../forged .GATEKIT", "cp -r ../forged .gatekit",
        "mkdir .gatekit", "mkdir -p .gatekit", "touch .gatekit",
        "echo x > .gatekit", "install -d .gatekit",
        # a directory the model filled, under a user-owned name
        "mv eval .gatekit", "cp -r .gatebound/eval .gatekit", "ln -s .gatebound/eval .gatekit",
        # a state directory created on the way to one below it
        "mkdir -p .gatekit/eval", "mkdir -p sub/.gatekit/x",
    )

    def test_every_form_is_denied_before_and_after_approval(self) -> None:
        for approved in (False, True):
            if approved:
                self.approve()
            for command in self.FORMS:
                with self.subTest(approved=approved, command=command):
                    self.assertProtected(self.bash(command), command)

    def test_plain_mkdir_of_the_current_name_stays_allowed(self) -> None:
        self.approve()
        for command in ("mkdir .gatebound", "mkdir -p .gatebound", "mkdir -p .gatebound/eval",
                        "mkdir -p sub/.gatebound/eval"):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command), command)

    def test_mkdir_of_the_current_name_is_denied_beside_another_state_dir(self) -> None:
        self.approve()
        (self.root / ".gatekit").mkdir()
        self.assertProtected(self.bash("mkdir .gatebound"), "mkdir .gatebound")
        self.assertProtected(self.ps("New-Item -ItemType Directory .gatebound"), "ni")

    def test_deny_names_the_targeted_directory(self) -> None:
        for command in ("mv ../forged .gatekit", "ln -s ../forged .gatekit"):
            with self.subTest(command=command):
                reason = self.bash(command)["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn(".gatekit/", reason)
        reason = self.ps("Rename-Item forged -NewName .gatekit")[
            "hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(".gatekit/", reason)

    def test_write_tool_cannot_create_a_state_dir_name(self) -> None:
        for path in (".gatekit", str(self.root / ".gatebound"), ".GATEKIT"):
            with self.subTest(path=path):
                result = write_gate.handle(self.tool("Write", {"file_path": path}))
                self.assertProtected(result, path)


@unittest.skipUnless(hasattr(os, "symlink"), "needs os.symlink")
class TestResolveStateDir(Project):
    def link(self, target: pathlib.Path, name: str = ".gatekit") -> pathlib.Path:
        path = self.root / name
        symlink_or_skip(self, target, path, target_is_directory=True)
        return path

    def test_a_linked_candidate_is_ignored(self) -> None:
        self.link(self.forged)
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_a_linked_candidate_alone_is_ignored(self) -> None:
        (self.root / ".gatebound" / "contract.json").unlink()
        os.rmdir(str(self.root / ".gatebound"))
        self.link(self.forged)
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")

    def test_a_candidate_resolving_outside_the_root_is_ignored(self) -> None:
        # a linked parent component: the directory itself is no link
        outside = self.root.parent / "outside"
        (outside / ".gatekit").mkdir(parents=True)
        (outside / ".gatekit" / "approvals.json").write_text("{}", encoding="utf-8")
        self.assertFalse(names._usable_state_dir(self.root, outside / ".gatekit"))
        self.assertTrue(names._usable_state_dir(self.root, self.root / ".gatebound"))

    def test_tie_prefers_the_current_name(self) -> None:
        (self.root / ".gatebound" / "approvals.json").write_text("{}", encoding="utf-8")
        (self.root / ".gatekit").mkdir()
        (self.root / ".gatekit" / "approvals.json").write_text("{}", encoding="utf-8")
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")

    def test_the_current_name_wins_whatever_the_other_holds(self) -> None:
        # before the first approval .gatebound/ has no approvals.json; a
        # .gatekit/approvals.json laid down by a program the gates do not
        # model (ditto, pax, an archive) must not capture the hooks
        (self.root / ".gatekit").mkdir()
        (self.root / ".gatekit" / "approvals.json").write_text("{}", encoding="utf-8")
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")
        (self.root / ".gatebound" / "contract.json").unlink()  # empty current dir
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")

    def test_the_other_name_is_read_only_without_a_current_dir(self) -> None:
        (self.root / ".gatebound" / "contract.json").unlink()
        os.rmdir(str(self.root / ".gatebound"))
        (self.root / ".gatekit").mkdir()
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatekit")

    def legacy_only(self) -> None:
        """An unmigrated gatekit project: only the legacy directory exists."""
        (self.root / ".gatebound").rename(self.root / ".gatekit")

    def test_an_unmigrated_gatekit_project_reads_legacy(self) -> None:
        self.legacy_only()
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatekit")
        (self.root / ".gatebound").mkdir()  # the current name appears
        self.assertEqual(names.resolve_state_dir(self.root), self.root / ".gatebound")

    def test_creating_the_current_dir_beside_legacy_is_denied(self) -> None:
        self.legacy_only()
        self.approve()
        self.assertTrue((self.root / ".gatekit" / "approvals.json").is_file())
        result = bash_gate.handle(self.tool("Bash", {"command": "mkdir .gatebound"}))
        self.assertIsNotNone(result)


class TestStopFailsClosedOnTwoApprovals(Project):
    def setUp(self) -> None:
        super().setUp()
        self.approve()
        led = ledger.Ledger.load(self.root, "s")
        led.data["active_pipeline"] = "build"
        led.save()
        (self.root / ".gatekit").mkdir()
        (self.root / ".gatekit" / "approvals.json").write_text(
            '{"version": 1, "approvals": {}}', encoding="utf-8")

    def stop(self):
        return stop_gate.handle({"session_id": "s", "hook_event_name": "Stop",
                                 "cwd": str(self.root)})

    def test_blocks_unverified_and_names_doctor_and_migrate(self) -> None:
        out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertIn("approvals.json", out["reason"])
        self.assertIn("doctor", out["reason"])
        self.assertIn("migrate", out["reason"])
        stop_state = ledger.Ledger.load(self.root, "s").data["stop"]
        self.assertEqual(stop_state["final_verdict"], "unverified")

    def test_never_ok_and_never_traps(self) -> None:
        results = [self.stop() for _ in range(stop_gate.MAX_BLOCKS + 1)]
        self.assertTrue(all(r and r.get("decision") == "block"
                            for r in results[:stop_gate.MAX_BLOCKS]))
        self.assertIsNone(results[-1])
        self.assertEqual(ledger.Ledger.load(self.root, "s").data["stop"]["final_verdict"],
                         "unverified")

    def test_one_approvals_file_judges_normally(self) -> None:
        (self.root / ".gatekit" / "approvals.json").unlink()
        out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertNotIn("migrate", out["reason"])


class TestSetupStillCreatesTheCurrentName(unittest.TestCase):
    def test_fresh_project_gets_the_current_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(os.path.realpath(tmp))
            self.assertEqual(paths.state_dir(root), root / names.state_dirname())
            # /gatebound:setup step 1: `workers set-default claude` -> config.save
            config.save(root, config.load(root))
            self.assertTrue((root / ".gatebound" / "config.json").is_file())
            self.assertEqual(paths.state_dir(root), root / ".gatebound")


if __name__ == "__main__":
    unittest.main()
