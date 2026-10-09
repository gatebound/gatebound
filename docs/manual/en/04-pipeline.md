# The pipeline end to end

![The gatebound pipeline](../../assets/en/pipeline.svg)

## The full diagram

```text
                    [ /gatebound:doctor ]  ← any time. 8-axis install/state diagnosis
                    [ /gatebound:setup  ]  ← once per project. config and worker check
                              │
   don't know what to build   ▼
        │            ┌───────────────────┐
        └───────────▶│ 0. discover (opt.)│──▶ spec/00-discovery.md
                     │  free conversation│    (verdict gate)
                     └───────────────────┘
                              │
   problem is chosen          ▼
        │            ┌───────────────────┐
        └───────────▶│ 1. interview      │──▶ spec/01-prd.md
                     │  conversation +   │    spec/03-architecture.md
                     │  research         │
                     └───────────────────┘
                              │
                              ▼
                     ┌───────────────────┐
                     │ 2. mockup         │──▶ spec/02-screens.md
                     │ ★ confirm the     │    spec/tokens.json
   pattern/reference │   prototype       │    spec/design/prototype-*.html
   site              └───────────────────┘
        │                     │
        │            ┌───────────────────┐
        └───────────▶│ 2b. design (opt.) │──▶ spec/02-design.md
                     │  (re-enter at any │    spec/tokens.json (shared with mockup)
                     │   stage)          │    gap rows added to 01's assumption ledger
                     └───────────────────┘
                              │
                              ▼
                     ┌───────────────────┐
                     │ 3. tasks          │──▶ spec/04-tasks.md
                     └───────────────────┘    (gatebound-task fences)
                              │
                              ▼
                     ┌───────────────────┐
                     │ 4. gate           │──▶ spec/05-gate.md
                     │  ★ human approval │    .gatebound/contract.json
                     └───────────────────┘    .gatebound/approvals.json
                              │
              [the write gate opens here]
                              │
                              ▼
                     ┌───────────────────┐
                     │ 5. build          │──▶ .gatebound/jobs/<job_id>/
                     │ host (default) →  │    spec/PROGRESS.md
                     │   this session    │
                     │ worker → spawned  │
                     │   workers         │
                     └───────────────────┘
                              │
                              ▼
                     ┌───────────────────┐
                     │ 6. verify         │──▶ independent evaluator verdict (+ -visual)
                     │ producer≠evaluator│    spec/PROGRESS.md last verification
                     └───────────────────┘
                              │
                [the Stop gate runs the contract]
```

## Input, output and gates per stage

| Stage | Command | Input | Output | Related gates |
|---|---|---|---|---|
| 0 | `/gatebound:discover` | Nothing is needed. Free conversation | `00-discovery.md` | `spec validate` blocks a confirmed verdict of `eliminate`/`reuse` as `pain_verdict_blocks`. Optional stage |
| 1 | `/gatebound:interview` | The improvement opportunity discovery chose (if any), the existing repo | `01-prd.md`, `03-architecture.md` | Free conversation plus domain research (`WebSearch`) proposes features, and the user prunes them |
| 2 | `/gatebound:mockup` | A Figma URL, HTML, screenshots, or a design preset | `02-screens.md`, `tokens.json`, the confirmed prototype | `prototype_required` clears only when the user confirms the prototype |
| 2b | `/gatebound:design` | A Figma URL, screenshots, HTML, a live site URL, a preset name, a user pattern file | `02-design.md`, `tokens.json` (shared), ledger gap rows | The question gate only counts here; its budget covers `interview` alone. `/gatebound:design` asks at most one `AskUserQuestion` by its own instruction. If `spec/tokens.json` exists, `tasks` adds a tokens gate to style-related tasks by default |
| 3 | `/gatebound:tasks` | `01`, `02`, `02-design`, `03`, the actual repo structure | `04-tasks.md` | Refuses to run if `02-screens.md` has no prototype confirmation record |
| 4 | `/gatebound:gate` | The acceptance criteria in `01`, the tasks in `04` | `05-gate.md`, `contract.json`, approval | Approval opens the write gate |
| 5 | `/gatebound:build` | `04-tasks.md`, the approved `05-gate.md` | The job directory, `PROGRESS.md` | If `build.execution` is `host` (the default), this session implements the tasks itself and `write_scope` is guidance in each task's prompt — nothing enforces it mechanically; the task gates and the Stop gate still judge the result. In a worker session (`build.execution: worker`, `--backend`, or a round handed to workers) the write gate enforces `write_scope` (ADR-0013). UI tasks require a screenshot artifact |
| 6 | `/gatebound:verify` | `contract.json`, `05-gate.md` | The verdict table (code criteria + `-visual`), the last verification in `PROGRESS.md` | The spawn gate checks the evaluator's scope; the stop gate runs the contract |

`doctor` and `setup` are not part of this sequence. Run `setup` once per project, and `doctor` any time you suspect a problem.

Unlike the other stages in this table, `/gatebound:design` has no fixed place in the order. You can run it before the mockup, together with the mockup, or even during `build`. When it runs during `build`, it does not edit `04-tasks.md` or `05-gate.md` directly; it only reports the list of affected tasks — redelegation has to go through `/gatebound:tasks` and `/gatebound:gate` again. If any of `02-screens.md`, `02-design.md` or `tokens.json` changes after the contract was derived, `contract status` returns `fail` (stale).

## What blocks at each stage

### Before stage 1

While `spec/` holds none of gatebound's spec files, write gate rule (a) blocks nothing; only rule (c), protected state, applies. An RSpec project's `spec/` or an empty `spec/` does not count. Rule (a) fires once `spec/` holds one of gatebound's spec files, such as `00-discovery.md` or `01-prd.md` (ADR-0036).

### During stages 1 to 3

`spec/` now holds gatebound's spec files and `05-gate.md` is not approved, so the write gate refuses edits to source files. Only `spec/**`, `.gatebound/**`, `docs/**`, `README*` and `*.md` at the root can be written. Rule (c) is checked first, so of `.gatebound/**` only `config.json` and `eval/**` are writable. Without this allowlist, you could not write the very spec that opens the gate.

### At the stage 4 approval

When the user reads and approves `05-gate.md`, its hash is pinned. From that moment, write gate rule (a) passes and source files can be written. Approval does not arm the Stop gate; that happens only when `/gatebound:build` or `/gatebound:verify` becomes the active pipeline (below).

### During stage 5

Under `build.execution: host` (the default), this session implements the tasks and `GATEBOUND_TASK_ID` is not set, so rule (b) does not fire: each task's `write_scope` is guidance in its prompt, and nothing enforces it mechanically. The task gates and the Stop gate still judge the result. A worker session — `build.execution: worker`, `--backend`, or a round handed to workers — has `GATEBOUND_TASK_ID` set, and write gate rule (b) fires. Rule (b) is stricter than (a): it has no documentation allowlist. A worker assigned `src/auth/**` cannot edit the PRD.

### Stage 6 and the end

Even if every task in `build` is `passed`, that is not the same as passing the completion contract. Only `verify` reports that. The Stop gate runs the contract at each turn end only while `/gatebound:build` or `/gatebound:verify` is the active pipeline — set by typing the command, or by the skill gate when the command starts through the `Skill` tool (ADR-0032). Under `build` it runs only `turn`-tier criteria, within `stop.budget_s`; under `verify` it runs every criterion. If anything is `fail` or `unverified`, it blocks the turn from ending, up to 3 times. Once a settled build or verify verdict is recorded, it stands down until one of those commands re-arms it (chapter 7).

## Paths back

- Editing `05-gate.md` makes the approval stale and the contract stale. You have to run `contract derive` and approve again.
- A failed task goes back for another attempt: under `host` this session fixes the code itself and runs `jobs complete` again; under `worker`, `jobs redelegate`. Within a job a task stops after 3 consecutive failures (1 + `build.max_retries`, default 2), and every path stops it after 2 identical failures in a row; a new `jobs start` also refuses a task that already carries 2 consecutive failures. The refusal exits with code 3. The session then writes the diagnosis into `spec/RECOVERY.md` and stops the pipeline. Once the cause is fixed, `jobs start --force-retry <task_id>` clears the count.
- If `verify` is not `ok`, it lists what has to change and stops. Fixes go back through `/gatebound:build`.
