# ADR-0032: doctor believes hooks it has seen run, and a gatekit skill can arm the Stop gate

Status: accepted 2026-10-04 (owner approval in session: "전부 진행", for the
designs below). Amends ARCHITECTURE.md section 3 (the prompt gate is the
only writer of `active_pipeline`) and the doctor's "hooks registered" axis.

## Context

Two findings of the first host run on Windows (`claude --plugin-dir
<integration build>`, `/gatekit:verify` on `examples/memo-board`):

1. **doctor said hooks would not fire while they were firing.** With the
   installed `gatekit@gatekit` disabled and the build loaded through
   `--plugin-dir`, axis 2 read `installed_plugins.json` and `settings.json`
   and reported `fail`: "installed as gatekit@gatekit but disabled …; hooks
   will not fire". Every turn of that session carried the prompt gate's
   context line and the Bash gate refused writes into `.gatekit/` — the
   hooks were running, from the `--plugin-dir` copy. Axis 2 can only see an
   install; a session-only load (`--plugin-dir`, a development checkout) is
   invisible to it.

2. **A command started through the Skill tool did not arm the Stop gate.**
   The session ran `/gatekit:verify` by invoking the skill itself after the
   user said "이어서 진행해줘". The ledger kept `active_pipeline: gate`, so the
   Stop gate never judged that verify. Only a typed `/gatekit:verify` set the
   pipeline. ARCHITECTURE section 3 makes the prompt gate "the **only**
   production writer of `active_pipeline` — commands never set it by prose",
   which also means a natural-language trigger ("빌드 시작해줘", which loads
   the `gatekit-build` skill) runs a build that the Stop gate never judges.

## Decision

### 1. The prompt gate records where it runs from; doctor believes it

The prompt gate stores `hook_root` (its own `paths.plugin_root()`) and
`hook_seen_at` in the session ledger at every prompt. Axis 2 first reads the
most recently updated ledger of the project: when its `hook_root` is the
plugin root doctor itself runs from, the axis is `ok` — "hooks are running
from <root> (seen <time>)" — whatever the install records say, because the
hooks were observed running, which is what the axis asks. Otherwise the
install checks run as before; a ledger written by another copy of the plugin
is not evidence for this one. Hooks that have not run yet in the project
(no ledger) leave the install checks as the only evidence, as before.

### 2. A `Skill` hook may arm the Stop gate, never disarm it

A PreToolUse hook on the `Skill` tool (`gates/skill.py`, Claude Code only:
Codex has no such tool) reads `tool_input.skill`. A gatekit skill —
`gatekit:<command>` or a trigger skill `gatekit:gatekit-<command>`, under any
of the plugin's names (ADR-0029) — naming `build` or `verify` does what the
prompt gate does for a typed `/gatekit:build` or `/gatekit:verify`: sets
`active_pipeline` and rearms the Stop gate (ADR-0024), with a
`pipeline_set` event whose `source` is `skill`. Every other skill — another
pipeline, `doctor`, `setup` — leaves `active_pipeline` alone: through a tool
call the model may start the gate's judging, never stop it or move a running
build to a pipeline the Stop gate does not judge. Clearing or switching
stays the user's, through a typed command. The hook never denies and exits 0
on any error, like every gate.

ARCHITECTURE section 3 changes accordingly: the prompt gate and the `Skill`
hook are the only writers of `active_pipeline`; commands still never set it
by prose.

## Consequences

- `doctor` run inside a `--plugin-dir` session reports the hooks it can see
  running instead of a false `fail`; a disabled install with no running
  hooks is still `fail`.
- "빌드 시작해줘" and a model continuing into `/gatekit:verify` are judged by
  the Stop gate, as a typed command is. A model cannot use a skill to end a
  build's judging early.
- The ledger gains two fields; old ledgers lack them, so axis 2 falls back
  to the install checks there.

## Rejected alternatives

- **Have the commands set the pipeline in prose.** Prose is never an
  enforcement mechanism in this repository; a model can skip it.
- **Let every gatekit skill set the pipeline, as a typed command does.** A
  `doctor` skill would then disarm a running build's Stop gate at the
  model's own initiative.
- **Detect `--plugin-dir` from the process.** The CLI does not inherit
  `CLAUDE_PLUGIN_ROOT`, and a development checkout loaded some other way
  would be missed too; a hook seen running is the direct evidence.
