"""The bin/gatebound.py launcher must work from a foreign cwd with no PYTHONPATH."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT / "bin" / "gatebound.py"


class TestLauncher(unittest.TestCase):
    def _run(self, args, cwd):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return subprocess.run([sys.executable, str(LAUNCHER), *args], cwd=cwd,
                              capture_output=True, text=True, env=env, timeout=30)

    def test_lang_from_foreign_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(["lang", "안녕하세요 기획서 만들어줘"], tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ko")

    def test_root_defaults_to_cwd_project_not_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / ".gatebound").mkdir()
            proc = self._run(["spec", "validate", "--json"], tmp)
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            # The report must be about the temp project, not the plugin's own tree.
            self.assertNotIn(str(PLUGIN_ROOT), proc.stdout)

    def test_output_survives_a_non_utf8_console(self) -> None:
        """Windows consoles often report cp1252; Korean findings and the em dash
        in the doctor banner must not crash the CLI (observed on a windows-latest
        fresh clone, 2026-10-04: UnicodeEncodeError in doctor, spec validate,
        contract derive and install)."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp) / "문서 테스트" / "my app"
            (project / "spec").mkdir(parents=True)
            (project / "spec" / "01-prd.md").write_text("# 메모\n\n## 문제\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            env["PYTHONIOENCODING"] = "cp1252"
            for args in (["doctor"], ["spec", "validate", "--json"], ["spec", "validate"]):
                proc = subprocess.run([sys.executable, str(LAUNCHER), *args], cwd=str(project),
                                      capture_output=True, text=True, env=env, timeout=60,
                                      encoding="utf-8", errors="replace")
                # The exit code is the command's own verdict (this bare project
                # fails validation); what must not happen is a crash.
                self.assertNotIn("Traceback", proc.stderr + proc.stdout, args)
                self.assertNotIn("UnicodeEncodeError", proc.stderr, args)
                self.assertIn("gatebound", proc.stdout + proc.stderr, args)

    def test_unknown_subcommand_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(["nope"], tmp)
        self.assertEqual(proc.returncode, 2)
