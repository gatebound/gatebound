# Quickstart

## Install

```
/plugin marketplace add https://github.com/gatebound/gatebound
/plugin install gatebound@gatebound
```

Restart Claude Code so the hooks in `plugin/hooks/hooks.json` load. Codex
installs the same plugin from the same marketplace; see "Codex (app and CLI)"
in `README.md` for its commands and the one-time hook trust step.

## Start from an idea

```
/gatebound:discover
/gatebound:interview
```

If you don't yet know what to build, start with `/gatebound:discover`: a
free-ranging conversation that surfaces problems worth solving and writes
`spec/00-discovery.md`. If you already know, go straight to
`/gatebound:interview`, which goes deep on pages, behavior and data and, for a
known product category, proposes standard features for you to prune. It
writes `spec/01-prd.md` (including an Assumption Ledger — anything decided on
your behalf, listed explicitly) and `spec/03-architecture.md`. Review both;
they're plain Markdown meant to be read and edited by hand.

If you're starting from a visual mockup or existing screens instead, run
`/gatebound:mockup` in place of (or in addition to) the interview. It
derives `spec/02-screens.md` and `spec/tokens.json`, and records anything
it had to guess at as a ledger gap entry rather than silently filling it
in.

If your design input is a pattern that applies across screens, or a
reference site rather than a mockup — a Figma file, a live URL, a preset,
or a pattern file you wrote — run `/gatebound:design` instead. It writes
`spec/02-design.md` and merges into the same `spec/tokens.json`, and it can
run at any stage, including after tasks are already underway.

## Break the spec into tasks

```
/gatebound:tasks
```

Writes `spec/04-tasks.md` as a set of `gatebound-task` fenced JSON blocks —
each with an id, a title, a `write_scope`, a self-contained instruction,
and at least one gate command that must pass.

## Set the completion bar

```
/gatebound:gate
```

Writes `spec/05-gate.md` as `gatebound-criterion` fenced JSON blocks — each
one an `argv` to run, an expected exit code, and any artifacts it must
produce. This command also asks you to approve the gate file
(`gatebound approve spec/05-gate.md`), which records its SHA-256 hash. If
`spec/05-gate.md` changes afterward, that approval goes stale
automatically — nothing has to be remembered.

## Build

```
/gatebound:build
```

By default this session implements each task itself, and `jobs complete`
runs that task's gates. With `--backend <name>` or `build.execution: worker`,
workers run the tasks instead, each inside its declared `write_scope`; the
`PreToolUse` write gate enforces that scope for the duration of the task,
independent of what the worker itself believes it's allowed to touch. Either
way the gates decide: a task that exits 0 but fails its own gate is recorded
as failed, not passed.

## Verify

```
/gatebound:verify
```

An independent, read-only evaluator runs the criteria and the E2E steps in
`spec/05-gate.md`; then this session re-runs the completion contract and
reports one verdict per criterion. The contract's aggregate is `ok`, `fail`
or `unverified`; an E2E step can also come back `warn`. `unverified` means a
criterion could not be checked at all; it is never rounded to a pass.

## Check the install itself

```
/gatebound:doctor
```

Runs an 8-axis diagnosis (plugin files, hook registration, project state,
spec validity, contract freshness, worker availability, Python version,
Codex host layer)
and prints a copy-pasteable fix for anything that isn't `ok`.

## Where things end up

```
spec/            # human-reviewed, meant to be committed
.gatebound/        # runtime state; config.json and approvals.json are
                 # committed, runs/ and jobs/ are gitignored
```

See `README.md` for the full command list and `docs/ARCHITECTURE.md` for
the complete file formats.
