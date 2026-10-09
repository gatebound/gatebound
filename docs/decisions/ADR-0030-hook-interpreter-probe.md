# ADR-0030: A hook probes its interpreter before running, so a failed attempt never writes to stdout

Status: accepted 2026-10-04 (owner-reported Windows reproduction in session).
Amends ADR-0019 decision 3a. Decision 2's CMD prediction is superseded by
ADR-0034: Codex on Windows runs hooks in PowerShell, where this form runs
nothing.

## Context

ADR-0019 made every hook command
`python3 "<script>" || python "<script>" || py -3 "<script>"`, reasoning
that a gate always exits 0, so the chain only advances when an interpreter
is *missing*, and a missing interpreter prints nothing.

A fresh clone run on an owner's Windows 10 PC (2026-10-04, Python 3.9.10
installed through the launcher, Claude Code's Git Bash present) showed the
premise is false on a stock Windows install. `python3` and `python` resolve to
`%LOCALAPPDATA%\Microsoft\WindowsApps\python*.exe`, the Microsoft Store
placeholder that Windows ships before any Python is installed. In Git Bash:

```
$ python3 --version; echo exit=$?
Python exit=49
$ python --version; echo exit=$?
Python exit=49
$ py -3 --version; echo exit=$?
Python 3.9.10
exit=0
```

The placeholder is not missing. It prints `Python` to **stdout**, without a
newline, and exits non-zero. The chain does fall through to `py -3`, which
runs the gate correctly, but the hook's stdout is now
`PythonPython{"hookSpecificOutput": …}`. Claude Code reads a PreToolUse
hook's stdout as JSON; this is not JSON, so the `deny` inside it is dropped
and the write is allowed. Every gate on that machine was silently
non-enforcing while `doctor` reported Python 3.9 as `ok`. The smoke run
recorded it as seven hooks that exited 0 with an unparsable decision.

The same machine showed a second, smaller gap: the interpreter chain is the
only place the plugin chooses a Python, so nothing told the user that two of
the three names on PATH were placeholders.

## Decision

1. **Each attempt is guarded by a silent probe of the same name.** The hook
   command becomes, for a script `S`:

   ```
   (python3 -c "import sys;sys.exit(sys.version_info<(3,9))" >/dev/null 2>&1 && python3 "S")
   || (python -c "import sys;sys.exit(sys.version_info<(3,9))" >/dev/null 2>&1 && python "S")
   || py -3 "S"
   ```

   on one line. A name runs the gate only after it has proven, with all of
   its output discarded, that it is a Python 3.9 or newer. A placeholder, a
   Python 2, or a broken install fails the probe and contributes nothing to
   stdout. The last attempt is unguarded on purpose: if `py -3` is also
   absent, its "command not found" goes to stderr, the chain exits non-zero,
   and Claude Code reports the hook error instead of silently allowing.
2. **The Codex layer generates the same form** (`hosts.codex_hooks`), with
   `--host codex` on each run. The form is POSIX sh, which is what Claude
   Code uses on every platform (Git Bash on Windows). Under CMD the
   `>/dev/null` redirect fails before the probe runs, so each guarded attempt
   fails closed and the chain reaches `py -3` with stdout still clean; this
   degradation is documented as `unverified`, since no Codex-on-Windows
   session has been observed.
3. **`doctor`'s python axis names the placeholder.** When `python3` or
   `python` on PATH resolves under `WindowsApps`, the axis is `warn`, says
   which names are the Store placeholder, and prints the fix (install Python
   or turn off the app execution alias). The interpreter running `doctor`
   itself may well be fine, as it was here; the warn is about what the hooks
   will meet.
4. **The install documentation lists Python as a prerequisite in its own
   right**, with the placeholder named, instead of implying that "reachable
   as `python3`, `python` or `py -3`" is satisfied by a stock Windows.

## Consequences

- One extra interpreter start per hook on machines where the first name is
  the right one (about 20 to 40 ms). Hook timeouts are 10 s and 600 s; the
  cost is accepted for a chain that can no longer corrupt its own output.
- A machine with only the placeholders and no `py` launcher now fails loudly
  (hook error in the Claude Code transcript) instead of silently allowing
  every write. That is the intended direction: `unverified` is never
  rounded to `ok`.
- `tools/smoke_fresh_clone.py` already detects the pollution (a hook that
  exits 0 with an unparsable decision is `fail`), and a regression test
  reproduces the placeholder with a shell stub that prints `Python` without
  a newline and exits 49, asserting the hook's stdout stays clean.
- ADR-0019 decision 3a is superseded by decision 1 here; its claim that the
  chain "only advances when an interpreter is missing" is withdrawn.

## Still unverified

- A real Claude Code session on Windows calling these hooks. The owner's PC
  has no `claude` on PATH (desktop app or not installed); the reproduction
  above drove the hooks through the same Git Bash by hand.
- Codex on Windows, and whether its hook runner is sh or CMD.
