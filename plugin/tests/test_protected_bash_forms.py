"""ADR-0027 amendment: shell forms that reached gatebound's state unseen.

An interpreter fed its script on stdin, a link made and written in one
command, a path built from a variable, and a git restore by directory
pathspec. Each is denied before and after approval; the normal-work forms
next to them stay allowed.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_protected_state import PLUGIN, Project  # noqa: E402
from tests._stubs import symlink_or_skip  # noqa: E402


class Forms(Project):
    def assertDenied(self, result) -> None:  # noqa: N802
        """The protected-state rule itself, not rule (a) or an opaque refusal."""
        super().assertDenied(result)
        self.assertIn("ADR-0027", result["hookSpecificOutput"]["permissionDecisionReason"])

    def assertOpaque(self, result) -> None:  # noqa: N802
        self.assertIsNotNone(result)
        self.assertIn("cannot determine", result["hookSpecificOutput"]["permissionDecisionReason"])

    def denied_always(self, commands) -> None:
        for approved in (False, True):
            if approved:
                self.approve()
            for command in commands:
                with self.subTest(approved=approved, command=command):
                    self.assertDenied(self.bash(command))

    def allowed_after_approval(self, commands) -> None:
        self.approve()
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))


class TestInterpreterOnStdin(Forms):
    def test_stdin_script_naming_the_file_is_denied(self) -> None:
        self.denied_always((
            "python3 <<PY\nimport json\njson.dump({}, open('.gatebound/contract.json','w'))\nPY",
            "node <<'JS'\nrequire('fs').writeFileSync('.gatebound/approvals.json','{}')\nJS",
            "echo \"open('.gatebound/approvals.json','w').write('{}')\" | python3",
            "python3 <<< \"open('.gatebound/approvals.json','w')\"",
            "ruby <<RB\nFile.write('.gatebound/contract.json', '{}')\nRB",
            "perl <<PL\nopen(F, '>', '.gatebound/approvals.json');\nPL",
        ))

    def test_stdin_script_is_opaque_before_approval(self) -> None:
        for command in ("python3 < script.py", "cat gen.py | python3", "node < build.js",
                        "python3 <<PY\nprint(1)\nPY", "echo 'puts 1' | ruby"):
            with self.subTest(command=command):
                self.assertOpaque(self.bash(command))

    def test_script_file_operand_unchanged(self) -> None:
        for command in ("python3 script.py", "python3 script.py < input.txt",
                        "cat data.json | python3 tool.py", "node build.js <<EOF\nx\nEOF",
                        "python3 -m json.tool .gatebound/contract.json", "python3 -m pytest -q",
                        "python3 --version", "node --version"):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))

    def test_stdin_script_not_naming_the_file_after_approval(self) -> None:
        self.allowed_after_approval(("python3 < script.py", "cat gen.py | python3"))


class TestLinkSources(Forms):
    def test_link_to_protected_state_is_denied(self) -> None:
        (self.root / "sub").mkdir()
        self.denied_always((
            "ln -s .gatebound/approvals.json l && echo x > l",
            "ln -s ../.gatebound/approvals.json sub/l; cp x sub/l",
            "ln .gatebound/approvals.json h2; echo x >> h2",
            "ln -sf .gatebound/contract.json x",
            "ln -s .gatebound g2; echo x > g2/approvals.json",
            "ln -sfn .gatebound g2",
            "cp -s .gatebound/approvals.json l",
            "cp -al .gatebound bk",
            "ln -t sub .gatebound/contract.json",
        ))

    def test_other_links_and_copies_allowed(self) -> None:
        self.allowed_after_approval((
            "ln -s src/app.py l", "ln -s ../shared/config.json .", "ln -sf build/out current",
            "cp -a .gatebound /tmp/backup", "cp .gatebound/contract.json /tmp/c.json",
        ))


class TestVariablePaths(Forms):
    def test_variable_built_paths_are_denied(self) -> None:
        self.denied_always((
            "d=.gatebound; echo x > $d/approvals.json",
            "d=.gatebound; cp sub/approvals.json $d/",
            "export d=.gatebound; echo > ${d}/contract.json",
            'D="$PWD/.gatebound"; rm -rf "$D"',
            "echo x > $PWD/.gatebound/approvals.json",
            'echo x > "${PWD}/.gatebound/contract.json"',
        ))

    def test_other_variable_paths_allowed(self) -> None:
        self.allowed_after_approval((
            "d=build; echo x > $d/out.txt", "echo x > $HOME/notes.txt",
            "out=dist; cp a.json $out/", "echo x > $TMPDIR/approvals.json",
        ))


class TestGitPathspec(Forms):
    def test_restore_by_directory_is_denied(self) -> None:
        self.denied_always((
            "git checkout -- .gatebound",
            "git restore .gatebound",
            "git checkout HEAD~1 -- .gatebound",
            "git restore --source=HEAD~1 .gatebound",
            "git restore -s HEAD~1 -- .gatebound/",
            "git checkout stash@{0} -- .gatebound/",
            "git stash push -- .gatebound",
            "git reset HEAD -- .gatebound/approvals.json",
            "git -C src checkout -- ../.gatebound",
        ))

    def test_trust_boundary_and_normal_git_allowed(self) -> None:
        self.allowed_after_approval((
            "git checkout -- .", "git reset --hard", "git reset --hard HEAD~1",
            "git checkout -b feature", "git checkout main", "git stash", "git stash pop",
            "git restore src/app.py", "git clean -fdx",
        ))

    def test_git_reads_allowed_before_approval(self) -> None:
        for command in ("git status", "git diff .gatebound/approvals.json",
                        "git log -p -- .gatebound/approvals.json",
                        "git show HEAD:.gatebound/approvals.json", "git add .gatebound/",
                        'git commit -m "approve gate"'):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))


class TestLauncherUnchanged(Forms):
    def test_launcher_commands_allowed(self) -> None:
        launcher = 'python3 "%s"' % (PLUGIN / "bin" / "gatebound.py")
        for approved in (False, True):
            if approved:
                self.approve()
            for sub in ("approve spec/05-gate.md", "contract derive", "contract run",
                        "jobs status", "jobs clean"):
                with self.subTest(approved=approved, sub=sub):
                    self.assertIsNone(self.bash("%s %s" % (launcher, sub)))



class TestWholeStateDirectory(Forms):
    """ADR-0027 amendment B: everything under .gatebound/ is gatebound's, except
    config.json (the user's settings) and eval/** (evaluator scratch)."""

    GATEBOUND_ONLY = (
        ".gatebound/runs/contract-last.json", ".gatebound/runs/sess-1.json",
        ".gatebound/runs/hook-errors.log", ".gatebound/jobs/j1/tasks/t1/status.json",
        ".gatebound/jobs/j1/job.json", ".gatebound/attempts.json", ".gatebound/baseline.json",
        ".gatebound/notes.txt", ".GATEBOUND/Runs/X.json", "other/.gatebound/runs/x.json",
        ".gatebound/eval/../runs/x.json", ".gatebound/jobs",
    )
    USER_OWNED = (".gatebound/config.json", ".GATEBOUND/Config.json", ".gatebound/eval",
                  ".gatebound/eval/drive.mjs", ".gatebound/eval/shots/a.png", ".gatebound",
                  "src/runs/x.json", "config/status.json")

    def test_protected_state_covers_the_directory(self) -> None:
        from gatebound.gates import write as write_gate
        for raw in self.GATEBOUND_ONLY:
            with self.subTest(raw=raw):
                self.assertIsNotNone(write_gate.protected_state(self.root, raw))
        for raw in self.USER_OWNED:
            with self.subTest(raw=raw):
                self.assertIsNone(write_gate.protected_state(self.root, raw))

    def test_user_owned_names_followed_through_links(self) -> None:
        from gatebound.gates import write as write_gate
        (self.root / ".gatebound" / "runs").mkdir()
        symlink_or_skip(self, self.root / ".gatebound" / "runs", self.root / ".gatebound" / "eval",
                        target_is_directory=True)
        symlink_or_skip(self, self.root / ".gatebound" / "approvals.json",
                        self.root / ".gatebound" / "config.json")
        self.assertIsNotNone(write_gate.protected_state(self.root, ".gatebound/eval/x.json"))
        self.assertIsNotNone(write_gate.protected_state(self.root, ".gatebound/config.json"))

    def test_write_tool_denied_before_and_after_approval(self) -> None:
        for approved in (False, True):
            if approved:
                self.approve()
            for path in self.GATEBOUND_ONLY[:9]:
                with self.subTest(approved=approved, path=path):
                    self.assertDenied(self.write(path))
            for path in (".gatebound/config.json", ".gatebound/eval/drive.mjs"):
                with self.subTest(approved=approved, path=path):
                    self.assertIsNone(self.write(path))

    def test_evaluator_scratch_still_writable(self) -> None:
        import json
        edir = self.root / ".gatebound" / "jobs" / "j1" / "evaluate"
        edir.mkdir(parents=True)
        (edir / "task.json").write_text(json.dumps({"id": "evaluate"}), encoding="utf-8")
        self.approve()
        os.environ["GATEBOUND_TASK_ID"] = "evaluate"
        os.environ["GATEBOUND_JOB_ID"] = "j1"
        self.assertIsNone(self.write(".gatebound/eval/drive.mjs"))
        self.assertIsNone(self.bash("echo x > .gatebound/eval/server.log"))
        self.assertDenied(self.write(".gatebound/runs/contract-last.json"))
        self.assertDenied(self.bash("echo x > .gatebound/jobs/j1/status.json"))

    def test_eval_files_named_like_state_files_are_writable(self) -> None:
        # ADR-0031 decision 3. Observed on the first host run: the evaluator's
        # `contract run --json > .gatebound/eval/contract.json` was refused by the
        # base-name rule while `eval/run-result.json` was allowed.
        self.allowed_after_approval([
            "py -3 g.py contract run --json > .gatebound/eval/contract.json",
            "echo x > .gatebound/eval/approvals.json",
            "cd sub && echo x > ../.gatebound/eval/baseline.json",
        ])

    def test_the_base_name_rule_still_guards_what_eval_does_not_cover(self) -> None:
        self.denied_always([
            "echo x > .gatebound/eval/../contract.json",
            "cd .gatebound || true; echo x > contract.json",
            "echo x > .gatebound/contract.json",
        ])

    def test_bash_writes_denied(self) -> None:
        (self.root / "sub").mkdir()
        self.denied_always((
            "echo x > .gatebound/other.json",
            "jq . x > .gatebound/runs/contract-last.json",
            "mkdir -p .gatebound/jobs/t1 && echo '{}' > .gatebound/jobs/t1/status.json",
            "echo '{}' > .gatebound/jobs/t1/contract.json",
            "rm -rf .gatebound/runs", "rm -rf .gatebound/jobs/abc", "rm -rf .gatebound",
            "rm .gatebound/runs/*", "echo > .gatebound/*.json", "rm -f .gatebound/b*",
            "cp x .gatebound/", "cp -R sub .gatebound", "ln -sfn sub .gatebound",
            "cp -a other/.gatebound/. .gatebound", "mv .gatebound/attempts.json /tmp/a",
            "ln -s .gatebound/runs/contract-last.json l",
            "tar -xf a.tar -C .gatebound", "unzip -o a.zip -d .gatebound/runs",
            "find .gatebound -name '*.json' -exec rm {} +", "find .gatebound/runs -delete",
            "cd .gatebound && python3 -c \"open('approvals.json','w').write('{}')\"",
            "python3 -c \"import pathlib; pathlib.Path('.gatebound','approvals.json').write_text('{}')\"",
            "python3 -c \"open('.gatebound/runs/s.json','w')\"",
            "if true; then cd .gatebound; fi; echo {} > attempts.json",
            "d=.gatebound/runs; echo x > $d/s.json",
            "git checkout -- .gatebound/runs",
        ))

    def test_bash_normal_work_allowed(self) -> None:
        commands = (
            "mkdir .gatebound", "mkdir -p .gatebound/eval", "echo x > .gatebound/eval/log.txt",
            "rm -rf .gatebound/eval", "cp cfg.json .gatebound/config.json",
            "cp config.json .gatebound/", "cat .gatebound/runs/x.json", "jq . .gatebound/attempts.json",
            "ls -R .gatebound", "grep -r x .gatebound", "diff .gatebound/baseline.json /tmp/b",
            "python3 -m json.tool .gatebound/baseline.json", "wc -c .gatebound/approvals.json",
            "tar -czf backup.tgz .gatebound", "zip -r b.zip .gatebound",
            "rsync -a .gatebound/ /tmp/bk/", "cp -a .gatebound /tmp/bk", "git add .gatebound/",
            "git diff .gatebound/attempts.json", "rm -rf node_modules", "rm -rf build dist",
            "echo x > sub/approvals.json", "echo x > config/status.json",
            "cd .gatebound && ls", "tar -xf a.tar -C build", "find . -name '*.pyc' -delete",
            "d=.gatebound/eval; echo x > $d/log.txt",
        )
        for approved in (False, True):
            if approved:
                self.approve()
            for command in commands:
                with self.subTest(approved=approved, command=command):
                    result = self.bash(command)
                    reason = (result or {}).get("hookSpecificOutput", {}).get(
                        "permissionDecisionReason", "")
                    self.assertNotIn("ADR-0027", reason)
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command))

    def test_git_clean_stays_allowed(self) -> None:
        self.allowed_after_approval(("git clean -fdx", "git stash", "git checkout -b f"))

    def test_message_names_the_rule(self) -> None:
        reason = self.write(".gatebound/runs/contract-last.json")["hookSpecificOutput"][
            "permissionDecisionReason"]
        self.assertIn(".gatebound/runs/contract-last.json", reason)
        self.assertIn("config.json", reason)

    def test_setup_still_creates_config(self) -> None:
        import shutil
        import subprocess
        launcher = PLUGIN / "bin" / "gatebound.py"
        fresh = self.root / "fresh"
        fresh.mkdir()
        (fresh / ".git").mkdir()
        command = 'python3 "%s" workers set-default claude' % launcher
        event = self.tool("Bash", {"command": command})
        event["cwd"] = str(fresh)
        from gatebound.gates import bash as bash_gate
        self.assertIsNone(bash_gate.handle(event))
        proc = subprocess.run([sys.executable, str(launcher), "workers", "set-default", "claude"],
                              cwd=str(fresh), capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((fresh / ".gatebound" / "config.json").is_file())
        shutil.rmtree(fresh)


if __name__ == "__main__":
    unittest.main()
