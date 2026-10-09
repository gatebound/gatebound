#!/usr/bin/env python3
"""test_tools.py — fault-injection tests for the tools/gate_*.py CI gates.

Each test builds a minimal, throwaway repo tree under a TemporaryDirectory,
injects exactly one fault the corresponding gate is supposed to catch, and
asserts the gate exits 1 with a finding that mentions the fault. A second
test per gate builds a clean tree and asserts exit 0. This is the CI gate
for the gates themselves: if a gate's logic regresses, one of these should
fail before it reaches main.

Run directly:
    python3 tools/test_tools.py -v

Or via the aggregate runner:
    python3 tools/run_tests.py
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent


def run_gate(script: str, root: pathlib.Path, extra_args: list[str] | None = None,
             json_output: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(TOOLS_DIR / script), "--root", str(root)]
    if json_output:
        cmd.append("--json")
    if extra_args:
        cmd.extend(extra_args)
    # A gate prints UTF-8 on any console; read it as UTF-8, not the locale.
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30, env=env)


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def minimal_clean_repo(root: pathlib.Path) -> None:
    """A tree with the minimum structure every gate expects to find clean."""
    write(root / ".claude-plugin" / "marketplace.json", json.dumps({
        "name": "gatebound",
        "plugins": [{"name": "gatebound", "source": "./plugin"}],
    }))
    write(root / "plugin" / ".claude-plugin" / "plugin.json", json.dumps({
        "name": "gatebound",
        "version": "0.1.0",
        "commands": "./commands",
        "skills": "./skills",
    }))
    write(root / "plugin" / "hooks" / "hooks.json", json.dumps({
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/gatebound/gates/stop.py"'}]}]
        }
    }))
    write(root / "plugin" / "gatebound" / "gates" / "stop.py", "# stop gate\n")
    write(root / "plugin" / "bin" / "gatebound.py", "# launcher\n")
    write(root / "plugin" / "gatebound" / "cli.py", 'SUBCOMMANDS = {\n    "doctor": ("gatebound.doctor", "x"),\n    "spec": ("gatebound.spec", "x"),\n}\n')
    write(root / "plugin" / "commands" / "build.md", (
        "---\nallowed-tools: Read, Bash\n---\n"
        "# /gatebound:build\n\nSee policy/verification.md. Output follows output_lang.\n"
    ))
    write(root / "plugin" / "skills" / "build" / "SKILL.md", (
        "---\nallowed-tools: Read\nuser-invocable: false\n---\n# build trigger\nSee the build command.\n"
    ))
    write(root / "CHANGELOG.md", "# Changelog\n\n## 0.1.0 — 2026-09-10\n\n- initial\n")
    write(root / "README.md", "# gatebound\n\nCommands: /gatebound:build\n")
    write(root / "README.ko.md", "# gatebound\n\n명령어: /gatebound:build\n")


class TestNoAbsPaths(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_no_abs_paths.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_abs_path_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "notes.md", "see /Users/alice/project/file.txt for details\n")
            proc = run_gate("gate_no_abs_paths.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("notes.md" in f["path"] for f in payload["findings"]))

    def test_windows_style_path_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "win.md", r"path: C:\Users\bob\file.txt" + "\n")
            proc = run_gate("gate_no_abs_paths.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_own_fixtures_are_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "tools" / "tests" / "fixtures" / "abs_path.txt", "/Users/alice/x\n")
            proc = run_gate("gate_no_abs_paths.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestSkillSize(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_oversized_skill_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            body = "---\nallowed-tools: Read\n---\n" + "\n".join(f"line {i}" for i in range(50))
            write(root / "plugin" / "skills" / "big" / "SKILL.md", body)
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("big/SKILL.md" in f["path"] for f in payload["findings"]))

    def test_oversized_command_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            body = "---\nallowed-tools: Read\n---\n" + "\n".join(f"line {i}" for i in range(200))
            write(root / "plugin" / "commands" / "huge.md", body)
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_ask_user_question_inline_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "commands" / "asks.md",
                "---\nallowed-tools: Read, AskUserQuestion, Bash\n---\n# cmd\n",
            )
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("AskUserQuestion" in f["message"] for f in payload["findings"]))

    def test_ask_user_question_block_list_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "skills" / "asks" / "SKILL.md",
                "---\nallowed-tools:\n  - Read\n  - AskUserQuestion\n---\n# trigger\n",
            )
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("AskUserQuestion" in f["message"] for f in payload["findings"]))


    def test_shim_duplicating_a_command_without_user_invocable_false_is_detected(self) -> None:
        # ADR-0026 D2: a shim shown next to its command doubles the slash menu.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "verify.md", "---\nallowed-tools: Read\n---\n# verify\n")
            write(root / "plugin" / "skills" / "gatebound-verify" / "SKILL.md",
                  "---\nname: gatebound-verify\ndescription: x\n---\n# trigger\n")
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("gatebound-verify/SKILL.md" in f["path"]
                                and "user-invocable" in f["message"] for f in payload["findings"]))

    def test_user_invocable_outside_the_frontmatter_does_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "skills" / "build" / "SKILL.md",
                  "---\nname: gatebound-build\n---\nuser-invocable: false\n")
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_shim_is_found_by_its_frontmatter_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "skills" / "anything" / "SKILL.md",
                  "---\nname: gatebound-build\ndescription: x\n---\n# trigger\n")
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_skill_whose_name_only_ends_in_a_command_may_stay_in_the_menu(self) -> None:
        # Review of 0.16.7: `design-gate` is not the shim of `gate`.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "gate.md", "---\nallowed-tools: Read\n---\n# gate\n")
            write(root / "plugin" / "skills" / "gatebound-gate" / "SKILL.md",
                  "---\nname: gatebound-gate\nuser-invocable: false\n---\n# trigger\n")
            write(root / "plugin" / "skills" / "design-gate" / "SKILL.md",
                  "---\nname: design-gate\ndescription: x\n---\n# design gate\n")
            write(root / "plugin" / "skills" / "gatebound-design-gate" / "SKILL.md",
                  "---\ndescription: x\n---\n# no name, folder is not a command's shim\n")
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_skill_without_a_command_may_stay_in_the_menu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "skills" / "helper" / "SKILL.md",
                  "---\nname: helper\ndescription: x\n---\n# helper\n")
            proc = run_gate("gate_skill_size.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestBlobSize(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_blob_size.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_oversized_blob_via_sparse_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            big = root / "assets" / "big.bin"
            big.parent.mkdir(parents=True, exist_ok=True)
            with big.open("wb") as fh:
                fh.seek(1024 * 1024 + 1)
                fh.write(b"\0")
            proc = run_gate("gate_blob_size.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("big.bin" in f["path"] for f in payload["findings"]))


class TestForbiddenPhrases(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_forbidden_phrases.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_execute_immediately_in_skill_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "skills" / "bad" / "SKILL.md",
                "---\nallowed-tools: Read\n---\nEXECUTE IMMEDIATELY when this triggers.\n",
            )
            proc = run_gate("gate_forbidden_phrases.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_step_one_in_skill_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "skills" / "bad2" / "SKILL.md",
                "---\nallowed-tools: Read\n---\nStep 1: do the thing\n",
            )
            proc = run_gate("gate_forbidden_phrases.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_command_missing_policy_reference_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "commands" / "nopolicy.md",
                "---\nallowed-tools: Read\n---\n# /gatebound:nopolicy\n\nOutput follows output_lang.\n",
            )
            proc = run_gate("gate_forbidden_phrases.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("policy/" in f["message"] for f in payload["findings"]))

    def test_command_missing_output_lang_reference_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(
                root / "plugin" / "commands" / "nolang.md",
                "---\nallowed-tools: Read\n---\n# /gatebound:nolang\n\nSee policy/verification.md.\n",
            )
            proc = run_gate("gate_forbidden_phrases.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("output_lang" in f["message"] for f in payload["findings"]))


class TestManifest(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_missing_hook_script_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            (root / "plugin" / "gatebound" / "gates" / "stop.py").unlink()
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("stop.py" in f["message"] for f in payload["findings"]))

    def test_empty_hook_script_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "gatebound" / "gates" / "stop.py", "")
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_version_mismatch_with_changelog_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "CHANGELOG.md", "# Changelog\n\n## 0.2.0 — 2026-09-11\n\n- newer\n")
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("0.2.0" in f["message"] for f in payload["findings"]))

    def test_non_semver_version_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            plugin_json_path = root / "plugin" / ".claude-plugin" / "plugin.json"
            data = json.loads(plugin_json_path.read_text())
            data["version"] = "v1"
            write(plugin_json_path, json.dumps(data))
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_invalid_json_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "hooks" / "hooks.json", "{not valid json")
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_missing_marketplace_source_dir_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / ".claude-plugin" / "marketplace.json", json.dumps({
                "name": "gatebound",
                "plugins": [{"name": "gatebound", "source": "./nonexistent"}],
            }))
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)


class TestReadmeSync(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_readme_sync.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_readme_missing_a_command_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "verify.md", (
                "---\nallowed-tools: Read\n---\n# /gatebound:verify\n\nSee policy/. output_lang applies.\n"
            ))
            # README.md not updated with the new command.
            proc = run_gate("gate_readme_sync.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("verify" in f["message"] for f in payload["findings"]))

    def test_readme_and_ko_readme_mismatch_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "doctor.md", (
                "---\nallowed-tools: Read\n---\n# /gatebound:doctor\n\nSee policy/. output_lang applies.\n"
            ))
            write(root / "README.md", "# gatebound\n\nCommands: /gatebound:build /gatebound:doctor\n")
            # README.ko.md not updated with /gatebound:doctor.
            proc = run_gate("gate_readme_sync.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_readme_extra_command_not_shipped_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "README.md", "# gatebound\n\nCommands: /gatebound:build /gatebound:ghost\n")
            proc = run_gate("gate_readme_sync.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(any("ghost" in f["message"] for f in payload["findings"]))


class TestCommandInvocations(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "doctor.md",
                  '---\nallowed-tools: Bash\n---\nRun `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" doctor`. policy/ output_lang\n')
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_module_form_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "x.md", "python3 -m gatebound doctor\n")
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("launcher", proc.stdout)

    def test_module_form_in_a_spec_template_is_rejected(self) -> None:
        # Review of 0.16.3: templates/ko/RECOVERY.md told the user to run
        # `python3 -m gatebound contract run`, which does not run from a project.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "spec-kit" / "templates" / "ko" / "RECOVERY.md",
                  "6. 다시 실행한다. `python3 -m gatebound contract run`.\n")
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("templates/ko/RECOVERY.md", proc.stdout)

    def test_unregistered_subcommand_in_a_spec_template_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "spec-kit" / "templates" / "en" / "05-gate.md",
                  '| x | `python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" frobnicate` |\n')
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("frobnicate", proc.stdout)

    def test_cd_into_plugin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "x.md",
                  'cd "${CLAUDE_PLUGIN_ROOT}" && python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" doctor\n')
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1)

    def test_unregistered_subcommand_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "plugin" / "commands" / "x.md",
                  'python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" frobnicate\n')
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("frobnicate", proc.stdout)

    def test_missing_launcher_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            (root / "plugin" / "bin" / "gatebound.py").unlink()
            proc = run_gate("gate_command_invocations.py", root)
            self.assertEqual(proc.returncode, 1)


class TestManifestHooksDuplicate(unittest.TestCase):
    def test_duplicate_hooks_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            pj = root / "plugin" / ".claude-plugin" / "plugin.json"
            data = json.loads(pj.read_text())
            data["hooks"] = "./hooks/hooks.json"
            pj.write_text(json.dumps(data))
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertIn("loaded automatically", proc.stdout)

    def test_missing_standard_hooks_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            (root / "plugin" / "hooks" / "hooks.json").unlink()
            proc = run_gate("gate_manifest.py", root)
            self.assertEqual(proc.returncode, 1, proc.stdout)


class TestManualAccuracy(unittest.TestCase):
    def _manual_repo(self, root: pathlib.Path) -> None:
        minimal_clean_repo(root)
        write(root / "plugin" / "spec-kit" / "templates" / "ko" / "01-prd.md", "# prd\n")
        write(root / "docs" / "manual" / "00-index.md",
              "# index\n\n- [소개](01-intro.md)\n")
        write(root / "docs" / "manual" / "01-intro.md",
              '# intro\n\n`python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" doctor`\n\n/gatebound:build\n\n01-prd.md\n')

    def test_clean_manual_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_module_form_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            write(root / "docs" / "manual" / "01-intro.md", "# intro\n\npython3 -m gatebound doctor\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("launcher", proc.stdout)

    def test_unknown_subcommand_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            write(root / "docs" / "manual" / "01-intro.md",
                  '# intro\n\n`python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" frobnicate`\n')
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("frobnicate", proc.stdout)

    def test_unknown_slash_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            write(root / "docs" / "manual" / "01-intro.md", "# intro\n\n/gatebound:nosuch\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)

    def test_broken_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            write(root / "docs" / "manual" / "00-index.md", "# index\n\n- [x](01-intro.md)\n- [y](99-gone.md)\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("99-gone.md", proc.stdout)

    def test_unlinked_page_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            write(root / "docs" / "manual" / "02-orphan.md", "# orphan\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("02-orphan.md", proc.stdout)

    def _english(self, root: pathlib.Path) -> None:
        write(root / "docs" / "manual" / "en" / "00-index.md",
              "# index\n\n- [Intro](01-intro.md)\n")
        write(root / "docs" / "manual" / "en" / "01-intro.md",
              '# intro\n\n`python3 "${CLAUDE_PLUGIN_ROOT}/bin/gatebound.py" doctor`\n')

    def test_english_manual_mirroring_every_page_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            self._english(root)
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_korean_page_without_an_english_one_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            self._english(root)
            write(root / "docs" / "manual" / "02-more.md", "# more\n")
            write(root / "docs" / "manual" / "00-index.md",
                  "# index\n\n- [소개](01-intro.md)\n- [더](02-more.md)\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/manual/en/02-more.md", proc.stdout)

    def test_english_page_without_a_korean_one_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            self._english(root)
            write(root / "docs" / "manual" / "en" / "02-extra.md", "# extra\n")
            write(root / "docs" / "manual" / "en" / "00-index.md",
                  "# index\n\n- [Intro](01-intro.md)\n- [Extra](02-extra.md)\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/manual/02-extra.md", proc.stdout)

    def test_english_pages_get_the_same_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._manual_repo(root)
            self._english(root)
            write(root / "docs" / "manual" / "en" / "01-intro.md", "# intro\n\n/gatebound:nosuch\n")
            proc = run_gate("gate_manual_accuracy.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/manual/en/01-intro.md", proc.stdout)


class TestCleanRoom(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = run_gate("gate_clean_room.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_foreign_project_name_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "manual" / "01-intro.md", "# intro\n\ngptaku 에서 영감을 받았다\n")
            proc = run_gate("gate_clean_room.py", root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("gptaku", proc.stdout)

    def test_korean_plugin_name_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "note.md", "# note\n\n품앗이 방식의 병렬 위임\n")
            proc = run_gate("gate_clean_room.py", root)
            self.assertEqual(proc.returncode, 1)

    def test_detection_is_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "note.md", "See Insane-Search for the ladder.\n")
            proc = run_gate("gate_clean_room.py", root)
            self.assertEqual(proc.returncode, 1)

    def test_ordinary_words_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            write(root / "docs" / "note.md",
                  "# note\n\nadded a note, ddl handling, gaseous mixtures, nopalito\n")
            proc = run_gate("gate_clean_room.py", root)
            self.assertEqual(proc.returncode, 0, proc.stdout)


class TestConsoleEncoding(unittest.TestCase):
    """A gate's findings print on any console.

    Observed on a Korean Windows host: gate_clean_room's message carries an
    em dash, cp949 cannot encode it, and the gate died with UnicodeEncodeError
    mid-print — exit 1 as if it had judged, with the finding lost. Forcing the
    child's stdio to ascii stands in for cp949 or cp1252 on any runner, and
    is stricter: it rejects Hangul paths too.
    """

    NARROW = {**os.environ, "PYTHONIOENCODING": "ascii"}

    def _foreign_name(self, root: pathlib.Path) -> None:
        minimal_clean_repo(root)
        write(root / "docs" / "매뉴얼" / "01-intro.md", "# intro\n\ngptaku 에서 영감을 받았다\n")

    def test_a_json_finding_prints_on_a_narrow_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._foreign_name(root)
            proc = run_gate("gate_clean_room.py", root, env=self.NARROW)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(proc.returncode, 1)
            finding = json.loads(proc.stdout)["findings"][0]
            self.assertEqual(finding["path"], "docs/매뉴얼/01-intro.md")
            self.assertIn("— describe it", finding["message"])

    def test_a_text_finding_prints_on_a_narrow_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._foreign_name(root)
            proc = run_gate("gate_clean_room.py", root, json_output=False, env=self.NARROW)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("docs/매뉴얼/01-intro.md:3: foreign project name 'gptaku' —", proc.stdout)

    def test_every_gate_sets_a_utf8_console(self) -> None:
        # Every gate prints a finding's path and message, either of which can
        # be non-ASCII; none may rely on the console's code page.
        gates = sorted(TOOLS_DIR.glob("gate_*.py"))
        self.assertTrue(gates)
        missing = [g.name for g in gates
                   if "console.utf8_stdio()" not in g.read_text(encoding="utf-8")]
        self.assertEqual(missing, [], "gates that do not call console.utf8_stdio()")


INSTALLER = REPO_ROOT / "install" / "install.ps1"
POWERSHELL = pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class TestInstallerScript(unittest.TestCase):
    """ADR-0033: the installer exists, and its test seams cannot steer a real run."""

    def source(self) -> str:
        self.assertTrue(INSTALLER.is_file(), INSTALLER)
        return INSTALLER.read_text(encoding="utf-8")

    def test_the_installer_is_where_the_documented_url_points(self) -> None:
        self.assertTrue(INSTALLER.is_file(), INSTALLER)

    def test_the_installer_is_ascii(self) -> None:
        # PowerShell 5.1 reads a BOM-less file in the ANSI code page, and a
        # BOM breaks `irm | iex` (the first command is no longer recognised):
        # only ASCII reads the same both ways. Korean text is \u-escaped.
        bad = [(n, ln) for n, ln in enumerate(self.source().splitlines(), 1) if not ln.isascii()]
        self.assertEqual(bad[:3], [], "non-ASCII lines in install.ps1")

    def test_the_installer_never_exits_a_piped_session(self) -> None:
        # Under `irm | iex` an `exit` closes the user's PowerShell window.
        import re
        exits = [ln.strip() for ln in self.source().splitlines()
                 if re.match(r"\s*exit\b", ln) or re.search(r"[;{]\s*exit\b", ln)]
        self.assertEqual(exits, ["if ($PSCommandPath) { exit $code }"], exits)

    def test_the_seams_are_read_only_under_dry_run(self) -> None:
        # Every GATEBOUND_INSTALL_* value goes through Get-Seam, whose first
        # statement returns nothing unless -DryRun is set. A real run is never
        # exercised here: a regression would install on the test machine.
        import re
        src = self.source()
        self.assertEqual(src.count("GATEBOUND_INSTALL_"), 1, "seam names read outside Get-Seam")
        body = re.search(r"function Get-Seam\b[^{]*\{(.*?)\n\}", src, re.S)
        self.assertIsNotNone(body, "no Get-Seam function")
        first = [ln.strip() for ln in body.group(1).splitlines() if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(first and first[1 if first[0].startswith("param") else 0].startswith("if (-not $DryRun)"),
                        "Get-Seam must return early unless -DryRun")
        self.assertIn("GATEBOUND_INSTALL_", body.group(1))


@unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "the installer runs on Windows PowerShell")
class TestInstallerPlan(unittest.TestCase):
    """ADR-0033: what `install.ps1 -DryRun` decides, against a stubbed machine.

    Each test builds a fake profile and PATH out of `.cmd` stubs — the Store
    placeholder prints `Python` and exits 49 (ADR-0030), a real Python
    forwards to this interpreter — and reads the plan as JSON. Nothing is
    installed and no real environment value is written: the test seams
    (`GATEBOUND_INSTALL_*`) stand in for the profile, the user and machine
    PATH, elevation and the user's PYTHONUTF8, and only under `-DryRun`.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.home = self.root / "home"
        self.windowsapps = self.home / "AppData" / "Local" / "Microsoft" / "WindowsApps"
        self.realpy = self.root / "Python312"
        self.gitdir = self.root / "Git" / "cmd"
        self.wingetdir = self.root / "winget"
        self.localbin = self.home / ".local" / "bin"
        self.system32 = pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        for d in (self.windowsapps, self.realpy, self.gitdir, self.wingetdir, self.localbin):
            d.mkdir(parents=True)
        # The Store placeholder: `Python` with no newline, exit 49.
        for name in ("python", "python3"):
            self.stub(self.windowsapps / name, "<nul set /p=Python\r\nexit /b 49")
        self.stub(self.wingetdir / "winget", "echo v1.9.0")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def stub(self, path: pathlib.Path, body: str) -> None:
        # cmd.exe reads a batch file in the OEM code page; sys.executable may
        # sit under a Korean user folder.
        path.with_suffix(".cmd").write_text("@echo off\r\n" + body + "\r\n", encoding="oem")

    def real_python(self) -> None:
        for name in ("python", "python3"):
            self.stub(self.realpy / name, '"%s" %%*' % sys.executable)

    def git(self) -> None:
        self.stub(self.gitdir / "git", "echo git version 2.56.0.windows.1")

    def claude(self) -> None:
        self.stub(self.localbin / "claude", "echo 2.1.289 (Claude Code)")

    def gatebound_installed(self) -> None:
        plugins = self.home / ".claude" / "plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        (plugins / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"gatebound@gatebound": [{"version": "0.16.10"}]}}), encoding="utf-8")

    def plan(self, user_path: list, extra: list | None = None, env: dict | None = None, lang: str = "en"):
        dirs = [str(d) for d in user_path]
        child = {k: v for k, v in os.environ.items() if not k.startswith("GATEBOUND_INSTALL_")}
        child.pop("PYTHONUTF8", None)
        child["PATH"] = ";".join([str(self.system32)] + dirs)
        child.update({
            "GATEBOUND_INSTALL_HOME": str(self.home),
            "GATEBOUND_INSTALL_USER_PATH": ";".join(dirs),
            "GATEBOUND_INSTALL_MACHINE_PATH": str(self.system32),
            "GATEBOUND_INSTALL_ELEVATED": "0",
            "GATEBOUND_INSTALL_USER_PYTHONUTF8": "",
        })
        child.update(env or {})
        cmd = [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-File", str(INSTALLER), "-DryRun", "-Json", "-Lang", lang] + (extra or [])
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, env=child)
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            self.fail("no JSON plan (exit %s)\nstdout: %s\nstderr: %s" % (proc.returncode, proc.stdout, proc.stderr))
        return proc, data

    @staticmethod
    def rows(data: dict, item: str) -> list:
        return [r for r in data["rows"] if r["item"] == item]

    def row(self, data: dict, item: str) -> dict:
        found = self.rows(data, item)
        self.assertEqual(len(found), 1, (item, data["rows"]))
        return found[0]

    def test_a_bare_machine_plans_every_install(self) -> None:
        proc, data = self.plan([self.windowsapps, self.wingetdir])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(data["dry_run"])
        for item, needle in (("git", "Git.Git"), ("python", "Python.Python.3.12"),
                             ("claude", "claude.ai/install.ps1")):
            row = self.row(data, item)
            self.assertEqual(row["action"], "install", row)
            self.assertIn(needle, row["detail"])
            # Planned, not done: never reported as a pass.
            self.assertEqual(row["verdict"], "unverified", row)
        self.assertEqual(self.row(data, "gatebound")["action"], "install")
        self.assertEqual(self.row(data, "pythonutf8")["action"], "set")

    def test_the_store_placeholder_is_not_a_python(self) -> None:
        # Only the placeholder is on PATH: it must not satisfy the Python row.
        _, data = self.plan([self.windowsapps, self.wingetdir])
        row = self.row(data, "python")
        self.assertEqual(row["action"], "install")
        self.assertIn("WindowsApps", row["detail"])

    def test_a_python_behind_the_placeholder_is_moved_in_front(self) -> None:
        self.real_python()
        _, data = self.plan([self.windowsapps, self.realpy, self.wingetdir])
        self.assertEqual(self.row(data, "python")["action"], "skip")
        prepends = [r for r in self.rows(data, "path") if r["action"] == "prepend"]
        self.assertEqual(len(prepends), 1, data["rows"])
        self.assertIn(str(self.realpy), prepends[0]["detail"])

    def test_a_python_already_in_front_changes_nothing(self) -> None:
        self.real_python()
        _, data = self.plan([self.realpy, self.windowsapps, self.wingetdir])
        self.assertEqual(self.row(data, "python")["action"], "skip")
        self.assertEqual([r for r in self.rows(data, "path") if r["action"] == "prepend"], [])

    def test_claude_installed_but_off_path_gets_local_bin_appended(self) -> None:
        self.claude()  # in $HOME\.local\bin, which the PATH lacks
        _, data = self.plan([self.windowsapps, self.wingetdir])
        self.assertEqual(self.row(data, "claude")["action"], "skip")
        appends = [r for r in self.rows(data, "path") if r["action"] == "append"]
        self.assertTrue(any(str(self.localbin) in r["detail"] for r in appends), data["rows"])

    def test_a_working_machine_only_updates_gatebound(self) -> None:
        self.real_python(); self.git(); self.claude(); self.gatebound_installed()
        proc, data = self.plan([self.realpy, self.windowsapps, self.gitdir, self.localbin, self.wingetdir,
                                self.node()],
                               env={"GATEBOUND_INSTALL_USER_PYTHONUTF8": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for item in ("git", "python", "claude", "pythonutf8", "node"):
            row = self.row(data, item)
            self.assertEqual((row["action"], row["verdict"]), ("skip", "ok"), row)
        self.assertEqual(self.rows(data, "path"), [])
        self.assertEqual(self.row(data, "gatebound")["action"], "update")

    def test_a_user_pythonutf8_is_left_alone(self) -> None:
        _, data = self.plan([self.windowsapps, self.wingetdir], env={"GATEBOUND_INSTALL_USER_PYTHONUTF8": "0"})
        self.assertEqual(self.row(data, "pythonutf8")["action"], "skip")

    def test_without_winget_installs_are_unverified_with_a_manual_link(self) -> None:
        proc, data = self.plan([self.windowsapps])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for item in ("git", "python"):
            row = self.row(data, item)
            self.assertEqual((row["action"], row["verdict"]), ("manual", "unverified"), row)
            self.assertIn("https://", row["detail"])

    def test_node_is_installed_by_default(self) -> None:
        # ADR-0033 decision 13: the plain line installs a missing Node.js.
        _, data = self.plan([self.windowsapps, self.wingetdir])
        row = self.row(data, "node")
        self.assertEqual((row["action"], row["verdict"]), ("install", "unverified"), row)
        self.assertIn("OpenJS.NodeJS.LTS", row["detail"])
        self.assertIn("--accept-package-agreements", row["detail"])

    def test_the_old_with_node_flag_is_still_accepted(self) -> None:
        proc, data = self.plan([self.windowsapps, self.wingetdir], extra=["-WithNode"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.row(data, "node")["action"], "install")  # one row, as without it

    def test_without_winget_node_is_unverified_with_a_manual_link(self) -> None:
        _, data = self.plan([self.windowsapps])
        row = self.row(data, "node")
        self.assertEqual((row["action"], row["verdict"]), ("manual", "unverified"), row)
        self.assertIn("https://nodejs.org", row["detail"])

    # ---- -WithCodex (ADR-0033 decision 12) -----------------------------
    def working(self) -> list:
        self.real_python(); self.git(); self.claude(); self.gatebound_installed()
        return [self.realpy, self.windowsapps, self.gitdir, self.localbin, self.wingetdir]

    def node(self) -> pathlib.Path:
        nodedir = self.root / "nodejs"
        nodedir.mkdir()
        self.stub(nodedir / "node", "echo v22.11.0")
        self.stub(nodedir / "npm", "echo npm")
        return nodedir

    def codex_hooks_row(self, data: dict) -> dict:
        row = self.row(data, "codex-hooks")
        self.assertEqual(row["verdict"], "warn", row)
        return row

    def test_codex_only_with_the_flag(self) -> None:
        _, data = self.plan(self.working(), env={"GATEBOUND_INSTALL_USER_PYTHONUTF8": "1"})
        self.assertEqual([r for r in data["rows"] if r["item"].startswith("codex")], [])

    def test_with_codex_the_cli_comes_from_npm_cmd(self) -> None:
        _, data = self.plan(self.working() + [self.node()], extra=["-WithCodex"])
        self.assertEqual(self.row(data, "node")["action"], "skip")  # -WithCodex implies -WithNode
        row = self.row(data, "codex")
        self.assertEqual((row["action"], row["verdict"]), ("install", "unverified"), row)
        self.assertIn("npm.cmd install -g @openai/codex", row["detail"])

    def test_a_codex_on_path_is_kept(self) -> None:
        nodedir = self.node()
        self.stub(nodedir / "codex", "echo codex-cli 0.160.0")
        _, data = self.plan(self.working() + [nodedir], extra=["-WithCodex"])
        row = self.row(data, "codex")
        self.assertEqual((row["action"], row["verdict"]), ("skip", "ok"), row)
        self.assertIn("0.160.0", row["detail"])

    def test_a_blocking_execution_policy_turns_codex_into_a_warn(self) -> None:
        # Observed 2026-10-05 on a second PC: npm's codex.ps1 wins over
        # codex.cmd in PowerShell and the default policy refuses it, while the
        # installer, which runs the .cmd, reported ok.
        nodedir = self.node()
        self.stub(nodedir / "codex", "echo codex-cli 0.160.0")
        for policy in ("Restricted", "AllSigned"):
            with self.subTest(policy=policy):
                _, data = self.plan(self.working() + [nodedir], extra=["-WithCodex"],
                                    env={"GATEBOUND_INSTALL_EXECUTION_POLICY": policy})
                row = self.row(data, "codex")
                self.assertEqual(row["verdict"], "warn", row)
                for needle in (policy, "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned",
                               "codex.cmd", "0.160.0"):
                    self.assertIn(needle, row["detail"])

    def test_a_permissive_execution_policy_keeps_codex_ok(self) -> None:
        nodedir = self.node()
        self.stub(nodedir / "codex", "echo codex-cli 0.160.0")
        for policy in ("RemoteSigned", "Unrestricted", "Bypass"):
            with self.subTest(policy=policy):
                _, data = self.plan(self.working() + [nodedir], extra=["-WithCodex"],
                                    env={"GATEBOUND_INSTALL_EXECUTION_POLICY": policy})
                self.assertEqual(self.row(data, "codex")["verdict"], "ok")

    def test_a_planned_codex_install_names_the_policy_too(self) -> None:
        _, data = self.plan(self.working() + [self.node()], extra=["-WithCodex"],
                            env={"GATEBOUND_INSTALL_EXECUTION_POLICY": "Restricted"})
        row = self.row(data, "codex")
        self.assertEqual((row["action"], row["verdict"]), ("install", "unverified"), row)
        self.assertIn("RemoteSigned", row["detail"])

    def test_the_policy_warning_follows_the_language(self) -> None:
        nodedir = self.node()
        self.stub(nodedir / "codex", "echo codex-cli 0.160.0")
        _, data = self.plan(self.working() + [nodedir], extra=["-WithCodex"], lang="ko",
                            env={"GATEBOUND_INSTALL_EXECUTION_POLICY": "Restricted"})
        detail = self.row(data, "codex")["detail"]
        self.assertTrue(any("가" <= ch <= "힣" for ch in detail), detail)

    def test_without_npm_codex_waits_for_a_new_window(self) -> None:
        _, data = self.plan(self.working(), extra=["-WithCodex"])
        self.assertEqual(self.row(data, "node")["action"], "install")
        row = self.row(data, "codex")
        self.assertEqual((row["action"], row["verdict"]), ("manual", "unverified"), row)
        self.assertIn("-WithCodex", row["detail"])

    def test_the_hooks_row_is_always_a_warn_with_the_steps_left(self) -> None:
        nodedir = self.node()
        self.stub(nodedir / "codex", "echo codex-cli 0.160.0")
        proc, data = self.plan(self.working() + [nodedir], extra=["-WithCodex"],
                               env={"GATEBOUND_INSTALL_USER_PYTHONUTF8": "1"})
        row = self.codex_hooks_row(data)
        for needle in ("install --host codex", "/hooks", "--no-daemon"):
            self.assertIn(needle, row["detail"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotEqual(data["verdict"], "ok")  # a Codex install never ends ok

    def test_the_hooks_row_names_the_installed_plugin(self) -> None:
        paths = self.working()
        # Claude Code writes this file as raw UTF-8 (not \u-escaped), and a
        # Korean user folder puts Hangul in the path; PowerShell 5.1 reads a
        # BOM-less file in the ANSI code page unless told otherwise.
        plugin = self.home / "사용자" / ".claude" / "plugins" / "cache" / "gatebound" / "gatebound" / "0.16.10"
        (self.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"gatebound@gatebound": [
                {"version": "0.16.10", "installPath": str(plugin)}]}}, ensure_ascii=False), encoding="utf-8")
        _, data = self.plan(paths + [self.node()], extra=["-WithCodex"])
        self.assertIn(str(plugin / "bin" / "gatebound.py"), self.codex_hooks_row(data)["detail"])

    def test_no_codex_plugin_is_installed(self) -> None:
        _, data = self.plan(self.working() + [self.node()], extra=["-WithCodex"])
        self.assertFalse(any("codex plugin" in r["detail"] for r in data["rows"]), data["rows"])

    def test_codex_rows_follow_the_language(self) -> None:
        _, data = self.plan(self.working(), extra=["-WithCodex"], lang="ko")
        for item in ("codex", "codex-hooks"):
            self.assertTrue(any("가" <= ch <= "힣" for ch in self.row(data, item)["detail"]), item)

    def test_an_elevated_window_is_refused(self) -> None:
        proc, data = self.plan([self.windowsapps, self.wingetdir], env={"GATEBOUND_INSTALL_ELEVATED": "1"})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(data["verdict"], "fail")
        self.assertEqual([r["item"] for r in data["rows"]], ["elevation"])

    def test_messages_follow_the_language(self) -> None:
        _, en = self.plan([self.windowsapps, self.wingetdir])
        _, ko = self.plan([self.windowsapps, self.wingetdir], lang="ko")
        self.assertEqual((en["lang"], ko["lang"]), ("en", "ko"))
        self.assertTrue(any("\uac00" <= ch <= "\ud7a3" for ch in self.row(ko, "python")["detail"]))
        self.assertFalse(any("\uac00" <= ch <= "\ud7a3" for ch in self.row(en, "python")["detail"]))

    def test_a_dry_run_leaves_the_real_user_path_alone(self) -> None:
        import winreg
        def user_path() -> str:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, "Path")[0]
        before = user_path()
        self.plan([self.windowsapps, self.wingetdir], extra=["-WithNode"])
        self.assertEqual(user_path(), before)


class TestManualBundle(unittest.TestCase):
    """The Notion bundle must keep the tree and survive Korean filenames."""

    def _repo(self, root: pathlib.Path) -> None:
        minimal_clean_repo(root)
        write(root / "docs" / "manual" / "00-index.md", "# 색인\n\n- [소개](01-intro.md)\n")
        write(root / "docs" / "manual" / "01-intro.md", "# 소개\n\n본문\n")

    def _build(self, root: pathlib.Path, out: pathlib.Path, title: str = "매뉴얼"):
        return subprocess.run(
            [sys.executable, str(TOOLS_DIR / "build_manual_bundle.py"),
             "--root", str(root), "--out", str(out), "--title", title],
            capture_output=True, text=True, timeout=30)

    def test_bundle_has_parent_and_children(self) -> None:
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._repo(root)
            out = root / "out.zip"
            proc = self._build(root, out)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
            self.assertIn("매뉴얼.md", names)
            self.assertIn("매뉴얼/00-index.md", names)
            self.assertIn("매뉴얼/01-intro.md", names)

    def test_filenames_carry_the_utf8_flag(self) -> None:
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._repo(root)
            out = root / "out.zip"
            self._build(root, out)
            with zipfile.ZipFile(out) as z:
                self.assertTrue(all(i.flag_bits & 0x800 for i in z.infolist()),
                                "UTF-8 filename flag missing; Korean titles would mangle")

    def test_missing_manual_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            minimal_clean_repo(root)
            proc = self._build(root, root / "out.zip")
            self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
