"""Tests for gates/tokens.py — the colour-literal task gate (ADR-0008 decision 5)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound.gates import tokens as tokens_gate  # noqa: E402
from tests._stubs import symlink_or_skip  # noqa: E402

GATE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "gatebound" / "gates" / "tokens.py"

V2 = {
    "version": 2,
    "source": ["figma"],
    "patterns": [],
    "color": {
        "primary": "#3366FF",
        "surface": {"value": "#ffffff", "evidence": "preset:x"},
        "danger": "rgb(200, 0, 0)",
    },
    "space": {"md": "16px"},
}


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "spec").mkdir()
        (self.root / "src").mkdir()

    def tokens(self, data) -> None:
        (self.root / "spec" / "tokens.json").write_text(json.dumps(data), encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_gate(self, *globs: str, extra=()) -> "tuple[int, str]":
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tokens_gate.main(["--root", str(self.root), *extra, *globs])
        return code, out.getvalue()


class VerdictTests(_Base):
    def test_all_literals_are_tokens_is_ok(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #3366ff; background: #FFF; border-color: rgb(200,0,0); }")
        code, out = self.run_gate("src/**/*.css")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("tokens: ok"), out)

    def test_unknown_literal_fails_with_nearest(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #3366fe; }")
        code, out = self.run_gate("src/**/*.css")
        self.assertEqual(code, 1, out)
        self.assertIn("src/a.css:1: #3366fe is not a design token", out)
        self.assertIn("nearest: color.primary = #3366FF", out)

    def test_line_numbers_are_reported(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #3366ff; }\n\n.b { color: #123456; }\n")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1)
        self.assertIn("src/a.css:3: #123456", out)

    def test_missing_tokens_file_is_unverified(self) -> None:
        self.write("src/a.css", ".a { color: #123456; }")
        code, out = self.run_gate("src/**/*.css")
        self.assertEqual(code, 3, out)
        self.assertTrue(out.startswith("tokens: unverified"), out)

    def test_no_colour_tokens_is_unverified(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [], "space": {"md": "16px"}})
        self.write("src/a.css", ".a { color: #123456; }")
        code, out = self.run_gate("src/**/*.css")
        self.assertEqual(code, 3, out)

    def test_no_matching_file_is_unverified(self) -> None:
        self.tokens(V2)
        code, out = self.run_gate("src/**/*.css")
        self.assertEqual(code, 3, out)
        self.assertIn("0 files", out)

    def test_unparsable_tokens_file_is_unverified(self) -> None:
        (self.root / "spec" / "tokens.json").write_text("{not json", encoding="utf-8")
        self.write("src/a.css", ".a { color: #123456; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 3)


class NormalisationTests(_Base):
    def test_three_digit_hex_matches_six_digit_token(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [], "color": {"white": "#ffffff"}})
        self.write("src/a.css", ".a { color: #FFF; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_function_colour_whitespace_is_collapsed(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [], "color": {"d": "rgb(200, 0, 0)"}})
        self.write("src/a.css", ".a { color: RGB( 200 ,0,  0 ); }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_v1_tokens_are_accepted(self) -> None:
        self.tokens({"version": 1, "source": "x", "color": {"p": "#000000"}})
        self.write("src/a.css", ".a { color: #000; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_object_token_with_value_key(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "brand-colors": {"ink": {"value": "#111111", "evidence": "preset:a"}}})
        self.write("src/a.css", ".a { color: #111111; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_nested_group_leaf_colours_count(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "font": {"body": {"size": "16px", "color": "#222222"}}})
        self.write("src/a.css", ".a { color: #222222; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)


class BareHslTripletTests(_Base):
    """The shipped shadcn-neutral preset stores colours as bare HSL triplets
    (``--primary: 0 0% 9%``) consumed through ``hsl(var(--primary))``. Found in
    the 2026-10-09 timed trial: the gate saw no colour tokens at all and read
    every correct ``hsl(var(...))`` as a literal, so /gatebound:tasks dropped it."""

    SHADCN = {"version": 2, "source": ["seed:shadcn-ui"], "patterns": [],
              "color": {"primary": "0 0% 9%",
                        "ring": {"value": "0 0% 3.9%", "evidence": "preset:shadcn-neutral"},
                        "accent": "240 4.8% 95.9% / 0.5"}}

    def test_bare_triplets_are_colour_tokens(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: hsl(0 0% 9%); border-color: hsl(0, 0%, 3.9%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)

    def test_var_reference_is_not_a_literal(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css",
                   ".a { color: hsl(var(--primary)); background: hsl(var(--ring) / 0.4); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)
        self.assertIn("0 literals", out)

    def test_unknown_hsl_literal_still_fails(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: hsl(10 50% 50%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1, out)
        self.assertIn("hsl(10 50% 50%)", out)

    def test_triplet_with_alpha_matches_slash_and_comma_forms(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: hsl(240 4.8% 95.9% / 0.5); "
                                "background: hsla(240, 4.8%, 95.9%, 0.5); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)

    def test_space_and_comma_rgb_forms_are_one_colour(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "color": {"shade": "rgba(0, 0, 0, 0.5)"}})
        self.write("src/a.css", ".a { color: rgb(0 0 0 / 0.5); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)

    def test_space_syntax_does_not_collide_with_other_colours(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "color": {"a": "hsl(0 0% 9%)"}})
        self.write("src/a.css", ".a { color: hsl(0 0% 99%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1, out)

    def test_shipped_shadcn_preset_has_colour_tokens(self) -> None:
        preset = pathlib.Path(__file__).resolve().parents[1] / "spec-kit" / "presets" / "design" / "shadcn-neutral.json"
        self.tokens(json.loads(preset.read_text(encoding="utf-8")))
        self.write("src/a.css", ".a { color: hsl(var(--primary)); background: hsl(var(--background)); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)


class IgnoreTests(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.tokens(V2)

    def test_allowlist_and_keywords_never_violate(self) -> None:
        data = dict(V2)
        data["allow"] = {"color": ["#abcdef"]}
        self.tokens(data)
        self.write("src/a.css", ".a { color: #abcdef; b: transparent; c: currentColor; d: inherit; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_block_comments_are_ignored(self) -> None:
        self.write("src/a.css", "/* #123456 */\n.a { color: #3366ff; /* rgb(1,2,3) */ }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_line_comments_are_ignored_in_js_only(self) -> None:
        self.write("src/a.ts", "const u = 'http://x'; // #123456\nconst c = '#3366ff';")
        code, _ = self.run_gate("src/a.ts")
        self.assertEqual(code, 0)
        self.write("src/b.css", ".a { color: #123456; } // not a comment in css")
        code, _ = self.run_gate("src/b.css")
        self.assertEqual(code, 1)

    def test_html_comments_are_ignored(self) -> None:
        self.write("src/a.html", "<!-- #123456 --><div style='color:#3366ff'></div>")
        code, _ = self.run_gate("src/a.html")
        self.assertEqual(code, 0)

    def test_url_contents_are_ignored(self) -> None:
        self.write("src/a.css", ".a { background: url(/img/#123456.png); color: #3366ff; }")
        code, _ = self.run_gate("src/a.css")
        self.assertEqual(code, 0)

    def test_unknown_extensions_and_skip_dirs_are_not_scanned(self) -> None:
        self.write("src/a.py", "x = '#123456'")
        self.write("src/node_modules/x.css", ".a { color: #123456; }")
        code, out = self.run_gate("src/**/*")
        self.assertEqual(code, 3, out)  # nothing scannable matched

    def test_globs_cannot_escape_the_root(self) -> None:
        outside = pathlib.Path(self.tmp.name).parent / ("gk_outside_%d" % os.getpid())
        outside.mkdir(exist_ok=True)
        self.addCleanup(lambda: [p.unlink() for p in outside.glob("*")] and outside.rmdir())
        (outside / "x.css").write_text(".a { color: #123456; }", encoding="utf-8")
        rel = os.path.relpath(outside, self.root)
        for pattern in (rel + "/*.css", rel + "/**/*.css"):
            code, out = self.run_gate(pattern)
            self.assertEqual(code, 3, out)
            self.assertNotIn("#123456", out)
            self.assertNotIn("internal error", out)
            self.assertIn("0 files", out)

    def test_symlink_to_outside_file_is_not_scanned(self) -> None:
        outside = pathlib.Path(self.tmp.name).parent / ("gk_outside_link_%d" % os.getpid())
        outside.mkdir(exist_ok=True)
        target = outside / "y.css"
        target.write_text(".a { color: #123456; }", encoding="utf-8")
        self.addCleanup(lambda: (target.unlink(), outside.rmdir()))
        symlink_or_skip(self, target, self.root / "src" / "link.css")
        code, out = self.run_gate("src/*.css")
        self.assertEqual(code, 3, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("internal error", out)

    def test_large_files_are_skipped(self) -> None:
        self.write("src/big.css", ".a{color:#123456}" + " " * 1_100_000)
        code, _ = self.run_gate("src/big.css")
        self.assertEqual(code, 3)


class OutputTests(_Base):
    def test_json_shape(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #123456; }")
        code, out = self.run_gate("src/a.css", extra=("--json",))
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["verdict"], "fail")
        self.assertEqual(data["files"], 1)
        self.assertEqual(data["literals"], 1)
        self.assertEqual(data["violations"][0]["path"], "src/a.css")
        self.assertEqual(data["violations"][0]["line"], 1)
        self.assertEqual(data["violations"][0]["literal"], "#123456")
        self.assertIn("nearest", data["violations"][0])

    def test_korean_summary(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #3366ff; }")
        code, out = self.run_gate("src/a.css", extra=("--lang", "ko"))
        self.assertEqual(code, 0)
        self.assertIn("리터럴", out)

    def test_internal_error_exits_3_without_traceback(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #3366ff; }")
        original = tokens_gate._read_text

        def boom(path):
            raise OSError("injected")

        tokens_gate._read_text = boom
        self.addCleanup(setattr, tokens_gate, "_read_text", original)
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 3)
        self.assertNotIn("Traceback", out)
        self.assertIn("injected", out)

    def test_runs_as_a_script(self) -> None:
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #123456; }")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GATEBOUND_")}
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), "src/a.css"],
            cwd=str(self.root), capture_output=True, text=True, encoding="utf-8",
            env=env, timeout=30,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("#123456", proc.stdout)

    def test_prints_on_a_non_utf8_console(self) -> None:
        # A Windows console reports cp949 or cp1252; the Korean report and the
        # em dash crashed print() and the gate died with a traceback instead
        # of returning its verdict. Forcing cp1252 reproduces it on any OS.
        self.tokens(V2)
        self.write("src/a.css", ".a { color: #123456; }")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GATEBOUND_")}
        env.pop("PYTHONPATH", None)
        env["PYTHONIOENCODING"] = "cp1252"
        for lang in ("ko", "en"):
            with self.subTest(lang=lang):
                proc = subprocess.run(
                    [sys.executable, str(GATE_SCRIPT), "--lang", lang, "src/a.css"],
                    cwd=str(self.root), capture_output=True, env=env, timeout=30,
                )
                out = proc.stdout.decode("utf-8", "replace")
                err = proc.stderr.decode("utf-8", "replace")
                self.assertNotIn("Traceback", err)
                self.assertEqual(proc.returncode, 1, out + err)
                self.assertIn("#123456", out)


if __name__ == "__main__":
    unittest.main()


class ReviewOfBareHslTests(_Base):
    """ADR-0040 review: a var() only in the alpha slot is still a hard-coded
    colour; hue units and alpha spellings compare as one colour; a triplet is
    a colour only in a colour group."""

    SHADCN = BareHslTripletTests.SHADCN

    def test_var_alpha_does_not_hide_a_hard_coded_colour(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: rgb(255 0 0 / var(--a)); border-color: rgba(0, 0, 0, var(--b)); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1, out)
        self.assertIn("2 violations", out)

    def test_var_in_a_channel_is_a_reference(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: rgba(var(--rgb), 0.5); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)

    def test_hue_unit_and_alpha_spelling_do_not_matter(self) -> None:
        self.tokens(self.SHADCN)
        self.write("src/a.css", ".a { color: hsl(0deg 0% 9%); background: hsl(240 4.8% 95.9% / 50%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 0, out)

    def test_triplet_outside_a_colour_group_is_not_a_colour(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "color": {"ink": "#111111"},
                     "position": {"odd": "10 50% 50%"}})
        self.write("src/a.css", ".a { color: hsl(10 50% 50%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1, out)

    def test_dangling_alpha_slash_is_not_a_triplet(self) -> None:
        self.tokens({"version": 2, "source": [], "patterns": [],
                     "color": {"ink": "#111111", "odd": "0 0% 9% /"}})
        self.write("src/a.css", ".a { color: hsl(0 0% 9%); }")
        code, out = self.run_gate("src/a.css")
        self.assertEqual(code, 1, out)
