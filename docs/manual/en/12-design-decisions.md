# Design decisions

`docs/ARCHITECTURE.md` is the single source of truth for module boundaries, file formats, and vocabulary. Every module, command, hook, and test must agree with it. If the implementation needs to deviate, write an ADR in `docs/decisions/`, change this file first, and then change the code.

gatebound is a **clean-room implementation**. It borrows common engineering patterns such as hook-enforced gates, an assumption ledger, hash-anchored approval, an executable completion contract, and worker job directories, but no code is copied from other projects.

## ADR-0001 — One plugin, one package

**Context**: the interview and mockup pipelines, the task and gate system, the worker job runner, and the hooks that enforce them. Each of these could have been split into a separate plugin.

**Problem**: Claude Code resolves `${CLAUDE_PLUGIN_ROOT}` per plugin, and there are no file paths across plugins. One plugin's hook script cannot reach another plugin's directory by a relative path. Splitting would either duplicate cross-cutting pieces such as the ledger, the verdict vocabulary, and the hook I/O contract, or depend on fragile absolute-path assumptions about where sibling plugins are installed.

**Decision**: gatebound is exactly one plugin (`plugin/`), and inside it is exactly one Python package (`plugin/gatebound/`). `marketplace.json` lists a single entry.

**Cost**: `plugin/` becomes one large tree instead of several small ones. `ARCHITECTURE.md` §1 exists to keep that tree navigable.

## ADR-0002 — Python standard library only

**Context**: convenience libraries such as `pyyaml`, `jsonschema`, and `rich` would each have saved implementation effort somewhere in the kernel or the CI gates.

**Problem**: hooks run on every prompt and tool call in the session. A hook that cannot import a missing package does not degrade gracefully. It fails on its first line, on every call, until someone notices and runs a package manager. That violates the `ARCHITECTURE.md` §3 requirement that "every hook exits 0 even on internal error" before the error handling even gets a chance to run.

**Decision**: `plugin/gatebound/`, `plugin/gatebound/gates/`, and `tools/` use only the Python 3.9+ standard library. No `pip install`, no `npm`, no vendored third-party source.

**Cost**: some implementations are verbose. The schema validation in `spec.py` is hand-written, and the front matter parsing in `tools/gate_skill_size.py` is a small regex, not a YAML parser. This is an accepted cost, not a mistake.

**Benefit**: right after a fresh clone, the CLI and the CI gates run immediately with no install step. CI needs neither a dependency resolution step nor the network.

## ADR-0003 — Claude CLI is the default worker, Codex is opt-in

**Context**: `workers.py` supports several backends. Users and organizations already have different tools and license agreements, and gatebound's job and gate machinery does not care which CLI actually does the work. It only needs the write-scope contract to be honored.

**Decision**: the `claude` backend is enabled by default. `codex` ships with `"enabled": false` and is turned on only through an explicit `/gatebound:setup codex` step. That step runs `workers.check("codex")`, and `enable` is recorded only after the user confirms the result.

**Reason**: gatebound itself is a Claude Code plugin, so the Claude CLI is a tool the user is already running gatebound inside. A fresh install works end to end with no extra setup. And no one's session quietly reaches out to a second CLI they never installed and never agreed to.

**Extension**: adding a third backend needs no new ADR as long as it follows the "ship disabled, `check` before `enable`" pattern.

## Core rules of the architecture contract

| Rule | Reason |
|---|---|
| Python 3.9+ standard library only | It must run on a fresh machine that has only `python3` |
| One plugin, one package | Paths across plugins do not exist |
| Gates are hooks, not prose | Prose instructions fire nondeterministically |
| Every hook exits 0 even on internal error | A broken hook must not break the user's session |
| Exactly four verdict words | "Not checked" must not round to a pass or a fail |
| No absolute personal paths | They leak the author's local layout and break for other contributors |
| 40-line cap on `SKILL.md` | Keeps a skill from becoming a second execution path that competes with the command |
| Command files are the execution instructions | Skills are only trigger shims |
| Data lives in JSON and Markdown files | Keeps prompts small and data diffable |
| No files over 1 MB | No committed corpora |
| Korean is not the default | Open-source posture |

## The seven CI gates

Each gate blocks a specific kind of failure. They run on Python 3.9 and 3.12.

| Gate | What it blocks |
|---|---|
| `gate_no_abs_paths.py` | A personal home path such as `/Users/<name>` getting into a committed file and breaking for other contributors |
| `gate_blob_size.py` | Files over 1 MB. Datasets, media, or vendored archives bloating every clone |
| `gate_skill_size.py` | A `SKILL.md` over 40 lines or a command over 160 lines, letting the command/skill split slide back into two duplicate artifacts. `AskUserQuestion` in the front matter's `allowed-tools`, which makes it auto-approved and run without confirmation. And a command's skill shim missing `user-invocable: false`, which makes the same command show up twice in the `/` menu (ADR-0026 D2) |
| `gate_forbidden_phrases.py` | Imperative execution steps such as "Step 1:" or "EXECUTE IMMEDIATELY" getting into a skill, so the skill quietly becomes a second execution path |
| `gate_manifest.py` | `marketplace.json` and `plugin.json` drifting from the actual files on disk. A renamed hook script, a version bump that never reached `CHANGELOG.md`, or a duplicate reference to `hooks.json` in `plugin.json` that makes the plugin fail to load |
| `gate_readme_sync.py` | The command lists in `README.md` and `README.ko.md` drifting from `plugin/commands/*.md`, so users who read the Korean docs see a different picture |
| `gate_command_invocations.py` | Invocation forms that do not run from the user's project directory getting into command or policy files or spec templates. Module-execution forms, forms that `cd` into the plugin root, and subcommand names that do not exist |

## Test conventions

```bash
cd plugin && python3 -m unittest discover -s tests -v
```

The tests must pass with no network and no external binaries. A test that needs the `claude` or `codex` binary creates a fake executable in a temporary directory and prepends it to `PATH`.

Every gate has at least three tests: allow, refuse/block, and **exit 0 even on internal error**. The third one exists as a test because it is hookio's core guarantee.
