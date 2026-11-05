# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.17.5 — 2026-11-05

A first install, made easier to get right before a study cohort starts.

### Changed

- **`doctor` reads a new folder as not started, not broken.** The verdict
  of a project with no `spec/` stays `unverified` (nothing checked is not
  a pass), and the table now adds a `next:` line under the headline: "not
  started yet — run /gatebound:setup, then /gatebound:discover", or "set
  up, no spec yet — run /gatebound:discover". Axis 3's fix is
  `/gatebound:setup` instead of a raw `doctor --root` line, and axis 5's is
  `/gatebound:gate` while `spec/05-gate.md` does not exist. The reinstall
  fixes name the marketplace: `/plugin install gatebound@gatebound`.
  `--json` is unchanged.
- **README install walkthrough.** Both READMEs open with an English |
  한국어 switch and walk five numbered steps: install Claude Code, install
  the plugin, open a new terminal in the project folder, run `claude` and
  log in, type `/gatebound:doctor`, with a table of what a healthy result
  in a new folder looks like. The intro names Codex as well.
- **Prerequisites stated up front** (README and install manual, ko/en):
  Python 3.9+ and git are the user's to install (macOS:
  `xcode-select --install`); on Windows, Git for Windows is required, since
  Claude Code 2.1.299 blocks a tool call guarded by a `PreToolUse` hook that
  names no shell when Git for Windows is missing; projects with screens
  should run `npx playwright install chromium` before the session.
- **Issue templates.** Bug reports ask for the host version
  (`claude --version` / `codex --version`); a new "[install]" form asks for
  the OS, host and version, the exact install command, its output and
  doctor's output. Labels carry a Korean hint.
- **Plugin folder README** (`plugin/README.md`) says what gatebound runs,
  reads and sends, including the local config folders doctor reads.
- `AGENTS.md` is a regular file pointing at `CLAUDE.md` rather than a
  symbolic link, which Anthropic's plugin directory refuses to validate.
- The marketplace owner and the plugin author are the public name, Logan
  Kim.

### Fixed

- **The install manual pinned an old installer.** The Windows one-liners in
  the manual (ko/en) still fetched `v0.17.0/install/install.ps1` and the
  index called 0.17.0 current; every pin and the index now name the
  release, as the README does. "Coming from gatekit" adds that the gatekit
  line continues, now at 0.16.21.

## 0.17.4 — 2026-10-13

### Fixed

- **A Codex evaluator can start the app it grades.** `jobs evaluate` runs
  Codex with `--sandbox workspace-write`, whose default bans the network,
  and that includes binding a localhost port (seen on WSL, reproduced on
  macOS). A gatekit
  study participant's verify run on WSL failed 4 criteria and could not run
  any E2E step, all with `listen EPERM`, while the host's own run passed
  every criterion. The evaluator run now adds
  `-c sandbox_workspace_write.network_access=true` (ADR-0015 Amendment A).
  The read-only evaluator and build workers are unchanged. Same fix as
  gatekit 0.16.21.

## 0.17.3 — 2026-10-10

### Fixed

- **`doctor` reads Codex's current hook-trust records.** Codex 0.157 records
  a plugin hook's trust under the plugin id
  (`gatebound@gatebound:hooks/hooks.json:<event>:<group>:<hook>`), not under the cached
  `hooks.json` path, so the host-layer axis kept warning "hooks are not
  trusted" after every hook had been trusted. Both forms count now, and the
  check is per hook: each hook Codex runs must have a trust entry with a
  `trusted_hash` that is not disabled, and partial trust is a `warn` naming
  how many of how many. Whether that trust predates an upgrade cannot be
  told (Codex's hash recipe is not documented); the `ok` detail says to
  trust again in `/hooks` if Codex lists the hooks as changed.

## 0.17.2 — 2026-10-10

Four smaller findings of the same timed build (none changes a verdict).

### Fixed

- **`jobs shape` can be found and run on a draft.** It was missing from
  `jobs --help`, and it read only `spec/04-tasks.md`, while `/gatebound:tasks`
  runs it on a draft before that file exists; the session concluded the
  command did not exist and counted rounds by hand. It is listed now, takes
  `--file <draft>`, and `/gatebound:tasks` gives the full command. Any
  `jobs <sub> --help` prints the usage instead of running the subcommand.
- **`spec validate` reads the language from the discovery record.** Right
  after `/gatebound:discover`, with no `01-prd.md` yet, a Korean
  `00-discovery.md` was judged as English and its headings reported as the
  wrong language. The discovery record now decides until the PRD exists.
- **Assumption markers count where the assumption is used.** Assumptions a
  mockup adds are marked in `02-screens.md`, as the policy says; the ledger
  check looked only in `01-prd.md` and warned about every such row (13
  false warnings at every stage of the trial). A marker in `02-screens.md`,
  `02-design.md` or `03-architecture.md` now marks its row.
- **Progress lines follow the output language.** During the build the
  short lines written between tool calls drifted into English while the
  hook said `output_lang=ko`. The language policy and the build and verify
  commands now name those lines.

## 0.17.1 — 2026-10-09

Three defects found in a timed end-to-end build of a 16-feature app
(ADR-0040).

### Fixed

- **A finished subagent releases its write scope.** The spawn gate never
  removed a recorded scope, so after the first parallel round every later
  delegation that overlapped a finished agent's scope was denied and the
  host session built the rest alone. The spawn gate now also runs on
  PostToolUse and PostToolUseFailure for `Agent|Task` and on SubagentStop:
  a foreground agent's scope is released when its call returns or fails, a
  background agent's when it stops. The ledger keeps every hook's scope
  changes when two hooks save at once.
- **The Stop gate waits for a running background subagent.** `/gatebound:verify`
  starts its evaluator in the background; the Stop gate ran the contract at
  the same moment, the two collided on the test server's port and the E2E
  criterion came back `unverified`. While Claude Code reports a background
  subagent that the spawn gate recorded as still running, the Stop gate now
  judges nothing and lets the turn end, at most three Stops in a row,
  without rewriting the last verdict; the Stop after the agent finishes
  judges.
- **The tokens gate reads the shipped `shadcn-neutral` preset.** Its colours
  are bare HSL triplets (`0 0% 9%`) used as `hsl(var(--primary))`. The gate
  now reads a triplet in a colour group as `hsl(...)`, compares colour
  functions across comma, space and slash syntax, and treats a colour
  function with `var(...)` among its colour channels as a token reference
  rather than a literal; a `var()` only in the alpha slot is still a
  hard-coded colour. Before, it found no colour tokens in that preset and
  `/gatebound:tasks` left it out.

## 0.17.0 — 2026-10-09

gatebound is the continuation of gatekit 0.16.15 under its own name: same
gates, same pipeline, same verdict words (`ok / warn / fail / unverified`).
The gatekit history, up to 0.16.15, lives at
[github.com/loganmakes/gatekit](https://github.com/loganmakes/gatekit). Still
early.

### What changed

- **New names** (ADR-0029, `plugin/gatebound/names.py`):
  - plugin and marketplace `gatebound` — install `gatebound@gatebound` from
    `gatebound/gatebound`;
  - commands `/gatebound:<cmd>`, Codex skills `$gatebound-<cmd>`;
  - CLI `${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py`, package
    `plugin/gatebound/`;
  - state directory `.gatebound/` for a new project;
  - spec fences `gatebound-task`, `gatebound-criterion`, `gatebound-budget`,
    `gatebound-discovery`, `gatebound-scope`;
  - worker environment `GATEBOUND_TASK_ID`, `GATEBOUND_JOB_ID`;
  - `AGENTS.md` markers `<!-- gatebound:begin … -->` / `<!-- gatebound:end -->`.
- **What stays readable from a gatekit project** (ADR-0029):
  - `.gatekit/` is read while the project has no `.gatebound/`;
  - `gatekit-*` fences are read everywhere, permanently — approved specs are
    hash-pinned, so never rewrite them;
  - criterion and task argv naming `…/gatekit/gates/<gate>.py` or
    `bin/gatekit.py` run this plugin's file;
  - workers also get `GATEKIT_TASK_ID` / `GATEKIT_JOB_ID`, and gates read
    either name;
  - `/gatekit:<cmd>` and `$gatekit-<cmd>` still arm the Stop gate; the
    worker approve guard still refuses `gatekit.py approve`;
  - a `<!-- gatekit:begin … -->` block in `AGENTS.md` is replaced by the new
    one.
- **How to migrate:**
  1. Uninstall gatekit and install gatebound:
     `claude plugin uninstall gatekit@gatekit`,
     `claude plugin marketplace remove gatekit`,
     `claude plugin marketplace add gatebound/gatebound`,
     `claude plugin install gatebound@gatebound` (Codex:
     `codex plugin remove gatekit@gatekit`,
     `codex plugin marketplace remove gatekit`, then
     `codex plugin marketplace add gatebound/gatebound` and
     `codex plugin add gatebound@gatebound`). Restart the host.
  2. Optionally move a project's state:
     `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" migrate` shows the
     plan, `migrate --apply` renames `.gatekit/` to `.gatebound/` (`git mv`
     when tracked), fixes `.gitignore` and regenerates a Codex layer; it never
     touches `spec/`. Unmigrated projects keep working.
  3. Run `/gatebound:doctor`. Axis 2 **fails** while gatekit and gatebound
     are both enabled, even when gatebound's hooks were seen running; in a
     project that still has `.gatekit/`, gatebound's Stop and question gates
     stand down meanwhile, so the two are never doubled.
- **Codex layer:** `install --host codex` writes `.agents/skills/gatebound-*`
  and removes the `.agents/skills/gatekit-*` directories a gatekit install
  generated (only those named after one of its commands and holding exactly
  its `SKILL.md` and `command.md`).
- **Manual:** the install page (ko + en) gains "Coming from gatekit".
