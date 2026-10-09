# ADR-0034: Under Codex on Windows a hook command runs in PowerShell, so the Codex layer carries a `commandWindows`

Status: accepted 2026-10-05 (owner, after the trusted-hooks run under
"Evidence" below).
Amends ADR-0030 decision 2 and ADR-0019 decision 3; answers the second
open point of ADR-0033 decision 11.

## Context

ADR-0033 decision 11 kept Codex out of the installer until a person saw the
gates run under Codex on Windows, and said that a code write going through
before approval would be a gatekit bug to fix first. ADR-0030 decision 2
predicted that Codex runs hooks through CMD, where the sh-form command would
degrade to `py -3`, and recorded that as `unverified`.

On 2026-10-05 the study PC (Windows 11, Codex CLI 0.160.0, Python 3.9.10
through the `py` launcher, `python3`/`python` the Microsoft Store
placeholders) was checked with `codex exec` in a scratch project prepared by
`gatekit install --host codex`, with a `spec/` directory and no approval:

| Run | Result |
|---|---|
| Hooks not trusted (project trusted or not) | Codex runs no project hook at all, silently; the write goes through |
| Hooks trusted for the run (`--dangerously-bypass-hook-trust`), a diagnostic hook `py -3 "<log.py>"` | `UserPromptSubmit`, `PreToolUse` (`apply_patch`, and `Bash` for every shell call) and `Stop` all run; a `deny` on stdout blocks the patch |
| Same, a hook carrying `$PSVersionTable` in its command | the command runs in Windows PowerShell 5.1 (`Desktop` edition), not CMD |
| Same, probes of single constructs | a plain command, `( … )` and `$x=1; …` run; any command containing `\|\|`, `&&`, `>NUL` or `>/dev/null` runs nothing |
| Same, gatekit's generated `.codex/hooks.json` | the write gate never starts; `src/app.py` is written before approval |
| The same `apply_patch` event fed to `gates/write.py --host codex` by hand | `deny` |

So the gate logic is right and the launcher is wrong: `||` and `&&` are
parse errors in Windows PowerShell 5.1, the whole command is rejected before
anything runs, `py -3` included, and Codex treats the failed hook as
non-blocking. ADR-0030 decision 2's prediction does not hold under Codex.

The same Codex build accepts a `commandWindows` string beside `command` in a
command hook (it is in the binary's `HookHandlerConfig::Command` fields:
`type`, `command`, `commandWindows`, `timeout`, `async`, `statusMessage`).
A diagnostic hook with both showed that on Windows `commandWindows` runs in
place of `command` and receives the full event on stdin.

## Decision

1. **The generated Codex layer adds a `commandWindows` to every hook.**
   `hosts.codex_hooks` keeps `command` (the ADR-0030 sh chain, for Codex on
   Linux and macOS) and adds `commandWindows`, built by
   `hosts.hook_command_windows(script, suffix)`: Windows PowerShell 5.1
   syntax, no `||`, `&&` or `/dev/null`:

   ```
   $s='S'; foreach($n in 'python3','python'){ if(Get-Command $n -CommandType Application -ErrorAction SilentlyContinue){ & $n -c 'import sys;sys.exit(sys.version_info<(3,9))' *>$null; if($LASTEXITCODE -eq 0){ & $n $s --host codex; exit $LASTEXITCODE } } }; if(Get-Command py -CommandType Application -ErrorAction SilentlyContinue){ py -3 $s --host codex; exit $LASTEXITCODE }; [Console]::Error.WriteLine('gatekit: no Python 3.9+ found as python3, python or py -3'); exit 1
   ```

   on one line. It keeps ADR-0030's rules: each name is probed with all of
   its output discarded before it runs the gate, so a Store placeholder
   never writes to the hook's stdout; `py -3` is the last attempt; a machine
   with no interpreter fails aloud (stderr, exit 1) rather than allowing
   silently. The script path is a single-quoted literal, a `'` in it doubled,
   so a space, `$` or non-ASCII character in the checkout path is taken as
   written.
2. **`hosts.hook_script` reads the script from either form**, so doctor's
   host-layer axis and the smoke tool judge `commandWindows` the same way.
3. **The plugin's own `hooks/hooks.json` is not changed by this ADR**
   (superseded by ADR-0038, which observed both open facts and adds a
   `commandWindows` there too). It is
   shared by Claude Code, which runs it through Git Bash on Windows and is
   unaffected, and by a Codex plugin install. Two facts needed for the
   latter are unobserved: how Codex exposes the plugin root to a PowerShell
   command (`${CLAUDE_PLUGIN_ROOT}` is a PowerShell variable reference, not
   text, there) and whether Claude Code accepts an unknown `commandWindows`
   key. Until a Codex plugin install on Windows is seen to deny a write
   before approval, that route stays `unverified` on Windows and the manual
   says so; `gatekit install --host codex` is the Windows route.
4. **The documentation stops calling Codex's Windows hook shell CMD.**
   ARCHITECTURE §3 and §15, ADR-0030 decision 2 (by this amendment) and
   ADR-0033 decision 11 point here.

## Consequences

- Under Codex on Windows the generated layer's gates run, once the user
  trusts the hooks in `/hooks` (unchanged: untrusted hooks are skipped with
  no message, which doctor's host-layer axis already reports as `warn` for a
  plugin install).
- Each hook in `.codex/hooks.json` carries two commands for the same script;
  tests pin that both name it and that `commandWindows` contains none of the
  constructs PowerShell 5.1 rejects.
- Tests run the PowerShell form for real where `powershell.exe` exists (the
  `windows-latest` CI job and the owner's PCs): a placeholder `python3` is
  skipped without touching stdout, `python` runs the gate with the event on
  stdin, `py -3` is reached when neither name is real, and no interpreter at
  all exits 1. Elsewhere those tests skip, as the sh ones skip on Windows.
- ADR-0033's `-WithCodex` still waits on the evidence its decision 11 asks
  for, now reachable: install the Codex CLI and the layer, trust the hooks in
  `/hooks`, and see the write denied.

## Evidence with the hooks trusted by a person (2026-10-05)

Study PC, Codex CLI 0.160.0, a fresh project prepared by
`gatekit install --host codex` with `spec/01-prd.md` and no approval. The
owner ran `codex --no-daemon` in a PowerShell window (plain `codex` stopped
with `os error 5` while starting its background server), opened `/hooks`,
saw each gatekit hook listed with the PowerShell `commandWindows` text and
`Trust: New hook - review required`, and trusted all six (`t`); the user
config then held six `hooks.state` entries for the project's
`.codex/hooks.json`. In a new session, with `AGENTS.md` set aside so the
model would attempt the calls rather than decline them from prose:

| Call | Result |
|---|---|
| `apply_patch` adding `src/app.py` | `Blocked by hook` - `gatekit: writing code is blocked until spec/05-gate.md is approved (current status: unverified) ... Blocked path: src/app.py` |
| shell `Set-Content -Path src/run.py -Value x` | blocked with the same reason, `Blocked path: src/run.py` |
| `apply_patch` adding `docs/notes.md` | written |

On disk afterwards: `src/app.py` and `src/run.py` absent, `docs/notes.md`
present. With `AGENTS.md` in place the model declined both code writes
itself and no hook ran, which is why prose is not counted as enforcement.
