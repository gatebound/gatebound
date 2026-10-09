# gatebound installer for Windows (ADR-0033).
#
#   irm https://raw.githubusercontent.com/gatebound/gatebound/<tag>/install/install.ps1 | iex
#
# Checks what is present and installs only what is missing: Git, Python 3.9+
# (the Microsoft Store placeholder does not count), Claude Code, the user
# PATH entries they need, PYTHONUTF8=1, and the gatebound plugin (installed, or
# updated when already there). Never elevated, never the machine PATH, safe to
# run again. Ends with one row per item: ok / warn / fail / unverified.
#
# Options (pass them through a script block when piping:
#   & ([scriptblock]::Create((irm <url>))) -DryRun
#   -DryRun     print the plan, change nothing
#   -WithNode   accepted for old instructions; Node.js LTS is installed by
#               default when missing (ADR-0033 decision 13)
#   -WithCodex  also install the Codex CLI; trusting the hooks in each
#               project stays the user's step (ADR-0033 d12)
#   -Json       print the result as JSON instead of a table
#   -Lang ko|en message language (default: from the Windows UI language)
#
# The file is ASCII on purpose: Windows PowerShell 5.1 reads a file without a
# BOM in the ANSI code page, and a BOM breaks `irm | iex`. Korean messages are
# \u-escaped and unescaped at run time.
param(
    [switch]$DryRun,
    [switch]$WithNode,
    [switch]$WithCodex,
    [switch]$Json,
    [string]$Lang = ""
)

$code = & {
    $ErrorActionPreference = "Stop"

    # ---- test seams -------------------------------------------------------
    # The tests stand in a fake profile, PATH, elevation and PYTHONUTF8. Seams
    # are read here and only here, and never outside -DryRun, so a stray
    # environment variable cannot steer a real install.
    function Get-Seam {
        param([string]$Name)
        if (-not $DryRun) { return $null }
        return [Environment]::GetEnvironmentVariable("GATEBOUND_INSTALL_" + $Name, "Process")
    }
    $Testing = $null -ne (Get-Seam "HOME")

    function Seam-Or {
        param([string]$Name, [scriptblock]$Real)
        if ($Testing) { $v = Get-Seam $Name; if ($null -eq $v) { return "" } else { return $v } }
        return (& $Real)
    }

    # ---- language ---------------------------------------------------------
    # Korean when either the display language or the regional format is
    # Korean: a Korean user on an English-display Windows (observed on the
    # study PC: UI en-US, format ko-KR) still reads Korean.
    if ($Lang -ne "ko" -and $Lang -ne "en") {
        $Lang = if ((Get-UICulture).Name -like "ko*" -or (Get-Culture).Name -like "ko*") { "ko" } else { "en" }
    }
    function U { param([string]$s) return [regex]::Unescape($s) }
    $En = @{
        'elevated' = 'This window runs as administrator. Close it, open PowerShell normally (not ''Run as administrator'') and run the installer again.'
        'no_winget' = 'winget is not available here, so nothing was installed. Install it by hand: {0}'
        'will_install' = 'will install with: {0}'
        'installing' = 'installing {0} ...'
        'install_failed' = 'installing {0} failed. Install it by hand: {1}'
        'installed' = 'installed: {0}'
        'new_window' = 'installed, but this window cannot find {0} yet. Open a new PowerShell window and run the installer again.'
        'placeholder_only' = 'only the Microsoft Store placeholder (WindowsApps\python.exe) was found, which is not a Python. '
        'will_prepend' = 'will put in front of your user PATH, ahead of the Store placeholder: {0}'
        'prepended' = 'put in front of your user PATH: {0}'
        'will_append' = 'will add to the end of your user PATH: {0}'
        'appended' = 'added to the end of your user PATH: {0}'
        'off_path' = 'found at {0}, but not on PATH'
        'utf8_kept' = 'PYTHONUTF8={0} is already set for your account; left as it is'
        'will_set_utf8' = 'will set PYTHONUTF8=1 for your account'
        'set_utf8' = 'set PYTHONUTF8=1 for your account'
        'will_run' = 'will run: {0}'
        'running' = 'running: {0}'
        'no_claude' = 'Claude Code is not available, so the plugin was not installed. Open a new PowerShell window and run the installer again.'
        'step_failed' = '{0} failed'
        'gatebound_ready' = 'gatebound {0} is installed'
        'dry_run' = 'dry run: nothing was changed'
        'next' = 'Next:'
        'next_window' = 'Open a new PowerShell window.'
        'next_folder' = 'Go to your project folder, e.g.  Set-Location "$HOME\study\my-app"'
        'next_claude' = 'Run  claude  (it opens a browser to log in on the first run).'
        'next_doctor' = 'In Claude, run  /gatebound:doctor  - rows 1 and 2 should read ok.'
        'codex_no_npm' = 'npm.cmd is not on PATH yet, so the Codex CLI was not installed. Open a new PowerShell window and run the installer again with -WithCodex.'
        'codex_hooks' = 'Codex runs gatebound''s gates only after you trust them, so two steps are left in each project: run  {0} "{1}" install --host codex , then run  codex  (codex --no-daemon if it stops with os error 5), type /hooks, press t on each gatebound hook and start a new session. Redo both after every gatebound update.'
        'codex_policy' = ' PowerShell''s execution policy ({0}) blocks npm''s codex.ps1, so typing  codex  in PowerShell fails. Run once:  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned  (your account only, no admin), or type  codex.cmd  instead.'
        'next_codex' = 'For Codex: in each project folder, run the install --host codex command from the codex-hooks row, then trust the hooks in /hooks.'
    }
    $Ko = @{
        'elevated' = (U '\uAD00\uB9AC\uC790 \uAD8C\uD55C\uC73C\uB85C \uC5F0 \uCC3D\uC774\uC5D0\uC694. \uCC3D\uC744 \uB2EB\uACE0 PowerShell\uC744 \uC77C\uBC18\uC73C\uB85C("\uAD00\uB9AC\uC790 \uAD8C\uD55C\uC73C\uB85C \uC2E4\uD589" \uB9D0\uACE0) \uC5F0 \uB4A4 \uB2E4\uC2DC \uC2E4\uD589\uD558\uC138\uC694.')
        'no_winget' = (U '\uC774 PC\uC5D0\uB294 winget\uC774 \uC5C6\uC5B4\uC11C \uC124\uCE58\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC9C1\uC811 \uC124\uCE58\uD558\uC138\uC694: {0}')
        'will_install' = (U '\uB2E4\uC74C \uBA85\uB839\uC73C\uB85C \uC124\uCE58\uD574\uC694: {0}')
        'installing' = (U '{0} \uC124\uCE58 \uC911 ...')
        'install_failed' = (U '{0} \uC124\uCE58\uC5D0 \uC2E4\uD328\uD588\uC5B4\uC694. \uC9C1\uC811 \uC124\uCE58\uD558\uC138\uC694: {1}')
        'installed' = (U '\uC124\uCE58\uD588\uC5B4\uC694: {0}')
        'new_window' = (U '\uC124\uCE58\uB294 \uB410\uC9C0\uB9CC \uC774 \uCC3D\uC5D0\uC11C\uB294 \uC544\uC9C1 {0}\uC744(\uB97C) \uBABB \uCC3E\uC544\uC694. PowerShell\uC744 \uC0C8\uB85C \uC5F4\uACE0 \uC124\uCE58 \uC2A4\uD06C\uB9BD\uD2B8\uB97C \uB2E4\uC2DC \uC2E4\uD589\uD558\uC138\uC694.')
        'placeholder_only' = (U 'Microsoft Store\uC758 \uAC00\uC9DC python(WindowsApps\\python.exe)\uB9CC \uC788\uC5B4\uC694. \uC9C4\uC9DC Python\uC774 \uC544\uB2C8\uC5D0\uC694. ')
        'will_prepend' = (U '\uC0AC\uC6A9\uC790 PATH \uB9E8 \uC55E(Store \uAC00\uC9DC python\uBCF4\uB2E4 \uC55E)\uC5D0 \uB123\uC744\uAC8C\uC694: {0}')
        'prepended' = (U '\uC0AC\uC6A9\uC790 PATH \uB9E8 \uC55E\uC5D0 \uB123\uC5C8\uC5B4\uC694: {0}')
        'will_append' = (U '\uC0AC\uC6A9\uC790 PATH \uB05D\uC5D0 \uCD94\uAC00\uD560\uAC8C\uC694: {0}')
        'appended' = (U '\uC0AC\uC6A9\uC790 PATH \uB05D\uC5D0 \uCD94\uAC00\uD588\uC5B4\uC694: {0}')
        'off_path' = (U '{0}\uC5D0 \uC788\uC9C0\uB9CC PATH\uC5D0 \uC5C6\uC5B4\uC694')
        'utf8_kept' = (U '\uACC4\uC815\uC5D0 PYTHONUTF8={0}\uC774(\uAC00) \uC774\uBBF8 \uC788\uC5B4\uC11C \uADF8\uB300\uB85C \uB46C\uC694')
        'will_set_utf8' = (U '\uACC4\uC815\uC5D0 PYTHONUTF8=1\uC744 \uC124\uC815\uD560\uAC8C\uC694')
        'set_utf8' = (U '\uACC4\uC815\uC5D0 PYTHONUTF8=1\uC744 \uC124\uC815\uD588\uC5B4\uC694')
        'will_run' = (U '\uB2E4\uC74C\uC744 \uC2E4\uD589\uD560\uAC8C\uC694: {0}')
        'running' = (U '\uC2E4\uD589 \uC911: {0}')
        'no_claude' = (U 'Claude Code\uB97C \uCC3E\uC9C0 \uBABB\uD574 \uD50C\uB7EC\uADF8\uC778\uC744 \uC124\uCE58\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. PowerShell\uC744 \uC0C8\uB85C \uC5F4\uACE0 \uC124\uCE58 \uC2A4\uD06C\uB9BD\uD2B8\uB97C \uB2E4\uC2DC \uC2E4\uD589\uD558\uC138\uC694.')
        'step_failed' = (U '{0} \uC2E4\uD589\uC5D0 \uC2E4\uD328\uD588\uC5B4\uC694')
        'gatebound_ready' = (U 'gatebound {0} \uC124\uCE58\uB428')
        'dry_run' = (U '\uBBF8\uB9AC \uBCF4\uAE30: \uC544\uBB34\uAC83\uB3C4 \uBC14\uAFB8\uC9C0 \uC54A\uC558\uC5B4\uC694')
        'next' = (U '\uB2E4\uC74C \uD560 \uC77C:')
        'next_window' = (U 'PowerShell\uC744 \uC0C8\uB85C \uC5EC\uC138\uC694.')
        'next_folder' = (U '\uD504\uB85C\uC81D\uD2B8 \uD3F4\uB354\uB85C \uAC00\uC138\uC694. \uC608:  Set-Location "$HOME\\study\\my-app"')
        'next_claude' = (U 'claude \uB97C \uC2E4\uD589\uD558\uC138\uC694 (\uCC98\uC74C\uC774\uBA74 \uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C \uB85C\uADF8\uC778).')
        'next_doctor' = (U 'Claude \uC548\uC5D0\uC11C /gatebound:doctor \uB97C \uC2E4\uD589\uD558\uC138\uC694. 1, 2\uBC88 \uC904\uC774 ok\uBA74 \uB3FC\uC694.')
        'codex_no_npm' = (U '\uC544\uC9C1 PATH\uC5D0 npm.cmd\uAC00 \uC5C6\uC5B4\uC11C Codex CLI\uB97C \uC124\uCE58\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. PowerShell\uC744 \uC0C8\uB85C \uC5F4\uACE0 -WithCodex\uB85C \uC124\uCE58 \uC2A4\uD06C\uB9BD\uD2B8\uB97C \uB2E4\uC2DC \uC2E4\uD589\uD558\uC138\uC694.')
        'codex_hooks' = (U 'Codex\uB294 \uC0AC\uC6A9\uC790\uAC00 \uC2E0\uB8B0\uD55C \uB4A4\uC5D0\uB9CC gatebound \uAC8C\uC774\uD2B8\uB97C \uC2E4\uD589\uD574\uC694. \uD504\uB85C\uC81D\uD2B8\uB9C8\uB2E4 \uB450 \uB2E8\uACC4\uAC00 \uB0A8\uC558\uC5B4\uC694: {0} "{1}" install --host codex \uB97C \uC2E4\uD589\uD558\uACE0, codex \uB97C \uC2E4\uD589\uD574(os error 5\uB85C \uBA48\uCD94\uBA74 codex --no-daemon) /hooks \uC5D0\uC11C gatebound \uD6C5\uB9C8\uB2E4 t \uB97C \uB204\uB978 \uB4A4 \uC0C8 \uC138\uC158\uC744 \uC5EC\uC138\uC694. gatebound\uC744 \uC5C5\uB370\uC774\uD2B8\uD560 \uB54C\uB9C8\uB2E4 \uB450 \uB2E8\uACC4\uB97C \uB2E4\uC2DC \uD558\uC138\uC694.')
        'codex_policy' = (U ' PowerShell \uC2E4\uD589 \uC815\uCC45({0})\uC774 npm\uC774 \uB9CC\uB4E0 codex.ps1\uC744 \uB9C9\uC544\uC11C PowerShell\uC5D0\uC11C codex \uB97C \uCE58\uBA74 \uC2E4\uD328\uD574\uC694. \uD55C \uBC88\uB9CC \uC2E4\uD589\uD558\uC138\uC694: Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned (\uB0B4 \uACC4\uC815\uB9CC, \uAD00\uB9AC\uC790 \uAD8C\uD55C \uD544\uC694 \uC5C6\uC74C). \uB610\uB294 codex \uB300\uC2E0 codex.cmd \uB97C \uC4F0\uC138\uC694.')
        'next_codex' = (U 'Codex\uB97C \uC4F4\uB2E4\uBA74: \uD504\uB85C\uC81D\uD2B8 \uD3F4\uB354\uB9C8\uB2E4 \uACB0\uACFC \uD45C codex-hooks \uC904\uC5D0 \uC801\uD78C install --host codex \uBA85\uB839\uC744 \uC2E4\uD589\uD558\uACE0, /hooks \uC5D0\uC11C \uD6C5\uC744 \uC2E0\uB8B0\uD558\uC138\uC694.')
    }
    function T {
        param([string]$Key)
        $table = if ($Lang -eq "ko") { $Ko } else { $En }
        $text = $table[$Key]
        if ($null -eq $text) { $text = $En[$Key] }
        if ($args.Count -gt 0) { return ($text -f $args) }
        return $text
    }

    # ---- what the machine looks like --------------------------------------
    $UserHome = Seam-Or "HOME" { $HOME }
    $UserPath = Seam-Or "USER_PATH" { [Environment]::GetEnvironmentVariable("Path", "User") }
    $MachinePath = Seam-Or "MACHINE_PATH" { [Environment]::GetEnvironmentVariable("Path", "Machine") }
    $UserUtf8 = Seam-Or "USER_PYTHONUTF8" { [Environment]::GetEnvironmentVariable("PYTHONUTF8", "User") }
    $Elevated = Seam-Or "ELEVATED" {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        if ((New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { "1" } else { "0" }
    }
    $LocalBin = Join-Path $UserHome ".local\bin"
    $PluginsDir = Join-Path $UserHome ".claude\plugins"
    $Rows = New-Object System.Collections.ArrayList

    function Add-Row {
        param([string]$Item, [string]$Verdict, [string]$Action, [string]$Detail)
        [void]$Rows.Add([ordered]@{ item = $Item; verdict = $Verdict; action = $Action; detail = $Detail })
    }
    function Say { param([string]$Text) if (-not $Json) { Write-Host $Text } }

    function Split-PathList { param([string]$List) return @($List -split ";" | Where-Object { $_ -ne "" }) }
    function Same-Dir {
        param([string]$A, [string]$B)
        return ($A.TrimEnd("\") -ieq $B.TrimEnd("\"))
    }
    function On-Path {
        param([string]$Dir)
        foreach ($d in (Split-PathList ($MachinePath + ";" + $UserPath))) { if (Same-Dir $d $Dir) { return $true } }
        return $false
    }
    function Find-Command {
        param([string]$Name)
        return @(Get-Command $Name -All -CommandType Application -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
    }
    function Run-Quiet {
        param([string]$Exe, [string[]]$Arguments)
        # A native tool's stderr must not turn into a terminating error here.
        $ErrorActionPreference = "Continue"
        try {
            $out = & $Exe @Arguments 2>&1 | Out-String
            return @{ ok = ($LASTEXITCODE -eq 0); out = $out.Trim() }
        } catch {
            return @{ ok = $false; out = $_.Exception.Message }
        }
    }
    function Refresh-SessionPath {
        if ($Testing) { return }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }
    function Set-UserPath {
        param([string[]]$Front, [string[]]$Back)
        $keep = @(Split-PathList $UserPath | Where-Object {
            $entry = $_
            -not (@($Front + $Back) | Where-Object { Same-Dir $_ $entry })
        })
        $new = (@($Front) + $keep + @($Back) | Where-Object { $_ }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $new, "User")
        Set-Variable -Name UserPath -Value $new -Scope 1
        Refresh-SessionPath
    }

    # Python 3.9+: the same probe the hooks use (ADR-0030), with no shell
    # metacharacters: hexversion // 0x03090000 is 0 below 3.9.
    $Probe = "import sys; sys.exit(sys.hexversion // 50921472 == 0)"
    function Test-Python {
        param([string]$Exe, [string[]]$Pre)
        $r = Run-Quiet $Exe (@($Pre) + @("-c", $Probe))
        return $r.ok
    }
    function Find-Python {
        $placeholder = $null
        # `python` is shadowed when the first `python` on PATH is the Store
        # placeholder while a real one sits further down. A placeholder
        # `python3` is harmless: the hooks skip it (ADR-0030).
        $pythons = @(Find-Command "python")
        $shadowed = ($pythons.Count -gt 0) -and ($pythons[0] -match "\\WindowsApps\\")
        foreach ($name in @("python3", "python")) {
            foreach ($p in (Find-Command $name)) {
                if ($p -match "\\WindowsApps\\") { if ($null -eq $placeholder) { $placeholder = $p }; continue }
                if (Test-Python $p @()) {
                    return @{ path = $p; placeholder = $placeholder; shadowed = $shadowed }
                }
            }
        }
        foreach ($p in (Find-Command "py")) {
            if (Test-Python $p @("-3")) {
                $exe = (Run-Quiet $p @("-3", "-c", "import sys; print(sys.executable)")).out
                return @{ path = $exe; placeholder = $placeholder; shadowed = $false; launcher = $true }
            }
        }
        return @{ path = $null; placeholder = $placeholder }
    }

    $Winget = @(Find-Command "winget") | Select-Object -First 1
    $Agree = "--source winget --accept-source-agreements --accept-package-agreements"

    function Install-Package {
        # One winget package: plan it, or install it and say how it went.
        param([string]$Item, [string]$Id, [string]$ManualUrl, [string]$Note)
        $command = "winget install --id $Id -e $Agree"
        if (-not $Winget) {
            Add-Row $Item "unverified" "manual" ($Note + (T "no_winget" $ManualUrl))
            return $false
        }
        if ($DryRun) {
            Add-Row $Item "unverified" "install" ($Note + (T "will_install" $command))
            return $false
        }
        Say (T "installing" $Id)
        $r = Run-Quiet $Winget (@("install", "--id", $Id, "-e") + ($Agree -split " "))
        Refresh-SessionPath
        if (-not $r.ok) {
            Add-Row $Item "fail" "install" (T "install_failed" $Id $ManualUrl)
            return $false
        }
        return $true
    }

    # ---- 0. elevation -----------------------------------------------------
    if ($Elevated -eq "1") {
        Add-Row "elevation" "fail" "refuse" (T "elevated")
    } else {

    # ---- 1. Git -----------------------------------------------------------
    $git = @(Find-Command "git") | Select-Object -First 1
    if ($git) {
        Add-Row "git" "ok" "skip" (Run-Quiet $git @("--version")).out
    } elseif (Install-Package "git" "Git.Git" "https://git-scm.com/downloads/win" "") {
        $git = @(Find-Command "git") | Select-Object -First 1
        if ($git) { Add-Row "git" "ok" "install" (T "installed" (Run-Quiet $git @("--version")).out) }
        else { Add-Row "git" "warn" "install" (T "new_window" "git") }
    }

    # ---- 2. Python 3.9+ ---------------------------------------------------
    $py = Find-Python
    if ($py.path) {
        $ver = (Run-Quiet $py.path @("--version")).out
        Add-Row "python" "ok" "skip" ("{0} ({1})" -f $ver, $py.path)
        if ($py.shadowed) {
            $dir = Split-Path $py.path -Parent
            $dirs = @($dir)
            if (Test-Path (Join-Path $dir "Scripts")) { $dirs += (Join-Path $dir "Scripts") }
            if ($DryRun) { Add-Row "path" "unverified" "prepend" (T "will_prepend" ($dirs -join "; ")) }
            else { Set-UserPath -Front $dirs -Back @(); Add-Row "path" "ok" "prepend" (T "prepended" ($dirs -join "; ")) }
        }
    } else {
        $note = if ($py.placeholder) { T "placeholder_only" } else { "" }
        if (Install-Package "python" "Python.Python.3.12" "https://www.python.org/downloads/windows/" $note) {
            $py = Find-Python
            if (-not $py.path) {
                $base = Join-Path $UserHome "AppData\Local\Programs\Python"
                $dir = @(Get-ChildItem $base -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1)
                if ($dir) {
                    Set-UserPath -Front @($dir[0].FullName, (Join-Path $dir[0].FullName "Scripts")) -Back @()
                    Add-Row "path" "ok" "prepend" (T "prepended" $dir[0].FullName)
                    $py = Find-Python
                }
            }
            if ($py.path) { Add-Row "python" "ok" "install" (T "installed" (Run-Quiet $py.path @("--version")).out) }
            else { Add-Row "python" "warn" "install" (T "new_window" "python") }
        }
    }

    # ---- 3. Claude Code ---------------------------------------------------
    $claude = @(Find-Command "claude") | Select-Object -First 1
    $offPath = $null
    foreach ($n in @("claude.exe", "claude.cmd")) {
        if (-not $claude -and (Test-Path (Join-Path $LocalBin $n))) { $offPath = Join-Path $LocalBin $n }
    }
    $installer = "irm https://claude.ai/install.ps1 | iex"
    if ($claude) {
        Add-Row "claude" "ok" "skip" (Run-Quiet $claude @("--version")).out
    } elseif ($offPath) {
        Add-Row "claude" "ok" "skip" (T "off_path" $offPath)
    } elseif ($DryRun) {
        Add-Row "claude" "unverified" "install" (T "will_install" $installer)
    } else {
        Say (T "installing" "Claude Code")
        try {
            if ($Json) { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression | Out-Null }
            else { Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression | Out-Host }
        } catch { }
        Refresh-SessionPath
        $claude = @(Find-Command "claude") | Select-Object -First 1
        if (-not $claude -and (Test-Path (Join-Path $LocalBin "claude.exe"))) { $offPath = Join-Path $LocalBin "claude.exe" }
        if ($claude -or $offPath) { Add-Row "claude" "ok" "install" (T "installed" "Claude Code") }
        else { Add-Row "claude" "fail" "install" (T "install_failed" "Claude Code" "https://docs.claude.com/en/docs/claude-code/setup") }
    }
    if (-not $claude -and -not (On-Path $LocalBin) -and ($offPath -or $DryRun)) {
        if ($DryRun) { Add-Row "path" "unverified" "append" (T "will_append" $LocalBin) }
        else {
            Set-UserPath -Front @() -Back @($LocalBin)
            Add-Row "path" "ok" "append" (T "appended" $LocalBin)
            $claude = @(Find-Command "claude") | Select-Object -First 1
        }
    }

    # ---- 4. PYTHONUTF8 ----------------------------------------------------
    if ($UserUtf8) {
        Add-Row "pythonutf8" "ok" "skip" (T "utf8_kept" $UserUtf8)
    } elseif ($DryRun) {
        Add-Row "pythonutf8" "unverified" "set" (T "will_set_utf8")
    } else {
        [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
        $env:PYTHONUTF8 = "1"
        Add-Row "pythonutf8" "ok" "set" (T "set_utf8")
    }

    # ---- 5. the gatebound plugin --------------------------------------------
    $installedJson = Join-Path $PluginsDir "installed_plugins.json"
    $hasGatebound = (Test-Path $installedJson) -and ((Get-Content $installedJson -Raw -Encoding UTF8) -match '"gatebound@gatebound"')
    $knownJson = Join-Path $PluginsDir "known_marketplaces.json"
    $hasMarket = (Test-Path $knownJson) -and ((Get-Content $knownJson -Raw -Encoding UTF8) -match '"gatebound"')
    $steps = if ($hasGatebound) {
        @(@("plugin", "marketplace", "update", "gatebound"), @("plugin", "update", "gatebound@gatebound"))
    } elseif ($hasMarket) {
        @(@("plugin", "marketplace", "update", "gatebound"), @("plugin", "install", "gatebound@gatebound"))
    } else {
        @(@("plugin", "marketplace", "add", "gatebound/gatebound"), @("plugin", "install", "gatebound@gatebound"))
    }
    $action = if ($hasGatebound) { "update" } else { "install" }
    $shown = ($steps | ForEach-Object { "claude " + ($_ -join " ") }) -join "; "
    if ($DryRun) {
        Add-Row "gatebound" "unverified" $action (T "will_run" $shown)
    } else {
        $exe = if ($claude) { $claude } else { $offPath }
        if (-not $exe) {
            Add-Row "gatebound" "fail" $action (T "no_claude")
        } else {
            Say (T "running" $shown)
            $failed = $null
            foreach ($s in $steps) {
                $r = Run-Quiet $exe $s
                if (-not $r.ok) { $failed = "claude " + ($s -join " "); break }
            }
            if ($failed) {
                Add-Row "gatebound" "fail" $action (T "step_failed" $failed)
            } else {
                $ver = ""
                try {
                    $data = Get-Content $installedJson -Raw -Encoding UTF8 | ConvertFrom-Json
                    $ver = @($data.plugins."gatebound@gatebound")[0].version
                } catch { }
                Add-Row "gatebound" "ok" $action (T "gatebound_ready" $ver)
            }
        }
    }

    # ---- 6. Node.js LTS (by default, ADR-0033 decision 13) -----------------
    $node = @(Find-Command "node") | Select-Object -First 1
    if ($node) {
        Add-Row "node" "ok" "skip" (Run-Quiet $node @("--version")).out
    } elseif (Install-Package "node" "OpenJS.NodeJS.LTS" "https://nodejs.org/" "") {
        $nodeDir = Join-Path ${env:ProgramFiles} "nodejs"
        $npmDir = Join-Path $env:APPDATA "npm"
        $back = @(@($nodeDir, $npmDir) | Where-Object { -not (On-Path $_) })
        if ($back.Count -gt 0) { Set-UserPath -Front @() -Back $back; Add-Row "path" "ok" "append" (T "appended" ($back -join "; ")) }
        $node = @(Find-Command "node") | Select-Object -First 1
        if ($node) { Add-Row "node" "ok" "install" (T "installed" (Run-Quiet $node @("--version")).out) }
        else { Add-Row "node" "warn" "install" (T "new_window" "node") }
    }

    # ---- 7. Codex CLI (only with -WithCodex, ADR-0033 decision 12) ----------
    # The CLI only: gatebound is not added as a Codex plugin, whose hooks are
    # unverified on Windows (ADR-0034 decision 3). The per-project layer and
    # the hook trust are the user's steps, so the last row is always a warn.
    if ($WithCodex) {
        $codex = @(Find-Command "codex") | Select-Object -First 1
        $npm = @(Find-Command "npm.cmd") | Select-Object -First 1
        $npmCommand = "npm.cmd install -g @openai/codex"
        # npm also writes codex.ps1, which PowerShell prefers to codex.cmd; a
        # policy that refuses unsigned scripts leaves `codex` unusable even
        # though the .cmd this script runs works (observed on a second PC).
        # The policy is the one a NEW window gets: the Process scope is left
        # out, since `-ExecutionPolicy Bypass -File install.ps1` sets only it.
        # With every other scope Undefined, a Windows client is Restricted.
        $Policy = Seam-Or "EXECUTION_POLICY" {
            $byScope = @{}
            foreach ($e in (Get-ExecutionPolicy -List)) { $byScope[[string]$e.Scope] = [string]$e.ExecutionPolicy }
            $found = "Restricted"
            foreach ($s in @("LocalMachine", "CurrentUser", "UserPolicy", "MachinePolicy")) {
                if ($byScope[$s] -and $byScope[$s] -ne "Undefined") { $found = $byScope[$s] }
            }
            $found
        }
        $policyNote = if (@("Restricted", "AllSigned") -contains $Policy) { T "codex_policy" $Policy } else { "" }
        $codexOk = if ($policyNote) { "warn" } else { "ok" }
        if ($codex) {
            Add-Row "codex" $codexOk "skip" ((Run-Quiet $codex @("--version")).out + $policyNote)
        } elseif (-not $npm) {
            Add-Row "codex" "unverified" "manual" (T "codex_no_npm")
        } elseif ($DryRun) {
            Add-Row "codex" "unverified" "install" ((T "will_install" $npmCommand) + $policyNote)
        } else {
            Say (T "installing" "Codex CLI")
            $r = Run-Quiet $npm @("install", "-g", "@openai/codex")
            $npmDir = Join-Path $env:APPDATA "npm"
            if ($r.ok -and -not (On-Path $npmDir)) { Set-UserPath -Front @() -Back @($npmDir); Add-Row "path" "ok" "append" (T "appended" $npmDir) }
            Refresh-SessionPath
            $codex = @(Find-Command "codex") | Select-Object -First 1
            if (-not $r.ok) { Add-Row "codex" "fail" "install" (T "install_failed" $npmCommand "https://developers.openai.com/codex/cli") }
            elseif ($codex) { Add-Row "codex" $codexOk "install" ((T "installed" (Run-Quiet $codex @("--version")).out) + $policyNote) }
            else { Add-Row "codex" "warn" "install" ((T "new_window" "codex") + $policyNote) }
        }
        $pluginRoot = "<gatebound plugin folder>"
        try {
            $entry = @((Get-Content $installedJson -Raw -Encoding UTF8 | ConvertFrom-Json).plugins."gatebound@gatebound")[0]
            if ($entry.installPath) { $pluginRoot = $entry.installPath }
        } catch { }
        $pyShown = if ($py.path) { '& "' + $py.path + '"' } else { "python" }
        Add-Row "codex-hooks" "warn" "manual" (T "codex_hooks" $pyShown (Join-Path $pluginRoot "bin\gatebound.py"))
    }
    }

    # ---- report -----------------------------------------------------------
    $verdicts = @($Rows | ForEach-Object { $_.verdict })
    $overall = if ($verdicts -contains "fail") { "fail" }
        elseif ($verdicts -contains "unverified") { "unverified" }
        elseif ($verdicts -contains "warn") { "warn" }
        else { "ok" }

    if ($Json) {
        $saved = [Console]::OutputEncoding
        try {
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
            $result = [ordered]@{ lang = $Lang; dry_run = [bool]$DryRun; verdict = $overall; rows = @($Rows) }
            [Console]::Out.WriteLine((ConvertTo-Json -InputObject $result -Depth 5))
        } finally {
            [Console]::OutputEncoding = $saved
        }
    } else {
        Write-Host ""
        Write-Host ("gatebound installer - " + $overall + $(if ($DryRun) { "  (" + (T "dry_run") + ")" } else { "" }))
        foreach ($r in $Rows) {
            $color = switch ($r.verdict) { "ok" { "Green" } "warn" { "Yellow" } "fail" { "Red" } default { "Gray" } }
            Write-Host ("  {0,-11} {1,-11} {2}" -f $r.verdict, $r.item, $r.detail) -ForegroundColor $color
        }
        if ($overall -ne "fail" -and -not $DryRun) {
            Write-Host ""
            Write-Host (T "next")
            Write-Host ("  1. " + (T "next_window"))
            Write-Host ("  2. " + (T "next_folder"))
            Write-Host ("  3. " + (T "next_claude"))
            Write-Host ("  4. " + (T "next_doctor"))
            if ($WithCodex) { Write-Host ("  5. " + (T "next_codex")) }
        }
    }
    if ($overall -eq "fail") { 1 } else { 0 }
}

$global:LASTEXITCODE = $code
if ($PSCommandPath) { exit $code }
