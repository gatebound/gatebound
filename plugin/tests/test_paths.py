"""Tests for gatebound.paths — project root and state directory resolution."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

# Make the `gatebound` package importable however this suite is discovered:
# `discover -s plugin/tests` loads tests as top-level modules and puts only
# `plugin/tests` on sys.path, so `plugin/` has to be added explicitly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import paths


class TempProject(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # realpath: macOS /var -> /private/var symlink would break comparisons.
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestProjectRoot(TempProject):
    def test_finds_ancestor_with_gatebound_dir(self) -> None:
        (self.root / ".gatebound").mkdir()
        deep = self.root / "src" / "auth" / "nested"
        deep.mkdir(parents=True)
        self.assertEqual(paths.project_root(str(deep)), self.root)

    def test_finds_ancestor_with_git_dir(self) -> None:
        (self.root / ".git").mkdir()
        deep = self.root / "a" / "b"
        deep.mkdir(parents=True)
        self.assertEqual(paths.project_root(str(deep)), self.root)

    def test_gatebound_marker_wins_over_higher_git(self) -> None:
        (self.root / ".git").mkdir()
        inner = self.root / "packages" / "app"
        inner.mkdir(parents=True)
        (inner / ".gatebound").mkdir()
        self.assertEqual(paths.project_root(str(inner)), inner)

    def test_falls_back_to_cwd_when_no_marker(self) -> None:
        deep = self.root / "no" / "markers"
        deep.mkdir(parents=True)
        self.assertEqual(paths.project_root(str(deep)), deep)

    def test_none_uses_process_cwd(self) -> None:
        (self.root / ".gatebound").mkdir()
        previous = os.getcwd()
        os.chdir(self.root)
        try:
            self.assertEqual(paths.project_root(None), self.root)
        finally:
            os.chdir(previous)

    def test_nonexistent_cwd_does_not_raise(self) -> None:
        missing = self.root / "gone"
        self.assertIsInstance(paths.project_root(str(missing)), pathlib.Path)


class TestDerivedDirs(TempProject):
    def test_state_dir(self) -> None:
        self.assertEqual(paths.state_dir(self.root), self.root / ".gatebound")

    def test_spec_dir(self) -> None:
        self.assertEqual(paths.spec_dir(self.root), self.root / "spec")

    def test_runs_dir_and_hook_error_log(self) -> None:
        self.assertEqual(paths.runs_dir(self.root), self.root / ".gatebound" / "runs")
        self.assertEqual(
            paths.hook_error_log(self.root),
            self.root / ".gatebound" / "runs" / "hook-errors.log",
        )

    def test_jobs_dir(self) -> None:
        self.assertEqual(paths.jobs_dir(self.root), self.root / ".gatebound" / "jobs")

    def test_plugin_root_contains_plugin_json(self) -> None:
        found = paths.plugin_root()
        self.assertTrue((found / ".claude-plugin" / "plugin.json").is_file())

    def test_expand_argv_replaces_plugin_root_token(self) -> None:
        # ADR-0018 decision 1: argv runs without a shell, so gatebound expands
        # the one token task-gates.md documents before subprocess.run sees it.
        root = str(paths.plugin_root())
        out = paths.expand_argv(
            ["python3", "${CLAUDE_PLUGIN_ROOT}/gatebound/gates/tokens.py", "src/**"]
        )
        # argv[0] may be resolved to a full path (ADR-0019 decision 3c).
        self.assertEqual(out[1:], [root + "/gatebound/gates/tokens.py", "src/**"])

    def test_expand_argv_touches_nothing_else(self) -> None:
        argv = ["echo", "$HOME", "~/x", "${OTHER}", "*.ts"]
        self.assertEqual(paths.expand_argv(argv)[1:], argv[1:])

    def test_expand_argv_returns_a_new_list(self) -> None:
        argv = ["${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py"]
        paths.expand_argv(argv)
        self.assertEqual(argv, ["${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py"])

    def test_ensure_dir_is_idempotent(self) -> None:
        target = self.root / "x" / "y"
        paths.ensure_dir(target)
        paths.ensure_dir(target)
        self.assertTrue(target.is_dir())


class TestPythonCommand(unittest.TestCase):
    """Fix strings name an interpreter that runs. On a Windows host every
    printed `python3 ...` remedy failed in a session whose PATH predated
    Python's directory: `python3` there was the Microsoft Store placeholder
    (prints "Python", exit 49). The shell a remedy is pasted into need not
    see the PATH this process sees, so on Windows the remedy names the
    interpreter that is running."""

    def test_posix_keeps_python3(self) -> None:
        self.assertEqual(paths.python_command(windows=False), "python3")

    def test_windows_names_the_running_interpreter(self) -> None:
        exe = sys.executable.replace("\\", "/")
        self.assertEqual(paths.python_command(windows=True),
                         '"%s"' % exe if " " in exe else exe)

    def test_a_path_with_a_space_is_quoted_and_slashes_are_forward(self) -> None:
        from unittest import mock
        with mock.patch.object(sys, "executable", "C:\\Program Files\\Python312\\python.exe"):
            self.assertEqual(paths.python_command(windows=True),
                             '"C:/Program Files/Python312/python.exe"')
        with mock.patch.object(sys, "executable", "C:\\Python312\\python.exe"):
            self.assertEqual(paths.python_command(windows=True), "C:/Python312/python.exe")

    def test_cli_invocation_uses_it(self) -> None:
        self.assertTrue(paths.cli_invocation().startswith(paths.python_command() + " "))
        self.assertIn("gatebound.py", paths.cli_invocation())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
