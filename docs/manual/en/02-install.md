# Install and diagnosis

## Requirements

| Item | Condition | How to check |
|---|---|---|
| Python | 3.9 or newer, **installed by you**. The hooks try `python3` → `python` → `py -3` in that order, and run only after quietly confirming that the name is a real Python 3.9+ (ADR-0030). The `python`/`python3` that Windows ships by default are Microsoft Store placeholders, not Python | doctor axis 7. `warn` if a placeholder is on PATH |
| `claude` CLI | Must be on PATH | doctor axis 6 |
| Claude Code | A version that can install and enable plugins | doctor axis 2 |

The gatebound kernel uses only the Python standard library. No `pip install` is needed. The `codex` CLI is optional and disabled by default.

**Windows is a preview.** Native Windows is supported in the same release, but it has not been verified end to end in a real session. CI (`windows-latest`) only proves that the Python code runs. For Claude Code, install Git for Windows (the hooks run through Git Bash). Windows does not come with Python. Install it with `winget install Python.Python.3.12`, or check that `py -3 --version` responds. On the owner's PC (2026-10-04), `tools/smoke_fresh_clone.py` confirmed a Korean-named user folder, paths with spaces, the 7 hooks, and the Codex layer install; a real Claude Code session calling the hooks has not been observed yet. On Windows, when Claude Code runs shell commands through its `PowerShell` tool, the same rules as the bash gate apply (the powershell gate, ADR-0028). WSL behaves the same as Linux.

## Windows from scratch

A Windows PC has none of what gatebound assumes. No Claude Code, no Git, no Python, and typing `python` runs a Microsoft Store placeholder that prints only the word `Python` and exits. One line in **PowerShell** (not as administrator) does it (ADR-0033). If the window was opened as administrator, the install script stops and tells you to reopen it.

```powershell
irm https://raw.githubusercontent.com/gatebound/gatebound/v0.17.0/install/install.ps1 | iex
```

The script skips what is already there and installs only what is missing. It installs Git, a real Python 3.9 or newer (the Store placeholder does not count), Claude Code, and Node.js LTS with `winget` and the official installers, and fixes the user PATH (real Python ahead of the placeholder, `.local\bin` added). It reloads the current window's PATH, sets `PYTHONUTF8=1`, then installs or updates the plugin. At the end, each item shows `ok`/`warn`/`fail`/`unverified`. It does not touch the system PATH or administrator rights, and it is safe to run again. Updating is the same line.

Next, open a new PowerShell window, run `claude` in your project folder, log in, then run `/gatebound:doctor`. To see the plan without changing anything: `& ([scriptblock]::Create((irm <url>))) -DryRun`. Node.js is installed if missing without any extra flag (the `-WithNode` from earlier instructions is harmless if you add it, ADR-0033 decision 13). To use Codex too, use the line below.

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/gatebound/gatebound/v0.17.0/install/install.ps1))) -WithCodex
```

It installs the Codex CLI with `npm.cmd`, and the last row, `codex-hooks`, reports as `warn` the two steps left for each project (`install --host codex`, and trusting the hooks in `/hooks`). It does not install the Codex plugin (`codex plugin add`) (ADR-0033 decision 12).

### When you cannot use the install script (manual)

If you are on an old Windows without `winget`, or script execution is blocked, follow the steps below exactly in **PowerShell** (no administrator rights needed; opening it as administrator only sets the working folder to `system32` and causes confusion).

1. Install four things. For anything already installed, `winget` tells you so. Node.js is not needed by gatebound itself, but the study uses it to build and deploy web apps (the install script also installs it by default, ADR-0033 decision 13).

   ```powershell
   winget install Git.Git
   winget install Python.Python.3.12
   winget install OpenJS.NodeJS.LTS
   irm https://claude.ai/install.ps1 | iex
   ```

   The Claude Code installer may put `$HOME\.local\bin\claude.exe` in place and leave a note that it is "not on PATH" (it did on the owner's PC). In that case, add it to the user PATH with the line below. You do not need to open the graphical settings window.

   ```powershell
   [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$HOME\.local\bin", "User")
   ```

2. **Close the PowerShell window and open a new one.** PATH is refreshed only in a new window. Then check that all four print a version.

   ```powershell
   git --version
   py -3 --version
   node --version
   claude --version
   ```

   If `python --version` prints only `Python` with no version, it is the placeholder. The hooks skip that name and use `py -3` (ADR-0030), so it works if you leave it, but doctor axis 7 reports it as `warn`.

3. Run `claude` once, log in through the browser, and exit.

4. Install the plugin.

   ```powershell
   claude plugin marketplace add https://github.com/gatebound/gatebound
   claude plugin install gatebound@gatebound
   ```

5. Go to your project folder, open Claude Code, and run the diagnosis. The folder name may contain non-English characters and spaces. If you are unsure, it is safer to create a new folder with a plain English name, like `$HOME\study\my-app`.

   ```powershell
   mkdir $HOME\study\my-app
   cd $HOME\study\my-app
   claude
   ```

   Inside the session, run `/gatebound:doctor`. If axes 1 and 2 are `ok`, the hooks are registered. A `warn` on axis 7 is the placeholder notice and does not affect operation.

These are the steps followed on the owner's Windows 10 PC (Korean-named user folder, Python 3.9.10) on 2026-10-04. Before installing, it is normal for `claude` to report that it "is not recognized as the name of a cmdlet", and for `python` without Python installed to print only `Python`.

## macOS and Linux from scratch

No install script is needed: three lines in a terminal do it.

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude plugin marketplace add gatebound/gatebound
claude plugin install gatebound@gatebound
```

The first line is Claude Code's official installer, and the other two lines install gatebound. You need `git` and `python3` (3.9 or newer). On macOS, `xcode-select --install` installs both (run it when `git --version` asks to install); on Linux they are usually already there (Debian/Ubuntu: `sudo apt install -y git python3`). After installing, open a new terminal and run `claude` → `/gatebound:doctor` in your project folder.

Install Node.js LTS at the start as well. gatebound itself does not need it, but the study uses it to build and deploy web apps, and the Windows install script also installs it by default (ADR-0033 decision 13). On macOS, use the installer from nodejs.org or `brew install node`; on Linux, follow the instructions on nodejs.org (distribution packages are often out of date). It is done when `node --version` prints a version.

To use Codex too, run `npm install -g @openai/codex`, then follow the "Codex users" section below. The hooks run in sh, so nothing like Windows' `commandWindows` is needed.

The reasons Windows needed an install script (the Store placeholder Python, PATH not refreshed right after install, cp949, hooks run in PowerShell, the `codex.ps1` execution policy) do not exist on these systems, so there is no script for them. However, the 2026-10-05 Windows checks did not cover macOS or Linux, so after installing, check the gates once before [project initialization](#project-initialization). With spec files in `spec/` and no approval yet, a code write must be blocked.

## Install

```bash
/plugin marketplace add https://github.com/gatebound/gatebound
/plugin install gatebound@gatebound
```

After installing, you must **restart Claude Code** for the hooks in `plugin/hooks/hooks.json` to load. If you do not restart, the files are on disk but not a single gate fires.

### Claude desktop app users

In the app, plugins and hooks work exactly as in the CLI. In **+ → Plugins → Add plugin**, add the marketplace `https://github.com/gatebound/gatebound`, install `gatebound`, then open **your own project folder**. If you installed at user scope in the terminal, it is already in the app. Opening the gatebound repository folder itself in the app is not an install — the model reads the command files and imitates them, but no hook is registered, so not a single gate runs.

### Codex users (app and CLI)

Codex installs the same plugin from the same marketplace.

```bash
codex plugin marketplace add gatebound/gatebound
codex plugin add gatebound@gatebound
```

Skills are invoked as `$gatebound-<name>`. **Plugin hooks do not run until the user trusts them.** The Codex desktop app cannot record that trust today (openai/codex#47283), so in a terminal run `codex` → `/hooks`, review and trust the gatebound hooks, then open a new session. Trust is per hook content, so do it again after every upgrade. Until then, doctor axis 8 reports `warn`.

**On Windows, Codex works with both the plugin route and the host layer route below.** Codex runs hook commands in PowerShell 5.1 on Windows, and both the plugin's `hooks/hooks.json` (ADR-0038) and the `.codex/hooks.json` created by `install --host codex` (ADR-0034) carry a Windows `commandWindows`. Trusting the hooks (`/hooks`) is needed in the same way. Codex skips untrusted hooks without any message.

To set up Codex on Windows from scratch, follow these steps.

1. In PowerShell (not as administrator), run the one-line Codex install above. The `codex-hooks` row of the result table shows the `install --host codex` command for this PC.
2. Run that command in your project folder. It creates `.codex/hooks.json`, `.agents/skills/gatebound-*`, and a managed block in `AGENTS.md`.
3. Run `codex` in the same folder (if it stops with `os error 5`, use `codex --no-daemon`). Type `/hooks`, and press `t` on each new hook (`[!] … new`) to trust it. Be careful: pressing Space or Enter on an already trusted hook (`[x]`) removes the trust.
4. Exit with `/quit` and run `codex` again. Trust applies from the new session.
5. When you update gatebound, repeat steps 2–4. When hook content changes, trust has to be given again.

The older route (creating a host layer per project) still works.

```bash
git clone https://github.com/gatebound/gatebound
python3 "gatebound/plugin/bin/gatebound.py" install --host codex
```

This creates `.codex/hooks.json`, `.agents/skills/gatebound-*` (one skill per command), and a managed block in `AGENTS.md`. Do not edit the generated files by hand; edit `plugin/` and run `install` again. When Codex asks whether to trust the project's `.codex/` layer, approve it and **open a new session**. What works per host and what is `unverified` is in the host parity table in the README.

After restarting, always run the diagnosis.

```bash
/gatebound:doctor
```

## The 8-axis doctor verdict table

`doctor` gives each of 8 axes an `ok`/`warn`/`fail`/`unverified` verdict, and prints a copy-paste-able `fix` string per axis. The exit code is 1 only when there is at least one `fail`. Exit code 0 means "nothing failed", not "everything is fine".

| # | Axis | What it checks | Fix when `fail` |
|---|---|---|---|
| 1 | plugin files | Do `plugin.json`, `hooks.json` and the 9 gate scripts (prompt, write, bash, powershell, skill, spawn, question, compact, stop) exist and are they non-empty? | `/plugin install gatebound` — if a script is missing, that gate never fires at all |
| 2 | hooks registered | Is it listed in `installed_plugins.json` and enabled in `enabledPlugins` of `settings.json`? | `/plugin enable gatebound@gatebound` |
| 3 | project state | Do `.gatebound/config.json` and `approvals.json` parse? `warn` if something is already listening on the `webServer` port of a Playwright config (`playwright.config.{ts,js,mjs,cjs}`, including under `spec/design/e2e/`) (the `port:`/`url:` numbers inside the braces or brackets of a `webServer:`, `'webServer':` or `const webServer: Type =` value, with comments removed, and the default after `\|\|` as in `process.env.PORT \|\| 3000`; this is a simple scan, not a parser, so a port given only through a variable is not found). On POSIX, if `lsof` is available, it records that process's PID, command and working directory, and whether it is inside or outside this project (ADR-0026) | Edit or delete the file by hand. For a port conflict, stop that process yourself or change the port. doctor terminates nothing |
| 4 | spec set | The `spec validate` verdict | Go to the pipeline that owns the failing file |
| 5 | contract freshness | Does `source_sha256` in `.gatebound/contract.json` match `05-gate.md`? | Run `contract derive` again |
| 6 | workers | Is the default backend binary on PATH? | Install that CLI, or `workers set-default <name>` |
| 7 | python | Is the interpreter 3.9 or newer? | Install Python 3.9 or newer |
| 8 | host layer | If there is a `.codex/hooks.json` for Codex, do the gate scripts in it actually exist (`ok` if there is none)? `warn` if installed as a Codex plugin with no hook trust record | If the layer is broken, `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" install --host codex`; if there is no trust, in a terminal `codex` → `/hooks` |

### Normal cases where `unverified` appears

- Axis 2: running from a source checkout, so there is no install manifest. Not a problem.
- Axis 3: the project has no `.gatebound/` yet. You have not run `/gatebound:setup`.
- Axis 4: the project has no `spec/` directory. You have not run `/gatebound:interview`.
- Axis 5: there is no `.gatebound/contract.json` yet. You have not run `/gatebound:gate`.
- Axis 6: the binary exists but the `--version` probe did not respond. Builds still run.

Do not summarize `unverified` as "no problems". It means it was not checked.

### The most dangerous failure

A `fail` on axis 2. If it is installed but disabled in `enabledPlugins`, every file is on disk and not a single hook fires. The harness looks installed while enforcing nothing.

## Project initialization

Run this in the project directory.

```bash
/gatebound:setup
```

If `.gatebound/config.json` does not exist, it creates it with defaults, checks the default worker (`claude`), then shows the backend table. If it already exists, it leaves it alone.

To use the Codex backend, you have to ask for it separately.

```bash
/gatebound:setup codex
```

In this case it runs `workers check codex` first, explains what will change, and enables it only after the user confirms. Before confirmation, it changes nothing.

## Update

Run two lines in a terminal. The first only refreshes the marketplace listing; the second moves the installed plugin to the new version. Inside a Claude Code session, `/plugin marketplace update gatebound` and `/plugin update gatebound@gatebound` do the same.

```bash
claude plugin marketplace update gatebound
claude plugin update gatebound@gatebound
```

Restart Claude Code after updating too. The current session keeps using the old version it already loaded. After restarting, check axes 1 and 2 with `/gatebound:doctor`. On Windows, if you installed with the install script, running that one line again also updates.

If you also use the Codex plugin, update it separately.

```bash
codex plugin marketplace upgrade gatebound
codex plugin add gatebound@gatebound
```

Then open `codex` → `/hooks` in a terminal, press `t` on every gatebound hook listed as changed to trust it again, and start a new session. Trust is per hook content, so a release that changes the hooks needs it again. Doctor axis 8 counts the trusted hooks.

## Coming from gatekit

gatebound 0.17.0 is gatekit 0.16.15 under its own name. Projects that gatekit set up keep working; only the plugin has to be swapped.

1. Replace the plugin. Do not keep both enabled: `/gatebound:doctor` axis 2 fails while they are, and in a project that still has `.gatekit/` the new plugin's Stop and question gates stand down so the old one's are not doubled.

   ```bash
   claude plugin uninstall gatekit@gatekit
   claude plugin marketplace remove gatekit
   claude plugin marketplace add gatebound/gatebound
   claude plugin install gatebound@gatebound
   ```

   Codex: `codex plugin remove gatekit@gatekit`, `codex plugin marketplace remove gatekit`, then `codex plugin marketplace add gatebound/gatebound` and `codex plugin add gatebound@gatebound`, and trust the new hooks under `/hooks`. Restart Claude Code or start a new Codex session afterwards.

2. Nothing else is required. gatebound reads a project's `.gatekit/` while it has no `.gatebound/`, reads `gatekit-*` fences in `spec/` (approvals stay valid; never rewrite them), runs criteria and task gates whose argv names `…/gatekit/gates/<gate>.py` or `bin/gatekit.py`, and still arms on `/gatekit:<cmd>` and `$gatekit-<cmd>`.

3. Optionally move the state directory: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" migrate` shows the plan, `migrate --apply` renames `.gatekit/` to `.gatebound/` (with `git mv` when tracked), fixes `.gitignore` lines, and regenerates the Codex layer if the project has one. It never touches `spec/`. A project with the generated Codex layer can also just rerun `install --host codex`, which removes the old `.agents/skills/gatekit-*` directories it generated.

## Uninstall

```bash
/plugin uninstall gatebound@gatebound
```

The project's `spec/` and `.gatebound/` stay as they are. `spec/` is an artifact meant to be committed; inside `.gatebound/`, only `config.json` and `approvals.json` are meant to be committed, and `runs/` and `jobs/` are ignored. Removing the plugin does not delete these files, so delete them yourself if needed.
