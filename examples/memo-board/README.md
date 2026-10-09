# Example: memo board

[한국어](README.ko.md)

A three-task memo board (add a note, delete a note, show the note count) for a
360 px mobile screen, notes kept in `localStorage`. It is the output of a real,
headless `/gatebound:build` run during the 0.16.0 rehearsal, copied here with its
spec so you can see what gatebound's inputs and outputs look like for a complete
small project, and run the pipeline on it yourself.

The spec is in Korean because the rehearsal was run in Korean; gatebound detects
the language from `spec/01-prd.md` and answers in it.

## What the rehearsal measured

| Step | Result |
|---|---|
| `/gatebound:build` (host execution, three tasks in dependency order) | 123 s, all three tasks `passed` on the first attempt |
| Follow-up turns after the build | 6–24 s each: the Stop gate had stood down after the finished build instead of re-running the contract on every turn |
| `/gatebound:verify` | 132 s, contract 5/5 `ok` |

The verify run also recorded three visual `warn`s, kept here as found: the
heading reads `메모 보드 v2` (a follow-up turn changed it to exercise the
stood-down Stop gate) while `spec/02-screens.md` says `메모 보드`; every glyph
uses one font; and the lower part of the screen is empty. A `warn` is reported,
not rounded to a pass or a fail. The captures are in [`screenshots/`](screenshots/).

## What is in the folder

| Path | What it is |
|---|---|
| `spec/01-prd.md` … `spec/05-gate.md`, `spec/RECOVERY.md` | the spec set that was approved in the rehearsal (`RECOVERY.md` stays a draft): PRD with its assumption ledger, screens, architecture, the three `gatebound-task` fences, and the completion contract |
| `index.html`, `style.css`, `app.js`, `server.js` | the page and a `node:http` static server on port **4183** |
| `notes.js`, `remove.js`, `count.js` | pure functions, one per task, unit-tested |
| `delete-ui.js`, `count-ui.js` | the delete and count features, each installed into the page without editing the files another task owns |
| `tests/` | `node:test` unit tests |
| `e2e/` | Playwright specs: one per task, a journey across all three, and the screenshot criterion |
| `package.json`, `package-lock.json`, `playwright.config.ts` | the only dependency is `@playwright/test` |
| `screenshots/` | the three captures from the rehearsal's verify run; the add-note and note-count captures are identical because the rehearsal's screenshot spec captured the same final state for both — a known flaw of this example spec |

There is no `.gatebound/` directory: approvals are hashes of your copy of the
files, so you record them yourself. `spec/PROGRESS.md` is left out too; the
build writes a fresh one.

## Try it

You need Node.js 22+ (the `unit-all` criterion passes `tests/*.test.js` to `node --test` unexpanded, which needs its glob support), gatebound installed in Claude Code (or Codex, using
`$gatebound-<name>` in place of `/gatebound:<name>`), and Playwright's Chromium.

1. **Copy the folder out of this repository.** gatebound finds a project by the
   nearest `.gatebound/` or `.git/`, so inside this checkout it would treat the
   whole gatebound repository as the project.

   ```bash
   cp -R examples/memo-board ~/memo-board
   cd ~/memo-board
   git init
   npm install
   npx playwright install chromium
   ```

2. **Approve the contract.** Open the project in your host and run
   `/gatebound:gate`. It derives the criteria from the PRD and tasks, runs each
   once, shows them to you, and on your approval pins the hash of
   `spec/05-gate.md`. Until then the write gate keeps code changes closed.

3. **Build.** Run `/gatebound:build`. The source files are already here, so the
   three tasks should pass their gates at once. To watch gatebound build the
   board from nothing, delete the source and test files first and keep
   `spec/`, `package.json`, `package-lock.json` and `playwright.config.ts`
   (the first task's instruction says the Playwright config already exists):

   ```bash
   rm -f index.html style.css app.js server.js notes.js remove.js count.js \
         delete-ui.js count-ui.js tests/*.js e2e/add.spec.ts e2e/delete.spec.ts e2e/count.spec.ts
   ```

   `e2e/journey.spec.ts` and `e2e/screenshots.spec.ts` are grading files
   named by the contract; keep them.

4. **Verify.** Run `/gatebound:verify` for the independent check, including the
   full end-to-end suite.

Port 4183 is fixed in `playwright.config.ts`; if something else holds it,
stop that process rather than editing the config, which is a grading file.
`/gatebound:doctor` reports a port conflict before you build.

## Criterion tiers

`spec/05-gate.md` splits its five criteria by when they run:

| Criterion | Tier | Runs |
|---|---|---|
| `server-syntax` (`node --check server.js`) | `turn` | Stop gate, end of each turn |
| `unit-all` (`node --test tests/*.test.js`) | `turn` | Stop gate, end of each turn |
| `journey-…` (one Playwright journey across all three tasks) | `turn` | Stop gate, end of each turn |
| `screenshots` (writes `spec/design/build-task-*.png`) | `turn` | Stop gate, end of each turn |
| `e2e-suite` (every Playwright spec) | `verify` | only in `/gatebound:verify` |

`turn` criteria are fast enough to judge at the end of each turn while
`/gatebound:build` runs; once the build has settled and been judged, the Stop
gate stands down, which is why the follow-up turns above took seconds, not
minutes. `/gatebound:verify` runs every tier. The full suite repeats what the
task gates already ran, so it waits for verify.

The `gatebound-budget` fence caps one contract run at 300 s. Under build the
Stop gate also starts within `stop.budget_s` (120 s by default); a criterion
that does not fit is listed as deferred and judged on a later Stop or in
verify, never counted as `ok`.
