"""PreToolUse gate for the Skill tool — a gatebound skill may arm the Stop gate.

ADR-0032. A typed ``/gatebound:build`` or ``/gatebound:verify`` sets
``active_pipeline`` through the prompt gate and rearms the Stop gate
(ADR-0024). The same command started through the Skill tool — the model
continuing into ``/gatebound:verify``, or a trigger skill loaded by "빌드
시작해줘" — used to leave the Stop gate idle, because only the prompt gate
wrote the pipeline.

Here a gatebound skill naming ``build`` or ``verify`` does what the typed
command does. Every other skill leaves the pipeline alone: through a tool call
the model may start the gate's judging, never stop it or move a running build
to a pipeline the Stop gate does not judge. Clearing and switching stay the
user's, through a typed command. Never denies; exits 0 on any error.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

if __name__ == "__main__" or __package__ in (None, ""):  # pragma: no cover
    from _bootstrap import ensure_package_path

    ensure_package_path()
else:
    from ._bootstrap import ensure_package_path

    ensure_package_path()

from gatebound import hookio, ledger, names, paths  # noqa: E402

#: The only commands a skill may act on: the ones that arm the Stop gate.
ARMING_COMMANDS = ("build", "verify")


def skill_command(skill: Any) -> Optional[str]:
    """The gatebound command a Skill tool ``skill`` value names, lowered —
    ``gatebound:verify`` and the trigger skill ``gatebound:gatebound-verify`` both
    give ``verify``, under any of the plugin's names (ADR-0029) — else None."""
    if not isinstance(skill, str) or ":" not in skill:
        return None
    plugin, _, name = skill.strip().lower().partition(":")
    if plugin not in names.all_names() or not name:
        return None
    for prefix in names.all_names():
        if name.startswith(prefix + "-"):
            return name[len(prefix) + 1:] or None
    return name


def handle(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    root = hookio.event_root(event)
    # A project with no state directory never asked gatebound to govern it.
    if not paths.state_dir(root).is_dir():
        return hookio.allow()
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    name = skill_command(tool_input.get("skill"))
    if name not in ARMING_COMMANDS:
        return hookio.allow()
    led = ledger.Ledger.load(root, hookio.session_id(event))
    led.set_pipeline(name, source="skill")
    led.rearm_stop()
    led.save()
    return hookio.allow()


def main() -> None:  # pragma: no cover - exercised via subprocess tests
    hookio.run(handle)


if __name__ == "__main__":  # pragma: no cover
    main()
