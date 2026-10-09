"""ADR-0037: a paste is not the user's language, and a gate with no
prompt-set language takes the spec's."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import ledger, names  # noqa: E402
from gatebound.gates import bash as bash_gate  # noqa: E402
from gatebound.gates import prompt as prompt_gate  # noqa: E402
from gatebound.gates import write  # noqa: E402

#: What a pasted PowerShell transcript looks like in the prompt (2026-10-05).
TERMINAL = ("PS C:\\Users\\lovep\\codex_install_test> codex --version\n"
            "codex : File C:\\Users\\lovep\\AppData\\Roaming\\npm\\codex.ps1 cannot be loaded "
            "because running scripts is disabled on this system.\n"
            "    + CategoryInfo          : SecurityError: (:) [], PSSecurityException\n")


def pasted(body: str, pid: str = "21ce") -> str:
    return '\n\n<pasted_content id="%s">\n%s\n</pasted_content id="%s">\n' % (pid, body, pid)


def hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


class Prompts(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / ".gatebound").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def send(self, text: str) -> None:
        prompt_gate.handle({"session_id": "s", "hook_event_name": "UserPromptSubmit",
                            "cwd": str(self.root), "prompt": text})

    def led(self) -> ledger.Ledger:
        return ledger.Ledger.load(self.root, "s")


class TestPasteCarriesNoLanguage(Prompts):
    def test_a_paste_only_prompt_keeps_a_korean_session_korean(self) -> None:
        self.send("설치 결과 확인해줘")
        self.send(pasted(TERMINAL))
        self.assertEqual(self.led().data["output_lang"], "ko")

    def test_words_around_the_paste_still_decide(self) -> None:
        self.send(pasted(TERMINAL) + "\n 확인해줘")
        self.assertEqual(self.led().data["output_lang"], "ko")
        self.send(pasted("설치 로그입니다 한국어 문서") + "\nplease check this output")
        self.assertEqual(self.led().data["output_lang"], "en")

    def test_a_paste_as_the_first_prompt_sets_no_language(self) -> None:
        self.send(pasted(TERMINAL))
        self.assertNotEqual(self.led().data.get("lang_source"), "prompt")

    def test_language_signal_drops_every_paste_and_an_unclosed_one(self) -> None:
        text = "앞 " + pasted(TERMINAL, "a1") + " 가운데 " + pasted(TERMINAL, "b2") + " 끝"
        signal = prompt_gate.language_signal(text)
        self.assertNotIn("codex", signal)
        self.assertIn("가운데", signal)
        self.assertEqual(prompt_gate.language_signal('확인 <pasted_content id="z">\n' + TERMINAL).strip(), "확인")


class GateProject(unittest.TestCase):
    """No state directory: the prompt gate stands down and writes no ledger,
    while rule (a) acts on the spec files (ADR-0036)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))
        (self.root / "spec").mkdir()
        self._env = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(names.env_prefixes())}

    def tearDown(self) -> None:
        os.environ.update(self._env)
        self._tmp.cleanup()

    def prd(self, text: str) -> None:
        (self.root / "spec" / "01-prd.md").write_text(text, encoding="utf-8")

    def event(self, tool: str, tool_input: dict) -> dict:
        return {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": str(self.root),
                "tool_name": tool, "tool_input": tool_input}

    def reasons(self) -> list:
        out = [write.handle(self.event("Write", {"file_path": str(self.root / "src" / "a.py"), "content": "x"})),
               bash_gate.handle(self.event("Bash", {"command": "echo x > src/a.py"}))]
        return [r["hookSpecificOutput"]["permissionDecisionReason"] for r in out]


class TestGateLanguageFromSpec(GateProject):
    def test_a_korean_spec_makes_the_denials_korean(self) -> None:
        self.prd("# 메모 앱\n\n## 문제\n사용자는 메모를 빠르게 남기고 싶다.\n")
        for reason in self.reasons():
            self.assertTrue(hangul(reason), reason)
        self.assertFalse((self.root / ".gatebound").exists())  # still writes nothing

    def test_an_english_spec_keeps_them_english(self) -> None:
        self.prd("# Notes app\n\n## Problem\nUsers want to jot notes down fast.\n")
        for reason in self.reasons():
            self.assertFalse(hangul(reason), reason)

    def test_a_prompt_set_language_wins_over_the_spec(self) -> None:
        self.prd("# 메모 앱\n\n## 문제\n사용자는 메모를 빠르게 남기고 싶다.\n")
        (self.root / ".gatebound").mkdir()
        led = ledger.Ledger.load(self.root, "s")
        led.set_output_lang("en", source="prompt")
        led.save()
        for reason in self.reasons():
            self.assertFalse(hangul(reason), reason)

    def test_session_lang_never_raises(self) -> None:
        self.assertEqual(write.session_lang(self.root, {"session_id": object()}), "en")


if __name__ == "__main__":
    unittest.main()
