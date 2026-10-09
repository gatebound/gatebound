"""ADR-0019 decision 3: Windows in the same tree.

These run on every OS. Windows-only branches are exercised by flipping the
module's platform switch and stubbing the process calls, so a POSIX CI run
still pins them; the windows-latest CI job runs the whole suite natively.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import hookio, jobs, paths  # noqa: E402
from tests._stubs import symlink_or_skip  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]

#: ADR-0030: each name is probed silently before it runs the gate, so a Store
#: placeholder that prints "Python" and exits non-zero never reaches stdout.
PROBE = '-c "import sys;sys.exit(sys.version_info<(3,9))" >/dev/null 2>&1'
CHAIN_RE = re.compile(
    r'^\(python3 ' + re.escape(PROBE) + r' && python3 "(?P<s>\$\{CLAUDE_PLUGIN_ROOT\}/gatebound/gates/\w+\.py)"\)'
    r' \|\| \(python ' + re.escape(PROBE) + r' && python "(?P=s)"\)'
    r' \|\| py -3 "(?P=s)"$'
)


def chain(script: str, suffix: str = "") -> str:
    """The hook command for *script*, as hooks.json spells it."""
    run = '"%s"%s' % (script, suffix)
    return ("(python3 %s && python3 %s) || (python %s && python %s) || py -3 %s"
            % (PROBE, run, PROBE, run, run))


def _stub(bindir: pathlib.Path, name: str, body: str) -> None:
    path = bindir / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class TestHookInterpreterChain(unittest.TestCase):
    """3a (ADR-0030): a hook must start where only `python` or `py` exists, and a
    placeholder on PATH must not leak into the hook's stdout."""

    def test_every_plugin_hook_probes_then_runs_three_interpreters(self) -> None:
        data = json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = [h["command"] for group in data["hooks"].values() for e in group for h in e["hooks"]]
        self.assertTrue(commands)
        for command in commands:
            self.assertRegex(command, CHAIN_RE)

    @unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "needs a POSIX sh")
    def test_chain_falls_through_to_python_when_python3_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            _stub(bindir, "python", 'exec "%s" "$@"\n' % sys.executable)
            script = bindir / "probe.py"
            script.write_text("print('ran')\n", encoding="utf-8")
            proc = subprocess.run(
                [shutil.which("sh"), "-c", chain(str(script))],
                env={"PATH": str(bindir)},  # no python3, no py
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "ran\n")

    @unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "needs a POSIX sh")
    def test_store_placeholder_never_reaches_stdout(self) -> None:
        """Windows ships `python3`/`python` placeholders that print `Python`
        with no newline and exit 49 (owner's PC, 2026-10-04). The old chain
        produced `PythonPython{json}`; the probed chain must not."""
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            _stub(bindir, "python3", "printf Python\nexit 49\n")
            _stub(bindir, "python", "printf Python\nexit 49\n")
            _stub(bindir, "py", 'shift\nexec "%s" "$@"\n' % sys.executable)  # py -3 <script>
            script = bindir / "gate.py"
            script.write_text("import json; print(json.dumps({'decision': 'deny'}))\n", encoding="utf-8")
            old = 'python3 "{s}" || python "{s}" || py -3 "{s}"'.format(s=script)
            polluted = subprocess.run([shutil.which("sh"), "-c", old], env={"PATH": str(bindir)},
                                      capture_output=True, text=True, timeout=30)
            clean = subprocess.run([shutil.which("sh"), "-c", chain(str(script))], env={"PATH": str(bindir)},
                                   capture_output=True, text=True, timeout=30)
        # the bug, pinned so the test is known to exercise it
        self.assertTrue(polluted.stdout.startswith("PythonPython"), polluted.stdout)
        # the fix
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(json.loads(clean.stdout), {"decision": "deny"})

    @unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "needs a POSIX sh")
    def test_a_python2_on_path_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            # a "python3" whose version check fails, standing in for Python 2 or a broken install
            _stub(bindir, "python3", 'case "$*" in *version_info*) exit 1;; esac\necho WRONG\n')
            _stub(bindir, "python", 'exec "%s" "$@"\n' % sys.executable)
            script = bindir / "gate.py"
            script.write_text("print('ran')\n", encoding="utf-8")
            proc = subprocess.run([shutil.which("sh"), "-c", chain(str(script))], env={"PATH": str(bindir)},
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.stdout, "ran\n", proc.stderr)

    def test_codex_layer_uses_the_same_probed_chain(self) -> None:
        from gatebound import hosts
        data = hosts.codex_hooks(PLUGIN_DIR)
        commands = [h["command"] for group in data["hooks"].values() for e in group for h in e["hooks"]]
        self.assertTrue(commands)
        for command in commands:
            self.assertIn("--host codex", command)
            self.assertIn("(python3 %s && python3 " % PROBE, command)
            self.assertNotRegex(command, r'^python3 "')


#: ADR-0034: constructs Windows PowerShell 5.1 rejects or misreads; a Codex
#: hook command containing any of them runs nothing on Windows.
PS51_REJECTS = ("||", "&&", "/dev/null", ">NUL")


def _cmd_stub(bindir: pathlib.Path, name: str, body: str) -> None:
    # cmd reads a batch file in the OEM code page; the interpreter's path may
    # hold non-ASCII characters (a Korean user folder).
    (bindir / (name + ".cmd")).write_text("@echo off\r\n" + body, encoding="oem")


class TestPluginHooksCarryAWindowsCommand(unittest.TestCase):
    """ADR-0038: a Codex *plugin* install on Windows runs `commandWindows` too
    (observed with Codex 0.160.0), so the plugin's own hooks.json carries one.
    Claude Code ignores the key and runs `command` (observed, Claude Code
    2.1.289), so the sh chain stays exactly as ADR-0030 pins it."""

    def _hooks(self) -> list:
        data = json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        return [h for group in data["hooks"].values() for e in group for h in e["hooks"]]

    def test_every_plugin_hook_has_a_powershell_form_for_the_same_script(self) -> None:
        from gatebound import hosts
        hooks = self._hooks()
        self.assertTrue(hooks)
        for h in hooks:
            win = h.get("commandWindows", "")
            self.assertEqual(hosts.hook_script(win), hosts.hook_script(h["command"]), win)
            for bad in PS51_REJECTS:
                self.assertNotIn(bad, win)
            # the root comes from the environment, never from text a path could break
            self.assertIn("$env:PLUGIN_ROOT", win)
            self.assertIn("$env:CLAUDE_PLUGIN_ROOT", win)
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", win)
            # the host is read from PLUGIN_ROOT (ADR-0019), as for `command`
            self.assertNotIn("--host", win)

    def test_the_builder_and_the_file_agree(self) -> None:
        from gatebound import hosts
        for h in self._hooks():
            rel = hosts.hook_script(h["command"]).replace("${CLAUDE_PLUGIN_ROOT}/", "", 1)
            self.assertEqual(h["commandWindows"], hosts.plugin_hook_command_windows(rel))


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "needs Windows PowerShell")
class TestPluginWindowsCommandRuns(unittest.TestCase):
    """ADR-0038: the plugin form finds the gate under PLUGIN_ROOT (Codex) or,
    failing that, CLAUDE_PLUGIN_ROOT, whatever characters the folder holds."""

    def _run(self, env_root: dict) -> subprocess.CompletedProcess:
        from gatebound import hosts
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "it's $here"
            (root / "gatebound" / "gates").mkdir(parents=True)
            (root / "gatebound" / "gates" / "gate.py").write_text(
                "import json, sys\nprint(json.dumps({'seen': json.loads(sys.stdin.read())['tool_name']}))\n",
                encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")}
            env.update({k: str(root) for k in env_root})
            return subprocess.run(
                [shutil.which("powershell"), "-NoProfile", "-NonInteractive", "-Command",
                 hosts.plugin_hook_command_windows("gatebound/gates/gate.py")],
                input='{"tool_name": "apply_patch"}', env=env, capture_output=True, text=True, timeout=60)

    def test_plugin_root_is_used(self) -> None:
        proc = self._run({"PLUGIN_ROOT": 1})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"seen": "apply_patch"})

    def test_claude_plugin_root_is_the_fallback(self) -> None:
        proc = self._run({"CLAUDE_PLUGIN_ROOT": 1})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"seen": "apply_patch"})


class TestCodexWindowsCommand(unittest.TestCase):
    """ADR-0034: Codex on Windows runs a hook command in Windows PowerShell 5.1,
    so the Codex layer carries a `commandWindows` that probes like ADR-0030."""

    def _hooks(self) -> list:
        from gatebound import hosts
        data = hosts.codex_hooks(PLUGIN_DIR)
        return [h for group in data["hooks"].values() for e in group for h in e["hooks"]]

    def test_every_codex_hook_has_a_windows_command_for_the_same_script(self) -> None:
        from gatebound import hosts
        hooks = self._hooks()
        self.assertTrue(hooks)
        for h in hooks:
            win = h.get("commandWindows", "")
            self.assertIn("--host codex", win)
            self.assertEqual(hosts.hook_script(win), hosts.hook_script(h["command"]))
            self.assertTrue(hosts.hook_script(win).endswith(".py"), win)
            for bad in PS51_REJECTS:
                self.assertNotIn(bad, win)
            # ADR-0030 order: python3, python, then py -3
            self.assertLess(win.index("'python3','python'"), win.index("py -3"))

    def test_a_quote_in_the_script_path_is_doubled(self) -> None:
        from gatebound import hosts
        win = hosts.hook_command_windows("C:/it's here/gate.py", " --host codex")
        self.assertIn("$s='C:/it''s here/gate.py'", win)
        self.assertEqual(hosts.hook_script(win), "C:/it's here/gate.py")


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "needs Windows PowerShell")
class TestCodexWindowsCommandRuns(unittest.TestCase):
    """ADR-0034: the PowerShell form run the way Codex runs it, with PATH
    holding only stubs, so each branch of the probe is exercised."""

    def _run(self, bindir: pathlib.Path, script: pathlib.Path, stdin: str = "") -> subprocess.CompletedProcess:
        from gatebound import hosts
        env = dict(os.environ, PATH=str(bindir))
        return subprocess.run(
            [shutil.which("powershell"), "-NoProfile", "-NonInteractive", "-Command",
             hosts.hook_command_windows(str(script), " --host codex")],
            input=stdin, env=env, capture_output=True, text=True, timeout=60,
        )

    def _gate(self, bindir: pathlib.Path) -> pathlib.Path:
        script = bindir / "gate's.py"
        script.write_text(
            "import json, sys\n"
            "event = json.loads(sys.stdin.read())\n"
            "print(json.dumps({'decision': 'deny', 'seen': event['tool_name'], 'argv': sys.argv[1:]}))\n",
            encoding="utf-8")
        return script

    def test_placeholder_is_skipped_and_python_runs_the_gate_with_the_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            _cmd_stub(bindir, "python3", "<nul set /p=Python\r\nexit /b 49\r\n")
            _cmd_stub(bindir, "python", '"%s" %%*\r\n' % sys.executable)
            proc = self._run(bindir, self._gate(bindir), '{"tool_name": "apply_patch"}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout),
                         {"decision": "deny", "seen": "apply_patch", "argv": ["--host", "codex"]})

    def test_py_launcher_is_reached_when_no_name_is_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            _cmd_stub(bindir, "python3", "<nul set /p=Python\r\nexit /b 49\r\n")
            _cmd_stub(bindir, "python", "<nul set /p=Python\r\nexit /b 49\r\n")
            _cmd_stub(bindir, "py", 'shift\r\n"%s" %%1 %%2 %%3 %%4\r\n' % sys.executable)
            proc = self._run(bindir, self._gate(bindir), '{"tool_name": "Bash"}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["seen"], "Bash")

    def test_no_interpreter_fails_aloud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = pathlib.Path(tmp)
            proc = self._run(bindir, self._gate(bindir), "{}")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("no Python 3.9+", proc.stderr)


class TestHookStdioIsUtf8(unittest.TestCase):
    """3b: a Korean prompt survives a cp949 console."""

    def test_utf8_round_trip_under_a_legacy_locale_encoding(self) -> None:
        program = (
            "import sys; sys.path.insert(0, %r)\n"
            "from gatebound import hookio\n"
            "hookio.run(lambda e: {'echo': e.get('prompt')}, exit_process=False)\n"
        ) % str(PLUGIN_DIR)
        env = dict(os.environ, PYTHONIOENCODING="cp949")
        env.pop("PYTHONUTF8", None)
        event = json.dumps({"prompt": "뭘 만들지 모르겠어 — 한글"}, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, "-c", program],
            input=event.encode("utf-8"), capture_output=True, env=env, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout.decode("utf-8"))["echo"], "뭘 만들지 모르겠어 — 한글")


class TestArgvZeroIsResolved(unittest.TestCase):
    """3c: `npm` must find `npm.cmd` without a shell."""

    def test_bare_program_name_is_resolved_through_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            name = "gatebound-fake-tool"
            exe = pathlib.Path(tmp) / (name + (".cmd" if os.name == "nt" else ""))
            exe.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {"PATH": tmp + os.pathsep + os.environ.get("PATH", "")}):
                out = paths.expand_argv([name, "run", "e2e"])
        self.assertEqual(pathlib.Path(out[0]).resolve(), exe.resolve())
        self.assertEqual(out[1:], ["run", "e2e"])

    def test_unresolvable_name_passes_through(self) -> None:
        self.assertEqual(paths.expand_argv(["no-such-tool-xyz", "a"]), ["no-such-tool-xyz", "a"])

    def test_explicit_path_is_left_alone(self) -> None:
        self.assertEqual(paths.expand_argv(["./node_modules/.bin/x"]), ["./node_modules/.bin/x"])


class TestWindowsProcessControl(unittest.TestCase):
    """3d: on Windows, os.kill(pid, 0) terminates the process; never call it.

    These cover the fallback the native probe (ADR-0039) hands over to when
    it cannot answer: tasklist for liveness, PowerShell for age.
    """

    def setUp(self) -> None:
        self.calls = []
        patcher_win = mock.patch.object(jobs, "_IS_WINDOWS", True)
        patcher_kill = mock.patch.object(jobs.os, "kill", side_effect=AssertionError("os.kill on Windows"))
        patcher_run = mock.patch.object(jobs.subprocess, "run", side_effect=self.fake_run)
        patcher_native = mock.patch.object(jobs, "_win_process_info", return_value=None)
        for p in (patcher_win, patcher_kill, patcher_run, patcher_native):
            p.start()
            self.addCleanup(p.stop)

    def fake_run(self, argv, **kwargs):
        self.calls.append(list(argv))
        out = b""
        if argv[0] == "tasklist":
            out = b'"python.exe","4242","Console","1","10,000 K"\r\n'
        elif argv[0] == "powershell":
            out = b"30.5\r\n"
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr=b"")

    def test_liveness_uses_tasklist(self) -> None:
        self.assertTrue(jobs._pid_alive(4242))
        self.assertEqual(self.calls[0][0], "tasklist")

    def test_age_uses_powershell(self) -> None:
        self.assertAlmostEqual(jobs._process_age_s(4242), 30.5)
        self.assertEqual(self.calls[0][0], "powershell")

    def test_terminate_uses_taskkill_tree(self) -> None:
        self.assertTrue(jobs._terminate_pid(4242, grace_s=0))
        killed = [c for c in self.calls if c[0] == "taskkill"]
        self.assertTrue(killed)
        self.assertIn("/T", killed[0])
        self.assertIn("4242", killed[0])


class TestWindowsNativeProcessInfo(unittest.TestCase):
    """ADR-0039: liveness and age come from kernel32, with no child process.

    A PowerShell probe took longer than its 10 s limit on a busy runner, so
    `jobs stop` listed a live worker as `skipped` and never ended it.
    """

    def setUp(self) -> None:
        self.calls = []
        patcher_win = mock.patch.object(jobs, "_IS_WINDOWS", True)
        patcher_kill = mock.patch.object(jobs.os, "kill", side_effect=AssertionError("os.kill on Windows"))
        patcher_run = mock.patch.object(jobs.subprocess, "run", side_effect=self.fake_run)
        for p in (patcher_win, patcher_kill, patcher_run):
            p.start()
            self.addCleanup(p.stop)

    def fake_run(self, argv, **kwargs):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    def test_a_live_process_is_answered_without_spawning_anything(self) -> None:
        import time as _time
        with mock.patch.object(jobs, "_win_process_info", return_value=(True, _time.time() - 30.0)):
            self.assertTrue(jobs._pid_alive(4242))
            self.assertAlmostEqual(jobs._process_age_s(4242), 30.0, delta=1.0)
        self.assertEqual(self.calls, [])

    def test_a_dead_process_is_not_alive_and_has_no_age(self) -> None:
        with mock.patch.object(jobs, "_win_process_info", return_value=(False, None)):
            self.assertFalse(jobs._pid_alive(4242))
            self.assertIsNone(jobs._process_age_s(4242))
        self.assertEqual(self.calls, [])

    def test_a_live_process_without_times_falls_back_to_powershell_for_age(self) -> None:
        with mock.patch.object(jobs, "_win_process_info", return_value=(True, None)):
            self.assertTrue(jobs._pid_alive(4242))
            jobs._process_age_s(4242)
        self.assertEqual([c[0] for c in self.calls], ["powershell"])

    def test_filetime_converts_to_unix_time(self) -> None:
        # 1970-01-01T00:00:00Z is 116444736000000000 hundred-nanosecond
        # intervals after 1601-01-01.
        value = 116444736000000000
        self.assertEqual(jobs._filetime_to_epoch(value >> 32, value & 0xFFFFFFFF), 0.0)
        value += 15 * 10_000_000
        self.assertAlmostEqual(jobs._filetime_to_epoch(value >> 32, value & 0xFFFFFFFF), 15.0)

    def _fake_kernel32(self, open_result, last_error=0, exit_code=259, times_ok=True):
        """A stand-in for ctypes.WinDLL("kernel32") driving each branch."""
        import ctypes
        calls = {"open": 0, "close": 0}

        def open_process(access, inherit, pid):
            calls["open"] += 1
            return open_result

        def exit_code_of(handle, code_ref):
            code_ref._obj.value = exit_code
            return 1

        def times_of(handle, created, exited, kernel, user):
            value = 116444736000000000 + 7 * 10_000_000
            created._obj.dwHighDateTime, created._obj.dwLowDateTime = value >> 32, value & 0xFFFFFFFF
            return 1 if times_ok else 0

        def close_handle(handle):
            calls["close"] += 1
            return 1

        k32 = mock.Mock()
        k32.OpenProcess, k32.GetExitCodeProcess = open_process, exit_code_of
        k32.GetProcessTimes, k32.CloseHandle = times_of, close_handle
        patches = [mock.patch.object(ctypes, "WinDLL", return_value=k32, create=True),
                   mock.patch.object(ctypes, "get_last_error", return_value=last_error, create=True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return calls

    def test_no_process_with_the_pid_reads_dead(self) -> None:
        calls = self._fake_kernel32(open_result=None, last_error=87)
        self.assertEqual(jobs._win_process_info(4240), (False, None))
        self.assertEqual(calls["close"], 0)

    def test_access_denied_gives_no_answer(self) -> None:
        self._fake_kernel32(open_result=None, last_error=5)
        self.assertIsNone(jobs._win_process_info(4240))

    def test_a_live_process_reports_its_creation_time_and_closes_the_handle(self) -> None:
        calls = self._fake_kernel32(open_result=1234)
        self.assertEqual(jobs._win_process_info(4240), (True, 7.0))
        self.assertEqual(calls["close"], 1)

    def test_an_exited_process_reads_dead_and_closes_the_handle(self) -> None:
        calls = self._fake_kernel32(open_result=1234, exit_code=1)
        self.assertEqual(jobs._win_process_info(4240), (False, None))
        self.assertEqual(calls["close"], 1)

    def test_unreadable_times_leave_alive_without_age(self) -> None:
        self._fake_kernel32(open_result=1234, times_ok=False)
        self.assertEqual(jobs._win_process_info(4240), (True, None))

    def test_a_pid_no_windows_process_can_have_gets_no_native_answer(self) -> None:
        calls = self._fake_kernel32(open_result=1234)
        for pid in (0, -4, 4243, 2 ** 32 + 4240):
            self.assertIsNone(jobs._win_process_info(pid), pid)
        self.assertEqual(calls["open"], 0)

    def test_off_windows_the_native_probe_answers_nothing(self) -> None:
        if os.name == "nt":
            self.skipTest("POSIX-only property")
        self.assertIsNone(jobs._win_process_info(os.getpid()))


@unittest.skipUnless(os.name == "nt", "needs real Windows")
class TestWindowsNativeProcessInfoLive(unittest.TestCase):
    """The kernel32 probe against real processes on a Windows host."""

    def test_a_running_child_is_alive_with_a_fresh_age_and_dead_after_exit(self) -> None:
        import time as _time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            info = jobs._win_process_info(child.pid)
            self.assertIsNotNone(info)
            alive, created = info
            self.assertTrue(alive)
            self.assertIsNotNone(created)
            self.assertLess(abs((_time.time() - created)), 30.0)
            self.assertTrue(jobs._pid_alive(child.pid))
        finally:
            child.kill()
            child.wait(timeout=10)
        self.assertFalse(jobs._pid_alive(child.pid))


class TestMsysPaths(unittest.TestCase):
    """3e: Git Bash reports /c/work/app for C:\\work\\app."""

    def test_msys_drive_path_becomes_a_windows_path(self) -> None:
        self.assertEqual(paths.from_msys("/c/work/app/x.ts", windows=True), "C:/work/app/x.ts")

    def test_other_paths_unchanged(self) -> None:
        self.assertEqual(paths.from_msys("/c/work/app", windows=False), "/c/work/app")
        self.assertEqual(paths.from_msys("src/x.ts", windows=True), "src/x.ts")
        self.assertEqual(paths.from_msys("/usr/bin/x", windows=True), "/usr/bin/x")


class TestSymlinkOrSkip(unittest.TestCase):
    """Windows needs a privilege (or Developer Mode) to create a symlink and
    refuses with WinError 1314 otherwise. A symlink test skips there, saying
    why; any other failure to create the link is still an error."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        (self.root / "real.txt").write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def refuse(self, exc: BaseException):
        return mock.patch("tests._stubs.os.symlink", side_effect=exc)

    def test_missing_privilege_skips_with_the_reason(self) -> None:
        err = OSError(22, "A required privilege is not held by the client")
        err.winerror = 1314
        with self.refuse(err):
            with self.assertRaises(unittest.SkipTest) as ctx:
                symlink_or_skip(self, self.root / "real.txt", self.root / "link.txt")
        self.assertIn("privilege", str(ctx.exception))

    def test_no_symlink_support_skips(self) -> None:
        with self.refuse(NotImplementedError("no symlinks")):
            with self.assertRaises(unittest.SkipTest):
                symlink_or_skip(self, self.root / "real.txt", self.root / "link.txt")

    def test_any_other_error_is_raised(self) -> None:
        with self.refuse(FileExistsError(17, "exists")):
            with self.assertRaises(FileExistsError):
                symlink_or_skip(self, self.root / "real.txt", self.root / "link.txt")

    def test_creates_the_link_when_allowed(self) -> None:
        link = self.root / "link.txt"
        with mock.patch("tests._stubs.os.symlink") as made:
            symlink_or_skip(self, self.root / "real.txt", link, target_is_directory=False)
        made.assert_called_once_with(str(self.root / "real.txt"), str(link),
                                     target_is_directory=False)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
