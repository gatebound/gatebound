# ADR-0022: "Not runnable yet" is not broken, zero tests is not a pass, and criteria get a baseline

Status: accepted 2026-10-03 (owner approval in session).

Origin: ADR-0009's first and third open questions, and a real job.

## Context

In `study-gallery` job `20260929T140930Z-bb7c`, 7 of 10 tasks started with
the preflight warning "gate `e2e` failed at preflight (exit 254) in a way that
may be the command rather than the work". The gate was
`npm run e2e -- e2e/login.spec.ts` and stderr said
`npm error code ENOENT … Could not read package.json`. `package.json` did not
exist yet because the first task, `shell-login`, creates it. The gate was
fine. The warning was noise, and seven repeats of it teach the reader to skip
warnings.

`classify_gate_result` only knows "a pattern matched and names an argv token"
(refuse), "a pattern matched and names nothing" (warn) and "anything else"
(silent). It never asks the one question that decides this case: **will any
task in this job create the path that is missing?**

The opposite hole is worse. Preflight records a task `passed` and spawns no
worker when its gates pass before any work, warning only when the write scope
is empty. A gate that runs zero tests passes: `jest --passWithNoTests`,
`vitest --passWithNoTests`, `mocha` with no specs, `node --test` with no
matches, `go test` on a package with no test files, `cargo test` with no
tests. Those all exit 0. Python's `unittest` exits 0 on "Ran 0 tests" before
3.12 and 5 after; `pytest` exits 5. A task whose tests do not exist yet but
whose scope has a file would be skipped silently. The same zero-test exit 0
would satisfy a completion criterion.

ADR-0009 also left open whether the command-error check should run on
`05-gate.md`'s criteria when `/gatekit:gate` derives them. Today the gate
command tells the author to run each criterion by hand, and that instruction
has been followed and still misread.

The constraints: `unverified` never rounds; stdlib only; hooks exit 0 on
error; and gatekit's own run time stays negligible. The owner watches it.

## Decision

### 1. A missing path that a task will write is `not_yet_runnable`

When a failing gate's output names a missing path, the path is extracted and
made relative to the project root. That covers:
- `ENOENT: no such file or directory, open|stat|lstat|scandir|access '<p>'`
- `No such file or directory: '<p>'`
- `<p>: No such file or directory`, where `<p>` opens the line or follows a
  `<prog>: ` prefix and holds no space. A path with spaces is ambiguous in
  that form, and no extraction beats a wrong one.
- `can't open file '<p>'`
- pytest's `ERROR: file or directory not found: <p>`
- node's `Cannot find module '<p>'`, only when `<p>` looks like a path:
  absolute, starting `./` or `../`, or holding a slash and not a scoped
  package (`@scope/pkg`), or equal to one of the gate's arguments. A bare
  package name such as `express` is not a path.

Python's `No module named` names a module, not a path, so it is left alone.
Matching is textual, so Windows backslashes and drive letters work. `.` and
`..` segments are collapsed first, with `ntpath` rules for a Windows-shaped
path and `posixpath` rules otherwise, so `/r/web/../src/a.ts` is
`src/a.ts`. A path under the root is stripped to relative. Both the root and
the path are also compared in realpath form where the path or its parent
exists on this host, so `/var/…` matches a root given as `/private/var/…`.
A relative path is taken relative to the root, which is the gates' cwd. A
path outside the root cannot be written by a task.

Each relative path is checked against every `write_scope` glob of the job's
tasks, using the write gate's own matcher (`gates/write.py: matches`), so
"covered" means exactly what the write gate would allow. Then:

- **Covered** → a new kind, `not_yet_runnable`. The job starts silently.
  `preflight.json` records, on that gate, `preflight: "not_yet_runnable"` and
  a detail naming the path and the task that writes it.
- **Not covered**:
  - If the path came from npm's `Could not read package.json`, the runner
    cannot start in this project and no task will make it start. That is
    `command_error`, refused with exit 4, and the message names
    `package.json` (not whichever path npm printed first, often `.npmrc`)
    and says no task writes it.
  - Otherwise ADR-0009's rule stands. A line naming one of the gate's own
    arguments is `command_error`, now worded with the missing path and "no
    task in this job writes it". Anything else is `suspicious`.
- **No path extracted** → today's behaviour.
- Exit 126/127 are `command_error` first, as before, with one exception.
  When argv[0] is a shell or interpreter (`sh`, `bash`, `zsh`, `node`,
  `python`, `python3`, `ruby`, `deno`, `bun`, `tsx`, `ts-node`; a version
  suffix or `.exe` is ignored) and the missing path is covered and is one of
  the gate's own arguments, the owner check runs first. `bash
  scripts/e2e.sh` exits 127 when the script does not exist yet. argv[0]
  itself not being found (`nonexistentprog`, 127) stays `command_error`.
- A program that could not be executed at all (`run_gates` gets an
  `OSError`) is recorded with `could not run: <error>` in `stderr_tail`, so
  the classifier sees it. It is `not_yet_runnable` when argv[0] is a path a
  task writes. A program path inside a dependency directory
  (`node_modules`, `.venv`, `venv`, all skipped by the tree fingerprint, such
  as `./node_modules/.bin/playwright` or `.venv/bin/pytest`) is missing until
  dependencies are installed. It is `not_yet_runnable` when a task writes a
  manifest beside that directory: `package.json` for `node_modules`, and for
  `.venv`/`venv` one of `pyproject.toml`, `requirements.txt`,
  `requirements-dev.txt`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`
  or `uv.lock`. The detail names that task. Without such a task it is
  `suspicious`: the job starts with a warning saying the dependencies are
  not installed, as before 0.14.0. It is never `command_error`. Anything
  else that cannot be executed is `command_error`. `contract baseline`
  applies the same rule, so both agree, with one mapping: baseline has no
  `suspicious` class, and an uninstalled dependency program no task
  provides for is `unverified` there, since nothing was judged.
- When the covered path is one of the gate's own arguments — including a
  program inside a dependency directory, covered through its manifest —
  `jobs start` prints one `note:` line per task naming the path and the task
  that writes it. It is a notice, not a warning, and is recorded as
  `preflight_notices` in `job.json`.

Refusal is deliberately *not* extended to every uncovered path. ADR-0009's
reason holds: a test that fails with `FileNotFoundError` about a file the
code under test should produce, outside any declared scope (a temp output, a
fixture), is expected pre-work failure. Refusing it would block a correct job
with exit 4. The new refusal is limited to a case that can only be a broken
command: the package manager cannot find the manifest, and nothing creates
it.

### 2. A gate that ran no tests is `unverified`, not `ok`

`plugin/spec-kit/no-tests-signatures.json` lists signatures. Each has an id,
an anchored multiline `pattern`, the exit codes it applies to, and a
`positive` pattern that reports a non-zero count. There is one per runner:
pytest, unittest, jest, vitest, playwright, node:test, mocha, go and cargo.

A result is "ran no tests" when, over the full stdout and stderr:
- some signature's pattern matches and its exit list contains the exit code,
  **and**
- **no** signature's positive pattern matches anywhere.

The second condition is what keeps a mixed run with real tests `ok`: cargo's
doc-test `running 0 tests` after `running 5 tests`, or `go test ./...` with
one empty package.

`run_gates` and the contract's criterion runner both apply it. A result that
would have been `ok` becomes `unverified` with detail `ran no tests
(<signature id>)`.

The exit list is `[0]` everywhere except pytest and unittest, which list
`[0, 5]`. Exit 5 is each runner's documented "no tests were collected/run"
code. That is the runner saying it could not judge, which is `unverified` by
this repo's vocabulary, not `fail`. Jest, vitest and playwright exit 1 on "no
tests found" by default. That is left a `fail`: it is already not a pass, and
a non-zero exit is indistinguishable from a real failure without guessing.

Because the result is no longer `ok`, preflight no longer skips the task, and
the Stop gate no longer counts the criterion as proven. No warning is
printed at preflight. "No tests yet" is the normal state before a task
writes them.

pytest's exit 5 also covers "every test deselected" (`-k nomatch` prints
`==== 1 deselected in 0.00s ====`). The `pytest-deselected` signature,
`^=*\s*\d+ deselected\b`, lists exit 5 only, so a run that deselects some
tests and passes the rest is untouched.

go's positive pattern accepts trailing text after the duration (`ok  m/pkg
0.123s  coverage: 80.0% of statements`) but not `[no tests to run]`, and its
pattern is anchored at the start of a `?` or `ok` line like the others.

ANSI escapes (`\x1b[...m` and other CSI sequences) are stripped before
matching, so colour forced on by `FORCE_COLOR` or `--color=yes` does not
split an anchored pattern.

The signature list is data under `plugin/spec-kit/`, which answers ADR-0009's
third open question for this list. An unreadable file, or one whose top
level is not an object with a `signatures` list, means "no signatures":
results stay as the runner reported them, and nothing raises. Each entry is
type-checked on its own. An entry that is not an object, lacks a string
`id`, `pattern` or `positive`, has a pattern that does not compile, or has
`exits` that is not a list of integers (`true` is not an exit code) is
skipped, and the other entries still apply.

The Stop gate's reuse record (`runs/contract-last.json`, ADR-0020) carries
`signatures_sha256`, the hash of the signature file. A record whose hash is
missing or differs is not reused. A result saved before 0.14.0, when a
zero-test run counted as `ok`, is therefore re-judged.

### 3. `contract baseline` runs the criteria once at gate time

`gatekit contract baseline [--json] [--budget S]` runs the derived contract
against the current tree within the contract's budget, the same budget as
`contract run`, and sorts each criterion into one of five classes:

- `already_passes` (`ok`)
- `not_yet_runnable` (decision 1, against `spec/04-tasks.md`'s scopes; also a
  could-not-execute whose program is a path a task writes)
- `fails` (expected before work)
- `command_error` (decision 1's refusal cases, 126/127, and a program that
  cannot be executed and that no task writes)
- `unverified` (timeout, budget, ran no tests)

It writes `.gatekit/baseline.json` (`recorded_at`, `source_sha256`,
`elapsed_s`, per-criterion `class`, `verdict`, `exit`, `elapsed_s`,
`detail`). It prints one line per criterion and the total time. It exits 0
unless a criterion is `command_error`, which exits 4, matching preflight. A
missing or stale contract exits 1 with the reason.

It is a separate file. It never writes `runs/contract-last.json`, so the
Stop gate's reuse (ADR-0020) neither sees it nor is invalidated by it.

`/gatekit:gate` runs it between derive and approval and puts the table in
the approval question:
- `already_passes` is flagged "passes before any work — confirm it tests new
  behaviour".
- `command_error` must be fixed before approval is asked for.
- Everything else is informational.

Baseline runs every criterion against the pre-work tree. Anything a
criterion creates there (build output, a database file, a snapshot)
persists into the build. `/gatekit:gate` says so before running it.

It never approves. `gate-criteria.md`'s "measure first" step uses `contract
baseline --budget 600`, which reports each criterion's `elapsed_s`. When no
budget needs declaring, that run is the only one. When the budget fence is
then added or changed, `/gatekit:gate` runs the baseline again, so
`baseline.json`'s `source_sha256` always matches the `05-gate.md` that gets
approved. There is no "skip after a budget-only edit" shortcut.

## Consequences

- The `study-gallery` job would have started silently. Each `e2e` gate's
  `preflight.json` names `shell-login` as the task that writes
  `package.json`.
- A zero-test pass can no longer skip a task or satisfy a criterion. A
  project whose criterion legitimately runs no tests must say so with a
  criterion that does not invoke a test runner.
- `/gatekit:gate` costs one contract run, the one `gate-criteria.md` already
  asked for, or two when the measurement leads to a budget edit. Preflight's added cost is a few regexes over output it already
  holds, plus glob matching against the job's scopes.
- New refusal surface, in full:
  - npm without a manifest that no task writes. That job could not have
    passed anyway.
  - A program that cannot be started at all and that no task writes, whether
    a bare name (`nonexistentprog`) or a path (`bin/run-e2e`), is now
    refused at preflight with exit 4. Before 0.14.0, `run_gates` recorded no
    output for an `OSError`, so preflight started such a job silently. The
    exception is a program inside `node_modules`, `.venv` or `venv`, which
    warns and starts as before.
- Trade-off: a typo'd path inside a broad scope (`python3 src/tset_app.py`
  with scope `src/**`) was refused before 0.14.0 and now starts, because a
  task could write that path. The gate fails after the task runs instead of
  at preflight. The `note:` line naming the path and its owner is the
  disclosure; it is not a warning because the common case is correct.
- `contract baseline` runs the criteria against the pre-work tree, and
  anything they create persists. `/gatekit:gate` runs it on every pass,
  including after a budget-only edit, so `baseline.json`'s `source_sha256`
  always matches the approved `05-gate.md`.

**Contract changes** (`docs/ARCHITECTURE.md`):
- §1 lists the data file.
- §2 lists `.gatekit/baseline.json`.
- §5 gains "ran no tests" and `contract baseline`.
- §10's preflight paragraph gains `not_yet_runnable` and the uncovered-path
  rules.
- §13 lists the tests.
- §14 gains `runcheck.py`'s functions and the new `classify_gate_result`
  arguments.

## Rejected alternatives

- **Refuse every uncovered missing path.** It turns a test's own
  `FileNotFoundError` into exit 4 and blocks correct jobs, which is what
  ADR-0009 avoided.
- **Treat any "no tests" text as unverified regardless of counts.** Breaks
  every multi-package run with one empty package.
- **Convert jest/vitest/playwright's exit 1 "no tests found" to
  `unverified`.** A non-zero exit already fails. Softening a failure into
  `unverified` is not wrong, but it adds a rule with no case behind it.
- **Run the baseline inside `approve`.** Approval is a hash pin and must stay
  instant. Running commands there would make an approval depend on the
  tree's state.

## Open questions

- A run where every collected test is skipped (`3 skipped`, exit 0) proved
  nothing either, but it is not detected. Skips are often intentional
  (platform guards), and a rule would need per-runner wording for "all
  skipped" versus "some skipped". Left open. *Resolved by Amendment A below.*
- The signature list is per runner, not per reporter. A custom reporter that
  prints none of these lines still passes on zero tests. Adding a signature
  is a data change.
- `baseline.json` is not consulted by anything after approval. Whether
  `/gatekit:verify` should report criteria that `already_passes` at baseline
  and were never seen failing is left open.

## Amendment A (2026-10-04, owner approval in session): a run where every test was skipped is `unverified`

Resolves the first open question above.

**Decision.** A run in which at least one test was skipped and none passed,
with the exit code in the signature's `exits`, proved nothing, exactly as a
run with zero tests proved nothing. It is `unverified` with the same
downstream effects everywhere: the gate result and the criterion are
`unverified`, preflight does not skip the task, the Stop gate, `contract
run` and `/gatekit:verify` do not count the criterion as proven, and
`contract baseline` classes it `unverified`. A partial skip whose output
shows a pass (`5 passed, 2 skipped`) stays `ok`; the two unittest shapes
whose pass the output cannot be told apart from a skip are listed under
"Known false `unverified`" below. Zero-test behaviour is
unchanged.

**Mechanism: more signatures, no new branch.** Each runner gets an
"all skipped" entry in `no-tests-signatures.json`, so `runcheck.ran_no_tests`
and every caller handle it through the path §2 already defines. The schema
gains two optional fields. The first is `kind`: `"no_tests"` (the default when absent) or
`"all_skipped"`. Any other value makes the entry malformed, and it is
skipped like any malformed entry. `kind` only chooses the detail wording,
through `runcheck.describe_empty(id, exit)`. A second optional field,
`requires`, is a pattern that must also match somewhere in the output (a
non-string or empty value, or one that does not compile, makes the entry
malformed); it carries a runner's own context where its summary line alone
is too generic. The detail wording is `ran no tests (<id>; exit N)`
for `no_tests` (unchanged) and `all tests skipped (<id>; exit N)` for
`all_skipped`. Signatures are tried in file order, and each runner's
all-skipped entry comes before its zero-test entry, so a cargo run whose
unit tests are all ignored and whose doc-tests number zero is described as
skipped.

**Positive patterns now mean "a test ran", not "tests were collected".** A
positive anywhere still vetoes every signature. Five positives counted
collection, which an all-skipped run also has, and are narrowed to a count of
tests that ran:

| Runner | Positive before | Positive now |
|---|---|---|
| unittest | `Ran N tests` (N ≥ 1) | `Ran N tests …` not followed by `OK (skipped=N)` with the same N; or a progress line holding a `.` (pass) or `x` (expected failure), made only of progress characters `.sxuEF`; or a line that ends with the word `ok` or `expected failure` and is either that word alone (the bare `ok` unittest prints after a test's own log or warning output) or holds ` ... ` before it (a verbose result, `test_x (…) ... progress: ok`) |
| node:test | `# tests N` or `# pass N` | `# pass N` |
| playwright | `N passed` | `N passed` or `N flaky` (a flaky test ran and passed on retry) |
| go | an `ok <pkg> <time>` line, or `--- PASS` | the same, except an `ok` line directly after `PASS` whose `PASS` itself directly follows a `--- SKIP:` line (that is `-v` output of a package whose last test skipped; its `--- PASS` lines, if any, already speak). A `PASS`/`ok` pair after any other line, or at the start of the output, is non-verbose local-directory output and counts, so `go test -v ./a && go test` with `./a` all skipped stays `ok` |
| cargo | `running N tests` | `test result: <status>. N passed`, `… 0 passed; N failed`, or `… N measured` (benchmarks ran) |

**Per-runner rule** (exit list in brackets; every pattern is anchored at a
line start):

| Signature | Matches | Exits | Verified against |
|---|---|---|---|
| `pytest-all-skipped` | the summary line opens with `N skipped`, optionally followed by `, N deselected` and `, N warning(s)`, then ` in <time>` (`=== 3 skipped in 0.01s ===`, `-q`: `3 skipped in 0.01s`) | 0 | pytest 7.4.3 run locally; `_pytest/terminal.py` `KNOWN_TYPES` order (failed, passed, skipped, deselected, xfailed, xpassed, warnings, error, subtests …) |
| `unittest-all-skipped` | positive evidence that the last result was a skip, then the summary: either the progress line directly before the 70-dash separator is only `s` characters (non-verbose), or the line before the blank line and separator is a verbose skip (`… ... skipped '…'`, or a bare `skipped '…'` as Python 3.9 prints for a `setUpModule` skip); then `Ran N tests in …`, a blank line, `OK (skipped=N)` with the same N (a bounded backreference), or `Ran 0 tests` with `OK`/`NO TESTS RAN (skipped=M)` | 0, 5 | Python 3.13 run locally; CPython `Lib/unittest/runner.py` and `main.py` (3.12.0–3.12.1 exited 5 on all-skipped, gh-113661) |
| `jest-all-skipped` | `Tests:` followed only by `N skipped, ` and/or `N todo, ` before `N total` | 0 | `jest-reporters/src/getSummary.ts` (order failed, skipped, todo, passed, total) |
| `vitest-all-skipped` | `Tests` followed only by `N skipped` and/or `N todo` (joined by ` \| `) before `(N)` | 0 | `vitest/src/node/reporters/renderers/utils.ts` `getStateString` (failed, passed, expected fail, skipped, todo) |
| `playwright-all-skipped` | a line that is only `N skipped`, and (`requires`) Playwright's `Running N test(s) using M worker(s)` header somewhere in the output | 0 | `playwright/src/reporters/base.ts` summary (`  N skipped`; the duration rides on the `passed` line only) and `generateStartingMessage`, printed in `onBegin` by the list, line and dot reporters |
| `node-test-all-skipped` | the consecutive summary lines `pass 0`, `fail 0`, `cancelled 0`, `skipped S`, `todo T` with S + T ≥ 1, `#` (TAP) or `ℹ` (spec) | 0 | node v24.7 run locally, spec and TAP reporters |
| `mocha-all-pending` | `0 passing (…)` directly followed by `N pending` | 0 | `mocha/lib/reporters/base.js` `epilogue` (passing, pending, failing) |
| `go-all-skipped` | a `--- SKIP:` line (any indent) | 0 | `testing/testing.go` (`--- %s: %s (%s)`, four-space indent for subtests; `PASS` printed before cmd/go's `ok` line) |
| `cargo-all-ignored` | `test result: ok. 0 passed; 0 failed; N ignored;` | 0 | `library/test/src/formatters/pretty.rs` |

mocha's all-pending run was already caught by the zero-test `mocha`
signature (`0 passing`); the new entry only changes its wording.

Expected failures count as having run, not as skipped: pytest `xfailed` and
`xpassed`, unittest `expected failures=` and vitest `expected fail` all
execute the test body. A pytest summary holding any of them is not matched.
`deselected` tests were never selected, so `3 skipped, 2 deselected` is
still all skipped. jest/vitest/node `todo` tests did not assert anything
and count with skipped. A run with any failure exits non-zero, which no
all-skipped signature lists.

**A pass anywhere vetoes the whole command.** Positives are checked over
the full output of the command, not per runner or per package. A chained
command (`pytest && npm test`, `go test -v ./a ./b`) where one part skipped
everything and another part passed is `ok`. That is conservative by design:
a false `unverified` on a run where tests really passed is worse than a
missed detection, and splitting the output into per-runner segments would
mean guessing where each runner's output begins.

**Still undetectable** (each passes as before):
- A runner or reporter with none of these lines (custom reporters, `pytest
  -qq` which prints no summary, JSON reporters).
- `go test` without `-v`: an all-skipped package prints only `ok  <pkg>
  0.01s`, the same as a passing one. With `-v` it is detected.
- A go parent test whose subtests all skip is reported `--- PASS` by the
  testing package, so it counts as a pass.
- `go test -v -cover`: `coverage: …` sits between `PASS` and `ok`, so the
  `ok` line counts as a pass.
- unittest when the skip count exceeds `Ran N` and nothing passed (a
  `setUpClass` skip beside skipped methods): a regex cannot compare two
  different counts. Only the equal case and `Ran 0` are matched.
- unittest `--durations` (3.12+): the slowest-durations block is printed
  between the progress line and the separator, so a run whose tests skip
  at run time (`skipTest()` inside the test) has no skip directly before
  the separator.
- unittest output written after a skip and glued to the progress line
  (e.g. a `tearDown` writing to stderr, which 3.11+ runs after a
  `skipTest()`): the line before the separator is not only `s`.

Both unittest misses fail safe: the run stays `ok` as before this amendment.

**unittest's skip count is not bounded by `Ran N`** (review finding,
reproduced on Python 3.9 and 3.13). A `setUpClass` or `setUpModule` that
raises `SkipTest` adds one skip and nothing to `Ran`; each skipped subtest
adds one skip, and a test whose subtests skipped prints no `.` even when its
other subtests passed. So `Ran 1 test` / `OK (skipped=1)` can sit beside a
real pass (`s.`: a skipped `setUpClass` and one passing test), and the
summary alone cannot say "all skipped". The pass shows only in the progress
line (`.`) or, with `-v`, in an `ok` result. A second review found both can
be split by the test's own output: `-v` prints `test_x (…) ... WARNING:…`
and then `ok` on a line of its own when a passing test logs or warns
(Django's verbosity 2 has the same shape), and a passing test that writes
to stderr without a newline turns the progress line into `sprogress: .`.

So the signature requires positive evidence instead of chasing each shape
that hides a pass. The summary is named only when the text directly before
the separator is a skip: a progress line made only of `s` (non-verbose), or
a verbose `skipped '…'` result. And three positives veto it: `Ran N` whose
summary is not `OK (skipped=N)`, a pure progress line holding `.` or `x`,
and a line ending with the word `ok` or `expected failure` that is either
that word alone or holds ` ... ` before it. unittest writes `ok` with its
own newline after a passing test in `-v`, right after the test's
`description ... ` and whatever the test itself wrote, so a verbose pass
always ends either a bare `ok` line or a ` ... ` line with `ok`. The
positive is global, so it is kept that narrow: a plain line ending in `ok`
is often another runner's skipped test title (Playwright `-  1 … › status
is ok`, vitest `↓ … > status is ok`, jest `○ skipped … ok`, mocha `- … ok`)
and must not hide that runner's all-skipped run.

**Known false `unverified`.** Two unittest shapes are still named although
something passed. Both are non-verbose only unless noted.

1. A pass, then a skip whose own output ends in a newline, so the last
   progress line holds only `s`: e.g. a passing test, then a class whose
   `setUpClass` writes `no db here\n` to stderr and raises `SkipTest`.
   unittest prints `.no db here`, `s`, `Ran 1 test`, `OK (skipped=1)`; the
   `.` is glued to the skip's message, not on a progress line of its own.
   With `-v` the pass's `ok` line vetoes it.
2. A run whose every test that did anything had a skipped subtest, and none
   passed outright — e.g. one test with three subtests, one skipped. unittest prints `s`, `Ran 1 test`, `OK (skipped=1)`, byte for byte
a run whose only test was skipped; Python 3.11+'s `-v` shows the subtest but
3.9's does not, and pytest before 9 reports such a `TestCase` as `1
skipped`. It is kept because the runner's own report is that nothing passed:
gatekit judges what the run printed, and the alternative — never naming a
unittest run whose only evidence is `s` — would give up the common case (a
whole suite behind a platform guard) to protect a rare one. Shape 1 is
kept for the same reason: the `.` it would need is indistinguishable from
the first character of arbitrary output. The remedy is
the same as for any all-skipped run: run the criterion where the skipped
subtest can run, or skip at the test level, not inside a subtest loop.

**Intentional platform skips now show `unverified`.** A criterion whose
tests all skip on this machine (a Windows-only suite on macOS, a GPU test on
a laptop) proved nothing here, and saying `ok` would be a claim gatekit
cannot back. `unverified` is not `fail`: it does not mark the work wrong, it
says this run could not judge it. The remedy is to un-skip, or to run the
criterion where its tests can run.

**Patterns are linear.** Five existing patterns opened with `^=*\s*` or
`^\s*`. Under `re.MULTILINE`, `\s*` crosses newlines, so a search over many
blank or whitespace-only lines re-scanned the rest of the output from every
line start: 20,000 blank lines took 1.6 s for `pytest-deselected` alone, and
the time grows with the square of the length. They now use `[ \t]*`, which
stays on its line, and the go positive's separators are `[ \t]+`. A test runs
every pattern over multi-megabyte outputs within a fixed bound.

The signature file's hash changes, so every Stop-gate reuse record is
re-judged once (§2, `signatures_sha256`), which is intended.

**Contract changes** (`docs/ARCHITECTURE.md` §5, §10, §14): the `kind`
field, `describe_empty`, the all-skipped rule and the narrowed positives.
