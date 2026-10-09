# ADR-0031: Host-run fixes: an environment failure is unverified and not reused, one contract run at a time, names under `eval/`

Status: accepted 2026-10-04 (owner approval in session: the three designs
below, recorded as one ADR). Amends ADR-0020 (reuse), ADR-0022 (signature
kinds), ADR-0024 (the Stop gate under `verify`) and ADR-0027 amendment B
(protected names).

## Context

The first host run of the Windows fixes (`fix/windows-locale` plus the
language and CLI branches, loaded with `claude --plugin-dir`, no encoding
override) verified `examples/memo-board` with `/gatekit:verify` typed by the
user. Three things went wrong that the unit suite could not show:

1. **A transient failure was judged again and again.** The evaluator's
   `contract run` and the Stop gate started Playwright within a second of each
   other. Both saw port 4183 free (`reuseExistingServer: true`), both started
   `node server.js`, and the loser died:

   ```
   Error: Process from config.webServer was not able to start. Exit code: 1
   [WebServer] Error: listen EADDRINUSE: address already in use :::4183
   ```

   `journey-…` was recorded `fail (exit 1)`. The next Stop found the tree
   unchanged and reused that record (`stop_reused`, `final_verdict: fail`).
   Run alone, the same command passed every time (`1 passed`). ADR-0020
   already says a reused result "is evidence about the same code, not a fresh
   observation of external services"; it did not consider that a failure
   *caused* by external state would then stick until a file changed.

2. **Two contract runs overlapped.** `/gatekit:verify` launches the evaluator
   in the background; the turn ended while it ran, and the Stop gate (rearmed
   by `verify`, ADR-0024) ran the same criteria against the same port and the
   same `test-results/`.

3. **The evaluator was refused its own scratch directory.** `py -3 gatekit.py
   contract run --json > .gatekit/eval/contract.json` was denied: the Bash
   gate's base-name rule (a target named like a file gatekit writes counts
   whenever the command's text names `.gatekit`) fired on a path that is
   explicitly under `eval/`, which ADR-0027 B leaves writable. The same
   command writing `eval/run-result.json` was allowed.

## Decision

### 1. A runner that could not start is `unverified`, and such a record is not reused

`no-tests-signatures.json` gains a third `kind`, `environment` (wording
"could not start the runner"), next to `no_tests` and `all_skipped`
(ADR-0022 Amendment A). Its first entry, `playwright-webserver`, is
Playwright's `Process from config.webServer was not able to start` (or
`exited early`) at exit 1. A bare `EADDRINUSE` is not an entry: a test that
checks a server's handling of a busy port prints it too, and must still be
able to fail. The existing path applies unchanged: a
criterion or task gate whose output matches, with no positive count anywhere,
is `unverified` with the detail `could not start the runner (<id>; exit N)` —
the code was not judged, so it neither passes nor fails.

A criterion so classified carries `"environment": true` in the result.
`contract.covers` (and so `reusable_last`) refuses a record holding one: the
Stop gate runs the contract again instead of judging a port collision a
second time. ADR-0020's fingerprint rules are otherwise unchanged.

### 2. One contract run at a time

`contract.execute` takes `.gatekit/runs/contract.lock` (created with
`O_CREAT|O_EXCL`, holding `pid` and `started_at`) before it runs a criterion
and removes it when done, on every path. A run that finds the lock held
waits up to `LOCK_WAIT_S` (30 s), polling; a lock whose holder is no longer
alive (`jobs._pid_alive`, never `os.kill` on Windows) or that is older than
the run-wide ceiling plus a margin is stale and taken over. If the lock is
still held after the wait, the run returns `unverified` with the reason
`contract_busy`, judges nothing, and is **not recorded** by `save_last` — so
it is never reused, and it never replaces the result of the run that held
the lock. The Stop gate treats it like any `unverified`: it blocks under the
usual `block_count` and `stop_hook_active` limits, and its message says
another contract run was in progress. gatekit's own writers are unaffected
by ADR-0027: the lock is written in process, never through a tool call.

### 3. Names under `eval/` are not protected names

The Bash gate's base-name rule exists for a working directory it may have
misread (a conditional `cd`). It now skips a target whose written form,
after the gate's canonicalisation and with no `..` segment, lies below a
`<state dir>/eval/` directory. Whatever directory the command really runs
in, such a target is inside some `eval/` directory, which ADR-0027 B leaves
writable, so it cannot reach `approvals.json`, `contract.json` or any other
gatekit-owned file. Every other use of the rule — a bare name, `$d/name`,
an unknown `cd` — is unchanged, and so is the refusal of an opaque command
(inline interpreter code) that spells a gatekit-owned path, even one that
only reads.

## Consequences

- A port collision, or any listed "could not start" output, reads
  `unverified` with a reason that names the runner, and the next Stop runs
  again rather than repeating it. A deterministic start failure (a broken
  `webServer.command`) is also `unverified`, not `fail`; the detail and
  `gatekit doctor`'s port probe (ADR-0026) point at it, and it never reads
  as a pass.
- Concurrent `contract run`, evaluator and Stop gate runs no longer race for
  ports or `test-results/`; one waits or says it could not judge.
- The evaluator can name its scratch files freely under `.gatekit/eval/`.

## Rejected alternatives

- **Never reuse a record with any non-`ok` criterion.** Simple, but a
  deterministic failure would rerun the full contract at every Stop while
  nothing changed — the cost ADR-0020 removed.
- **Have `/gatekit:verify` keep the turn open until the evaluator returns.**
  A command cannot hold a turn open on a background agent, and a user's own
  `contract run` in another terminal would still collide; the lock covers
  every caller.
- **Exempt `eval/` by dropping the base-name rule.** It still guards the
  misread-`cd` case it was written for.
