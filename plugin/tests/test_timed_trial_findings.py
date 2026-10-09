"""Findings of the 2026-10-09 timed trial that are not in ADR-0040.

A 16-feature app was built end to end with 0.16.17. Besides the three
defects ADR-0040 fixed, four smaller ones cost a session time or noise:

* ``jobs shape`` was missing from ``jobs --help`` and read only
  ``spec/04-tasks.md``, while ``/gatebound:tasks`` tells the session to run it
  on a draft before that file exists; the session concluded it did not exist.
* ``spec validate`` right after ``/gatebound:discover`` judged a Korean
  ``00-discovery.md`` as English, because only ``01-prd.md`` decided.
* Assumptions ``/gatebound:mockup`` adds are marked inline in ``02-screens.md``
  where they are used, as the policy says, but the ledger check looked for
  markers in ``01-prd.md`` only: thirteen false warnings at every stage.
* During the build the session's progress lines between tool calls drifted
  into English although the hook kept saying ``output_lang=ko``; the
  language policy and the build/verify commands did not name those lines.
"""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import jobs, spec  # noqa: E402

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "spec"

TASK = (
    "```gatebound-task\n"
    '{"id": "%s", "instruction": "write %s", "write_scope": ["src/%s.txt"], '
    '"gates": [], "depends_on": %s, "round": %d}\n'
    "```\n"
)


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / "spec").mkdir()

    def capture(self, argv) -> "tuple[int, str]":
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = jobs.run(argv)
        return code, out.getvalue()


class TestJobsShapeIsDiscoverable(_Tmp):
    def test_usage_lists_shape(self) -> None:
        self.assertIn("shape", jobs._usage())
        self.assertIn("--file", jobs._usage())

    def test_subcommand_help_prints_usage_and_succeeds(self) -> None:
        code, out = self.capture(["shape", "--help", "--root", str(self.root)])
        self.assertEqual(code, 0, out)
        self.assertIn("shape", out)

    def test_shape_reads_a_draft_before_04_tasks_exists(self) -> None:
        draft = self.root / "draft-tasks.md"
        draft.write_text(TASK % ("a", "a", "a", "[]", 1) + TASK % ("b", "b", "b", '["a"]', 2),
                         encoding="utf-8")
        self.assertFalse((self.root / "spec" / "04-tasks.md").exists())
        info = jobs.shape(self.root, source=draft)
        self.assertEqual((info["tasks"], info["rounds"]), (2, 2))
        code, out = self.capture(["shape", "--file", str(draft), "--root", str(self.root)])
        self.assertEqual(code, 0, out)
        self.assertIn("rounds 2", out)

    def test_tasks_command_runs_shape_on_its_draft(self) -> None:
        text = (PLUGIN / "commands" / "tasks.md").read_text(encoding="utf-8")
        self.assertIn("jobs shape --file", text)


class TestLanguageBeforeThePrd(_Tmp):
    def test_korean_discovery_alone_decides_korean(self) -> None:
        (self.root / "spec" / "00-discovery.md").write_text(
            "# 장비 대여 — 발굴 기록\n\n장비를 누가 갖고 있는지 기록이 실제와 어긋난다.\n",
            encoding="utf-8")
        self.assertEqual(spec.validate(self.root)["lang"], "ko")

    def test_prd_still_decides_when_present(self) -> None:
        shutil.copytree(FIXTURES / "valid-en" / "spec", self.root / "spec", dirs_exist_ok=True)
        (self.root / "spec" / "00-discovery.md").write_text(
            "# 발굴 기록\n\n한국어 문장입니다.\n", encoding="utf-8")
        self.assertEqual(spec.validate(self.root)["lang"], "en")

    def test_nothing_to_read_is_english(self) -> None:
        self.assertEqual(spec.validate(self.root)["lang"], "en")


class TestAssumptionMarkersOutsideThePrd(_Tmp):
    def setUp(self) -> None:
        super().setUp()
        shutil.copytree(FIXTURES / "valid-ko" / "spec", self.root / "spec", dirs_exist_ok=True)
        prd = self.root / "spec" / "01-prd.md"
        text = prd.read_text(encoding="utf-8")
        row = "| 1 | 현재 저장 시간은 측정된 적이 없다 | 로그가 없음 | 목표치가 근거를 잃는다 | 로그 계측 추가 |\n"
        self.assertIn(row, text)
        prd.write_text(text.replace(
            row, row + "| 2 | 화면 간격은 4px 단위다 | 프리셋에 없음 | 간격이 어긋난다 | 목업 확인 |\n"),
            encoding="utf-8")

    def row_warnings(self) -> list:
        return [f for f in spec.validate(self.root)["findings"]
                if f["file"] == "01-prd.md" and f["verdict"] == "warn"]

    def test_row_without_any_marker_still_warns(self) -> None:
        self.assertEqual(len(self.row_warnings()), 1)

    def test_marker_in_the_screen_spec_satisfies_the_row(self) -> None:
        screens = self.root / "spec" / "02-screens.md"
        screens.write_text(screens.read_text(encoding="utf-8")
                           + "\n> ⚠️ 가정 2: 화면 간격은 4px 단위다.\n", encoding="utf-8")
        self.assertEqual(self.row_warnings(), [])

    def test_marker_in_the_architecture_satisfies_the_row(self) -> None:
        arch = self.root / "spec" / "03-architecture.md"
        arch.write_text(arch.read_text(encoding="utf-8")
                        + "\n> ⚠️ 가정 2: 화면 간격은 4px 단위다.\n", encoding="utf-8")
        self.assertEqual(self.row_warnings(), [])

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "chmod 000 does not make a file unreadable here")
    def test_unreadable_marker_file_is_a_finding_not_a_crash(self) -> None:
        screens = self.root / "spec" / "02-screens.md"
        screens.chmod(0)
        self.addCleanup(screens.chmod, 0o644)
        report = spec.validate(self.root)
        self.assertIn(report["verdict"], ("ok", "warn", "fail", "unverified"))


class TestShapeDraftPaths(_Tmp):
    def test_relative_draft_resolves_against_the_root(self) -> None:
        (self.root / "drafts").mkdir()
        (self.root / "drafts" / "t.md").write_text(TASK % ("a", "a", "a", "[]", 1), encoding="utf-8")
        code, out = self.capture(["shape", "--file", "drafts/t.md", "--root", str(self.root)])
        self.assertEqual(code, 0, out)

    def test_missing_draft_says_so(self) -> None:
        code, out = self.capture(["shape", "--file", "nope.md", "--root", str(self.root)])
        self.assertEqual(code, 2, out)
        self.assertIn("not found", out)

    def test_help_only_as_the_first_argument(self) -> None:
        code, out = self.capture(["shape", "--tasks", "-h", "--root", str(self.root)])
        self.assertNotEqual(out, jobs._usage())


class TestProgressLinesFollowTheLanguage(unittest.TestCase):
    def test_policy_names_progress_lines(self) -> None:
        text = (PLUGIN / "policy" / "language.md").read_text(encoding="utf-8")
        self.assertIn("progress lines", text)

    def test_build_and_verify_name_progress_lines(self) -> None:
        for name in ("build.md", "verify.md"):
            text = (PLUGIN / "commands" / name).read_text(encoding="utf-8")
            self.assertIn("progress lines", text, name)


if __name__ == "__main__":
    unittest.main()
