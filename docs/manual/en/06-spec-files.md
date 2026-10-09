# Spec file format

`plugin/spec-kit/heading-map.json` defines the required H2 headings of the documents under `spec/`. `spec validate` checks that every heading listed there is present, and that no heading from the other language is mixed in. It does not enforce order, only presence. The headings below are the English (`en`) set; a separate Korean (`ko`) set exists too.

## 00-discovery.md (optional)

An after-the-fact summary of the improvement opportunities found in one free-ranging conversation, with no named gates and no fixed order. Each opportunity holds a `summary` (one sentence stating only the problem or the want, with no solution), `notes` (everything that does not fit a structured field), and as much of `user`/`current_way`/`frequency_per_month`/`minutes_per_run`/`why_chain`/`failed_attempts` as is known. When one becomes `chosen: true`, it gets a `verdict_suggested` that the model proposes and a `verdict` that the user confirms (`build`/`reuse`/`eliminate`/`unknown`).

If the confirmed `verdict` is `eliminate` or `reuse`, `spec validate` reports `pain_verdict_blocks` and blocks `/gatebound:interview`. `unknown` never blocks.

`insights_count` honestly records how substantive the conversation actually was (the number of distinct facts and branches). It has no upper limit; if it is too low, `spec validate` reports only `warn`.

## 01-prd.md (required)

What you build and why. If this file is missing, `spec validate` fails.

| Required heading | What it holds |
|---|---|
| `## Problem` | What is inconvenient today |
| `## Current state (measured)` | Measured values. If there are none, write "not measured" and add it to the ledger |
| `## Goals` | What you want to achieve |
| `## Non-goals` | What you explicitly will not do |
| `## Users` | Who uses it |
| `## Features` | The list of features, each with an `F<n>` id |
| `## Acceptance criteria` | The conditions each feature must meet |
| `## Assumption ledger` | Every judgment nobody has confirmed |

The assumption ledger is a table with two extra columns at the end: `Blocking` and `Confirmed` (`y`/`n`). Judge `Blocking: y` not by "if this row is wrong, does the whole plan collapse?" but by **"if this row is wrong, does the perceived quality of a core feature directly suffer?"** A judgment that decides the quality of the feature itself, even if the plan survives (such as how closeness is calculated, which is the feature's reason to exist), is `Blocking: y`. If any row is `Blocking: y` and `Confirmed: n`, `spec validate` reports `fail`, and `/gatebound:gate` refuses to proceed until that row is resolved. Wherever the body leans on that assumption, leave an inline marker with the same number. Here is a real example from the playground.

```markdown
| # | Assumption | Basis | Impact if wrong | How to confirm | Blocking | Confirmed |
|---|---|---|---|---|---|---|
| 3 | The list is sorted by modified time, newest first, with no pagination | The target scale is 100 notes, so one screen is enough | If notes grow to hundreds, the first screen gets slow | Re-confirm the note count ceiling with the user | n | n |
```

## 02-screens.md

`## Screen list` / `## Screen flow` / `## Per-screen states` / `## Components` / `## Design tokens` / `## Negative space`

Write all four states for every screen: normal, empty, error, and loading. Mark any state you designed because the mockup did not show it as an assumption. `## Negative space` records what the mockup does **not** cover. Look for offline, permissions, long lists, long strings, error recovery, first run, and so on.

After `## Negative space`, once the user confirms a real clickable prototype, a `Prototype confirmed <date>` line is added (in Korean, `프로토타입 확정 <날짜>`). In a project with a UI, if this line is missing, `spec validate` reports `prototype_required` and `/gatebound:tasks` refuses to proceed.

## 02-design.md (optional)

`## Sources` / `## Design patterns` / `## Components` / `## Design tokens` / `## Not covered`

Where `/gatebound:mockup` holds per-screen information, this file holds design patterns that cut across screens (`P<n>`) and the visual specs of components. It shares `spec/tokens.json` with `mockup` and merges into it.

## 03-architecture.md

`## Stack` / `## Data model` / `## Identifiers and tokens` / `## External integrations` / `## Constraints`

The gate commands and `write_scope` in `04-tasks.md` must match the stack and paths written here.

## 04-tasks.md

`## Task list` / `## Execution order` / `## Scope rules`

Write each task as one JSON object in one `gatebound-task` fence.

### gatebound-task schema

| Field | Type | Rule |
|---|---|---|
| `id` | string | Unique within the file |
| `title` | string | A human-readable title |
| `write_scope` | list of globs, or `"read-only"` | Cannot be empty |
| `instruction` | string | Self-contained. The worker sees only this string and the scope |
| `gates` | list of objects | At least one. Each has `name` and `argv` |
| `depends_on` | list of ids | Every id must exist in this file |
| `round` | integer | Tasks in the same round cannot have overlapping `write_scope` |

```json
{"id": "task-db-schema",
 "title": "Create the Note store (db.py) with basic CRUD",
 "write_scope": ["db.py", "tests/test_db.py"],
 "instruction": "Using only the standard library sqlite3, create a NoteStore class in db.py. ...",
 "gates": [{"name": "test", "argv": ["python3", "-m", "unittest", "tests.test_db", "-v"]}],
 "depends_on": [],
 "round": 1}
```

`instruction` must not be short. The worker cannot see this conversation. The playground's real `instruction` packs the schema, method signatures, validation rules, and test cases into a single paragraph.

## 05-gate.md (required)

`## Completion criteria` / `## Not counted as done` / `## How evidence is collected`

Each criterion is one JSON object in one `gatebound-criterion` fence.

### gatebound-criterion schema

| Field | Type | Rule |
|---|---|---|
| `id` | string | Unique. Including the id of the task it verifies makes the traceability warning go away |
| `argv` | list of strings | Not empty. Runs without a shell, so no `&&`, pipes, or redirection |
| `expect` | object | Besides `exit` (integer, default 0): `stdout_contains` / `stdout_not_contains` / `stderr_contains` / `stderr_not_contains` (a string or a list of strings, all of which must hold), and `stdout_regex` / `stderr_regex` (one pattern). Output checks run against the full stream, not the stored tail. An unknown key, a wrong type, or an invalid regex is a `derive` error and a `validate` `fail` |
| `timeout_s` | number | The ceiling for this criterion |
| `artifacts` | list of relative paths | Must exist after the run. If missing, `fail` |
| `tier` | `"turn"` or `"verify"` | Optional, default `"turn"` (ADR-0024). The Stop gate runs `turn` at the end of every turn while it judges the build; `verify` runs only in `/gatebound:verify`, `contract run`, and `contract baseline`. Any other value is a `derive` error and a `validate` `fail`. If there is no `turn` criterion at all, or a screenshot criterion (artifact `spec/design/build-*.png`) is `verify`, `validate` reports `warn`: the end of a turn during the build would then check nothing (or no screen) |

```json
{"id": "task-note-search-works",
 "argv": ["python3", "-m", "unittest", "tests.test_notes_search", "-v"],
 "expect": {"exit": 0},
 "timeout_s": 45,
 "artifacts": []}
```

To make "no skips" a criterion instead of prose, write an output expectation.

```json
{"id": "task-note-search-no-skips",
 "argv": ["python3", "-m", "unittest", "tests.test_notes_search", "-v"],
 "expect": {"exit": 0, "stdout_not_contains": ["skipped", "SKIP"], "stderr_not_contains": ["skipped"]},
 "timeout_s": 45}
```

`artifacts` paths must be relative, cannot contain `..`, and must stay inside the project root after `realpath` resolution. Escaping through a symbolic link is `fail`.

### gatebound-budget schema

The overall run budget. `05-gate.md` can hold **at most one**.

| Field | Type | Rule |
|---|---|---|
| `total_budget_s` | number | Default 45, ceiling 600 |

```json
{"total_budget_s": 180}
```

Missing, not a number, zero, negative, more than one, or over 600 is a `derive` error. The ceiling exists because the Stop gate runs this. A check that takes longer than the user's patience is worse than a check that reports `unverified` and stands down.

Measure first, declare later. Do not raise the budget to hide a slow test you have not looked into.

### Not counted as done

This section is the heart of this file. Write the conditions that void a plausible-looking pass. Include at least the following.

- Tests were skipped, disabled, or narrowed to make them pass
- A criterion timed out — that is `unverified`, not a pass
- The command exited 0 but a declared artifact is missing
- TODOs, stubs, or empty implementations remain
- A failing criterion was deleted by editing this file
- Success was reported without actually running anything

Add project-specific conditions that come from the constraints in `03-architecture.md`.

### Screenshot criteria and the `-visual` verdict

A criterion for a task that touches the UI requires `spec/design/build-<task-id>.png` as an `artifacts` entry (captured with Playwright or similar, with `argv` run directly as a subprocess). When this criterion is `ok`, the `verify` evaluator actually reads that image, compares it against the recorded design direction and `design-antipatterns.json`, and issues a separate verdict, `<criterion-id>-visual`. **This verdict is not part of the `contract run` aggregate**, because the aggregate counts only code criteria (exit code, artifact presence). Even if the aggregate is `ok`, do not report completion while any `-visual` verdict is `fail`.

## RECOVERY.md

`## Diagnosis loop` / `## Retry limit` / `## Scope lock` / `## Rollback procedure`

When `build` fails the same task 3 times, it reads this file and writes its diagnosis here, under a heading named after the task.

## PROGRESS.md

`## Status` / `## Milestones` / `## Failed attempts` / `## Last verification`

`build` and `verify` write it. Keep the template's headings exactly as they are. `spec validate` treats headings from the other language as cross-language residue and fails. The `verify` evaluator writes only under `## Last verification`.

## tokens.json

An optional output that both `mockup` and `design` create or merge into. It holds machine-readable values grouped by kind.

```json
{"version": 1, "source": "mockup.html",
 "color": {"accent": "#0E5C55", "danger": "#B3382C"},
 "space": {"md": "12px", "lg": "16px"}}
```

When `design` writes it, it is v2 and also holds the patterns that cut across screens.

```json
{"version": 2, "source": ["mockup.html", "preset:shadcn-neutral"],
 "patterns": [{"id": "P1", "rule": "Cards use only a 1px border, no shadow", "applies_to": ["all"], "evidence": "preset:shadcn-neutral"}],
 "color": {"accent": "#0E5C55"}, "space": {"md": "12px"}}
```

Token names are identifiers. Keep the spelling the design system uses. Dropping a whole group is better than inventing values. If the file already exists, both commands merge into it instead of overwriting it.
