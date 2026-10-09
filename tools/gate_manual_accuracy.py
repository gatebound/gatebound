#!/usr/bin/env python3
"""gate_manual_accuracy — the manual must describe the code that exists.

A user manual rots faster than the code it documents, and a wrong manual is
worse than none: it sends people to commands and files that are not there.
This gate checks the mechanical claims only — the things a rename or a
removal would invalidate:

  * every ``python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" <sub>`` call names a
    subcommand registered in plugin/gatebound/cli.py
  * the unrunnable ``python3 -m gatebound`` form never appears
  * every ``/gatebound:<name>`` names a file in plugin/commands/
  * every spec file named as ``NN-*.md`` exists in the ko template set
  * the index links to every other manual page, and links resolve
  * when the English manual (docs/manual/en/) exists, it gets the same
    checks, and each language has every page the other has

It cannot check whether the prose is true; that is what review is for.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import console

LAUNCHER_RE = re.compile(r'bin/gatebound\.py"?\s+([a-z-]+)')
MODULE_FORM_RE = re.compile(r"python3 -m gatebound")
SLASH_CMD_RE = re.compile(r"/gatebound:([a-z-]+)")
#: Only the real spec basenames. A looser pattern also matches manual page
#: names such as 01-intro.md and reports them as missing spec files.
SPEC_FILE_RE = re.compile(
    r"\b(01-prd\.md|02-screens\.md|03-architecture\.md|04-tasks\.md|05-gate\.md)\b"
)
#: A page may be referenced as a markdown link or as a bare code span; both
#: are navigable in a repo view, so both count as a reference.
LINK_RE = re.compile(r"\]\((\d\d-[a-z-]+\.md)\)")
REF_RE = re.compile(r"(?:\]\(|`)(\d\d-[a-z-]+\.md)(?:\)|`)")
SUBCOMMANDS_RE = re.compile(r'^\s*"([a-z-]+)":\s*\("gatebound\.', re.MULTILINE)


def scan(root: pathlib.Path) -> list:
    manual = root / "docs" / "manual"
    if not manual.is_dir():
        return [{"path": "docs/manual", "line": 0, "message": "manual directory is missing"}]
    findings = scan_pages(root, manual)
    english = manual / "en"
    if english.is_dir():
        findings += scan_pages(root, english)
        ko = {p.name for p in manual.glob("*.md")}
        en = {p.name for p in english.glob("*.md")}
        for name in sorted(ko - en):
            findings.append({"path": f"docs/manual/en/{name}", "line": 0,
                             "message": f"English page is missing; docs/manual/{name} has no translation"})
        for name in sorted(en - ko):
            findings.append({"path": f"docs/manual/{name}", "line": 0,
                             "message": f"Korean page is missing; docs/manual/en/{name} has no original"})
    return findings


def scan_pages(root: pathlib.Path, manual: pathlib.Path) -> list:
    findings = []
    rel_dir = manual.relative_to(root).as_posix()
    pages = sorted(manual.glob("*.md"))
    if not pages:
        return [{"path": rel_dir, "line": 0, "message": "manual directory has no pages"}]

    cli = root / "plugin" / "gatebound" / "cli.py"
    subs = set(SUBCOMMANDS_RE.findall(cli.read_text(encoding="utf-8"))) if cli.is_file() else set()
    commands = {p.stem for p in (root / "plugin" / "commands").glob("*.md")}
    templates = {p.name for p in (root / "plugin" / "spec-kit" / "templates" / "ko").glob("*.md")}
    names = {p.name for p in pages}

    for page in pages:
        rel = page.relative_to(root).as_posix()
        for lineno, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if MODULE_FORM_RE.search(line):
                findings.append({"path": rel, "line": lineno,
                                 "message": "python3 -m gatebound does not run from a project; use the bin/gatebound.py launcher"})
            for sub in LAUNCHER_RE.findall(line):
                if subs and sub not in subs:
                    findings.append({"path": rel, "line": lineno,
                                     "message": f"subcommand '{sub}' is not registered in cli.py"})
            for cmd in SLASH_CMD_RE.findall(line):
                if commands and cmd not in commands:
                    findings.append({"path": rel, "line": lineno,
                                     "message": f"/gatebound:{cmd} has no file in plugin/commands/"})
            for spec in SPEC_FILE_RE.findall(line):
                if templates and spec not in templates:
                    findings.append({"path": rel, "line": lineno,
                                     "message": f"spec file '{spec}' is not in the template set"})
            for target in LINK_RE.findall(line):
                if target not in names:
                    findings.append({"path": rel, "line": lineno,
                                     "message": f"link target '{target}' does not exist"})

    index = manual / "00-index.md"
    if not index.is_file():
        findings.append({"path": f"{rel_dir}/00-index.md", "line": 0, "message": "index page is missing"})
    else:
        linked = set(REF_RE.findall(index.read_text(encoding="utf-8")))
        for page in pages:
            if page.name != "00-index.md" and page.name not in linked:
                findings.append({"path": f"{rel_dir}/00-index.md", "line": 0,
                                 "message": f"index does not link to {page.name}"})
    return findings


def main(argv=None) -> int:
    console.utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = scan(pathlib.Path(args.root).resolve())
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False))
    else:
        for f in findings:
            print(f"{f['path']}:{f['line']}: {f['message']}")
        if not findings:
            print("gate_manual_accuracy: ok")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
