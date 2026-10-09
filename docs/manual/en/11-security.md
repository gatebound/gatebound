# Security and operating posture

gatebound's hooks run on every prompt, tool call and stop event in the session, and a worker backend launches another CLI with write access to the project. This surface determines the defaults below.

## Hooks never block the session on their own errors

Every hook goes through `hookio.run` and always ends with exit 0. An internal exception is appended as one line to `.gatebound/runs/hook-errors.log`.

A gate that cannot parse its own state, hits a bug, or times out degrades to "allow the action and log it." It does not become "stop, or kill the user's session." A broken gate script is a logged annoyance, not an outage.

This is a security posture and a reliability posture. If the harness breaks the session, the user turns the harness off, and at that moment no rule is enforced at all.

## Worker sandboxing is on by default, and bypass is refused

Worker backends in `.gatebound/config.json` run sandboxed by default. The Codex backend's default argv is `codex exec --sandbox workspace-write`: it edits only files inside the project workspace and touches nothing outside it.

Bypassing the sandbox is an explicit opt-in.

- The backend must set `"unsafe": true` in its own config entry directly.
- gatebound never sets this value on the user's behalf.
- `workers enable` refuses to enable a backend whose argv has a bypass, dangerous or yolo style flag but no `"unsafe"`.
- When a backend runs unsafe, that fact is recorded in the job receipt (`job.json`).

There is no code path that silently falls back to bypass mode. If the sandbox is off, it is because the config says so, and that fact stays in the job history.

## Secrets never land in the ledgers or logs

The files below are all designed to hold only structural state: hashes, verdicts, scopes, timestamps.

| File | Content |
|---|---|
| `.gatebound/runs/<session_id>.json` | Session ledger |
| `.gatebound/runs/hook-errors.log` | One-line hook error log |
| `.gatebound/jobs/<job_id>/` | Job records |
| `.gatebound/approvals.json` | Approval records |

API keys, tokens and credentials do not go into these. If you find a code path that writes a secret into one of them, that is a bug. Do not open a public issue with reproduction details; report it privately.

## Mockups and web content are data, not instructions

Text that flows in from outside and passes through the interview or mockup pipeline — mockup images, screenshots, scraped web pages and so on — is treated **only as data to reason about**. However it is phrased, the agent does not treat it as instructions to follow.

If content from such a source appears to contain instructions aimed at the agent, that is not something to follow; it is something to mark as a gap in the ledger.

## Actions that need approval

These are things gatebound does not do on the user's behalf.

| Action | Who does it |
|---|---|
| Approving `spec/05-gate.md` | The user only. The command asks with `AskUserQuestion` |
| Enabling the Codex backend | Needs user confirmation after an explanation |
| Making Codex the default backend | Needs a separate confirmation |
| Setting `"unsafe": true` | gatebound never sets it |
| Running doctor's fixes | Asks before running |

In particular, doctor **never** automatically runs a fix that rewrites `05-gate.md`, records an approval, or turns on an unsafe backend. These are the user's decisions and are made through the user's own commands.

## Write scope is enforced, not declared

A task's `write_scope` is enforced by the `PreToolUse` write gate, based on the `GATEBOUND_TASK_ID` environment variable that the job runner sets.

A task cannot write outside its declared scope, whether by accident or through a misbehaving prompt. The gate refuses at the tool-call boundary, regardless of what the worker believes it is allowed to do.

If the scope cannot be confirmed, the write is refused. A worker that claims a task id whose `task.json` cannot be read has every write refused.

## Blocking artifact path escapes

The `artifacts` paths of a completion criterion have three constraints.

1. They must be relative paths.
2. They cannot contain `..`.
3. They must still be inside the project root after `os.path.realpath` resolution.

A symbolic link that points outside the root is `fail`. The write gate normalizes paths the same way. It resolves relative input against the root and follows symbolic links, so a link cannot be used to land outside the project.

## Reporting a vulnerability

If you find a security problem in gatebound, do not open a public issue; report it privately. The contact is in the repository's `SECURITY.md`.
