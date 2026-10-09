# ADR-0040: A finished subagent releases its scope, and a running one defers the Stop gate

Status: accepted 2026-10-09. Amends the spawn and stop gates (ARCHITECTURE.md
§3); adds two hook registrations. Also records the tokens-gate fix found in
the same trial, which needed no decision of its own.

## Context

On 2026-10-09 a timed end-to-end trial built a 16-feature equipment-rental
app with gatekit 0.16.17 (the cohort line, whose gates this line shares),
from `/gatekit:setup` to `/gatekit:verify`
(53 minutes, verdict `ok`). Three defects cost it time or a verdict:

1. **Scopes were never released.** The spawn gate records every subagent's
   `write_scope` in the session ledger and denies a new spawn whose scope
   intersects any recorded one. Nothing ever removed an entry. Round 2 of
   the build ran four subagents in parallel; round 3 could not delegate
   anything that overlapped their scopes, though all four had finished, and
   the host session built rounds 3 to 5 alone. The same denial was seen on
   2026-09-13 and parked in the backlog.
2. **The Stop gate judged while the evaluator ran.** `/gatebound:verify`
   launched its read-only evaluator in the background and ended the turn.
   The Stop gate then ran the contract at once; the evaluator, starting its
   own run, freed the test port the Stop gate's Playwright server had just
   taken, and the E2E criterion came back `unverified (could not start the
   runner)`. Contract runs already serialise on `contract.lock`; the clash
   was with the evaluator's own commands, which no lock can see.
3. **The tokens gate could not read the shipped preset.** `shadcn-neutral`
   stores colours as bare HSL triplets (`"primary": "0 0% 9%"`) consumed as
   `hsl(var(--primary))`. The gate found no colour token in that file
   (`unverified`) and would have read every correct `hsl(var(...))` as a
   foreign literal, so `/gatebound:tasks` left the gate out of every task.

A probe of Claude Code 2.1.295 with hooks that dump their input showed what
the host sends:

- PreToolUse and PostToolUse on `Agent` carry the same `tool_use_id`.
- A foreground agent's PostToolUse comes after it finishes, with
  `tool_response.status: "completed"` and its `agentId`.
- A background agent's PostToolUse comes at launch, with
  `tool_response.status: "async_launched"`, `isAsync: true` and its
  `agentId`; `SubagentStop` with the same `agent_id` comes when it ends.
- The Stop payload lists `background_tasks`, each with `type`
  (`subagent` for an agent) and `status` (`running`); the session's next
  Stop, after the agent's notification wakes it, lists it no more.

## Decision

1. **Release on finish.** The spawn gate records the spawn call's
   `tool_use_id` with the scope. It is also registered on PostToolUse and
   PostToolUseFailure for `Agent|Task` and on `SubagentStop`:
   - PostToolUse with `async_launched` (or `isAsync`) ties the `agentId` to
     the entry with that `tool_use_id`;
   - any other PostToolUse, and any PostToolUseFailure (an error or an
     interrupt), releases the entry with that `tool_use_id`;
   - `SubagentStop` releases the entry with that `agent_id`; an id that
     matches nothing yet is remembered (the last 50), so a spawn call whose
     async PostToolUse arrives later releases at once.
   SubagentStop saves the ledger while the main session's hooks may hold an
   older copy, so `Ledger.save` re-reads the scopes on disk and replays only
   its own scope changes onto them; no save undoes another's.
   A release removes the entry and logs `scope_released`. Neither event can
   deny anything. An entry recorded without a `tool_use_id` (an older
   ledger, a host that sends none) is never released, as before: a false
   conflict costs one re-declared scope, a missed one costs a collision.
   Codex's `collaborationspawn_agent` is not added to the PostToolUse
   matcher: its scope is never recorded (it is unreadable there), so there
   is nothing to release.
2. **Defer while a subagent runs.** When the Stop payload lists a
   `background_tasks` entry with `type: "subagent"` and `status: "running"`
   whose id is an agent the spawn gate recorded, the Stop gate judges
   nothing, logs `stop_deferred_for_subagents` and allows the stop without
   spending a block. It does so at most `MAX_BLOCKS` (3) Stops in a row;
   a Stop that judges resets the count. It leaves `final_verdict` and
   `last_reasons` as they are, setting `unverified` only when no verdict is
   recorded yet, and the check comes after the stand-down check.
   The session wakes when the agent finishes, and that Stop judges as usual.
   Other background work (a dev-server shell) does not defer: it does not
   wake the session and is often meant to outlive the turn. A host that
   sends no `background_tasks` (Codex) is judged as before.
3. **Tokens: triplets and references.** A token value that is a bare HSL
   triplet (`H S% L%`, optionally `/ alpha`) is the colour `hsl(<triplet>)`.
   Functional colours normalise across comma, space and slash syntax and
   the `a` suffix (`hsla(0, 0%, 9%, .5)` = `hsl(0 0% 9% / .5)`). A colour
   function whose arguments use `var(...)` reads a token through a custom
   property when a `var(...)` is among its colour channels: it is a
   reference, not a literal, and is not counted. A `var()` only in the alpha
   slot leaves a hard-coded colour, which is counted. Numbers have one
   spelling (`0deg` = `0`, alpha `50%` = `0.5`), and a triplet is a colour
   only in a colour group (its name contains `colo`).

## Consequences

- Parallel builds keep their parallelism past the first round.
- `/gatebound:verify`'s turn no longer races its own evaluator; the contract
  is judged once the evaluator is done.
- Deferral is a new way for a Stop to end without a verdict. It is bounded
  by the agent's own life: the gate judges at the first Stop after it ends.
  A model could launch a do-nothing background agent to postpone judging,
  but only through the spawn gate, for at most three Stops in a row, and
  never past the agent's return; no verdict is rewritten meanwhile.
- Projects using the `shadcn-neutral` preset get the tokens gate on their
  styled tasks again, and a hard-coded `hsl(10 50% 50%)` still fails.
- Three more hook registrations run a Python process: one per spawn
  call's completion or failure and one per subagent end. All stand down
  without `.gatebound/`.
