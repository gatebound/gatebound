# ADR-0038: The plugin's own hooks.json carries a `commandWindows` too, so a Codex plugin install works on Windows

Status: accepted 2026-10-05 (owner chose to run the experiments below).
Answers ADR-0034 decision 3, which left the Codex plugin route `unverified`
on Windows.

## Context

ADR-0034 gave the generated Codex layer (`install --host codex`) a
`commandWindows`, because Codex runs hook commands in Windows PowerShell 5.1
where the sh chain runs nothing. It left the plugin's own
`plugin/hooks/hooks.json` alone: it is shared with Claude Code, and two facts
were unobserved — how Codex hands a PowerShell command the plugin root, and
whether Claude Code tolerates an unknown `commandWindows` key.

Both were observed on 2026-10-05 on the study PC, with a throwaway
diagnostic plugin whose one `UserPromptSubmit` hook had both commands, each
logging which ran and the environment:

| Host | Which command ran | Plugin root given as |
|---|---|---|
| Claude Code 2.1.289 (`claude -p --plugin-dir`) | `command` (sh) only; the plugin loaded with no error or warning | `CLAUDE_PLUGIN_ROOT` set; `PLUGIN_ROOT` unset |
| Codex CLI 0.160.0 (plugin from a local marketplace) | `commandWindows` only | both `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` set; `${CLAUDE_PLUGIN_ROOT}` in the text was also substituted before PowerShell saw it |

`claude plugin validate` passes the file with the key, `--strict` included.

## Decision

1. **Every hook in `plugin/hooks/hooks.json` gains a `commandWindows`**,
   built by `hosts.plugin_hook_command_windows(relative)`: the ADR-0034
   PowerShell chain (python3, python, each probed silently, then `py -3`,
   `exit 1` aloud when none exists) with the script path
   `Join-Path $r '<relative>'`, where `$r` is `$env:PLUGIN_ROOT`, else
   `$env:CLAUDE_PLUGIN_ROOT`. The root comes from the environment rather
   than the substituted text, so no character in the folder's name (a quote,
   a `$`) can break the command. No `--host` flag: as for `command`, the
   host is read from `PLUGIN_ROOT` (ADR-0019), which only Codex sets.
2. **`command` is unchanged**, so Claude Code on every platform runs exactly
   what ADR-0030 pins. `hosts.hook_script` reads the script from the new
   form too, spelled as the sh form spells it.
3. **On Windows, the Codex plugin route and the generated layer are both
   supported.** The documentation stops calling the plugin route
   `unverified` there; the hook trust in `/hooks` is still the user's step
   either way.

## Consequences

- Seen end to end the same day: this branch's plugin installed into Codex
  from a local marketplace, no `.codex/` layer in the project, a Korean
  `spec/01-prd.md`, hooks trusted for the run
  (`--dangerously-bypass-hook-trust`): an `apply_patch` into `src/` and a
  shell `Set-Content` into `src/` were both denied before approval and
  `src/` was never created. The plugin, its marketplace, its cache folder
  and a project-trust entry Codex had added were removed afterwards and the
  user config compared equal to its backup.
- Not yet seen: the same with the trust given by a person in `/hooks` (the
  mechanism is the one ADR-0034's evidence used for the layer).
- Tests: every plugin hook has a PowerShell form naming the same script,
  with none of the constructs PowerShell 5.1 rejects, reading the root from
  `PLUGIN_ROOT` then `CLAUDE_PLUGIN_ROOT`, with no `--host`; the file equals
  what the builder makes; run in real PowerShell, the form finds the gate
  under either variable in a folder named `it's $here`.
- ADR-0033 decision 12 (`-WithCodex` does not add the plugin) was written
  while this route was unverified; an amendment may now let it.
