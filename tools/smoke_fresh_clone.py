#!/usr/bin/env python3
"""smoke_fresh_clone.py — does a fresh download of gatebound actually work here?

This is the test a new user runs implicitly: clone the public repository,
point the CLI at a small project, and see whether the hooks, the contract and
the worker gates behave. CI's unit suite proves the code; this proves the
*install path* on the machine it runs on — in particular on Windows, where
the interpreter chain (`python3 || python || py -3`), UTF-8 stdio, Git Bash
hook execution and paths with Korean characters and spaces are all in play.

Every step records ``ok``, ``fail`` or ``unverified`` and the run continues,
so one broken step does not hide the others. The exit code is 1 when any step
is ``fail``; ``unverified`` (a tool this machine lacks) never rounds either way.

    python3 tools/smoke_fresh_clone.py [--repo URL] [--ref main]
        [--work DIR] [--clone DIR] [--skip-e2e] [--summary FILE.md]

``--clone DIR`` reuses an existing checkout instead of cloning (local runs).
``--work DIR`` is where the clone and the sample project are created (a temp
directory by default).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_REPO = "https://github.com/gatebound/gatebound.git"
#: Korean folder name plus a space: the shape that tripped a Windows participant.
PROJECT_REL = pathlib.Path("문서 테스트") / "my app"
SESSION = "smoke-fresh-clone"

OK, WARN, FAIL, UNVERIFIED = "ok", "warn", "fail", "unverified"


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


class Report:
    def __init__(self) -> None:
        self.steps: List[Dict[str, Any]] = []

    def add(self, name: str, verdict: str, detail: str, output: str = "") -> None:
        self.steps.append({"name": name, "verdict": verdict, "detail": detail, "output": output})
        print("%-11s %-28s %s" % (verdict, name, detail), flush=True)

    @property
    def verdict(self) -> str:
        vs = [s["verdict"] for s in self.steps]
        if FAIL in vs:
            return FAIL
        if UNVERIFIED in vs:
            return UNVERIFIED
        if WARN in vs:
            return WARN
        return OK

    def markdown(self, env: Dict[str, str]) -> str:
        lines = ["# gatebound fresh-clone smoke — %s" % self.verdict, ""]
        lines += ["- %s: %s" % (k, v) for k, v in env.items()]
        lines += ["", "| step | verdict | detail |", "|---|---|---|"]
        for s in self.steps:
            lines.append("| %s | %s | %s |" % (s["name"], s["verdict"], s["detail"].replace("|", "\\|")))
        failing = [s for s in self.steps if s["verdict"] in (FAIL, UNVERIFIED) and s["output"]]
        if failing:
            lines.append("")
            for s in failing:
                lines += ["<details><summary>%s output</summary>" % s["name"], "", "```",
                          s["output"][-3000:], "```", "</details>", ""]
        return "\n".join(lines) + "\n"


def sh(argv: List[str], cwd: pathlib.Path, env: Optional[Dict[str, str]] = None,
       stdin: Optional[str] = None, timeout: int = 600) -> Tuple[int, str]:
    """Run *argv*; return (exit, combined output). Never raises for a non-zero exit."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), env=full_env, input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except FileNotFoundError as exc:
        return 127, "not found: %s" % exc
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds: %s" % (timeout, " ".join(argv))
    return proc.returncode, proc.stdout or ""


def find_interpreters() -> List[Tuple[List[str], str]]:
    """Every interpreter the hooks' fallback chain would try, with its version."""
    found: List[Tuple[List[str], str]] = []
    for argv in (["python3"], ["python"], ["py", "-3"]):
        if shutil.which(argv[0]) is None:
            continue
        code, out = sh(argv + ["--version"], pathlib.Path.cwd(), timeout=30)
        if code == 0:
            found.append((argv, out.strip()))
    return found


def hook_commands(plugin: pathlib.Path) -> Dict[str, str]:
    """{event or matcher: command string} straight from hooks.json."""
    data = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    out: Dict[str, str] = {}
    for event, entries in data["hooks"].items():
        for entry in entries:
            key = entry.get("matcher") or event
            out["%s:%s" % (event, key)] = entry["hooks"][0]["command"]
    return out


def git_bash() -> Optional[str]:
    """The bash Claude Code uses for hooks.

    On Windows that is Git Bash, never ``C:\\Windows\\System32\\bash.exe``
    (the WSL launcher, which is what a bare ``bash`` on PATH resolves to on a
    GitHub runner and prints "no installed distributions"). Located from
    ``git --exec-path`` first, then the default install path, then PATH with
    System32 excluded.
    """
    if not sys.platform.startswith("win"):
        return shutil.which("bash")
    code, out = sh(["git", "--exec-path"], pathlib.Path.cwd(), timeout=30)
    candidates: List[pathlib.Path] = []
    if code == 0 and out.strip():
        exec_path = pathlib.Path(out.strip())
        for up in (exec_path, *exec_path.parents):
            candidates.append(up / "bin" / "bash.exe")
            candidates.append(up / "usr" / "bin" / "bash.exe")
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files (x86)"):
        candidates.append(pathlib.Path(base) / "Git" / "bin" / "bash.exe")
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    found = shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    return None


def run_hook(command: str, plugin: pathlib.Path, event: Dict[str, Any],
             cwd: pathlib.Path) -> Tuple[int, str]:
    """Run a hook the way Claude Code does: the hooks.json string through Git Bash."""
    bash = git_bash()
    if bash is None:
        return 127, "no Git Bash found: Claude Code on Windows needs Git for Windows to run hooks"
    root = plugin.resolve().as_posix()  # forward slashes: Git Bash and Windows Python both accept them
    return sh([bash, "-c", command], cwd, env={"CLAUDE_PLUGIN_ROOT": root},
              stdin=json.dumps(event), timeout=120)


def doctor_step(report: "Report", name: str, code: int, out: str, json_out: str) -> None:
    """``fail`` only for a failing axis other than the worker CLI being absent.

    A runner has no claude or codex binary, so the workers axis is ``fail`` by
    design; that says nothing about the install path and is reported as
    ``unverified`` with the reason, never rounded to ``ok``.
    """
    banner = out.splitlines()[0].split("(root")[0].strip() if out.strip() else "exit %d" % code
    if "Traceback" in out:
        report.add(name, FAIL, "crashed: %s" % out.strip().splitlines()[-1][:100], out)
        return
    try:
        axes = json.loads(json_out).get("axes", [])
    except ValueError:
        report.add(name, FAIL if code != 0 else OK, banner, out + json_out)
        return
    failing = [a for a in axes if a.get("verdict") == FAIL]
    only_workers = failing and all(a.get("axis") == "workers" and "not found" in a.get("detail", "") for a in failing)
    if not failing and code == 0:
        report.add(name, OK, banner, out)
    elif only_workers:
        report.add(name, UNVERIFIED, "%s; only the workers axis fails: no claude/codex CLI on this machine" % banner, out)
    else:
        report.add(name, FAIL, "%s: %s" % (banner, "; ".join(a.get("axis", "?") for a in failing)), out)


def decision(output: str) -> Optional[str]:
    """permissionDecision from a hook's JSON stdout, or None when it printed nothing."""
    text = output.strip()
    if not text:
        return None
    try:
        data = json.loads(text.splitlines()[-1])
    except ValueError:
        return "unparsable"
    hso = data.get("hookSpecificOutput") or {}
    return hso.get("permissionDecision") or ("context" if hso.get("additionalContext") else "json")


def main(argv: List[str]) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(prog="smoke_fresh_clone")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--work", default=None)
    parser.add_argument("--clone", default=None, help="reuse this checkout instead of cloning")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--summary", default=None)
    args = parser.parse_args(argv)

    report = Report()
    work = pathlib.Path(args.work).resolve() if args.work else pathlib.Path(tempfile.mkdtemp(prefix="gk-smoke-"))
    work.mkdir(parents=True, exist_ok=True)
    env_info = {
        "platform": platform.platform(),
        "python (this script)": sys.version.split()[0],
        "work": str(work),
        "repo": "%s @ %s" % (args.repo, args.ref) if not args.clone else "local checkout %s" % args.clone,
    }
    print("gatebound fresh-clone smoke\n" + "\n".join("  %s: %s" % kv for kv in env_info.items()), flush=True)

    # 1. clone --------------------------------------------------------------
    if args.clone:
        clone = pathlib.Path(args.clone).resolve()
        report.add("clone", OK, "reused %s" % clone)
    else:
        clone = work / "gatebound"
        if clone.exists():
            shutil.rmtree(clone)
        started = time.time()
        code, out = sh(["git", "clone", "--depth", "1", "--branch", args.ref, args.repo, str(clone)], work)
        if code != 0:
            report.add("clone", FAIL, "git clone exited %d" % code, out)
            _finish(report, env_info, args.summary)
            return 1
        code, head = sh(["git", "rev-parse", "--short", "HEAD"], clone)
        report.add("clone", OK, "%s in %.0fs, HEAD %s" % (args.ref, time.time() - started, head.strip()))
    plugin = clone / "plugin"
    gk = plugin / "bin" / "gatebound.py"

    # 2. interpreters --------------------------------------------------------
    interpreters = find_interpreters()
    if not interpreters:
        report.add("interpreters", FAIL, "none of python3 / python / py -3 found")
        _finish(report, env_info, args.summary)
        return 1
    report.add("interpreters", OK, "; ".join("%s -> %s" % (" ".join(a), v) for a, v in interpreters))
    py = interpreters[0][0]

    def cli(*rest: str, cwd: pathlib.Path, timeout: int = 600) -> Tuple[int, str]:
        return sh(py + [str(gk)] + list(rest), cwd, timeout=timeout)

    # 3. sample project under a Korean path with a space -------------------
    project = work / PROJECT_REL
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(clone / "examples" / "memo-board", project)
    sh(["git", "init", "-q"], project)
    report.add("project", OK, "examples/memo-board copied to %s" % project)

    # 4. doctor (before any state exists) -----------------------------------
    code, out = cli("doctor", cwd=project)
    _, json_out = cli("doctor", "--json", cwd=project)
    doctor_step(report, "doctor", code, out, json_out)

    # 5. language detection with Korean input -------------------------------
    code, out = cli("lang", "메모 보드 만들어줘", cwd=project)
    report.add("lang ko", OK if out.strip() == "ko" else FAIL, "lang -> %r (exit %d)" % (out.strip(), code), out)

    # 6. spec validate -----------------------------------------------------
    code, out = cli("spec", "validate", "--json", cwd=project)
    try:
        verdict = json.loads(out).get("verdict")
    except ValueError:
        verdict = None
    report.add("spec validate", OK if verdict in (OK, WARN) else FAIL, "verdict %s" % verdict, out)

    # 7. contract derive (creates .gatebound/) ---------------------------------
    code, out = cli("contract", "derive", cwd=project)
    report.add("contract derive", OK if code == 0 else FAIL, out.strip().splitlines()[0] if out.strip() else "exit %d" % code, out)

    # 8. hooks through Git Bash, before approval -----------------------------
    hooks = hook_commands(plugin)
    report.add("git bash", OK if git_bash() else UNVERIFIED, git_bash() or "not found; hook steps will be unverified")
    base = {"session_id": SESSION, "cwd": str(project)}
    cases = [
        ("hook prompt", "UserPromptSubmit:UserPromptSubmit",
         dict(base, hook_event_name="UserPromptSubmit", prompt="메모 보드 만들어줘"), "context"),
        ("hook write (unapproved)", "PreToolUse:Write|Edit|MultiEdit|NotebookEdit|apply_patch",
         dict(base, hook_event_name="PreToolUse", tool_name="Write",
              tool_input={"file_path": str(project / "src" / "new.js"), "content": "x"}), "deny"),
        ("hook bash (unapproved)", "PreToolUse:Bash",
         dict(base, hook_event_name="PreToolUse", tool_name="Bash",
              tool_input={"command": "echo x > app.js"}), "deny"),
        ("hook powershell (state)", "PreToolUse:PowerShell",
         dict(base, hook_event_name="PreToolUse", tool_name="PowerShell",
              tool_input={"command": "Set-Content -Path .gatebound\\approvals.json -Value x"}), "deny"),
        ("hook spawn (no fence)", "PreToolUse:Agent|Task|collaborationspawn_agent",
         dict(base, hook_event_name="PreToolUse", tool_name="Task",
              tool_input={"prompt": "do the work", "description": "x"}), "deny"),
        ("hook compact", "PreCompact:PreCompact",
         dict(base, hook_event_name="PreCompact", trigger="manual"), None),
        ("hook stop", "Stop:Stop",
         dict(base, hook_event_name="Stop", stop_hook_active=False), None),
    ]
    for name, key, event, expected in cases:
        command = hooks.get(key)
        if command is None:
            report.add(name, FAIL, "no hooks.json entry for %s" % key)
            continue
        code, out = run_hook(command, plugin, event, project)
        got = decision(out)
        if code != 0:
            report.add(name, FAIL, "hook exited %d (hooks must exit 0)" % code, out)
        elif expected is None:
            report.add(name, OK, "exit 0, decision %s" % got, out)
        elif got == expected:
            report.add(name, OK, "exit 0, decision %s" % got, out)
        else:
            report.add(name, FAIL, "expected %s, got %s" % (expected, got), out)

    # 9. approve, then the same write is allowed -----------------------------
    code, out = cli("approve", "spec/05-gate.md", cwd=project)
    code2, out2 = cli("approve", "check", "spec/05-gate.md", cwd=project)
    code3, out3 = cli("contract", "status", cwd=project)
    ok = code == 0 and out2.strip().startswith(OK) and out3.strip().startswith(OK)
    report.add("approve + status", OK if ok else FAIL,
               "approve exit %d, check %s, status %s" % (code, out2.strip()[:12], out3.strip()[:12]), out + out2 + out3)
    code, out = run_hook(hooks["PreToolUse:Write|Edit|MultiEdit|NotebookEdit|apply_patch"], plugin,
                         dict(base, hook_event_name="PreToolUse", tool_name="Write",
                              tool_input={"file_path": str(project / "src" / "new.js"), "content": "x"}), project)
    got = decision(out)
    report.add("hook write (approved)", OK if code == 0 and got in (None, "allow") else FAIL,
               "exit %d, decision %s" % (code, got), out)

    # 10. the real contract: node + playwright --------------------------------
    if args.skip_e2e:
        report.add("contract run", UNVERIFIED, "skipped by --skip-e2e")
    elif shutil.which("npm") is None or shutil.which("node") is None:
        report.add("contract run", UNVERIFIED, "node/npm not on PATH")
    else:
        npm = shutil.which("npm") or "npm"
        npx = shutil.which("npx") or "npx"
        code, out = sh([npm, "ci", "--no-audit", "--no-fund"], project, timeout=600)
        if code != 0:
            report.add("contract run", UNVERIFIED, "npm ci exited %d" % code, out)
        else:
            extra = ["--with-deps"] if sys.platform.startswith("linux") else []
            code, out = sh([npx, "playwright", "install", "chromium"] + extra, project, timeout=900)
            if code != 0:
                report.add("contract run", UNVERIFIED, "playwright install exited %d" % code, out)
            else:
                started = time.time()
                code, out = cli("contract", "run", "--json", cwd=project, timeout=900)
                try:
                    data = json.loads(out)
                    verdict = data.get("verdict")
                    crit = ", ".join("%s=%s" % (c.get("id"), c.get("verdict")) for c in data.get("criteria", []))
                except ValueError:
                    verdict, crit = None, "unparsable output"
                report.add("contract run", OK if verdict == OK else (FAIL if verdict == FAIL else UNVERIFIED),
                           "%s in %.0fs: %s" % (verdict, time.time() - started, crit), out)
                # host-mode build: the example's code exists, so every task gate
                # (node --test, playwright) must pass at preflight with no worker.
                code, out = cli("jobs", "start", cwd=project, timeout=900)
                code2, out2 = cli("jobs", "status", "--json", cwd=project)
                try:
                    data = json.loads(out2)
                    tasks = data.get("tasks") or []
                    detail = ", ".join("%s=%s (%s/%s gates)" % (t.get("id"), t.get("state"), t.get("gates_passed"), t.get("gates_total")) for t in tasks)
                    bad = [t for t in tasks if t.get("state") != "passed"]
                    report.add("jobs start (host)", OK if code == 0 and tasks and not bad else FAIL,
                               detail or "no tasks; exit %d" % code, out + out2)
                except ValueError:
                    report.add("jobs start (host)", FAIL, "status unparsable (start exit %d)" % code, out + out2)
                code, out = cli("jobs", "recheck", "--json", cwd=project, timeout=900)
                try:
                    data = json.loads(out)
                    report.add("jobs recheck", OK if data.get("verdict") == OK else FAIL,
                               "verdict %s, rechecked %s" % (data.get("verdict"), ", ".join(data.get("rechecked", []))), out)
                except ValueError:
                    report.add("jobs recheck", FAIL, "exit %d, unparsable" % code, out)

    # 11. Codex host layer -----------------------------------------------------
    code, out = cli("install", "--host", "codex", cwd=project)
    expect = [project / ".codex" / "hooks.json", project / ".agents" / "skills" / "gatebound-build" / "SKILL.md",
              project / "AGENTS.md"]
    missing = [str(p.relative_to(project)) for p in expect if not p.exists()]
    report.add("install --host codex", OK if code == 0 and not missing else FAIL,
               "exit %d%s" % (code, ", missing " + ", ".join(missing) if missing else ", 3 expected files present"), out)

    # 12. doctor again, with state -------------------------------------------
    code, out = cli("doctor", cwd=project)
    _, json_out = cli("doctor", "--json", cwd=project)
    doctor_step(report, "doctor (with state)", code, out, json_out)

    # 13. the clone's own unit suite -------------------------------------------
    started = time.time()
    code, out = sh(py + [str(clone / "tools" / "run_tests.py")], clone, timeout=1800)
    tail = [l for l in out.splitlines() if l.startswith("Ran ") or l.startswith("tests:")]
    report.add("unit suite", OK if code == 0 else FAIL, "%s in %.0fs" % ("; ".join(tail) or "exit %d" % code, time.time() - started), out)

    _finish(report, env_info, args.summary)
    return 1 if report.verdict == FAIL else 0


def _finish(report: Report, env_info: Dict[str, str], summary: Optional[str]) -> None:
    print("\nsmoke: %s" % report.verdict, flush=True)
    if summary:
        pathlib.Path(summary).write_text(report.markdown(env_info), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
