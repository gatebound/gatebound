"""ADR-0019 decision 2: the same plugin/ tree installs as a Codex plugin."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import doctor, hookio, hosts, verdict  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


def plugin_hooks() -> dict:
    return json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))


def matcher_for(event: str, script: str) -> str:
    for entry in plugin_hooks()["hooks"][event]:
        if any(script in h["command"] for h in entry["hooks"]):
            return entry.get("matcher", "")
    raise AssertionError("%s not registered on %s" % (script, event))


class TestHooksServeCodexTools(unittest.TestCase):
    """2a: Codex's own tool names reach the same gates."""

    def test_write_gate_sees_apply_patch(self) -> None:
        self.assertIn("apply_patch", matcher_for("PreToolUse", "gates/write.py").split("|"))

    def test_spawn_gate_sees_codex_spawn(self) -> None:
        self.assertIn(
            "collaborationspawn_agent", matcher_for("PreToolUse", "gates/spawn.py").split("|")
        )

    def test_claude_tool_names_kept(self) -> None:
        self.assertIn("Write", matcher_for("PreToolUse", "gates/write.py").split("|"))
        self.assertIn("Agent", matcher_for("PreToolUse", "gates/spawn.py").split("|"))


class TestHostFromEnvironment(unittest.TestCase):
    """2b: with no --host flag, Codex is recognised by PLUGIN_ROOT."""

    def test_plugin_root_env_means_codex(self) -> None:
        self.assertEqual(hookio.host_from_argv([], env={"PLUGIN_ROOT": "/p"}), "codex")

    def test_claude_env_means_claude(self) -> None:
        self.assertEqual(hookio.host_from_argv([], env={"CLAUDE_PLUGIN_ROOT": "/p"}), "claude")

    def test_flag_beats_environment(self) -> None:
        self.assertEqual(
            hookio.host_from_argv(["--host", "claude"], env={"PLUGIN_ROOT": "/p"}), "claude"
        )

    def test_empty_plugin_root_is_not_evidence(self) -> None:
        self.assertEqual(hookio.host_from_argv([], env={"PLUGIN_ROOT": ""}), "claude")


class TestHostNeutralSkills(unittest.TestCase):
    """2c: every shim tells a host without slash commands where the command is."""

    def commands(self) -> list:
        return sorted(p.stem for p in (PLUGIN_DIR / "commands").glob("*.md"))

    def test_every_command_has_a_skill(self) -> None:
        skills = {p.name for p in (PLUGIN_DIR / "skills").iterdir() if p.is_dir()}
        self.assertEqual(skills, {"gatebound-" + c for c in self.commands()})

    def test_shim_names_the_command_file_relative_to_the_plugin(self) -> None:
        for name in self.commands():
            text = (PLUGIN_DIR / "skills" / ("gatebound-" + name) / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("`/gatebound:%s`" % name, text, name)
            self.assertIn("commands/%s.md" % name, text, name)
            self.assertIn("policy/codex.md", text, name)
            self.assertLessEqual(len(text.splitlines()), 40, name)

    def test_codex_policy_exists_and_covers_the_differences(self) -> None:
        text = (PLUGIN_DIR / "policy" / "codex.md").read_text(encoding="utf-8")
        for needle in ("${CLAUDE_PLUGIN_ROOT}", "AskUserQuestion", "$gatebound-", "/hooks"):
            self.assertIn(needle, text)


class TestDoctorReportsCodexPluginTrust(unittest.TestCase):
    """2d: an installed Codex plugin whose hooks are untrusted is a visible warn."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(os.path.realpath(self._tmp.name))
        self.codex_home = base / "codex-home"
        self.root = base / "project"
        (self.root / ".gatebound").mkdir(parents=True)
        self._old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self._old
        self._tmp.cleanup()

    def install_plugin(self) -> pathlib.Path:
        hooks = self.codex_home / "plugins" / "cache" / "gatebound" / "gatebound" / "9.9.9" / "hooks" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_text("{}", encoding="utf-8")
        return hooks

    def write_config(self, text: str) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.codex_home / "config.toml").write_text(text, encoding="utf-8")

    def test_no_codex_plugin_is_not_a_finding(self) -> None:
        self.assertIsNone(hosts.codex_plugin_trust())

    def test_installed_but_untrusted_warns_with_terminal_fix(self) -> None:
        self.install_plugin()
        self.write_config("[plugins.\"gatebound@gatebound\"]\nenabled = true\n")
        result = doctor.axis_host_layer(self.root)
        self.assertEqual(result["verdict"], verdict.WARN)
        self.assertIn("/hooks", result["fix"])

    def test_installed_and_trusted_is_ok(self) -> None:
        hooks = self.install_plugin()
        self.write_config(
            '[hooks.state.%s]\ntrusted_hash = "abc"\n' % json.dumps(str(hooks) + ":pre_tool_use:0:0")
        )
        self.assertTrue(hosts.codex_plugin_trust())
        self.assertEqual(doctor.axis_host_layer(self.root)["verdict"], verdict.OK)


    # Codex 0.157 records a plugin hook's trust under the plugin's id, not the
    # cached hooks.json path (seen on the owner's Mac, 2026-10-10): doctor kept
    # warning "not trusted" after the user had trusted every hook.
    def trust_key(self, key: str) -> None:
        self.write_config('[hooks.state.%s]\ntrusted_hash = "abc"\n' % json.dumps(key))

    def test_plugin_id_key_is_trusted(self) -> None:
        self.install_plugin()
        self.trust_key("gatebound@gatebound:hooks/hooks.json:pre_tool_use:0:0")
        self.assertTrue(hosts.codex_plugin_trust())
        self.assertEqual(doctor.axis_host_layer(self.root)["verdict"], verdict.OK)

    def test_plugin_id_from_another_marketplace_does_not_count(self) -> None:
        # Only gatebound@gatebound is what Codex's cache/gatebound/gatebound holds.
        self.install_plugin()
        self.trust_key("gatebound@team-tools:hooks/hooks.json:stop:0:0")
        self.assertFalse(hosts.codex_plugin_trust())

    def test_another_plugins_id_is_not_trusted(self) -> None:
        self.install_plugin()
        for key in ("other@gatebound:hooks/hooks.json:stop:0:0",
                    "gateboundx@gatebound:hooks/hooks.json:stop:0:0",
                    "gatebound@gatebound:other/hooks.json:stop:0:0"):
            self.trust_key(key)
            self.assertFalse(hosts.codex_plugin_trust(), key)


    # ADR-0040 review of the fix: every hook Codex runs must be trusted, not one.
    HOOKS = {"hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "a"}]},
                       {"matcher": "Agent", "hooks": [{"type": "command", "command": "b"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "c"}]}],
        "PostToolUseFailure": [{"matcher": "Agent", "hooks": [{"type": "command", "command": "d"}]}],
    }}
    ALL = ("pre_tool_use:0:0", "pre_tool_use:1:0", "stop:0:0")

    def install_real_hooks(self) -> pathlib.Path:
        hooks = self.install_plugin()
        hooks.write_text(json.dumps(self.HOOKS), encoding="utf-8")
        return hooks

    def trust(self, *suffixes: str, extra: str = "") -> None:
        self.write_config("".join(
            '[hooks.state.%s]\ntrusted_hash = "abc"\n%s\n'
            % (json.dumps("gatebound@gatebound:hooks/hooks.json:" + sfx), extra) for sfx in suffixes))

    def test_every_codex_hook_trusted_is_ok(self) -> None:
        self.install_real_hooks()
        self.trust(*self.ALL)
        self.assertTrue(hosts.codex_plugin_trust())
        result = doctor.axis_host_layer(self.root)
        self.assertEqual(result["verdict"], verdict.OK)
        self.assertIn("/hooks", result["detail"])  # says how to renew after an upgrade

    def test_partial_trust_warns_with_counts(self) -> None:
        self.install_real_hooks()
        self.trust("stop:0:0")
        self.assertFalse(hosts.codex_plugin_trust())
        result = doctor.axis_host_layer(self.root)
        self.assertEqual(result["verdict"], verdict.WARN)
        self.assertIn("1 of 3", result["detail"])

    def test_absolute_path_form_still_counts_per_hook(self) -> None:
        hooks = self.install_real_hooks()
        self.write_config("".join(
            '[hooks.state.%s]\ntrusted_hash = "abc"\n\n' % json.dumps(str(hooks) + ":" + sfx)
            for sfx in self.ALL))
        self.assertTrue(hosts.codex_plugin_trust())

    @unittest.skipIf(hosts.tomllib is None, "the 3.9/3.10 reader sees table headers only")
    def test_entry_without_hash_or_disabled_is_not_trust(self) -> None:
        self.install_real_hooks()
        self.write_config(
            '[hooks.state."gatebound@gatebound:hooks/hooks.json:pre_tool_use:0:0"]\nenabled = true\n\n'
            '[hooks.state."gatebound@gatebound:hooks/hooks.json:pre_tool_use:1:0"]\n'
            'trusted_hash = "abc"\nenabled = false\n\n'
            '[hooks.state."gatebound@gatebound:hooks/hooks.json:stop:0:0"]\ntrusted_hash = "abc"\n')
        self.assertFalse(hosts.codex_plugin_trust())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
