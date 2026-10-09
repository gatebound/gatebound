# ADR-0035: Under Codex on Windows the Bash gate also reads the command as PowerShell

Status: accepted 2026-10-05 (owner, after the trusted-hooks run recorded
in ADR-0034 "Evidence": the shell `Set-Content` into `src/` was denied). Amends ADR-0028 (the Codex layer "has no counterpart") and
ADR-0004.

## Context

With ADR-0034 the gates start under Codex on Windows. In the same scratch
project (a `spec/` directory, no approval, hooks trusted for the run) the
write gate denied `apply_patch` into `src/`, and a `docs/` patch went
through as it should. A shell call did not:

| Codex shell call (`tool_name` `Bash`) | What ran | Bash gate |
|---|---|---|
| `Set-Content -Path src/run.py -Value 'x'` | `powershell.exe -Command "Set-Content …"` | allowed |
| `echo x > src/run.py` (same event, fed by hand) | — | denied |

Codex on Windows runs every shell call in Windows PowerShell and reports it
as `Bash` with the PowerShell text in `tool_input.command` (observed twice:
`echo hello` and the `Set-Content` above, both wrapped in
`powershell.exe -Command`). The Bash gate reads POSIX sh: to it
`Set-Content` is a program invoked by name, which is outside its reach by
design, so the write is allowed. ADR-0028 built a PowerShell reader for
Claude Code's `PowerShell` tool and said the Codex layer needs no
counterpart because Codex reports every shell call as `Bash`; that holds for
the tool name, not for the syntax.

Whether Codex can be configured to use another shell on Windows (Git Bash,
`pwsh`) is not known here, so the gate cannot assume the text is always
PowerShell.

## Decision

1. **Under Codex on Windows, a `Bash` event is judged by both readers.**
   `gates/bash.py` judges the command as today; when that allows, and the
   host is `codex` (from `--host`, or `PLUGIN_ROOT`, `hookio.host_from_argv`)
   and the platform is Windows, it also judges it exactly as the PowerShell
   gate judges a `PowerShell` event (`powershell.judge`: the approve
   refusal, protected state, spec-before-code, task scope, `opaque`). The
   first deny wins. A command that is safe under one reading and a write
   under the other is a write: "could not tell" is never rounded to
   "allowed".
2. **`gates/powershell.py` exposes `judge(event, command)`**, the body of
   its `handle` after the tool-name check, so both gates run one
   implementation. `handle` is unchanged for Claude Code's `PowerShell`
   tool.
3. **Nothing changes for Claude Code** (its `Bash` tool is Git Bash on
   Windows and its `PowerShell` tool already meets the powershell gate) **or
   for Codex on Linux and macOS.** The extra reading is keyed on host and
   platform, both pinned by tests in each direction.

## Consequences

- A PowerShell write in a Codex shell call on Windows is denied before
  approval, outside a task's scope, and always into gatekit's state, with
  the PowerShell gate's reasons (in `output_lang`).
- A command both readers allow costs one more parse (pure Python, no
  process); a command PowerShell cannot read (`$var` in a write target, an
  unknown cmdlet parameter of a write cmdlet, …) is `opaque` and denied
  while a restriction is active — the same friction Claude Code's
  PowerShell tool already has.
- Tests: Codex + Windows denies `Set-Content`, `Out-File`, `New-Item` into
  `src/` before approval, allows them into `docs/` and after approval,
  allows reads, `git` and `npm`, denies a `Remove-Item` of
  `.gatekit/approvals.json` with no restriction active, and keeps a worker
  from approving; Codex off Windows and Claude Code on Windows still allow
  `Set-Content` (unchanged); the gate run as a process with `--host codex`
  on Windows denies; an internal error still exits 0.
