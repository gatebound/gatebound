# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
