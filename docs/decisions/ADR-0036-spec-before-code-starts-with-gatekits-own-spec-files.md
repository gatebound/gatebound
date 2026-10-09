# ADR-0036: Spec-before-code starts with gatekit's own spec files, not with any `spec/` directory

Status: accepted 2026-10-05 (owner chose this option over the two below).
Amends ADR-0018 and the "Gate behaviour" preamble of ARCHITECTURE §3
(0.11.2).

## Context

0.11.2 made the gates of a globally installed plugin stand down in projects
gatekit does not manage, keyed on the state directory (`.gatekit/`). It
changed spawn, prompt, question and stop (skill followed in ADR-0032), and
ARCHITECTURE §3 said "Every gate stands down in a project that has no
`.gatekit/` directory". The write, Bash and PowerShell gates were not
changed: their rule (a), spec before code, switches on when a `spec/`
directory exists.

Checked on 2026-10-05 in a temporary project gatekit had never touched,
holding only `spec/models/user_spec.rb` (an RSpec layout): a `Write` to
`app/models/user.rb` and the Bash command `echo x > app/models/user.rb`
were both denied with "writing code is blocked until spec/05-gate.md is
approved". Every Ruby project, and every JavaScript project that keeps its
tests in `spec/`, is blocked the same way once the plugin is installed.

Making these gates follow the documented rule instead would open a hole in
real gatekit projects: the state directory appears late. In an empty
project neither `gatekit.py lang` nor `spec validate` creates it, nor does a
`spec/01-prd.md`; `/gatekit:setup` (through `workers set-default`) and
`/gatekit:gate` (approve, contract derive) do. Keyed on `.gatekit/`, rule
(a) would be off for the whole interview → design → tasks stretch it exists
to guard.

Options considered:

- **A (chosen):** rule (a) starts when `spec/` holds at least one of
  gatekit's spec files.
- B: every gate keys on `.gatekit/`, and discover, interview, mockup and
  design create it first. One marker, but a project mid-pipeline today
  (`spec/` without `.gatekit/`) loses enforcement on upgrade until its next
  command, and four command bodies change.
- C: correct the document only. The RSpec block stays.

## Decision

1. **Rule (a) is active only while `spec/` holds a gatekit spec file**:
   one of the names in `plugin/spec-kit/heading-map.json` → `files`
   (`00-discovery.md`, `01-prd.md`, `02-screens.md`, `02-design.md`,
   `03-architecture.md`, `04-tasks.md`, `05-gate.md`, `RECOVERY.md`,
   `PROGRESS.md`), the list `spec validate` already judges, so the data
   lives in one place. `write.spec_set_present(root)` reads it; both places
   that switched on `spec/` existing (`restrictions_active`, `decide_path`)
   use it, so the Write, Bash and PowerShell gates change together. The
   other conditions are unchanged: `enforce_spec_before_code`, no valid
   approval of `spec/05-gate.md`, the target inside the root and outside
   the allowlist.
2. **Unchanged:** protected state (ADR-0027) holds in every project — with
   no `.gatekit/` there is nothing for it to protect; rule (b), the task
   write scope, is keyed on `GATEKIT_TASK_ID`, which only gatekit's own
   workers carry.
3. **ARCHITECTURE §3 states what each gate keys on**: the five ledger gates
   on the state directory, rule (a) on gatekit's spec files, protected
   state and rule (b) as above.

## Consequences

- A project with an unrelated `spec/` directory (RSpec, Jasmine, a `spec/`
  of documents) is no longer blocked. A gatekit project is guarded from the
  first spec file a command writes (`00-discovery.md` from discover,
  `01-prd.md` from interview), as before.
- A project that happens to keep its own `spec/01-prd.md` (or another name
  in the list) is still treated as a gatekit project. Accepted: the names
  are numbered stage files, and the deny message says how to proceed.
- An empty `spec/` directory no longer switches rule (a) on. Tests that
  relied on that now create a spec file.
- Tests: an RSpec-shaped project allows `Write`, Bash and PowerShell writes
  into `app/`; each listed spec file switches rule (a) on; an empty `spec/`
  does not; a non-listed file (`spec/notes.md`) does not; approval still
  lifts it; the protected-state deny still holds with no spec file.
