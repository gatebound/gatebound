"""`python3 -m gatebound <subcommand> ...` dispatcher.

Each subcommand lives in its own module exposing `run(argv: list[str]) -> int`.
The mapping is the single registry; modules are imported lazily so a broken
subcommand never takes the others down.
"""
from __future__ import annotations

import importlib
import sys

SUBCOMMANDS = {
    "doctor":   ("gatebound.doctor",   "Diagnose install, hooks, state, workers (ok/warn/fail/unverified)."),
    "spec":     ("gatebound.spec",     "Validate the spec set (spec/01..05, RECOVERY, PROGRESS)."),
    "contract": ("gatebound.contract", "Derive and run the completion contract from spec/05-gate.md."),
    "approve":  ("gatebound.approval", "Hash-anchored approvals: approve / check / list."),
    "design":   ("gatebound.design",   "Design tokens: merge-preset / impact."),
    "jobs":     ("gatebound.jobs",     "Worker jobs: start / status / wait / results / redelegate / clean."),
    "workers":  ("gatebound.workers",  "Worker backends: list / check / set-default (claude default, codex optional)."),
    "ledger":   ("gatebound.ledger",   "Session ledger: show / init / set-pipeline."),
    "lang":     ("gatebound.lang",     "Detect output language for a text (ko/en)."),
    "install":  ("gatebound.hosts",    "Generate a host layer (--host codex): hooks, skills, AGENTS.md block."),
    "migrate":  ("gatebound.migrate",  "Move the state directory to another name (dry run unless --apply)."),
}


def main(argv: list[str] | None = None) -> int:
    # Print UTF-8 regardless of the console's code page: a Windows console
    # reports cp1252 or cp949 while every gatebound message may carry Korean or
    # an em dash, and `doctor`, `spec validate`, `contract derive` and
    # `install` died with UnicodeEncodeError on a windows-latest fresh clone.
    # The token gate's script entry shares the helper.
    from gatebound import hookio
    hookio.utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("usage: python3 -m gatebound <subcommand> [args]\n")
        for name, (_, help_text) in SUBCOMMANDS.items():
            print(f"  {name:<10} {help_text}")
        return 0 if argv else 1
    name, rest = argv[0], argv[1:]
    if name not in SUBCOMMANDS:
        print(f"gatebound: unknown subcommand '{name}'", file=sys.stderr)
        return 2
    module = importlib.import_module(SUBCOMMANDS[name][0])
    return int(module.run(rest))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
