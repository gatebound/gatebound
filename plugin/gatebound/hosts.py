"""Host layers: run the gates and commands under a host other than Claude Code.

Claude Code loads gatebound as a plugin. Codex CLI has no plugin format, but it
reads the same three things from a project: hooks (``.codex/hooks.json``),
skills (``.agents/skills/<name>/SKILL.md``) and ``AGENTS.md``. This module
generates those files **from the plugin tree**, so ``plugin/`` stays the
single source and the host layer is a build product, never hand-edited.

* ``.codex/hooks.json`` registers the six gate scripts with ``--host codex``
  (see :mod:`gatebound.hookio`). Codex loads project hooks only once the
  project's ``.codex/`` layer is trusted; that trust cannot be read from
  here, so :func:`status` never claims the hooks fire.
* Each ``plugin/commands/<name>.md`` becomes a skill: ``SKILL.md`` is a
  short shim (the plugin's own trigger text plus the Codex differences) and
  ``command.md`` is the command body with ``${CLAUDE_PLUGIN_ROOT}`` and
  ``/gatebound:<name>`` rewritten for Codex.
* ``AGENTS.md`` gains a managed block between markers; text outside the
  markers is the user's and is never touched.

Everything here is stdlib and idempotent: installing twice yields the same
files.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

from gatebound import config, names, paths, verdict

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only on 3.9/3.10 in CI
    tomllib = None  # type: ignore[assignment]

#: Hosts that need a generated layer. Claude Code is served by the plugin.
INSTALLABLE_HOSTS = ("codex",)

BLOCK_BEGIN, BLOCK_END = names.agents_markers()

#: Gate registrations, mirroring plugin/hooks/hooks.json with the Codex
#: differences: file edits arrive as apply_patch, and unified exec matches
#: as Bash.
_CODEX_HOOKS = (
    ("UserPromptSubmit", None, "prompt.py", 10),
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|apply_patch", "write.py", 10),
    ("PreToolUse", "Bash", "bash.py", 10),
    ("PreToolUse", "Agent|Task|collaborationspawn_agent", "spawn.py", 10),
    ("PostToolUse", "AskUserQuestion", "question.py", 10),
    ("Stop", None, "stop.py", None),  # timeout copied from the Claude hooks file
)

_SKILL_NOTES = """
## Differences under Codex

- Where the command says `AskUserQuestion`, ask the same options as a
  numbered list in plain chat and wait for the answer; Codex has no such tool.
  **Answering such a list with a bare number is the normal path here**, so it
  never changes the output language — keep replying in the language the
  conversation started in.
- Where the command says to run `WebSearch` (the domain research in
  `$gatebound-interview`), use whatever web search this session actually has.
  **If it has none, say so plainly and ask the user whether to skip that
  step or paste findings themselves** — do not route around it by spawning a
  subagent to "research" from memory. A proposal with no source is exactly
  what that step exists to avoid, and the command records a source line for
  every item it keeps.
- Where the command says to spawn an `Agent` with a ```gatebound-scope fence,
  keep the fence in the prompt you give the subagent; the spawn gate reads it.
- Commands are invoked as `$gatebound-<name>`, not `/gatebound:<name>`.
- Project hooks fire only after you trust this project's `.codex/` layer.
- Build workers and CLI evaluators are other agent CLIs (`claude`, `codex`)
  that need the user's login and network. Inside the Codex sandbox they fail
  with "Not logged in" (observed). Run `workers check <name> --probe` first,
  and run `jobs start`, `jobs redelegate` and `jobs evaluate` with escalated
  permissions when Codex asks; say so to the user before doing it.
"""

_AGENTS_BLOCK = """{begin}
# gatebound — operating rules for this project under Codex

gatebound is installed as a host layer: hooks in `.codex/hooks.json`, skills in
`.agents/skills/gatebound-*`. Do not edit those files; they are generated from
the gatebound plugin by `python3 "{launcher}" install --host codex`.

- Work spec-first. Until `spec/05-gate.md` is approved, write only under
  `spec/`, `docs/`, `.gatebound/` and root-level Markdown; the write gate denies
  anything else, including edits made through `apply_patch` and shell
  redirects.
- Invoke the pipeline as skills: `$gatebound-discover`, `$gatebound-interview`,
  `$gatebound-mockup`, `$gatebound-design`, `$gatebound-tasks`, `$gatebound-gate`,
  `$gatebound-build`, `$gatebound-verify`, `$gatebound-doctor`, `$gatebound-setup`.
- After writing any file under `spec/`, run
  `python3 "{launcher}" spec validate` and fix `fail` findings before
  reporting.
- Verdict words are exactly `ok / warn / fail / unverified`. `unverified` is
  never rounded to a pass or a failure.
- Codex has no `AskUserQuestion` tool: where a command calls for it, ask the
  same options as a numbered list in plain chat. A bare number in reply is a
  normal answer, not a switch to English — keep the conversation's language.
- A command that calls for web search (`$gatebound-interview`'s domain
  research) needs a real source. If this session has no web search, say so
  and ask whether to skip the step or have the user paste findings; never
  substitute a subagent recalling from memory.
- Do not claim a task is done; the gates and `contract run` decide.
- `jobs start`, `jobs redelegate` and `jobs evaluate` launch another agent
  CLI that needs the user's login and network; the Codex sandbox hides those
  (observed: "Not logged in"). Probe first with `workers check <name>
  --probe`, then run those commands with escalated permissions, telling the
  user why.
{end}
"""


def _launcher(plugin_root: pathlib.Path) -> str:
    return str(pathlib.Path(plugin_root) / "bin" / "gatebound.py")


def _claude_stop_timeout(plugin_root: pathlib.Path) -> int:
    hooks = json.loads((pathlib.Path(plugin_root) / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return int(hooks["hooks"]["Stop"][0]["hooks"][0]["timeout"])


#: ADR-0030: the probe a hook runs, output discarded, before trusting a name.
INTERPRETER_PROBE = '-c "import sys;sys.exit(sys.version_info<(3,9))" >/dev/null 2>&1'


def hook_command(script: str, suffix: str = "") -> str:
    """The sh command that runs *script* under the first name that is a real
    Python 3.9+: ``(python3 probe && python3 S) || (python probe && python S)
    || py -3 S``. A placeholder or a Python 2 fails its probe silently; only a
    missing ``py`` launcher is allowed to fail aloud, so the host sees an error
    rather than an allowed write (ADR-0030)."""
    run = '"%s"%s' % (script, suffix)
    return "(python3 %s && python3 %s) || (python %s && python %s) || py -3 %s" % (
        INTERPRETER_PROBE, run, INTERPRETER_PROBE, run, run)


def hook_command_windows(script: str, suffix: str = "") -> str:
    """The Windows PowerShell 5.1 form of :func:`hook_command`, for Codex's
    ``commandWindows`` (ADR-0034): Codex runs a hook command in PowerShell on
    Windows, where ``||`` and ``&&`` are parse errors and nothing would run.
    Same order and rules: each name is probed with its output discarded, ``py
    -3`` is last, and no interpreter at all fails aloud."""
    return "$s=%s; %s" % (_ps_literal(script), _ps_chain(suffix))


def plugin_hook_command_windows(relative: str, suffix: str = "") -> str:
    """The ``commandWindows`` of the plugin's own hooks.json (ADR-0038).

    A Codex plugin install on Windows runs it in PowerShell with the plugin
    root in ``PLUGIN_ROOT`` (and ``CLAUDE_PLUGIN_ROOT``); Claude Code never
    runs it. The root is read from the environment, so no character in the
    folder's name can break the command; *relative* is the gate script under
    the plugin root (``gatebound/gates/write.py``)."""
    return ("$r=$env:PLUGIN_ROOT; if(-not $r){ $r=$env:CLAUDE_PLUGIN_ROOT }; "
            "$s=Join-Path $r %s; %s") % (_ps_literal(relative), _ps_chain(suffix))


def _ps_literal(text: str) -> str:
    return "'%s'" % text.replace("'", "''")


def _ps_chain(suffix: str) -> str:
    """Run ``$s`` under the first real Python 3.9+, as :func:`hook_command`."""
    probe = "'import sys;sys.exit(sys.version_info<(3,9))'"
    found = "Get-Command %s -CommandType Application -ErrorAction SilentlyContinue"
    return (
        "foreach($n in 'python3','python'){ if(%s){ & $n -c %s *>$null; "
        "if($LASTEXITCODE -eq 0){ & $n $s%s; exit $LASTEXITCODE } } }; "
        "if(%s){ py -3 $s%s; exit $LASTEXITCODE }; "
        "[Console]::Error.WriteLine('gatebound: no Python 3.9+ found as python3, python or py -3'); exit 1"
    ) % (found % "$n", probe, suffix, found % "py", suffix)


_SCRIPT_IN_COMMAND_RE = re.compile(r'"([^"]+\.py)"')
_SCRIPT_IN_PS_COMMAND_RE = re.compile(r"^\$s='((?:[^']|'')+\.py)'")
_SCRIPT_IN_PLUGIN_PS_RE = re.compile(r"\$s=Join-Path \$r '((?:[^']|'')+\.py)'")


def hook_script(command: str) -> str:
    """The gate script a hook command runs: its first quoted ``*.py`` operand,
    or the ``$s='…'`` literal of the PowerShell form (ADR-0034).

    The probe that precedes it (ADR-0030) is also quoted, so the first quoted
    segment is no longer the script.
    """
    ps = _SCRIPT_IN_PS_COMMAND_RE.search(command or "")
    if ps:
        return ps.group(1).replace("''", "'")
    plugin = _SCRIPT_IN_PLUGIN_PS_RE.search(command or "")
    if plugin:  # ADR-0038: spelled as the sh form spells it
        return "${CLAUDE_PLUGIN_ROOT}/" + plugin.group(1).replace("''", "'")
    match = _SCRIPT_IN_COMMAND_RE.search(command or "")
    return match.group(1) if match else ""


def codex_hooks(plugin_root: pathlib.Path) -> Dict[str, Any]:
    """The ``.codex/hooks.json`` document for this plugin checkout."""
    gates = pathlib.Path(plugin_root) / "gatebound" / "gates"
    stop_timeout = _claude_stop_timeout(plugin_root)
    events: Dict[str, List[dict]] = {}
    for event, matcher, script, timeout in _CODEX_HOOKS:
        entry: Dict[str, Any] = {}
        if matcher is not None:
            entry["matcher"] = matcher
        entry["hooks"] = [
            {
                "type": "command",
                # ADR-0030: each name is probed silently before it runs the
                # gate, so a Store placeholder never writes to the hook's stdout.
                "command": hook_command(str(gates / script), " --host codex"),
                # ADR-0034: on Windows Codex runs this one, in PowerShell.
                "commandWindows": hook_command_windows(str(gates / script), " --host codex"),
                "timeout": timeout if timeout is not None else stop_timeout,
            }
        ]
        events.setdefault(event, []).append(entry)
    return {"hooks": events}


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _frontmatter_field(text: str, key: str) -> str:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return ""
    for line in match.group(1).splitlines():
        if line.startswith(key + ":"):
            return line[len(key) + 1:].strip()
    return ""


def stale_skill_dirs(root: pathlib.Path,
                     plugin_root: Optional[pathlib.Path] = None) -> List[pathlib.Path]:
    """Skill directories an installer under a :data:`names.LEGACY` name wrote
    (``.agents/skills/gatekit-<cmd>``, ``<cmd>`` one of this plugin's
    commands): exactly ``SKILL.md`` and ``command.md``, the shim naming
    itself. Anything else there — a file the user added, another skill such
    as ``gatekit-mytool`` — is left alone (ADR-0029 rename checklist)."""
    skills = pathlib.Path(root) / ".agents" / "skills"
    out: List[pathlib.Path] = []
    if not skills.is_dir():
        return out
    proot = pathlib.Path(plugin_root) if plugin_root else paths.plugin_root()
    commands = sorted(p.stem for p in (proot / "commands").glob("*.md"))
    for legacy in names.LEGACY:
        for skill in [skills / ("%s-%s" % (legacy, c)) for c in commands]:
            try:
                if skill.is_symlink() or not skill.is_dir():
                    continue
                if sorted(p.name for p in skill.iterdir()) != ["SKILL.md", "command.md"]:
                    continue
                shim = (skill / "SKILL.md").read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _frontmatter_field(shim, "name") == skill.name:
                out.append(skill)
    return out


def rewrite_command(text: str, plugin_root: pathlib.Path) -> str:
    """The command body as Codex must read it."""
    # Forward slashes, as Claude Code substitutes on Windows (ADR-0019).
    out = text.replace("${CLAUDE_PLUGIN_ROOT}", pathlib.Path(plugin_root).as_posix())
    names = sorted((p.stem for p in (pathlib.Path(plugin_root) / "commands").glob("*.md")), key=len, reverse=True)
    if names:
        # Only real command names, not preceded by a URL path character and
        # not followed by more identifier, become skill references.
        pattern = re.compile(r"(?<![\w/])/gatebound:(%s)(?![\w-])" % "|".join(re.escape(n) for n in names))
        out = pattern.sub(r"$gatebound-\1", out)
    return out


def skill_shim(name: str, description: str) -> str:
    return (
        "---\nname: gatebound-%s\ndescription: %s\n---\n\n# gatebound-%s\n\n"
        "Read `command.md` in this directory and follow it step by step; it is\n"
        "the execution instruction. This file only routes to it.\n%s"
        % (name, description or ("gatebound %s pipeline" % name), name, _SKILL_NOTES)
    )


def _agents_block(plugin_root: pathlib.Path) -> str:
    return _AGENTS_BLOCK.format(begin=BLOCK_BEGIN, end=BLOCK_END, launcher=_launcher(plugin_root))


def merged_agents_md(existing: Optional[str], plugin_root: pathlib.Path) -> str:
    """*existing* with the managed block replaced or appended."""
    block = _agents_block(plugin_root).rstrip("\n") + "\n"
    if not existing:
        return block
    # ADR-0029: blocks written under any of the plugin's names are replaced
    # by one, at the place of the first.
    text, first = existing, None
    for name in names.all_names():
        begin, end_marker = names.agents_markers(name)
        start = text.find(begin)
        end = text.find(end_marker, start) if start >= 0 else -1
        if start >= 0 and end > start:
            text = text[:start] + "\0" + text[end + len(end_marker):]
            first = True
        # markers out of order: leave the user's text alone
    if first:
        head, _, tail = text.partition("\0")
        return head + block.rstrip("\n") + tail.replace("\0", "").replace("\n\n\n", "\n\n")
    joiner = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + joiner + block


#: A `[hooks.state."<quoted key>"]` table header. Codex quotes the whole key
#: because it embeds `/`, `.` and `:`, which bare TOML keys cannot hold.
_HOOKS_STATE_HEADER_RE = re.compile(
    r'^\[hooks\.state\."((?:[^"\\]|\\.)*)"\]\s*$'
)


def _codex_home() -> pathlib.Path:
    """`$CODEX_HOME`, defaulting to `~/.codex` — Codex's own convention."""
    override = os.environ.get("CODEX_HOME")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".codex"


def _trusted_hook_keys_fallback(text: str) -> List[str]:
    """`[hooks.state."<key>"]` table names, for Python 3.9/3.10 without
    `tomllib`.

    Not a general TOML reader: `~/.codex/config.toml` mixes plugin config,
    MCP server settings and other tables this gatebound has no reason to parse,
    so a full parser would be scope creep for a dependency-free build. This
    reads exactly one shape — the table headers under `[hooks.state]` — and
    ignores everything else in the file, including whether those tables carry
    a real `trusted_hash` key; a header existing at all is Codex's own record
    that the approval flow ran for that hook.
    """
    keys = []
    for line in text.splitlines():
        m = _HOOKS_STATE_HEADER_RE.match(line)
        if not m:
            continue
        try:
            keys.append(_toml_unescape(m.group(1)))
        except ValueError:
            continue  # malformed escape: TOML rejects it, so this is no entry
    return keys


#: TOML basic-string escapes, one alternation so `\\u0041` reads as a
#: backslash followed by `u0041`, never as `\` + `A`.
_TOML_ESCAPE_RE = re.compile(r'\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|(.))')
_TOML_SIMPLE_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r",
                        '"': '"', "\\": "\\"}


def _toml_unescape(body: str) -> str:
    """Decode a TOML basic string's escapes, as `tomllib` would.

    Codex writes the hook path into the key; a path with non-ASCII characters
    can be spelled `\\uXXXX`, so reading only `\\"` and `\\\\` left a project
    under a non-ASCII home directory never matching its own trust entry.
    """
    def one(m: "re.Match[str]") -> str:
        code = m.group(1) or m.group(2)
        if code:
            point = int(code, 16)
            if 0xD800 <= point <= 0xDFFF or point > 0x10FFFF:
                raise ValueError("not a Unicode scalar value")
            return chr(point)
        if m.group(3) in _TOML_SIMPLE_ESCAPES:
            return _TOML_SIMPLE_ESCAPES[m.group(3)]
        raise ValueError("invalid escape")

    return _TOML_ESCAPE_RE.sub(one, body)


def _trusted_hook_keys(text: str) -> List[str]:
    """Every `hooks.state` key in *text*, via `tomllib` when available."""
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError):
            return []
        state = ((data.get("hooks") or {}).get("state") or {})
        return list(state) if isinstance(state, dict) else []
    return _trusted_hook_keys_fallback(text)


def codex_hooks_trusted(root: pathlib.Path) -> bool:
    """True when Codex has recorded trust for *this project's* `.codex/hooks.json`.

    ADR-0015. Codex tracks two kinds of trust separately: a project's own
    `trust_level`, and a per-hook `hooks.state."<hooks.json path>:<event>:*"`
    entry keyed by content hash. Only the second gates whether a hook actually
    fires — a trusted *project* with zero `hooks.state` entries for it (the
    real shape found on a fresh install) still has every project hook skipped
    silently. A malformed or unreadable config file, or no file at all, reads
    as **not trusted**: "could not tell" must never round to "trusted" here,
    the same rule the write gate itself applies to an unreadable task scope.
    """
    hooks_path = root / ".codex" / "hooks.json"
    if not hooks_path.is_file():
        return False
    config_path = _codex_home() / "config.toml"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False
    prefix = str(hooks_path.resolve()) + ":"
    return any(key.startswith(prefix) for key in _trusted_hook_keys(text))


def codex_plugin_cache(name: str) -> pathlib.Path:
    """Where Codex caches the plugin called *name* (one directory per version)."""
    return _codex_home() / "plugins" / "cache" / name / name


def codex_cached_names() -> List[str]:
    """The plugin's names that have at least one version in Codex's cache."""
    out = []
    for name in names.all_names():
        cache = codex_plugin_cache(name)
        try:
            if cache.is_dir() and any(p.is_dir() for p in cache.iterdir()):
                out.append(name)
        except OSError:
            continue
    return out


def codex_plugin_trust() -> Optional[bool]:
    """Whether Codex has recorded trust for an installed gatebound *plugin*.

    ADR-0019. ``None`` when no gatebound plugin is in Codex's plugin cache (the
    question does not arise). Otherwise ``True`` when some ``hooks.state``
    key names a ``hooks.json`` inside that cache, ``False`` when none does or
    the config cannot be read — "could not tell" is not "trusted".
    """
    cache = codex_plugin_cache(names.CURRENT)
    hook_files = sorted(cache.glob("*/hooks/hooks.json")) if cache.is_dir() else []
    if not hook_files:
        return None
    try:
        text = (_codex_home() / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    prefixes = []
    for hook_file in hook_files:
        prefixes.append(str(hook_file) + ":")
        prefixes.append(str(hook_file.resolve()) + ":")
    return any(key.startswith(tuple(prefixes)) for key in _trusted_hook_keys(text))


CODEX_PLUGIN_TRUST_FIX = (
    "open a terminal, run `codex`, type /hooks, review and trust the gatebound "
    "hooks, then start a new session"
)


def install(
    root: pathlib.Path,
    host: str,
    plugin_root: Optional[pathlib.Path] = None,
    dry_run: bool = False,
) -> dict:
    """Write the host layer into *root* and remove the skill directories a
    gatekit install left (:func:`stale_skill_dirs`). Returns ``{"host",
    "written": [rel paths], "removed": [rel paths]}``."""
    if host not in INSTALLABLE_HOSTS:
        if host == "claude":
            raise ValueError("Claude Code loads gatebound as a plugin; nothing to install into the project")
        raise ValueError("unknown host %r; installable hosts: %s" % (host, ", ".join(INSTALLABLE_HOSTS)))
    root = pathlib.Path(root)
    proot = pathlib.Path(plugin_root) if plugin_root else paths.plugin_root()
    planned: List[tuple] = []

    planned.append((root / ".codex" / "hooks.json", json.dumps(codex_hooks(proot), indent=2) + "\n"))

    for command in sorted((proot / "commands").glob("*.md")):
        name = command.stem
        body = command.read_text(encoding="utf-8")
        skill_dir = root / ".agents" / "skills" / ("%s-%s" % (names.CURRENT, name))
        description = _frontmatter_field(body, "description")
        planned.append((skill_dir / "SKILL.md", skill_shim(name, description)))
        planned.append((skill_dir / "command.md", rewrite_command(body, proot)))

    agents = root / "AGENTS.md"
    existing = agents.read_text(encoding="utf-8") if agents.is_file() else None
    planned.append((agents, merged_agents_md(existing, proot)))

    real_root = root.resolve()
    for path, _ in planned:
        # A symlinked .codex/ or .agents/ must not carry the layer outside the
        # project; resolve the deepest existing ancestor and check it.
        probe = path.parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            probe.resolve().relative_to(real_root)
        except ValueError:
            raise ValueError("%s resolves outside the project root; refusing to write" % path.relative_to(root))

    written: List[str] = []
    for path, content in planned:
        rel = path.relative_to(root).as_posix()
        written.append(rel)
        if dry_run:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        config.write_text_atomic(path, content)
    removed: List[str] = []
    for skill in stale_skill_dirs(root, proot):
        removed.append(skill.relative_to(root).as_posix())
        if dry_run:
            continue
        for leaf in ("SKILL.md", "command.md"):
            (skill / leaf).unlink()
        skill.rmdir()
    return {"host": host, "written": written, "removed": removed}


def status(root: pathlib.Path, host: str, plugin_root: Optional[pathlib.Path] = None) -> dict:
    """``{"verdict", "detail", "fix"}`` for the host layer in *root*.

    ``unverified`` when absent, ``fail`` when present but broken, ``ok`` when
    every registered gate script exists. Whether Codex actually loads the
    hooks depends on project trust, which is not readable from here.
    """
    root = pathlib.Path(root)
    proot = pathlib.Path(plugin_root) if plugin_root else paths.plugin_root()
    fix = 'python3 "%s" install --host %s' % (_launcher(proot), host)
    if host != "codex":
        return {"verdict": verdict.UNVERIFIED, "detail": "no host layer for %s" % host, "fix": ""}
    path = root / ".codex" / "hooks.json"
    if not path.is_file():
        return {"verdict": verdict.UNVERIFIED, "detail": ".codex/hooks.json absent", "fix": fix}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        groups = data["hooks"]
        commands = [h["command"] for group in groups.values() for entry in group for h in entry["hooks"]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"verdict": verdict.FAIL, "detail": ".codex/hooks.json unreadable: %s" % exc, "fix": fix}
    missing = []
    for command in commands:
        script = hook_script(command)
        if not script or not pathlib.Path(script).is_file():
            missing.append(script or command)
    if missing:
        return {"verdict": verdict.FAIL, "detail": "hook script missing: %s" % ", ".join(missing), "fix": fix}
    skills = root / ".agents" / "skills"
    count = len([p for p in skills.glob(names.CURRENT + "-*/command.md")]) if skills.is_dir() else 0
    return {
        "verdict": verdict.OK,
        "detail": "%d hook commands, %d skills; whether Codex loads project hooks depends on trusting .codex/ (not checkable here)"
        % (len(commands), count),
        "fix": "",
    }


def run(argv: List[str]) -> int:
    """``python3 -m gatebound install --host codex [--root PATH] [--dry-run]``."""
    parser = argparse.ArgumentParser(prog="gatebound install", add_help=True)
    parser.add_argument("--host", required=True, help="host to generate a layer for (%s)" % ", ".join(INSTALLABLE_HOSTS))
    parser.add_argument("--root", default=None, help="project root (default: detected)")
    parser.add_argument("--dry-run", action="store_true", help="list the files without writing")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 2)
    root = pathlib.Path(args.root).expanduser() if args.root else paths.project_root()
    try:
        result = install(root, args.host, dry_run=args.dry_run)
    except ValueError as exc:
        print("gatebound install: %s" % exc, file=sys.stderr)
        return 2
    verb = "would write" if args.dry_run else "wrote"
    print("%s %d files for host %s under %s" % (verb, len(result["written"]), args.host, root))
    for rel in result["written"]:
        print("  " + rel)
    for rel in result.get("removed", []):
        print("  %s %s/ (left by gatekit)" % ("would remove" if args.dry_run else "removed", rel))
    if not args.dry_run:
        print("next: trust this project's .codex/ layer in Codex, then start a new Codex session.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run(sys.argv[1:]))
