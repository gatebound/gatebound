# Command reference

Each command is described in the same order: **when to use it / what happens / what it leaves behind / what to do when it blocks**. All of them are `/gatebound:<name>` slash commands; you never need to type the CLI yourself.

## Summary

| Command | When to use it | What it leaves |
|---|---|---|
| `/gatebound:discover` | When what to build is still vague | `spec/00-discovery.md` |
| `/gatebound:interview` | When what to build is decided and you are pinning down screens and features | `spec/01-prd.md`, `spec/03-architecture.md` |
| `/gatebound:mockup` | When you check the screens with your own eyes and confirm them (required if there is a UI) | `spec/02-screens.md`, `spec/tokens.json`, the confirmed prototype |
| `/gatebound:design` | When you apply a design pattern or a reference site (optional, any time) | `spec/02-design.md`, `spec/tokens.json` |
| `/gatebound:tasks` | When you split the spec into units of work | `spec/04-tasks.md` |
| `/gatebound:gate` | When you decide and approve "what has to hold for this to be done" | `spec/05-gate.md`, the approval record |
| `/gatebound:build` | When you actually build | The job record, `spec/PROGRESS.md` |
| `/gatebound:verify` | When everything is built and you verify it with an independent evaluator | The verdict table, `spec/PROGRESS.md` |
| `/gatebound:doctor` | When something seems wrong (any time) | A diagnosis table only; it fixes nothing |
| `/gatebound:setup` | Once, the first time you use gatebound in a project | `.gatebound/config.json` |

## /gatebound:discover

**When to use it**: when what to build is still vague. "I want to make something like a chatbot" — you have a thing to build but not yet whose problem it solves or what that problem is. That is exactly this stage. It is optional; if you skip it, the rest still runs as usual.

**What happens**: there is no fixed question list and no progress indicator such as "3/6". It is a free conversation, one question at a time. It asks about things that actually happened in the past ("The last time you did that, what did you actually do?"), so just answer as it was — "last Tuesday it went like this" is far more useful than "usually it's like this". If you name a solution ("I'd like a search feature"), it asks back how you manage today without that feature.

When the conversation seems to have run dry, **it asks you directly whether to continue or wrap up here.** It does not decide on its own to move on to the summary. If you say "just handle it", it summarizes right away from what has come up so far.

In the summary step, it **condenses what came up into a few improvement opportunities, shows them, and asks you to confirm** they are right. When you pick one, it proposes a judgment on "whether building this yourself is the right call" (`build`/`reuse`/`eliminate`/`unknown`), and you confirm it.

**What it leaves**: one file, `spec/00-discovery.md`.

**When it blocks**: if the confirmed judgment is `eliminate` (no need to build it) or `reuse` (use something that already exists), `/gatebound:interview` is blocked — this is intended behavior. Pick a different improvement opportunity, or change the judgment.

**Next**: `/gatebound:interview`. It takes over the improvement opportunity you picked here without asking about it again.

## /gatebound:interview

**When to use it**: when what to build is decided, but **how many screens there are and what each one does** is not yet written down. If you went through discover, it continues automatically; if not, start with `/gatebound:interview <one line about what you want to build>`. If `spec/01-prd.md` already exists, it works in edit mode rather than writing a new one.

**What happens**: two steps.

First, **a conversation that digs into screens, features and data**. It asks, one at a time, how many screens there are, what the user can do on each screen, what has to exist for each feature to work, and the cases that go badly (an empty list, a failure, two people touching the same thing at once). There is no limit on the number of questions.

Second, **research into the features products in this category usually have**. It first fixes the features that came up in the conversation (these are what make this product different, so it does not touch them), then researches the product's field on the web to find **standard features that never came up in the conversation**, and proposes them. Features confirmed repeatedly across several sources are shown as "hygiene candidates"; features seen in only one place are shown separately as "reference ideas".

Your job here is **to prune the proposals**. "Drop this", "later", "change this to that" — each is a complete answer, and you do not need to give a reason. You refine a proposed list instead of filling in a blank form.

Finally, it **merges the features from the conversation and the features added by research into one list, shows it**, and asks for final confirmation to build it as is.

**What it leaves**: `spec/01-prd.md` (problem, goals, feature list, acceptance criteria, assumption ledger) and `spec/03-architecture.md` (stack, data model, constraints).

**When it blocks**: every judgment you did not confirm stays in the assumption ledger of `spec/01-prd.md` with a number. If any of them that **decides the quality of a core feature** (`Blocking: y`) is still unconfirmed, `/gatebound:gate` later refuses to proceed. The report says which assumptions those are, so you can confirm them then.

**Next**: `/gatebound:mockup`.

## /gatebound:mockup

**When to use it**: after the interview, when you check the screens with your own eyes before building. **For a project with a UI, it is effectively required** — if you do not confirm a prototype here, `/gatebound:tasks` refuses to proceed.

**What happens**: first, **it settles the design direction.** If you have a Figma link, HTML files or screenshots, it reads them; if not, it shows a few prepared design presets and has you pick one. There is no path that skips this without choosing anything — screens built without a design decision come out bland.

Next, it builds **an HTML prototype that actually clicks** and hands you the file path. Every screen and every state (normal, empty, error, loading) can actually be clicked through, and instead of empty forms, it is **filled with plausible sample data** so it looks like a finished product's screens.

Open it and say what to fix, and it fixes it and gives it back. Repeat this round trip as often as you like. Right before confirmation, it asks separately: **"Does this prototype capture enough of what you want? Is any feature missing?"** — omissions you cannot see in a list show up when you click through real screens. If you say something is missing, it goes back to `/gatebound:interview` to define that feature properly, then rebuilds the prototype.

**What it leaves**: `spec/02-screens.md` (screen list, flow, states), `spec/tokens.json` (design values such as colors and spacing), `spec/design/prototype-<name>.html` (the confirmed prototype). When you confirm, a `Prototype confirmed <date>` line is added to `02-screens.md`.

**When it blocks**: in an environment where the Figma integration tools are unavailable, it says so, asks for an export file or screenshots, and stops — it does not guess the design from the URL alone. Also, a mockup usually does not show all four states, so the missing states are designed and filled in, but all of them are marked as "assumptions".

**Next**: `/gatebound:tasks`.

## /gatebound:design

**When to use it**: when you have **rules that cut across screens** rather than a per-screen mockup ("cards get a border only, no shadow", "a dangerous action always asks for confirmation once"), or a site to use as a reference. It is optional, and **you can run it at any point in the pipeline** — even in the middle of a build.

**What happens**: it reads what you give it (a Figma link, screenshots, HTML, a live site URL, a preset name, a rules file you wrote) and extracts design patterns and tokens. A live site is captured and saved to `spec/design/`, and that file becomes the evidence — a URL can change at any time, so only files inside the repository count as evidence.

If design files already exist, it **merges** rather than overwriting. Even when a new source conflicts with existing content, it does not delete existing rows; it records "what replaced what".

**If you run it during a build**, it does not edit the task files directly; it **only tells you the list of affected tasks.** To actually apply the change, you have to go through `/gatebound:tasks` and `/gatebound:gate` again.

**What it leaves**: `spec/02-design.md`, `spec/tokens.json` (shared with mockup).

**When it blocks**: in an environment without web access tools (Codex and others), it asks for local captures and stops. A screenshot over 1 MB is shrunk or refused.

## /gatebound:tasks

**When to use it**: when the spec is ready and you now split it into units of work. If there is a UI and you have not confirmed a prototype, it blocks here — with a message telling you to go back to `/gatebound:mockup`.

**What happens**: it is mostly automatic. It reads the features, screens, stack and the actual repository structure and builds the task list. **This stage asks almost nothing.**

Tasks are cut not into layers such as "build every DB model" but into vertical slices such as **"submit the form and the saved value shows up"**. Tasks in the same sequence number (round) are arranged so they do not touch the same files; when they conflict, the round is split instead of widening the scope. Tasks that build screens automatically get a condition to leave a screenshot of the result — later, `/gatebound:verify` looks at that image itself to judge it. A task's e2e gate runs only that task's one spec file and one viewport (for example, Playwright `--project mobile`), and starts the development or production server once and reuses it (`reuseExistingServer`). In a measured build, task gates ran both projects and took about 299 seconds per pass, and gates run again at every preflight, `jobs complete` and `recheck`. The full suite runs only once, as a criterion in `05-gate.md`.

**What it leaves**: `spec/04-tasks.md`.

**When it blocks**: if some feature has no task covering it, it reports that. If task scopes overlap, it re-cuts them; it does not widen the scope.

**Next**: `/gatebound:gate`.

## /gatebound:gate

**When to use it**: after the task list exists, right before building starts. **Only after you approve here can source code be written** — this is the single most important moment in the pipeline.

**What happens**: it reads the acceptance criteria and the task list and turns **"what has to hold for this to be done" into a list of commands that can actually run**. Each criterion is one command that runs directly, with no shell tricks, and each one is actually run once before it is written down — a criterion that was never run is only a guess, and it will really run later when you end the session.

Before asking for approval, it runs every criterion once (`contract baseline`) and shows the current state of each criterion alongside. It runs again every time, even when only the budget changed, and because it runs on the tree before any work, files a criterion creates stay in place. **A criterion that already passes before any work** is flagged so you can confirm it really tests the new behavior, and a criterion whose command itself is wrong is fixed before approval is asked.

Then **it shows the whole list as a table and asks for approval.** You have one job here: **"If all of these pass, is it really done?"** If you think not, ask it to fix or add criteria, and it shows the table again after the change.

**What changes when you approve** — this is the core of it, so it is worth knowing in advance.

1. The file's hash is pinned.
2. **Source files can be written** (until then, only `spec/`, `docs/` and root Markdown could be written).
3. When you try to end the session, **these commands actually run**, and if any one is `fail` or `unverified`, ending is blocked.
4. If you edit this file afterward, the approval expires automatically and you have to approve again.
5. The hashes of the test files that grade the criteria (the tests and scripts named in argv) are pinned too. If such a file changes later, that criterion becomes `unverified`, and deriving again does not clear it. If the change was intended, run `/gatebound:gate` again to re-approve; otherwise, revert the change (ADR-0023). Writes are not blocked. A worker cannot approve.

**What it leaves**: `spec/05-gate.md`, and the approval record.

**When it blocks**: if you do not approve, it leaves things as they are and tells you "the write gate is still closed". It never approves on your behalf. If unconfirmed core assumptions remain in the assumption ledger from `/gatebound:interview`, it refuses to proceed here — confirming those assumptions clears it.

**Next**: `/gatebound:build`.

## /gatebound:build

**When to use it**: after the gate is approved. This is the stage where the code actually gets built.

**What happens**: it implements the tasks in round order, and as each task finishes, it runs that task's gates and records pass or fail. **The verdict always comes from the gates** — even if the implementer says "all done", a failing gate means a failure.

`build.execution` in `.gatebound/config.json` decides who actually writes the code. **The default `host` has this session implement the tasks itself**; switch to `"execution": "worker"` and a separate process is spawned per task. Either way, the gates and the records are the same. A worker is a new session of the same model and has to learn the project from scratch every time, so use workers only when the model actually has to differ (adversarial verification) or when there are enough independent tasks for parallelism to pay. In `host`, after implementing a task, call `jobs complete <task_id>` **once**, and it runs the gates. Do not run the task's gate commands yourself before that — in a measured build, the session ran the e2e gate first (24–62 seconds per task) and `jobs complete` ran the same gate again, paying the time twice. Running narrow unit tests during development is fine, but not the gate's full command.

**It runs the gates once before work on a task starts.** If they already pass, it builds nothing and moves on; if a gate command itself is wrong (it points to a path that does not exist, for example), it does not even start building and tells you so — this keeps you from working for minutes toward a wrong condition.

**How to watch progress**: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs results --compact` shows one line of status per task. A worker's full output log is very long; better not to read it.

**What it leaves**: per-task status records, `spec/PROGRESS.md`.

**When it blocks**:

- **A task failed** → in the default `host` mode, this session fixes the code and runs `jobs complete <task_id>` again; with workers, retry it (`jobs redelegate <task_id>`), and the failed gate's output is attached automatically to the next attempt's prompt.
- **The gate command itself is wrong** → fix `spec/04-tasks.md`, then, instead of retrying, run `jobs recheck` to re-run only the fixed gates. If the code is already right, it finishes in seconds.
- **The same task keeps failing** → at 3 in a row (the default), it stops automatically and leaves a diagnosis in `spec/RECOVERY.md`. This counter does not reset when you start a new job, so once you have fixed the cause, reset just that task with `jobs start --force-retry <task_id>`. In the default mode where this session implements the tasks, `jobs complete` also stops at the same limit with exit 3.
- **The same task failed the same way twice** → it stops with exit 3 even if retries remain. If the gate output is the same (ignoring times, durations and the like), trying again unchanged will not converge: if the gate is wrong, fix it and run `jobs recheck`; if the instructions are wrong, fix the task.
- **A task is `blocked`** → another task it depends on has not passed yet. It is not something to retry; resolve the dependency first.
- **You want to stop midway** → `jobs stop`.

**Next**: if everything passed, `/gatebound:verify`. **Passing the build and passing the completion contract are different things.**

## /gatebound:verify

**When to use it**: after every task has passed. **A finished build is not completion** — the final verdict is made here.

**What happens**: it spawns **a separate evaluator that did not write the code**. This is why the stage exists — a producer grading its own result looks for reasons to pass it. The evaluator can read and run things but cannot write, and where possible it is **a different model from the one that built it** (for example, if Claude built it, Codex grades it). If no other model is available, it falls back to a read-only agent of the same model, but **it tells you so with a warning.**

The evaluator runs every completion criterion and also **walks through the user scenarios written in `spec/05-gate.md` by hand** (starting the server and sending real requests, for example). Then this session runs the completion criteria **once more, independently**. If the two results differ, it does not pick the better one; it reports the disagreement itself.

If the screen-building tasks left screenshots, the evaluator **actually looks at those images** and judges whether they match the design direction and whether they avoid the common patterns that make something look obviously AI-made.

**How to read the result**: there are four verdicts, `ok`/`warn`/`fail`/`unverified`, and **`unverified` is not a pass.** Checks that could not run for lack of time and artifacts that could not be confirmed all land here. And **even if the code check aggregate is all `ok`, it does not report "passed" when the screenshot verdict is `fail`** — the two are shown separately.

If any job in the build has a task that passed only **after the test file its own gate runs had changed**, following an earlier failure (including a failure in preflight or in an earlier job), the verdict stays as it is, but a separate warning says "passed only after its own test changed — review the diff of that file" (ADR-0023). It asks a person to check whether the test was loosened to make it pass.

**What it leaves**: a verdict record in the last verification section of `spec/PROGRESS.md`.

**When it blocks**:
- **Most results come back `unverified`** → the time budget is most likely smaller than the real run time. Measure how many seconds it actually takes, then declare the budget in `05-gate.md` (do not raise it on a guess).
- **The Codex evaluator was refused** → this project's Codex hooks are not trusted yet. Run the command shown in the message once yourself and approve it. This guard keeps permissions from being granted while nothing is watching the writes.
- **There is a `fail`** → do not fix the code here. Go back to `/gatebound:build` and fix it there.

## /gatebound:doctor

**When to use it**: right after installing, when the hooks do not seem to take effect, when something seems wrong. **It is safe to run at any time.**

**What happens**: it gives a verdict on each of 8 items (plugin files, hook registration, project state, spec, contract freshness, workers, Python version, the Codex layer), and for each item it shows **a fix command you can copy and use right away**. **It fixes nothing** — it only diagnoses.

**How to read the result**: exit code 0 means "nothing failed", not "everything is fine". An `unverified` item means **the check could not be done**, so do not read it as "no problem". That said, `unverified` is often normal (because you are not at that stage yet). Which cases are normal is laid out in `02-install.md`.

**The most dangerous failure**: a `fail` on item 2 (hook registration). Every file is there but not a single hook fires — **the harness looks installed while blocking nothing.**

## /gatebound:setup

**When to use it**: once, the first time you use gatebound in a project. Once more later if you want Codex as a worker or evaluator.

**What happens**: if `.gatebound/config.json` does not exist, it creates one with the defaults, checks that the default worker actually works, and shows the result. **If a config file already exists, it leaves it alone.**

When run as `/gatebound:setup codex`, it **first explains what will change** before turning Codex on: which commands run, whether it runs with the sandbox on, and whether it can be undone. It changes nothing until you answer.

**What it leaves**: `.gatebound/config.json`.
