"""console — the CI gates print UTF-8 regardless of the console's code page.

A gate prints a finding's path and message, and either can be non-ASCII: a
Hangul path, an em dash in a message. A Windows console reports cp949 or
cp1252; printing there died with ``UnicodeEncodeError`` mid-print, exit 1 as
if the gate had judged, with the finding itself lost. The plugin's own
entry points do the same through ``gatebound.hookio.utf8_stdio``; tools/ is
stdlib-only and imports nothing from plugin/, so it keeps its own copy.

Each gate runs as ``python tools/gate_*.py``, which puts tools/ first on
``sys.path``, so ``import console`` resolves here.
"""
from __future__ import annotations

import sys


def utf8_stdio() -> None:
    """Reconfigure stdout and stderr to UTF-8; characters the console still
    cannot show are replaced, never raised: a finding must print."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # closed or detached stream: nothing to fix
            pass
