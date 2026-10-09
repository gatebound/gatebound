# ADR-0039: On Windows, process liveness and age come from kernel32, not a child process

Status: accepted 2026-10-05. Amends ADR-0019 decision 3d (liveness through
`tasklist`, age through PowerShell); `taskkill /T /F` is unchanged.

## Context

`jobs stop` ends a worker only when its recorded pid is alive **and** the
process's age agrees with `pid_started_at` within
`STOP_PID_AGE_TOLERANCE_S`, so a recycled pid is never signalled. A pid that
fails either check is listed in `skipped` and left running.

On Windows both checks started a child process: `tasklist` (5 s timeout) for
liveness and `powershell -Command (Get-Process -Id N).StartTime` (10 s
timeout) for age. On 2026-10-05 the `windows-latest` / Python 3.12 job of CI
run 37249139807 failed
`test_stop_ends_the_running_worker_and_marks_queued_tasks_stopped`: the
test took 25.9 s where the passing run of the same commit took 2.8 s, and
`stop()` returned after about 10 s, the PowerShell timeout. The age probe
gave no answer, the live worker was `skipped`, the 30 s fake worker kept
running past the 15 s join, and its open `output.txt` then broke the
temporary directory's cleanup. The run was busy with 1,946 tests; a cold
PowerShell start on a loaded machine is enough.

The same can happen to a user: a slow machine or an antivirus scan delaying
PowerShell makes `jobs stop` record every task `stopped` while the running
worker carries on to the end. The stop marker still keeps new tasks from
starting, which is why this went unnoticed.

## Decision

1. **`jobs._win_process_info(pid)` asks kernel32 directly** through `ctypes`
   (standard library): `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`,
   `GetExitCodeProcess` (alive while it reads `STILL_ACTIVE`, 259) and
   `GetProcessTimes` (creation time, a FILETIME converted to Unix seconds).
   It returns `(alive, created_at)`, `(False, None)` when no process has the
   pid (`ERROR_INVALID_PARAMETER`) or it has exited, and `None` — no
   answer — for anything else: not Windows, `ctypes` unavailable, access
   denied, an API failure, an exception. No child process is started, so
   load cannot push the answer past a timeout. A pid no Windows process can
   have (not a positive multiple of 4 that fits a DWORD, as a corrupt
   `status.json` might hold) gets no native answer: the kernel would mask or
   round it onto another process.
2. **`_pid_alive` and `_process_age_s` use it first on Windows** and fall
   back to the existing `tasklist` and PowerShell probes only when it gives
   no answer (and, for age, when the process is alive but its times are
   unreadable). The age tolerance, the `skipped` rule and termination
   through `taskkill /T /F` are unchanged, as is the POSIX path.
3. **The stop test asserts the worker was signalled** before it joins the
   runner thread, so a skipped worker fails with the `stop()` result in the
   message instead of a bare join timeout.

## Consequences

- `jobs stop` on Windows answers in milliseconds per task and no longer
  depends on PowerShell starting quickly.
- A process exiting with code 259 reads as alive to `GetExitCodeProcess`;
  the age check still has to agree with `pid_started_at`, so such a pid is
  at worst signalled after it has already ended, which `taskkill` reports as
  a failure and the task is listed `skipped`.
- The kernel32 path is exercised for real only on Windows (CI
  `windows-latest`, a test skipped elsewhere). On every OS a stand-in for
  `ctypes.WinDLL` drives each branch of the helper (no such pid, access
  denied, alive, exited, unreadable times, impossible pid), and mocks drive
  both Windows branches of `_pid_alive` and `_process_age_s`.
