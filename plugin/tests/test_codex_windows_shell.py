"""ADR-0035: under Codex on Windows a `Bash` event carries PowerShell text, so
the Bash gate also reads it as the PowerShell gate does. Pure parsing; the
platform is passed in, so the suite pins both directions on any OS."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import hookio, names  # noqa: E402
from gatebound.gates import bash as bash_gate  # noqa: E402
from tests.test_gate_powershell import PLUGIN, READS, PSProject  # noqa: E402

GATE_SCRIPT = PLUGIN / "gatebound" / "gates" / "bash.py"

PS_WRITES_INTO_CODE = (
    "Set-Content -Path src/run.py -Value 'x'",
    "'x' | Out-File src\\run.py",
    "New-Item -ItemType File -Path src/run.py",
)


class CodexWindowsProject(PSProject):
    host = "codex"
    windows = True

    def run_ps(self, command: str, **kwargs):
        return bash_gate.handle(self.event(command, tool="Bash", **kwargs),
                                host=self.host, windows=self.windows)


class TestCodexOnWindows(CodexWindowsProject):
    def test_powershell_writes_into_code_denied_before_approval(self) -> None:
        for cmd in PS_WRITES_INTO_CODE:
            with self.subTest(cmd=cmd):
                self.assertDenied(cmd, "src/run.py")

    def test_sh_redirect_still_denied(self) -> None:
        self.assertDenied("echo x > src/run.py", "src/run.py")

    def test_docs_allowed_before_approval_and_code_after(self) -> None:
        self.assertAllowed("Set-Content -Path docs/notes.md -Value x")
        self.approve()
        for cmd in PS_WRITES_INTO_CODE:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_reads_git_and_npm_allowed(self) -> None:
        for cmd in READS:
            with self.subTest(cmd=cmd):
                self.assertAllowed(cmd)

    def test_protected_state_denied_with_no_restriction(self) -> None:
        (self.root / "spec").rename(self.root / "spec-away")  # rule (a) inactive
        self.assertDenied("Remove-Item .gatebound\\approvals.json")

    def test_worker_never_approves(self) -> None:
        os.environ[names.env_prefixes()[0] + "TASK_ID"] = "t1"
        self.assertDenied("& python plugin/bin/gatebound.py approve spec/05-gate.md")


class TestCodexOffWindowsUnchanged(CodexWindowsProject):
    windows = False

    def test_powershell_text_is_not_read(self) -> None:
        self.assertAllowed("Set-Content -Path src/run.py -Value 'x'")


class TestClaudeOnWindowsUnchanged(CodexWindowsProject):
    host = "claude"

    def test_powershell_text_is_not_read(self) -> None:
        self.assertAllowed("Set-Content -Path src/run.py -Value 'x'")


class TestProcess(CodexWindowsProject):
    @unittest.skipUnless(os.name == "nt", "the platform switch is the real one in a process")
    def test_gate_process_with_host_codex_denies(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), "--host", "codex"],
            input=json.dumps(self.event(PS_WRITES_INTO_CODE[0], tool="Bash")),
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_internal_error_exits_zero(self) -> None:
        from gatebound.gates import powershell as ps_gate
        original = ps_gate.judge

        def boom(*_a, **_k):
            raise RuntimeError("judge exploded")

        ps_gate.judge = boom
        try:
            code = hookio.run(lambda e: bash_gate.handle(e, host="codex", windows=True),
                              stdin=io.StringIO(json.dumps(self.event("Get-ChildItem", tool="Bash"))),
                              exit_process=False)
        finally:
            ps_gate.judge = original
        self.assertEqual(code, 0)
        log = self.root / ".gatebound" / "runs" / "hook-errors.log"
        self.assertIn("judge exploded", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
