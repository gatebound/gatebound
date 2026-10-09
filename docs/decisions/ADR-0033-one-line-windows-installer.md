# ADR-0033: A one-line Windows installer sets up the prerequisites, the PATH and the plugin

Status: accepted 2026-10-05 (owner, after review; Codex scope narrowed in
decision 11). Implemented in `install/install.ps1`, tested from
`tools/test_tools.py` (`TestInstallerScript`, `TestInstallerPlan`).
Adds a repository area outside `plugin/` (`install/`); no change to the
plugin, its hooks or its gates.

## Context

The Windows walkthrough (`docs/manual/02-install.md`, "Windows에서 처음부터",
and the PowerShell tab of the study guide) is ten steps long, and almost every
step exists because of a failure someone actually hit on a Korean Windows PC
between 2026-10-01 and 2026-10-05:

| What the user had to do by hand | Why it was needed (observed) |
|---|---|
| Install Git, Python and Claude Code one by one | A stock Windows has none of them; `claude` reads "not recognized" |
| Add `$HOME\.local\bin` to the user PATH | The Claude Code installer left `claude.exe` there and said it was not on PATH |
| Make sure the real Python comes before `WindowsApps` | `python`/`python3` resolve to the Microsoft Store placeholder, which prints `Python` and exits 49 (ADR-0030); a Python folder *appended* to the user PATH still loses to it |
| Close and reopen PowerShell after each install | PATH is read when a window starts; a running Claude session keeps the PATH it started with (0.16.10 names this case, ADR-0032) |
| Set `PYTHONUTF8=1` | cp949 consoles raised `UnicodeEncodeError` in gatekit and in other Python tools (fixed in gatekit by 0.16.9, 0.16.10 and #10) |
| Install Node from a PowerShell window, with agreement flags | `winget` run through Claude's `!` cannot answer its agreement prompt and fails with `0x8a150042` |
| Update with `marketplace update` + `plugin update`, then restart | gatekit runs from the plugin cache; restarting or `git pull` of the repository changes nothing |
| Run `/gatekit:doctor` and read rows 1, 2 and 7 | The only proof the hooks are live and which version runs |

Each fix is one or two lines of PowerShell, but a first-time user has to
notice the failure, find the right row in a troubleshooting table and type
the fix correctly. A pattern common to CLI tools removes that: one command,
`irm <url> | iex`, runs a script that checks what is present, installs what
is missing, merges the new PATH into the running window and registers the
plugin, then prints what is left for the user to do.

gatekit is a good fit for that pattern and needs less of it than most: it has
no Python package to install (standard library only), so the script only has
to provide an interpreter, Git for the hooks' shell, the host CLI and the
plugin itself.

## Decision

1. **A PowerShell script, `install/install.ps1`, at the repository root.**
   It lives outside `plugin/` because it runs before the plugin exists and is
   not part of what the host copies into its plugin cache. It targets the
   PowerShell 5.1 every supported Windows ships, uses no module beyond what
   that version includes, and is invoked as

   ```powershell
   irm https://raw.githubusercontent.com/gatebound/gatebound/<tag>/install/install.ps1 | iex
   ```

   with `<tag>` a release tag in every document that shows the command, so a
   user runs a reviewed version, not whatever `main` holds that minute.

2. **What it does, in order, each step skipped when already satisfied:**
   1. Refuse to run elevated. An administrator window starts in
      `C:\Windows\system32` and installs into the wrong profile; the script
      says to reopen PowerShell normally and stops.
   2. **Git**: present when `git --version` succeeds; otherwise
      `winget install --id Git.Git -e` with the agreement flags.
   3. **Python 3.9+**: present when an interpreter that is *not* under
      `WindowsApps` passes the same probe the hooks use
      (`import sys; sys.exit(sys.version_info < (3, 9))`, ADR-0030), tried as
      `python3`, `python`, then `py -3`; otherwise
      `winget install --id Python.Python.3.12 -e` with the agreement flags.
   4. **Claude Code**: present when `claude --version` succeeds; otherwise
      the official installer, `irm https://claude.ai/install.ps1 | iex`.
   5. **User PATH**, changed only through the user scope
      (`[Environment]::SetEnvironmentVariable(…, "User")`), never the machine
      scope, and only by adding entries that are missing:
      `$HOME\.local\bin` when `claude.exe` is there; the real Python folder
      and its `Scripts`, placed **before** `WindowsApps` when the placeholder
      would otherwise win.
   6. **This window's PATH** is rebuilt from the machine and user values, so
      the remaining steps, and the user's next command, see what was just
      installed without reopening anything.
   7. **`PYTHONUTF8=1`** in the user environment, unless the user already set
      `PYTHONUTF8` to something.
   8. **The plugin**: `claude plugin marketplace add gatebound/gatebound` and
      `claude plugin install gatekit@gatekit` on a first install;
      `claude plugin marketplace update gatekit` and
      `claude plugin update gatekit@gatekit` when gatekit is already there.
   9. **Node.js LTS only with `-WithNode`** (by default since decision 13), through
      `winget install OpenJS.NodeJS.LTS --source winget
      --accept-source-agreements --accept-package-agreements`, and
      `C:\Program Files\nodejs` plus `$env:APPDATA\npm` on the user PATH when
      missing. Only web projects need it.

3. **What it does not do.** It does not log in (`claude` opens a browser on
   first run, which the user does), create or open a project, touch `spec/`
   or `.gatekit/`, change the machine PATH, turn off the Store's app
   execution aliases (the PATH order makes them harmless), install Codex
   (decision 11), or set up WSL. Codex and WSL keep their manual sections.

4. **It reports with the four verdicts.** The script ends with one table, a
   row per item (Git, Python, Claude Code, PATH, PYTHONUTF8, gatekit, and
   Node when asked): `ok` (present or installed and verified by running
   it), `warn` (works, worth knowing: e.g. a Python older than 3.12 but at
   least 3.9), `fail` (tried and did not work, with the fix), `unverified`
   (not checked: e.g. `winget` absent, so nothing could be installed). The
   exit code is 1 when any row is `fail`. Under it, the next steps: open a
   new PowerShell window, `Set-Location` to the project folder, run `claude`
   (log in on first run), then `/gatekit:doctor`.

5. **It is safe to run again.** Every step checks before it acts, so a
   second run on a working machine changes nothing and reports all `ok`;
   running it again is also how a user updates gatekit.

6. **`-DryRun` prints the plan and changes nothing.** Each row then reads
   what would happen (`install Python.Python.3.12`, `add to user PATH:
   …\.local\bin`). The manual also shows the inspect-first form for people
   who do not run piped scripts:

   ```powershell
   irm <url> -OutFile install.ps1; notepad install.ps1
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```

7. **Its messages follow the user's language.** Korean when the Windows
   display language or the regional format is `ko-*`, English otherwise; the
   study PC has an English display with a Korean format and system locale,
   and its user reads Korean. `-Lang ko|en` overrides. Identifiers, commands
   and verdict words are never translated.

8. **Tests and CI.** The decisions the script makes (is this Python real,
   which PATH entries are missing and where they go, which step runs) are
   exercised from `tools/test_tools.py` by running `install.ps1 -DryRun`
   against a fake environment: a temporary profile with a stub
   `WindowsApps\python.exe` that prints `Python` and exits 49, a stub
   `claude.exe`, and a controlled PATH. These tests run on Windows and skip
   elsewhere. The `windows-latest` job of `fresh-clone-smoke` additionally
   runs the script for real on the runner and then `doctor` in a sample
   project.

9. **The manual shrinks.** After a release ships the script, the PowerShell
   tab becomes three steps (run the one line, log in with `claude`, run
   `/gatekit:doctor`), and today's manual steps move under "if the installer
   cannot run".

10. **macOS and Linux are out of scope here.** Their manual path has no
    comparable failures recorded. An `install/install.sh` would be a
    separate decision.

11. **Codex is out of scope until its gates are seen running on Windows.**
    The install half would likely work the same way: a participant
    installed the Codex CLI with npm and added the plugin with
    `codex plugin marketplace add` / `codex plugin add` on Windows. But the
    script could then report every Codex row `ok` while nothing enforces,
    which is the failure this project ranks worst (doctor's hooks axis):
    - Codex runs a plugin's hooks only after the user trusts them in
      `/hooks`, an interactive review inside the Codex terminal, redone
      after every upgrade; the desktop app does not record the trust today
      (openai/codex#47283). An installer must not take that decision for
      the user, so it cannot finish the Codex setup.
    - Whether the gates start at all under Codex on Windows is unverified.
      Codex appears to run hooks through CMD there, and the hook command is
      sh syntax; ADR-0030 decision 2 only predicts a degraded fallback to
      `py -3`, and no Codex-on-Windows session has been observed.
    - The study PC used for this decision has the Codex desktop app but no
      Codex CLI and no gatekit Codex plugin, so neither point could be
      checked here.

    The way in is evidence first: a person installs the Codex CLI and the
    plugin by the manual, trusts the hooks in `/hooks`, and runs the
    manual's gate check (a code write before approval must be denied). If
    the write is denied, an amendment adds `-WithCodex`, which installs the
    CLI (through `npm.cmd`, which PowerShell's script policy does not block)
    and the plugin, and always ends with a `warn` row saying the `/hooks`
    trust is still to do. If the write goes through, that is a gatekit bug
    to fix before any installer work.

    Update 2026-10-05: on the study PC the write went through, because
    Codex runs hooks in PowerShell 5.1, not CMD, and the sh-form command
    runs nothing there. ADR-0034 fixes the generated layer
    (`install --host codex`) with a `commandWindows`; the plugin-install
    route stays `unverified` on Windows. The same day the owner trusted
    the hooks in `/hooks` and saw a code write and a shell write denied
    before approval (ADR-0034 "Evidence", ADR-0035), which is the evidence
    this decision asks for, so the `-WithCodex` amendment can follow.

12. **`-WithCodex` installs the Codex CLI and says what is left per project
    (amendment, 2026-10-05).** It implies `-WithNode`, since the CLI comes
    from npm. Rows, after Node:
    - `codex`: `ok`/`skip` when `codex` is on PATH; otherwise
      `npm.cmd install -g @openai/codex` (through `npm.cmd`, which the
      script policy does not block where `npm.ps1` is), planned as
      `unverified` under `-DryRun`, then `ok` when `codex` answers,
      `warn` when only a new window would find it, `fail` when npm fails;
      `unverified`/`manual` when no `npm.cmd` exists yet (Node was just
      installed or `winget` is missing): run the installer again in a new
      window.
    - `codex-hooks`: always `warn`, with or without `-DryRun`. It names the
      two steps no installer may take for the user: in each project,
      `install --host codex` from the installed plugin (its path read from
      `installed_plugins.json` when known), then `codex` → `/hooks` → trust
      each gatekit hook and open a new session (`codex --no-daemon` if
      `codex` stops with `os error 5`, as on the study PC), again after
      every gatekit update. A Codex install therefore never ends `ok`.

    It does **not** add gatekit as a Codex plugin (`codex plugin add`): on
    Windows that route is `unverified` (ADR-0034 decision 3), and a plugin
    whose hooks cannot run beside a project layer whose hooks can would
    look installed while adding nothing. The tests plan each row against
    stubbed machines (`codex` present, `npm.cmd` present, neither) and pin
    that no row mentions `codex plugin`.

    **Seen on a second PC (2026-10-05).** A Windows PC with Git, an Anaconda
    Python 3.12, Claude Code and gatekit 0.16.10 but no Node.js and no
    Codex ran the v0.16.12 line with `-WithCodex`: `-DryRun` planned Node
    and named the missing `npm.cmd`; the real run installed Node.js v24.19.0
    (appending `C:\Program Files\nodejs` and `%APPDATA%\npm` to the user
    PATH), Codex CLI 0.160.0 and gatekit 0.16.12, and ended `warn` on
    `codex-hooks` alone. The printed `install --host codex` wrote 22 files
    in the project; after `/hooks` trust, an `apply_patch` and a shell
    `Set-Content` into `src/` were both denied before approval and neither
    file existed afterwards.

    **Amendment: the execution policy.** The same run reported `codex` `ok`,
    yet typing `codex --version` in a new window failed with "running
    scripts is disabled on this system" for `%APPDATA%\npm\codex.ps1`:
    npm writes `codex.ps1` beside `codex.cmd`, PowerShell prefers the
    `.ps1`, and the PC's policy was the client default, `Restricted`. The
    installer had run the `.cmd`. The owner fixed it with
    `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
    The `codex` row now reads the policy a **new** window gets — the first
    defined of MachinePolicy, UserPolicy, CurrentUser, LocalMachine, else
    `Restricted`; never the Process scope, which
    `powershell -ExecutionPolicy Bypass -File install.ps1` sets for itself
    only — and when it is `Restricted` or `AllSigned` the row is `warn`
    (not `ok`), naming the policy, that one-line fix and `codex.cmd` as the
    alternative; a planned or new-window row carries the same note. The
    installer never changes the policy: it is a security setting the user
    owns. The closing "next steps" line now says to run the
    `install --host codex` command from the `codex-hooks` row (the second
    PC's user typed `codex-hooks` as a command).

13. **Node.js LTS is installed by default (amendment, 2026-10-05,
    owner's request).** Step 9 no longer waits for `-WithNode`: the plain
    `irm … | iex` line checks for `node` and, when it is missing, installs
    it the same way (winget with the agreement flags, `C:\Program
    Files\nodejs` and `$env:APPDATA\npm` appended to the user PATH when
    missing). The study builds web apps, so "only web projects need it"
    left most participants one flag short, and Node from a PowerShell window
    is exactly the step the Context table lists as failing through Claude's
    `!` (`0x8a150042`). `-WithNode` is still accepted, so instructions that
    pass it keep working; it changes nothing. `-WithCodex` no longer needs to
    imply it. The `node` row joins every report (`ok`/`skip` when present).

## Consequences

- A first install on Windows is one command plus a browser login, and every
  failure in the Context table is handled by the script instead of a
  troubleshooting row.
- `docs/ARCHITECTURE.md` gains an `install/` entry in the repository layout.
  `gate_no_abs_paths.py` and `gate_clean_room.py` already scan it; the script
  uses `$HOME` and `$env:` variables, never a personal path.
- The script calls `winget`, the Claude Code installer and `claude plugin`,
  which change outside the repository. The release that ships the script
  must run the dry-run tests and the smoke job, and the script pins nothing
  but the plugin source, so a changed upstream flag surfaces as a `fail` row
  rather than a silent skip.
- Running a piped remote script is a trust decision the user makes. The
  script states what it will change before changing it, never elevates,
  never touches the machine scope, and the documented URL is a release tag.

## Still unverified

- **A truly fresh Windows.** GitHub's `windows-latest` already has Git,
  Python and Node, so CI exercises the skip paths and the plugin steps, not
  the installs; the first full run has to be a participant's PC, reported
  through the study.
- **Whether `winget install Git.Git` prompts for elevation** on a standard
  account. Git for Windows installs machine-wide by default; if it raises a
  UAC prompt the script cannot answer, the row reads `fail` with the
  git-scm.com installer as the fix.
- **Windows without `winget`** (older Windows 10 builds). The script reports
  `unverified` for every install step and links the manual install pages;
  it does not try to install `winget` itself.
- **Pinning the plugin version.** `claude plugin marketplace add` takes the
  repository's default branch today; whether it can be pointed at a tag is
  not established, so the script installs the marketplace's current gatekit
  and prints the version it got.
