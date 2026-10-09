# Troubleshooting

## First — most blocks are not breakage

When you use gatebound, **you get blocked often.** That is the point of the tool. So before you look for a problem, sort out one thing first.

| This is normal (an intended block) | This is breakage |
|---|---|
| You cannot write source files → `/gatebound:gate` is not approved yet | **Not a single** hook fires |
| `/gatebound:tasks` refuses → the prototype is not confirmed | Item 2 of `/gatebound:doctor` is `fail` |
| You cannot end the session → the completion conditions have a `fail`/`unverified` | The CLI dies with `ModuleNotFoundError` |
| The verdict is `unverified` → the check **could not run**; nothing is wrong | Exceptions pile up in the hook error log |

An intended block **comes with a message that says what is missing and what to do next.** When something simply does not work with no message, that is the real problem.

When you are blocked, the first thing to run is `/gatebound:doctor`. Seeing which item is `fail` tells you right away which of the two columns above you are in.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Hooks have no effect at all | The plugin is not installed, or it is disabled in `enabledPlugins` in `settings.json` | Check axis 2 of `/gatebound:doctor`, then `/plugin install gatebound@gatebound` or `/plugin enable gatebound@gatebound`. Then restart Claude Code |
| Installed, but still no effect | The current session loaded an old version | Restart Claude Code |
| Axis 2 of `/gatebound:doctor` is `fail` with "more than one plugin of this name family" | gatebound and gatekit (the plugin's name before 0.17.0) are both on — both are in `enabledPlugins` in the user or project `settings.json`, or in the Codex plugin cache. If the old plugin is on in the **user** settings (`~/.claude/settings.json` or `$CLAUDE_CONFIG_DIR`), is also in the install list and the plugin cache directory, and the project still has `.gatekit/`, the new plugin's Stop and question gates stand down and the prompt hook warns once per session. Project settings can only turn the old plugin off, never on, and this decision is made once, on the session's first prompt, and recorded in the ledger (a settings change mid-session applies from the next session; ADR-0029 amendment) | Turn the old one off as the fix says (`/plugin disable gatekit@gatekit`), or uninstall it (`claude plugin uninstall gatekit@gatekit`). The write, Bash and spawn gates only issue the same denial even when both run (ADR-0029) |
| Axis 3 of `/gatebound:doctor` is `fail` with "both .gatebound/ and .gatekit/ exist" | The project has two state directories. When a directory with the **current name** (`.gatebound/`) exists, the hooks always use it, whatever the other one holds. They read the directory with the other name only when the current-name directory does not exist (a gatekit project not yet moved with `migrate --apply`). A state directory that is a symbolic link or junction (reparse point), or whose real path is not directly under the project root, is dropped from the candidates entirely | Move only what you need out of the one you do not use and delete that directory in a terminal (inside a session the state-protection rule denies it). Until then `migrate` refuses (ADR-0029) |
| The Stop gate blocks with "both .gatebound/, .gatekit/ hold approvals.json" and records `unverified` | **Both** state directories have `approvals.json`. One of them may be forged (unpacking an archive, a link, a rename), so no approval or contract is judged. It blocks at most 3 times, then lets go with `unverified` | Check with `/gatebound:doctor` which one the hooks use, then delete the directory you did not create yourself in a terminal, or keep only one with `gatebound migrate` (ADR-0029 amendment) |
| Editing a source file is blocked | `spec/05-gate.md` is not approved (`unverified`) or the approval expired (`fail`) | Run `/gatebound:gate` and have the user approve. If you are in a hurry, write to `spec/`, `docs/` or root `*.md` first |
| Spec validation fails — missing heading | A template H2 heading was deleted or changed | Restore that language's heading from `heading-map.json` exactly. Page 06 has the full list |
| Spec validation fails — heading from the other language mixed in | One file mixes `## 목표` and `## Goals` | Use one language. This happens often when you write freehand headings in `PROGRESS.md`. Copy from the template |
| Spec validation fails — assumption ledger numbers do not match | An inline marker number and a ledger row number do not match | Inline marker with no row is `fail`, so add the row. A row with no inline marker is `warn` |
| The contract is stale | `05-gate.md` changed after derivation, or a design input (`02-screens.md`, `02-design.md`, `tokens.json`) changed — `contract status` names the changed file | Re-run `/gatebound:tasks` and then `/gatebound:gate` (if the design changed), or re-run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" contract derive` (if only 05 changed). If the approval also expired, approve again |
| `approve check` is `fail` | The file changed after approval | The user reads it again and approves again. Do not revert the file just to make the hash match |
| `approve check` is `unverified` | There is no approval record at all | Run `/gatebound:gate` from the start |
| The Stop gate or `contract run` reports `gate_not_approved` | `05-gate.md` has no approval, or it does not match (the file or `approvals.json` changed) | Revert what changed and fix the code to meet the approved criteria. If the gate has to change, approve it anew with `/gatebound:gate` (ADR-0027) |
| The Stop gate or `contract run` reports `contract_mismatch` | `contract.json` differs from what is derived from `05-gate.md` (it was edited directly) | Restore it with `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" contract derive`, then fix the code. If the criteria have to change, use `/gatebound:gate` (ADR-0027) |
| Writing or deleting under `.gatebound/` is denied (`approvals.json`, `contract.json`, `runs/`, `jobs/`, `attempts.json`, `baseline.json`, etc.) | Everything in `.gatebound/` except `config.json` and `eval/` is written only by gatebound itself (the hooks and the CLI) | Do not edit it directly; re-run `/gatebound:gate`. Settings go in `config.json`; old jobs go with `jobs clean` (ADR-0027) |
| `rm -rf .gatebound` is denied in a session | While the hooks are on, gatebound denies commands that delete its own state | Remove the plugin first, then delete it yourself in a terminal (`UNINSTALL.md`) |
| `enforce_spec_before_code: false`, yet the Stop gate reports `gate_not_approved` | That setting turns off only write rule (a). The Stop gate judges only approved criteria | Approve `05-gate.md` with `/gatebound:gate` (ADR-0027) |
| `python3 <<PY` or `echo … \| python3` is denied before approval (`script on stdin`) | There is no way to know what a script read from standard input writes | Write the script to a file and run it with `python3 script.py`, or use the Write/Edit tools |
| `approve check` is `fail` with `grading files changed` on stderr | The approved criteria's test files changed and were derived again (`grading_unapproved`) | If the change is intended, re-approve with `/gatebound:gate`; otherwise revert the test change (ADR-0023) |
| No worker (`workers check` is `fail`) | The default backend binary is not on PATH | Install that CLI, or pick another backend with `workers set-default <name>` |
| codex is disabled | The default is `"enabled": false` | Run `/gatebound:setup codex`. It turns on only after you read the explanation and confirm |
| `workers enable` is refused | argv has a sandbox bypass flag but no `"unsafe": true` | gatebound does not set `unsafe` on your behalf. Use a backend without a bypass |
| Task write_scope conflict | Two tasks in the same round write the same file | Split them into different rounds, or re-cut the tasks so the file boundaries differ. **Do not widen the scope** |
| A write is denied inside a worker | The path is outside that task's `write_scope` | It is a sign that the breakdown in `04-tasks.md` is wrong. Re-cut the task |
| `unverified` because the total budget was exceeded | The criteria add up to more than the 45-second default budget | Measure, then declare `total_budget_s` with a `gatebound-budget` fence (limit 600). Do not raise it without measuring |
| The verdict is `unverified` with the reason `all tests skipped (…)` | Every collected test was skipped (`.skip`, `@unittest.skip`, platform conditions, and so on). The runner output shows not a single pass, so this run proved nothing (ADR-0022 amendment A). A partial skip whose output shows passes is `ok`. Exception: in unittest, if one subTest per test is skipped and only the remaining subTests pass, or if a skipped test after the passed tests leaves output ending in a newline (without `-v`), the output cannot be told apart from an all-skipped run and the verdict is `unverified`. Running with `-v` then shows the passes (except in the subTest case) | Remove the skip, or run the criterion in an environment where the test can really run. Skip per test, not inside a subTest |
| The Stop gate blocks repeatedly | The contract has a `fail` or `unverified` criterion | Fix the cause of the criterion named in the message. After 3 blocks it stands down automatically, but the verdict is recorded as a failure |
| The Stop gate blocks with "another contract run (an evaluator's or a `contract run`) was still in progress, so nothing was judged this time (contract_busy)" | Another contract run held `contract.lock` for 30 seconds, so this run judged nothing. The result is `unverified` and is not recorded (ADR-0031) | It is neither a failure nor a pass. Wait for the other run (an evaluator's, or a `contract run`) to finish, then end the turn again |
| The contract runs at every turn end, and the context line says "Stop-gate budget left criteria unjudged" | Not every turn-tier criterion could start within `stop.budget_s`. With any criterion left unjudged the result is not `ok`, so the gate does not stand down | If you leave the files as they are, the following turn ends run the deferred criteria first and converge. Move slow criteria to `"tier": "verify"` or declare them last. You may also raise `stop.budget_s` after measuring |
| The build is over, yet the contract runs at every turn end, and the context line says "build job unfinished: N tasks queued" | Tasks in a host job are left `queued`, so the job never finishes. An unfinished job is judged every turn (ADR-0024) | Carry on with the remaining tasks, or, if you are giving up, `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs stop`. Stopped tasks are recorded as `fail`, and the gate stands down after the hand-off check |
| An e2e test sees the wrong screen and fails | `reuseExistingServer: true`, and another project's server holds the same port, so the test runs against that app | Axis 3 of `/gatebound:doctor` names the port and the process (ADR-0026). Stop that server or change the port in `playwright.config` |
| You asked in Korean, but the output is in English | Hangul makes up less than 30% of the prompt, or `en` is stored in the ledger | Send the prompt again as Korean sentences. The `lang` subcommand shows the detection result directly |
| `ModuleNotFoundError: gatebound` when running the CLI | You used the module form, and from the project directory the package is not on `sys.path` | Use the launcher form `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" <sub>` |
| A spawn is denied | The prompt has no `gatebound-scope` fence, or its JSON is invalid | Add the fence. `write_scope` and `stop_when` are required |
| Spawn scope conflict | It overlaps the scope of an agent that is already active | Narrow the scope, or wait until that agent finishes. The message names the owner |
| The build passed, but it says the work is not done | Passing the build and passing the contract are different | `/gatebound:verify` judges the contract |

## Where the hook error log is

```text
.gatebound/runs/hook-errors.log
```

When an exception happens inside a hook, one line is appended here.

```text
<iso timestamp> <event name> <error>
```

Even then the hook exits 0 and allows the action. So if you think "the gate let something through oddly", look at this file first. If the file is empty or missing, the hooks worked normally.

## Looking at the session ledger directly

Use this to check what the gates recorded.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" ledger show --session <session_id>
```

What to check in the output:

- `output_lang` — does the detected language differ from what you expect?
- `active_pipeline` — for the Stop gate to run the contract, this must be `build` or `verify`
- `questions.asked` / `budget_exceeded` — how many questions did the interview ask?
- `scopes` — which agent holds which scope?
- `stop.block_count` / `final_verdict` — how many times was it blocked, and what is the final verdict?
- `stop.stood_down` — did the Stop gate record the finished job's verdict and stand down (ADR-0024)? If it has a value, later turn ends do not run the contract. `skipped` is the number of turn ends passed over without a verdict. To check again, run `/gatebound:verify`
- `stop.deferred` — criteria deferred in the last verdict (`tier`: verify tier, `budget`: `stop.budget_s` ran out). If `budget` is present, that verdict is `unverified` and the gate does not stand down

## Looking at job state directly

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs results --compact
```

If you need the reason a particular gate failed, read only that task's `gates.json`.

```text
.gatebound/jobs/<job_id>/tasks/<task_id>/gates.json
```

`output.txt` and `stderr.txt` are the full worker transcript. Do not read them into context.

## Cleaning up job directories

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs clean        # keep only recent jobs
python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" jobs clean --all  # delete all
```

## Diagnosis order when you are stuck

1. `/gatebound:doctor` — which of the 8 axes is `fail`?
2. `.gatebound/runs/hook-errors.log` — are hooks quietly dying?
3. `spec validate --json` — which finding, in which file?
4. `contract status` — `ok` / `fail` (stale) / `unverified` (missing)
5. `approve check spec/05-gate.md` — is the approval still live?
6. `jobs results --compact` — which task stopped, and where?
