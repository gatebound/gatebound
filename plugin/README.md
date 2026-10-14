# gatebound

gatebound is a gate-enforced harness for AI-assisted development in Claude
Code. It turns the steps you would otherwise write as prose in a `CLAUDE.md`
(interview before building, approve the spec before writing source, prove
"done" by running commands) into hooks that run on every tool call.

The full guide, the manual and the changelog live at the repository root and
at [gatebound.dev](https://gatebound.dev). This file describes the plugin
folder you install.

## What it adds

- **Commands** under `/gatebound:`: `discover`, `interview`, `mockup`,
  `design`, `tasks`, `gate`, `build`, `verify`, `doctor` and a few helpers.
  Each writes a spec file under `spec/` in your project.
- **Hooks** on `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `PostToolUseFailure`, `PreCompact`, `SubagentStop` and `Stop`.
- **A CLI**, `bin/gatebound.py`, that the commands call.

## What it runs, reads and sends

- **Hooks fire in every project but act only in a gatebound project.** A
  project becomes one when a gatebound command creates a `.gatebound/`
  folder in it (a project carried over from gatekit keeps its older state
  folder). Without that folder every hook exits 0 and prints nothing.
- **Each hook starts Python 3.9 or newer** from `python3`, `python` or
  `py -3`, after a silent version check, and runs one script from
  `gatebound/gates/`. The plugin uses the Python standard library only and
  installs no packages.
- **Files.** It reads your `spec/` files and writes its own state under
  `.gatebound/` in the project. The write gate blocks edits outside `spec/`
  until the gate file is approved.
- **Commands you approve.** The `Stop` hook and `/gatebound:verify` run the
  acceptance criteria written in `spec/05-gate.md`, which are commands you
  review and approve. `/gatebound:build` and `/gatebound:verify` may start a
  worker or evaluator session with the `claude` CLI, or with the `codex` CLI
  when you enable it.
- **Local configuration.** `doctor` and the Codex setup read the Claude
  Code and Codex configuration folders (`~/.claude` and `~/.codex`, or the
  folders named by `CLAUDE_CONFIG_DIR` and `CODEX_HOME`) to check that the
  plugin and its hooks are installed and trusted. The plugin reads no API
  key or token, and nothing it reads there leaves your machine.
- **Network.** The plugin itself makes no network requests and sends no
  telemetry. `doctor` connects to `127.0.0.1` and `::1` to check whether your dev
  server's port is already in use. Your approved criteria and any worker CLI you enable
  use the network as they normally would.

## Requirements

Claude Code, Python 3.9 or newer, and Git. Native Windows is in preview;
see the install chapter of the manual.

## License

MIT. See `LICENSE` at the repository root.
