"""Cross-platform stand-ins for CLIs such as `claude` (ADR-0019).

A `#!/bin/sh` script named `claude` is found on PATH on POSIX only; Windows
finds programs by PATHEXT (`claude.cmd`) and cannot run a shebang. These
stubs are Python programs behind a launcher each OS can run from PATH.
"""
from __future__ import annotations

import os
import pathlib
import stat
import sys


def make_python_stub(directory: pathlib.Path, name: str, body: str) -> pathlib.Path:
    """Put an executable `name` on *directory* that runs Python *body*.

    *body* sees ``sys.argv[1:]`` as the stub's own arguments. Returns the path
    that ``shutil.which(name)`` resolves to.
    """
    directory = pathlib.Path(directory)
    script = directory / ("_%s_stub.py" % name)
    script.write_text(body, encoding="utf-8")
    if os.name == "nt":
        # cmd.exe reads a batch file in the OEM code page, so a UTF-8 file
        # mangles a non-ASCII path (a home directory with a Korean name). The script is
        # found through %~dp0, which cmd expands itself; only the interpreter
        # path is written into the file, in the codec cmd will read it with.
        launcher = directory / (name + ".cmd")
        launcher.write_text(
            '@echo off\r\n"%s" "%%~dp0%s" %%*\r\nexit /b %%ERRORLEVEL%%\r\n'
            % (sys.executable, script.name),
            encoding="oem",
        )
    else:
        launcher = directory / name
        launcher.write_text(
            '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script), encoding="utf-8"
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


#: ERROR_PRIVILEGE_NOT_HELD: Windows without the symlink privilege or
#: Developer Mode refuses os.symlink with this.
_WINERROR_PRIVILEGE_NOT_HELD = 1314


def symlink_or_skip(test, target, link, target_is_directory: bool = False) -> None:
    """Create *link* → *target*, or skip *test* where this OS will not let us.

    Only a missing privilege (WinError 1314) or no symlink support at all
    skips, with the reason; any other failure is raised, so a broken test is
    never hidden as a skip. CI's Windows runner holds the privilege, so these
    tests still run there.
    """
    try:
        os.symlink(str(target), str(link), target_is_directory=target_is_directory)
    except NotImplementedError as exc:
        test.skipTest("symlinks are not supported here: %s" % exc)
    except OSError as exc:
        if getattr(exc, "winerror", None) != _WINERROR_PRIVILEGE_NOT_HELD:
            raise
        test.skipTest("creating a symlink needs a privilege this Windows account "
                      "lacks (WinError 1314; enable Developer Mode to run it)")


def echo_stub_body(text: str, exit_code: int = 0, sleep: float = 0,
                   read_stdin: bool = False, echo_args: bool = False) -> str:
    """Python body: optionally drain stdin, sleep, print, exit."""
    return (
        "import sys, time\n"
        "if %r:\n    sys.stdin.read()\n"
        "time.sleep(%r)\n"
        "print(' '.join(sys.argv[1:]) if %r else %r)\n"
        "sys.exit(%d)\n"
    ) % (read_stdin, float(sleep), echo_args, text, exit_code)
