# gatebound user manual

This is the English edition. The Korean original is in [docs/manual/](../00-index.md).

gatebound is a Claude Code plugin. It turns the rules you used to write as prose in `CLAUDE.md` into hooks that actually run. This manual has 12 documents, and everything in it was checked against the `docs/ARCHITECTURE.md` contract and the actual code.

## Documents

| Document | In one line |
|---|---|
| `01-what-and-why.md` | What gatebound is, which problems it solves, the 4 core principles, and a **first-30-minutes quick start** |
| `02-install.md` | Install, requirements, the 8-axis doctor verdict table, uninstall and update |
| `03-concepts.md` | Core concepts: verdict words, the spec set, the assumption ledger, the completion contract, hash-anchored approval |
| `04-pipeline.md` | The 7-stage pipeline flow chart and each stage's inputs, outputs and gates |
| `05-commands.md` | Reference for the 10 commands |
| `06-spec-files.md` | Required sections of the spec documents and the fence JSON schemas |
| `07-gates.md` | What each of the 9 hook gates blocks |
| `08-cli.md` | CLI reference, subcommands and exit codes |
| `09-worked-example.md` | The Quicknote worked example — from one sentence to done |
| `10-troubleshooting.md` | Symptom → cause → fix table |
| `11-security.md` | Security and operating posture |
| `12-design-decisions.md` | Summaries of the key ADRs and the core rules of the architecture contract |

## Reading order

### First-time users

If you want to get a feel for it fast, **start at the "first 30 minutes" section of `01-what-and-why.md` and run it right away**. You can look up the concepts when you get stuck.

If you prefer to read step by step, use this order.

1. `01-what-and-why.md` — understand first why you need this tool. If you skip it, the tool feels like it is in your way when a gate blocks you.
2. `02-install.md` — install, and use `/gatebound:doctor` to confirm the hooks are actually attached.
3. `03-concepts.md` — learn why `unverified` is not a pass and why approval is tied to a hash.
4. `04-pipeline.md` — see the order of the pipeline stages.
5. `09-worked-example.md` — read through an example that actually ran.
6. If you get stuck, `10-troubleshooting.md`.

### For reference

- Command arguments → `05-commands.md`
- Which headings a spec file needs → `06-spec-files.md`
- Why you were blocked → `07-gates.md`
- Typing the CLI yourself → `08-cli.md`
- Why it is designed this way → `12-design-decisions.md`

## Assumptions

- Every CLI example in this manual has the form `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" <subcommand>`. The reason is in `08-cli.md`. **Most work is done with `/gatebound:<command>` slash commands, without typing the CLI yourself** — the commands call the CLI internally, and you type it directly only to inspect state.
- Identifiers (file names, commands, flags, JSON keys, fence names, `ok`/`warn`/`fail`/`unverified`) are not translated.
- The current version is 0.17.0.

## Export to Notion

To put this manual into Notion, build an import bundle.

```bash
python3 tools/build_manual_bundle.py
```

This creates `dist/gatebound 사용자 매뉴얼.zip`. In Notion, upload it with Import → Markdown & CSV,
and it arrives as a tree of one parent page and 13 child pages (this index plus the 12 documents).
The bundle packages the Korean manual (`docs/manual/`) only; this English edition is not included.

The repository is the source of truth. To change the content, edit `docs/manual/` and rebuild the
bundle, then re-import. If you edit only the Notion copy, the two copies drift apart.
