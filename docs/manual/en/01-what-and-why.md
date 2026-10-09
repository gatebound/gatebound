# What gatebound is

gatebound is a gate-enforced harness for Claude Code. It takes the rules that AI-assisted development usually writes as prose in `CLAUDE.md` or in slash commands, and moves them into hooks that actually run every time.

Prose instructions fire nondeterministically. You can write "write tests first" or "get approval before touching `src/`", but whether that instruction is followed depends on how much attention the model paid in that turn. gatebound moves the parts that matter into things a hook enforces.

## Three problems it solves

### 1. You cannot verify that what was built is right

The AI says "Implementation complete." Is that evidence? In gatebound, done is a list of commands. The commands written in the `gatebound-criterion` blocks of `spec/05-gate.md` actually run, and the verdict comes from their exit codes and artifacts. Even if a worker ends with exit 0, a failing gate means `failed`, not `passed`.

### 2. Nobody ever agreed on what counts as done

When the definition of "done" lives only in someone's head, it changes every time. gatebound has you write the completion conditions in a file, and has a person read and approve that file. The hash at approval time is recorded, so you cannot later delete a failing criterion to get a pass.

### 3. Docs and code drift apart

You write a spec, and the code goes another way. In gatebound, until the spec is approved, the write gate refuses writes to files outside `spec/`, `docs/` and root Markdown. The spec exists before the code, and a task's `write_scope` becomes the worker's actual write permission.

## Four core principles

### Gates are hooks, not prose

The `UserPromptSubmit`, `PreToolUse`, `PostToolUse` and `Stop` hooks read structured state and decide. They are not instructions the model has to remember. Hooks fire every time.

### Done is an argv contract

A criterion is an argv list that runs without a shell. You cannot use `&&`, pipes or redirection. To chain steps, add another criterion. A gate that always passes is worse than no gate, because it creates false evidence.

### Approval is tied to a hash

`gatebound approve spec/05-gate.md` records the SHA-256 of the file at that moment. If the file changes, the approval becomes `fail` (stale), and the write gate closes again. Reverting the file to match the hash is forbidden.

### "Not verified" is not a pass

The verdict words are exactly four: `ok` / `warn` / `fail` / `unverified`. A criterion that timed out, a step that could not run, an artifact that could not be checked — all of these are `unverified`. It is never rounded to a pass or a fail. The Stop gate blocks the session from ending not only on `fail` but also on `unverified`.

## How it differs from other tools

| Aspect | Typical prompts and rule files | gatebound |
|---|---|---|
| Rule firing | Depends on the model's attention | A hook runs on every call |
| Done verdict | The model's self-report | Result of running argv |
| Approval | Verbal agreement in the conversation | File hash pinned |
| Unverified state | Usually treated as a pass | Kept separately as `unverified` |
| Parallel agent conflicts | Found after the fact | Blocked up front by the spawn gate |
| Evaluator | The session that built it grades itself | A separate read-only evaluator |

## What it is not

- gatebound is not a tool that writes code for you. Workers or this session write the code; gatebound judges the result.
- Hooks do not break your session. Every hook exits 0 even on an internal error and leaves only one diagnostic line in `.gatebound/runs/hook-errors.log`.
- Korean is not the default. The output language is detected from what the user writes.

## The first 30 minutes — run one loop

You do not need to read all the concepts before you start. Once installation (`02-install.md`) is done, it is faster to learn by running one loop in the order below. Go in knowing only **what you will do** at each step.

### 1. Decide what to build (10–20 minutes, conversation)

```
/gatebound:discover
```

Start here if you are still vague about what to build. A **free-ranging conversation** follows, with no fixed question list, one question at a time. Answer mostly with things that actually happened ("Last week this happened" is far more useful than "Usually it's like this"). When it looks like nothing more will come out of the conversation, it asks you directly whether to continue or wrap up here.

If you already know clearly what to build, you can skip this step and go straight to the next one.

```
/gatebound:interview what you want to build, in one line
```

This step digs into **how many screens there are, what you can do on each screen, and what each one needs**. Along the way it researches the features products in this category usually have and proposes them ("Do you also need this?"). If you do not need one, ask for it to be removed. The result is `spec/01-prd.md` and `spec/03-architecture.md`.

### 2. See the screens with your own eyes (10–20 minutes)

```
/gatebound:mockup
```

If you have a design draft, it reads that; if not, it has you pick one of the prepared design presets. Then it builds and hands you an **HTML prototype you can actually click through**. Open it, say what you do not like, and it fixes it and gives it back. If you do not confirm it here, you cannot move to the next step — this is there to prevent the situation where you see the screens for the first time only after the whole build is done.

### 3. Create the tasks and completion conditions (5 minutes, mostly automatic)

```
/gatebound:tasks
/gatebound:gate
```

`tasks` splits the spec into units of work, and `gate` turns "what has to be met for this to be done" into a **list of commands that can actually run**. At the end of `gate`, it shows you that list and asks for approval — only after you approve here can source code be written. Reading the list and judging "if all of this passes, is it really done?" is all you have to do in this step.

### 4. Build and verify (depends on project size)

```
/gatebound:build
/gatebound:verify
```

`build` implements the tasks in order and runs each task's gates. When everything is done, `verify` launches **a separate evaluator that did not write the code** and checks all the completion conditions again. Passing the build and passing the completion contract are different, and `verify` gives the final verdict.

### If you get stuck

- Editing a source file is refused → you have not approved `/gatebound:gate` yet. This is intended behavior.
- `/gatebound:tasks` refuses → you did not confirm the prototype in `/gatebound:mockup`.
- Anything else → look it up in the symptom table in `10-troubleshooting.md`.

**A block is not a breakdown.** Most of the moments when gatebound blocks you are points where "moving on now means a more expensive rollback later." The message tells you what is missing and what to do next.
