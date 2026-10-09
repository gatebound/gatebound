# Worked example — Quicknote

This is a record of a real run from a one-sentence idea to a completion contract at `ok`. Every number comes from the real state files under `.gatebound/`.

**How to read this page**: it shows the commands to type, and alongside them **what appears on screen and what you, the user, have to decide at that point**. Stages 5 and 6 in particular show "how the tool reacts when things do not go well", so for a first-time user those parts are often the most useful.

> **Version note**: this run took place before discover/interview became free-ranging conversations and before the prototype confirmation gate was added. The overall flow (spec → tasks → completion criteria → build → verify) and the numbers are still valid, but the way questions are actually asked in the interview and mockup stages follows the current description in `05-commands.md`.

## Starting point

Notes were scattered across several text files, and finding last week's meeting notes took 20 minutes. The project started from that frustration.

## Stage 1 — interview

```bash
/gatebound:interview A personal notes app where I can jot things down and find them again quickly later
```

This produced `spec/01-prd.md` and `spec/03-architecture.md`. A value that could not be measured was not made up: it went into the table as "not measured" and onto row 1 of the assumption ledger.

```markdown
| Metric | Current value | Source | Measured on |
|---|---|---|---|
| Time it took to find last week's meeting notes | 20 minutes | User statement (1 case) | 2026-09-10 |
| Number of scattered note files | not measured | — | 2026-09-10 |
```

The assumption ledger got 6 rows. Every judgment the user had not stated was recorded: the title length limit, the list sort order, no undo for deletion, the search method, the DB file location, and so on.

> **What you do here**: read the feature list and the assumption ledger and decide "is this what I wanted?". The assumption ledger is **the list of things the AI decided on its own**, so if something is wrong, now is the cheapest time to say so. A value that could not be measured staying "not measured" is normal — it means nothing was made up.

## Stage 2 — mockup

```bash
/gatebound:mockup mockup.html
```

It extracted the screens and CSS custom properties from `mockup.html` and wrote `spec/02-screens.md` and `spec/tokens.json`. The tokens are exactly the values the mockup actually uses.

```json
{"version": 1, "source": "mockup.html",
 "color": {"accent": "#0E5C55", "danger": "#B3382C"}}
```

## Stage 3 — tasks

```bash
/gatebound:tasks
```

`spec/04-tasks.md` got 8 tasks. All are vertical slices, and each has 1 gate.

| Task id | Round | write_scope |
|---|---|---|
| `task-db-schema` | 1 | `db.py`, `tests/test_db.py` |
| `task-note-create` | 2 | `app.py`, `tests/test_notes_create.py` |
| `task-note-list` | 3 | `app.py`, `tests/test_notes_list.py` |
| `task-note-update` | 4 | `app.py`, `tests/test_notes_update.py` |
| `task-note-delete` | 5 | `app.py`, `tests/test_notes_delete.py` |
| `task-note-search` | 6 | `app.py`, `tests/test_notes_search.py` |
| `task-static-frontend` | 7 | `static/`, `tests/test_static.py` |
| `task-full-suite-gate` | 8 | Full suite check |

Several tasks touch `app.py`, so they were assigned different rounds. Instead of widening scopes to remove the conflict, the tasks were serialized.

> **What you do here**: very little. This stage is mostly automatic. Still, it is worth glancing at the number of tasks and rounds — **more rounds means more sequential execution, so it takes longer.** If you see rounds split with no reason, you can ask whether they can be merged.

## Stage 4 — gate

```bash
/gatebound:gate
```

`spec/05-gate.md` got 8 criteria. Each id contains a task id so that they map 1:1 to the 8 tasks. `## Not counted as done` got 6 general clauses plus project-specific ones: importing a package outside the standard library, the server binding to anything other than `127.0.0.1`, reporting the search performance criterion as passed without measuring it, and so on.

> **What you do here — the most important decision in this example**: the 8 criteria are shown as a table and you are asked for approval. There is one question to ask: **"If all 8 of these pass, has what I wanted really been built?"** If something is missing, ask for more criteria. The moment you approve, writing source code opens up, and when the session ends these commands really run.

After approval, the contract was derived.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" contract derive
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" approve spec/05-gate.md
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" approve check spec/05-gate.md
```

## Stage 5 — build

```bash
/gatebound:build
```

Job `20260910T060008Z-b1dc` started. Backend `claude`, parallelism 3, task timeout 900 seconds, at most 2 retries.

### What the gate caught — the worker exited 0

On the first attempt at `task-note-delete`, the worker **reported success with exit code 0**. But when the gate ran the test, it failed.

```text
File "tests/test_notes_delete.py", line 148
    </content>
    ^
SyntaxError: invalid syntax
```

The worker had left the string `</content>` at the end of the test file. The Python file could not even be imported. Had the worker's own report been trusted, this task would have been recorded as passed.

Because the same file was broken, `python3 -m unittest discover` in `task-full-suite-gate` failed too. It ran 67 tests and exited 1 with 1 collection error.

The job state recorded this:

```json
{"state": "failed", "exit": 0, "gates_verdict": "fail",
 "gates_passed": 0, "gates_total": 1,
 "detail": "worker exited 0 but gates verdict is fail (0/1 ok)"}
```

### Redelegation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs redelegate task-note-delete
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs redelegate task-full-suite-gate
```

The previous attempt was kept as `attempt-1/`, and the task ran again with the failed gate's output appended to the prompt. Both tasks passed on the 2nd redelegation. The final state of `task-full-suite-gate` was all 73 tests OK, gate 1/1.

The final result was 8/8 `passed`.

> **What you do here**: when you see a failed task, have it retried. There is one thing to judge — **is the cause the code, or the completion condition itself?** In the case above the code was the problem, so retrying was right. If the condition had pointed at a file that does not exist, the fix would be to edit `spec/04-tasks.md`, not to retry. If the same task fails 3 times in a row, it stops automatically and leaves a diagnosis, so retries do not repeat forever.

## Stage 6 — verify and the budget problem

```bash
/gatebound:verify
```

An independent evaluator ran the contract. The aggregate verdict was not `ok` but **`unverified`**. Of the 8 criteria, 6 were `ok` and 2 were `unverified` because of timeouts.

| Criterion | Verdict | Measured | Budget at the time |
|---|---|---|---|
| `task-note-update-works` | `unverified` | 6.61–6.65 s (3 measurements) | 5 s |
| `task-full-suite-gate-works` | `unverified` | 24.5 s | 10 s |

The important point is that this was **not an implementation defect**. Both tests passed when run by hand. The budget was simply smaller than the measured time. Even so, gatebound did not round this up to a pass. The check could not finish, so it is `unverified`.

> **What you do here — the first time you meet `unverified`**: at first it is easy to feel "the tool is being fussy", but it is simple to read. **`unverified` does not mean "wrong"; it means "could not check".** So the fix goes in a different direction too — you do not touch the code; you look at why the check could not complete (usually a timeout) and remove that cause. Stage 7 below is that process.

The evaluator also ran every E2E step by hand. It started the server on a temporary DB and port and sent real HTTP requests.

```bash
QUICKNOTE_DB=/tmp/e2e_notes.db QUICKNOTE_PORT=8099 python3 app.py
```

All 10 E2E steps were `ok`. After seeding 101 notes through the API, the measured search round trip was 0.0115 seconds, meeting the 1-second acceptance criterion.

## Stage 7 — raising the budget and re-approving

Based on the measurements, the individual `timeout_s` values were raised to 15 and 45 seconds, and the total budget was declared with a `gatebound-budget` fence.

```json
{"total_budget_s": 180}
```

This is the full suite's measured 49 seconds plus headroom. It was declared after measuring, not guessed.

Because `05-gate.md` changed, the approval expired and the contract became stale. It was derived again and approved again.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" contract derive
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" approve spec/05-gate.md --note "budget fence added after measuring 49s total"
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" contract run --json
```

This time it was 8/8 `ok`, 49.4 seconds in total.

## Final state

| Item | Value |
|---|---|
| Tasks | 8/8 `passed` |
| Completion contract criteria | 8/8 `ok` |
| Redelegated tasks | 2 (`task-note-delete`, `task-full-suite-gate`) |
| Declared budget | 180 seconds |
| Measured total time | 49.4 seconds |
| Longest criterion | 24.5 seconds |

## What this run showed

1. **A worker's exit 0 is not evidence.** The worker reported success on a file that still had a SyntaxError. The gate caught it.
2. **`unverified` was not rounded up to a pass.** Two criteria could in fact pass, but they were not confirmed within the budget. The tool reported exactly that.
3. **The budget was declared after measuring.** It was not raised to hide slow tests; 180 seconds was declared on the basis of a measured 49 seconds.
4. **Editing the file expired the approval.** Changing the gate file automatically required re-approval.
5. **The evaluator was not the builder.** A separate read-only agent ran the 10 E2E steps by hand against a real server.
