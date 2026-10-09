"""Tests for gatebound.runcheck (ADR-0022): "ran no tests" signatures, missing
paths named by a failing command, and which task's write scope covers them."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import paths, runcheck
from tests._stubs import symlink_or_skip  # noqa: E402


class plugin_with_signatures:
    """Context manager: a throwaway plugin root (found through
    CLAUDE_PLUGIN_ROOT, as an installed hook finds it) whose signature file
    holds *body*."""

    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        root = os.path.join(self._tmp.name, "plugin")
        os.makedirs(os.path.join(root, ".claude-plugin"))
        os.makedirs(os.path.join(root, "spec-kit"))
        with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w") as h:
            h.write('{"name": "gatebound", "version": "0"}')
        with open(os.path.join(root, "spec-kit", runcheck.SIGNATURES_FILE), "w") as h:
            h.write(self.body)
        self._old = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = root
        runcheck._signatures.cache_clear()
        return root

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = self._old
        runcheck._signatures.cache_clear()
        self._tmp.cleanup()
        return False

#: (signature id, zero-test output, its exit code, real-run output with a
#: positive count, its exit code). Each zero-test output must be named by
#: its signature; each real run must not be named at all.
SIGNATURE_CASES = (
    ("pytest", "============ no tests ran in 0.01s ============\n", 5,
     "collected 3 items\n\ntests/test_a.py ...\n============ 3 passed in 0.12s ============\n", 0),
    ("unittest", "\n----------------------------------------------------------------------\n"
                 "Ran 0 tests in 0.000s\n\nNO TESTS RAN\n", 5,
     "....\n----------------------------------------------------------------------\n"
     "Ran 4 tests in 0.010s\n\nOK\n", 0),
    ("jest", "No tests found, exiting with code 0\n", 0,
     "PASS src/a.test.ts\nTests:       2 passed, 2 total\n", 0),
    ("vitest", "No test files found, exiting with code 0\n", 0,
     " Test Files  1 passed (1)\n      Tests  3 passed (3)\n", 0),
    ("playwright", "Error: No tests found\n", 0,
     "Running 5 tests using 2 workers\n  5 passed (3.2s)\n", 0),
    ("node-test", "# tests 0\n# suites 0\n# pass 0\n# fail 0\n", 0,
     "# tests 3\n# suites 1\n# pass 3\n# fail 0\n", 0),
    ("mocha", "\n\n  0 passing (1ms)\n\n", 0,
     "\n  thing\n    ✓ works\n\n  4 passing (12ms)\n", 0),
    ("pytest-deselected", "collected 3 items / 3 deselected / 0 selected\n"
                          "============ 3 deselected in 0.01s ============\n", 5,
     "collected 3 items / 1 deselected / 2 selected\n"
     "============ 2 passed, 1 deselected in 0.05s ============\n", 0),
    ("go", "?   \texample.com/app\t[no test files]\n", 0,
     "?   \texample.com/app/cmd\t[no test files]\nok  \texample.com/app/lib\t0.004s\n", 0),
    ("cargo", "running 0 tests\n\ntest result: ok. 0 passed; 0 failed; 0 ignored\n", 0,
     "running 5 tests\ntest a ... ok\n\ntest result: ok. 5 passed; 0 failed\n\n"
     "   Doc-tests app\n\nrunning 0 tests\n\ntest result: ok. 0 passed; 0 failed\n", 0),
)


#: ADR-0022 Amendment A: (signature id, all-skipped output, its exit code,
#: partial-skip output that also passed tests, its exit code). Outputs are
#: the runners' real formats (see the amendment's table for the source).
ALL_SKIPPED_CASES = (
    ("pytest-all-skipped",
     "collected 3 items\n\ntest_s.py sss                [100%]\n\n"
     "============================== 3 skipped in 0.01s ==============================\n", 0,
     "============================== 2 passed, 3 skipped in 0.01s ===================\n", 0),
    ("unittest-all-skipped",
     "ss\n----------------------------------------------------------------------\n"
     "Ran 2 tests in 0.000s\n\nOK (skipped=2)\n", 0,
     "ss.\n----------------------------------------------------------------------\n"
     "Ran 3 tests in 0.000s\n\nOK (skipped=2)\n", 0),
    ("jest-all-skipped",
     "Test Suites: 1 skipped, 0 of 1 total\nTests:       3 skipped, 3 total\n", 0,
     "Test Suites: 1 passed, 1 total\nTests:       2 skipped, 1 passed, 3 total\n", 0),
    ("vitest-all-skipped",
     " Test Files  1 skipped (1)\n      Tests  3 skipped (3)\n", 0,
     " Test Files  1 passed (1)\n      Tests  1 passed | 2 skipped (3)\n", 0),
    ("playwright-all-skipped",
     "Running 3 tests using 1 worker\n\n  3 skipped\n", 0,
     "Running 3 tests using 1 worker\n\n  2 skipped\n  1 passed (1.2s)\n", 0),
    ("node-test-all-skipped",
     "\u2139 tests 3\n\u2139 suites 0\n\u2139 pass 0\n\u2139 fail 0\n\u2139 cancelled 0\n"
     "\u2139 skipped 3\n\u2139 todo 0\n\u2139 duration_ms 38.19\n", 0,
     "# tests 3\n# suites 0\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 2\n# todo 0\n", 0),
    ("mocha-all-pending",
     "\n  thing\n    - works\n\n\n  0 passing (2ms)\n  3 pending\n\n", 0,
     "\n  0 failing\n\n  2 passing (2ms)\n  3 pending\n\n", 0),
    ("go-all-skipped",
     "=== RUN   TestA\n    a_test.go:5: needs linux\n--- SKIP: TestA (0.00s)\n"
     "PASS\nok  \texample.com/m\t0.002s\n", 0,
     "=== RUN   TestA\n--- SKIP: TestA (0.00s)\n=== RUN   TestB\n--- PASS: TestB (0.00s)\n"
     "PASS\nok  \texample.com/m\t0.002s\n", 0),
    ("cargo-all-ignored",
     "running 2 tests\ntest a ... ignored\ntest b ... ignored\n\n"
     "test result: ok. 0 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; "
     "finished in 0.00s\n", 0,
     "running 3 tests\ntest a ... ignored\ntest b ... ok\n\n"
     "test result: ok. 1 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; "
     "finished in 0.00s\n", 0),
)

#: ADR-0031: (id, output when the runner could not start, its exit, output of
#: a run that did start and passed something, that exit).
ENVIRONMENT_CASES = (
    ("playwright-webserver",
     "[WebServer] Error: listen EADDRINUSE: address already in use :::4183\n\n"
     "Error: Process from config.webServer was not able to start. Exit code: 1\n", 1,
     "Running 2 tests using 1 worker\n\n  1 failed\n  1 passed (3.1s)\n", 1),
)


class TestSignatureFile(unittest.TestCase):
    def test_the_data_file_lists_every_runner(self) -> None:
        path = paths.plugin_root() / "spec-kit" / "no-tests-signatures.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = {s["id"] for s in data["signatures"]}
        self.assertEqual(ids, {case[0] for case in
                               SIGNATURE_CASES + ALL_SKIPPED_CASES + ENVIRONMENT_CASES})
        kinds = {s["id"]: s.get("kind", "no_tests") for s in data["signatures"]}
        for case in SIGNATURE_CASES:
            self.assertEqual(kinds[case[0]], "no_tests", case[0])
        for case in ALL_SKIPPED_CASES:
            self.assertEqual(kinds[case[0]], "all_skipped", case[0])
        for case in ENVIRONMENT_CASES:
            self.assertEqual(kinds[case[0]], "environment", case[0])
        for sig in data["signatures"]:
            self.assertTrue(sig.get("pattern") and sig.get("positive"), sig["id"])
            self.assertTrue(sig.get("exits"), sig["id"])

    def test_each_environment_signature_matches_only_its_failure(self) -> None:
        for sig, failed, failed_exit, started, started_exit in ENVIRONMENT_CASES:
            with self.subTest(sig=sig):
                self.assertEqual(runcheck.ran_no_tests("", failed, failed_exit), sig)
                self.assertIsNone(runcheck.ran_no_tests(started, "", started_exit))
                self.assertIsNone(runcheck.ran_no_tests("", failed, 0))

    def test_malformed_files_never_raise(self) -> None:
        cases = (
            "[]",
            '{"signatures": {"id": "x"}}',
            '{"signatures": ["not a dict", 3, null]}',
            '{"signatures": [{"id": "x", "pattern": 5, "positive": "a", "exits": [0]}]}',
            '{"signatures": [{"id": "x", "pattern": "a", "positive": "b", "exits": "0"}]}',
            '{"signatures": [{"id": "x", "pattern": "a", "positive": "b", "exits": [true]}]}',
            '{"signatures": [{"id": "x", "pattern": "a", "positive": "b", "exits": [0.5]}]}',
            "null",
        )
        for body in cases:
            with self.subTest(body=body):
                with plugin_with_signatures(body):
                    self.assertIsNone(runcheck.ran_no_tests("Ran 0 tests in 0.000s", "", 0))

    def test_one_bad_entry_does_not_disable_the_rest(self) -> None:
        body = json.dumps({"signatures": [
            {"id": "broken", "pattern": "(unclosed", "positive": "x", "exits": [0]},
            "junk",
            {"id": "bad-exits", "pattern": "a", "positive": "b", "exits": [False]},
            {"id": "unittest", "pattern": "^Ran 0 tests in\\b",
             "positive": "^Ran [1-9]\\d* tests? in\\b", "exits": [0, 5]},
        ]})
        with plugin_with_signatures(body):
            self.assertEqual(runcheck.ran_no_tests("Ran 0 tests in 0.000s", "", 0), "unittest")
            self.assertEqual([s[0] for s in runcheck._signatures()], ["unittest"])

    def test_the_digest_follows_the_file(self) -> None:
        with plugin_with_signatures('{"signatures": []}'):
            first = runcheck.signatures_digest()
        with plugin_with_signatures('{"signatures": [], "v": 2}'):
            second = runcheck.signatures_digest()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)

    def test_an_unreadable_file_means_no_signatures(self) -> None:
        runcheck._signatures.cache_clear()
        try:
            with mock.patch.object(runcheck, "SIGNATURES_FILE", "nope.json"):
                runcheck._signatures.cache_clear()
                self.assertIsNone(runcheck.ran_no_tests("Ran 0 tests in 0.000s", "", 0))
        finally:
            runcheck._signatures.cache_clear()


class TestRanNoTests(unittest.TestCase):
    def test_each_signature_names_its_zero_test_output(self) -> None:
        for sig, zero, zero_exit, _real, _real_exit in SIGNATURE_CASES:
            with self.subTest(sig=sig):
                self.assertEqual(runcheck.ran_no_tests(zero, "", zero_exit), sig)
                # stderr counts as much as stdout
                self.assertEqual(runcheck.ran_no_tests("", zero, zero_exit), sig)

    def test_a_real_run_with_a_positive_count_is_never_named(self) -> None:
        for sig, _zero, _zero_exit, real, real_exit in SIGNATURE_CASES:
            with self.subTest(sig=sig):
                self.assertIsNone(runcheck.ran_no_tests(real, "", real_exit))

    def test_a_positive_count_anywhere_wins_over_a_zero_line(self) -> None:
        mixed = "Ran 0 tests in 0.000s\n" + "============ 2 passed in 0.1s ============\n"
        self.assertIsNone(runcheck.ran_no_tests(mixed, "", 0))
        self.assertIsNone(runcheck.ran_no_tests("# tests 0\n", "  3 passing (2ms)\n", 0))

    def test_an_exit_code_outside_the_signature_is_not_named(self) -> None:
        self.assertIsNone(runcheck.ran_no_tests("No tests found, exiting with code 1", "", 1))
        self.assertIsNone(runcheck.ran_no_tests("# tests 0\n", "", 1))
        self.assertIsNone(runcheck.ran_no_tests("no tests ran in 0.01s", "", 2))

    def test_pytest_and_unittest_exit_five(self) -> None:
        self.assertEqual(runcheck.ran_no_tests("no tests ran in 0.01s", "", 5), "pytest")
        self.assertEqual(runcheck.ran_no_tests("Ran 0 tests in 0.000s\n\nNO TESTS RAN", "", 5),
                         "unittest")

    def test_unittest_before_312_exits_zero(self) -> None:
        self.assertEqual(runcheck.ran_no_tests("Ran 0 tests in 0.000s\n\nOK", "", 0), "unittest")

    def test_pytest_all_deselected_is_exit_five_only(self) -> None:
        text = "============ 1 deselected in 0.00s ============\n"
        self.assertEqual(runcheck.ran_no_tests(text, "", 5), "pytest-deselected")
        self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_go_cover_lines_count_as_a_real_run(self) -> None:
        out = ("ok  \texample.com/m/pkg\t0.123s\tcoverage: 80.0% of statements\n"
               "?   \texample.com/m/cmd\t[no test files]\n")
        self.assertIsNone(runcheck.ran_no_tests(out, "", 0))
        cached = "ok  \texample.com/m/pkg\t(cached)\tcoverage: 80.0% of statements\n" \
                 "?   \texample.com/m/cmd\t[no test files]\n"
        self.assertIsNone(runcheck.ran_no_tests(cached, "", 0))

    def test_go_no_tests_to_run_is_not_a_positive(self) -> None:
        out = "ok  \texample.com/m/pkg\t0.002s [no tests to run]\n"
        self.assertEqual(runcheck.ran_no_tests(out, "", 0), "go")

    def test_go_pattern_is_anchored(self) -> None:
        self.assertIsNone(runcheck.ran_no_tests("the docs mention [no test files]\n", "", 0))

    def test_ansi_colour_is_ignored(self) -> None:
        pytest = "\x1b[33m============ \x1b[33mno tests ran\x1b[0m\x1b[33m in 0.01s ============\x1b[0m\n"
        self.assertEqual(runcheck.ran_no_tests(pytest, "", 5), "pytest")
        jest = "\x1b[1mNo tests found, exiting with code 0\x1b[22m\n"
        self.assertEqual(runcheck.ran_no_tests("", jest, 0), "jest")
        real = "\x1b[32m============ 3 passed in 0.1s ============\x1b[0m\nRan 0 tests in 0s\n"
        self.assertIsNone(runcheck.ran_no_tests(real, "", 0))

    def test_patterns_are_anchored(self) -> None:
        self.assertIsNone(runcheck.ran_no_tests("the doc says Ran 0 tests in 0s", "", 0))
        self.assertIsNone(runcheck.ran_no_tests("we had 10 passing (4ms)", "", 0))
        self.assertIsNone(runcheck.ran_no_tests("# tests 05\n", "", 0))


class TestKind(unittest.TestCase):
    """ADR-0022 Amendment A: `kind` chooses the wording, nothing else."""

    def test_describe_empty_words_each_kind(self) -> None:
        self.assertEqual(runcheck.describe_empty("pytest", 5), "ran no tests (pytest; exit 5)")
        self.assertEqual(runcheck.describe_empty("pytest-all-skipped", 0),
                         "all tests skipped (pytest-all-skipped; exit 0)")

    def test_a_webserver_that_did_not_start_is_an_environment_failure(self) -> None:
        # ADR-0031 decision 1, the output of the first host run's collision.
        out = ("[WebServer] Error: listen EADDRINUSE: address already in use :::4183\n\n"
               "Error: Process from config.webServer was not able to start. Exit code: 1\n")
        sig = runcheck.ran_no_tests("", out, 1)
        self.assertEqual(sig, "playwright-webserver")
        self.assertEqual(runcheck.signature_kind(sig), "environment")
        self.assertEqual(runcheck.describe_empty(sig, 1),
                         "could not start the runner (playwright-webserver; exit 1)")
        # A run in which a test passed was not blocked by its runner.
        self.assertIsNone(runcheck.ran_no_tests("  3 passed (2.1s)\n", out, 1))
        self.assertEqual(runcheck.signature_kind("pytest"), "no_tests")
        self.assertEqual(runcheck.signature_kind("gone"), "no_tests")

    def test_an_unknown_id_reads_as_ran_no_tests(self) -> None:
        self.assertEqual(runcheck.describe_empty("gone", 0), "ran no tests (gone; exit 0)")

    def test_requires_must_also_match(self) -> None:
        body = json.dumps({"signatures": [
            {"id": "bad-req", "requires": 5, "pattern": "^a$", "positive": "^p$"},
            {"id": "broken-req", "requires": "(open", "pattern": "^a$", "positive": "^p$"},
            {"id": "empty-req", "requires": "", "pattern": "^a$", "positive": "^p$"},
            {"id": "needs-h", "requires": "^HEADER$", "pattern": "^s$", "positive": "^p$"},
        ]})
        with plugin_with_signatures(body):
            self.assertEqual([s[0] for s in runcheck._signatures()], ["needs-h"])
            self.assertIsNone(runcheck.ran_no_tests("s", "", 0))
            self.assertEqual(runcheck.ran_no_tests("s\n", "HEADER\n", 0), "needs-h")

    def test_kind_defaults_and_a_bad_kind_is_malformed(self) -> None:
        body = json.dumps({"signatures": [
            {"id": "bad-kind", "kind": "sometimes", "pattern": "^a$", "positive": "^b$"},
            {"id": "bad-type", "kind": 3, "pattern": "^a$", "positive": "^b$"},
            {"id": "skips", "kind": "all_skipped", "pattern": "^s$", "positive": "^p$"},
            {"id": "plain", "pattern": "^a$", "positive": "^p$"},
            {"id": "explicit", "kind": "no_tests", "pattern": "^e$", "positive": "^p$"},
        ]})
        with plugin_with_signatures(body):
            self.assertEqual([s[0] for s in runcheck._signatures()],
                             ["skips", "plain", "explicit"])
            self.assertEqual(runcheck.ran_no_tests("a", "", 0), "plain")
            self.assertEqual(runcheck.describe_empty("skips", 0), "all tests skipped (skips; exit 0)")
            self.assertEqual(runcheck.describe_empty("plain", 0), "ran no tests (plain; exit 0)")
            self.assertEqual(runcheck.describe_empty("explicit", 0),
                             "ran no tests (explicit; exit 0)")


#: Real unittest modules for the review cases of ADR-0022 Amendment A. Each
#: is run with this interpreter, so the output is the runner's own.
UNITTEST_MODULES = {
    # (a) setUpClass raises SkipTest: one skip, nothing added to `Ran`.
    "case_a": (
        "import unittest\n"
        "class Integration(unittest.TestCase):\n"
        "    @classmethod\n"
        "    def setUpClass(cls): raise unittest.SkipTest('no db')\n"
        "    def test_x(self): pass\n"
        "class Unit(unittest.TestCase):\n"
        "    def test_real(self): pass\n"),
    # (b) one test passes, another skips two subtests.
    "case_b": (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_a(self): pass\n"
        "    def test_b(self):\n"
        "        for i in range(2):\n"
        "            with self.subTest(i=i): self.skipTest('x')\n"),
    # (c) one test, three subtests, one skipped and two passing.
    "case_c": (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_a(self):\n"
        "        for i in range(3):\n"
        "            with self.subTest(i=i):\n"
        "                if i == 0: self.skipTest('x')\n"),
    # (d) every test skipped.
    "case_d": (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    @unittest.skip('x')\n"
        "    def test_a(self): pass\n"
        "    @unittest.skip('x')\n"
        "    def test_b(self): pass\n"),
    # (f) a passing test that logs: verbose prints `... WARNING:…` then a
    # bare `ok` line.
    "case_f": (
        "import logging, sys, unittest, warnings\n"
        "class Integration(unittest.TestCase):\n"
        "    @classmethod\n"
        "    def setUpClass(cls): raise unittest.SkipTest('no db')\n"
        "    def test_x(self): pass\n"
        "class Unit(unittest.TestCase):\n"
        "    def test_log(self): logging.warning('computing')\n"),
    # (g) a passing test that warns: same shape as (f).
    "case_g": (
        "import logging, sys, unittest, warnings\n"
        "class Integration(unittest.TestCase):\n"
        "    @classmethod\n"
        "    def setUpClass(cls): raise unittest.SkipTest('no db')\n"
        "    def test_x(self): pass\n"
        "class Unit(unittest.TestCase):\n"
        "    def test_warn(self): warnings.warn('old api')\n"),
    # (h) a passing test that writes to stderr without a newline: the
    # progress line becomes `sprogress: .`, verbose `... progress: ok`.
    "case_h": (
        "import logging, sys, unittest, warnings\n"
        "class Integration(unittest.TestCase):\n"
        "    @classmethod\n"
        "    def setUpClass(cls): raise unittest.SkipTest('no db')\n"
        "    def test_x(self): pass\n"
        "class Unit(unittest.TestCase):\n"
        "    def test_partial(self): sys.stderr.write('progress: ')\n"),
    # (i) known false unverified: a pass, then a class whose setUpClass
    # writes a line to stderr and skips; the last progress line holds only `s`.
    "case_i": (
        "import sys, unittest\n"
        "class A(unittest.TestCase):\n"
        "    def test_real(self): pass\n"
        "class B(unittest.TestCase):\n"
        "    @classmethod\n"
        "    def setUpClass(cls):\n"
        "        sys.stderr.write('no db here\\n')\n"
        "        raise unittest.SkipTest('no db')\n"
        "    def test_x(self): pass\n"),
    # (e) a setUpModule skip and nothing else.
    "case_e": (
        "import unittest\n"
        "def setUpModule(): raise unittest.SkipTest('linux only')\n"
        "class T(unittest.TestCase):\n"
        "    def test_a(self): pass\n"),
}


def run_unittest(module: str, verbose: bool = False) -> "tuple[str, str, int]":
    """Run one of `UNITTEST_MODULES` in a scratch directory."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, module + ".py"), "w") as handle:
            handle.write(UNITTEST_MODULES[module])
        argv = [sys.executable, "-m", "unittest"] + (["-v"] if verbose else []) + [module]
        done = subprocess.run(argv, cwd=tmp, capture_output=True, text=True, timeout=60)
    return done.stdout, done.stderr, done.returncode


class TestRealUnittestRuns(unittest.TestCase):
    """A skip count is not bounded by `Ran N` (setUpClass/setUpModule skips,
    skipped subtests), so the summary alone cannot tell "all skipped"."""

    def test_a_set_up_class_skip_beside_a_pass_stays_ok(self) -> None:
        for verbose in (False, True):
            with self.subTest(verbose=verbose):
                out, err, code = run_unittest("case_a", verbose)
                self.assertIn("OK (skipped=1)", err)
                self.assertIsNone(runcheck.ran_no_tests(out, err, code))

    def test_a_pass_beside_skipped_subtests_stays_ok(self) -> None:
        for verbose in (False, True):
            with self.subTest(verbose=verbose):
                out, err, code = run_unittest("case_b", verbose)
                self.assertIn("OK (skipped=2)", err)
                self.assertIsNone(runcheck.ran_no_tests(out, err, code))

    def test_every_test_skipped_is_named(self) -> None:
        for module in ("case_d", "case_e"):
            for verbose in (False, True):
                with self.subTest(module=module, verbose=verbose):
                    out, err, code = run_unittest(module, verbose)
                    self.assertEqual(runcheck.ran_no_tests(out, err, code),
                                     "unittest-all-skipped")

    def test_a_passing_test_that_logs_warns_or_writes_stays_ok(self) -> None:
        for module in ("case_f", "case_g", "case_h"):
            for verbose in (False, True):
                with self.subTest(module=module, verbose=verbose):
                    out, err, code = run_unittest(module, verbose)
                    self.assertIn("OK (skipped=1)", err)
                    self.assertIsNone(runcheck.ran_no_tests(out, err, code))

    def test_a_skip_that_writes_a_line_after_a_pass_is_a_known_false_unverified(self) -> None:
        # Documented in ADR-0022 Amendment A: non-verbose prints `.no db here`
        # then `s` on the line before the separator, and Ran 1 / skipped=1.
        out, err, code = run_unittest("case_i")
        self.assertEqual(runcheck.ran_no_tests(out, err, code), "unittest-all-skipped")
        # -v shows the pass.
        out, err, code = run_unittest("case_i", verbose=True)
        self.assertIsNone(runcheck.ran_no_tests(out, err, code))

    def test_the_summary_alone_is_not_evidence(self) -> None:
        # Without the progress line or a verbose skip line before the
        # separator, `Ran N` / `OK (skipped=N)` is not enough.
        self.assertIsNone(runcheck.ran_no_tests("", "Ran 2 tests in 0.000s\n\nOK (skipped=2)\n", 0))
        text = "sprogress: .\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nOK (skipped=1)\n"
        self.assertIsNone(runcheck.ran_no_tests("", text, 0))

    def test_a_skipped_subtest_hiding_passes_is_a_known_false_unverified(self) -> None:
        # Documented in ADR-0022 Amendment A: unittest prints `s`, `Ran 1
        # test`, `OK (skipped=1)` — byte for byte a run whose only test was
        # skipped. The runner itself reports no pass, so gatebound cannot either.
        out, err, code = run_unittest("case_c")
        self.assertEqual(runcheck.ran_no_tests(out, err, code), "unittest-all-skipped")

    def test_progress_and_verbose_lines_count_as_run(self) -> None:
        for text in (".s\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nOK (skipped=1)\n",
                     "sx\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nOK (skipped=1)\n",
                     "test_real (m.Unit.test_real) ... ok\n\n" + "-" * 70 +
                     "\nRan 1 test in 0.000s\n\nOK (skipped=1)\n",
                     "test_x (m.T) ... expected failure\n\nRan 1 test in 0.000s\n\n"
                     "OK (skipped=1)\n"):
            with self.subTest(text=text):
                self.assertIsNone(runcheck.ran_no_tests("", text, 0))


class TestAllSkipped(unittest.TestCase):
    """ADR-0022 Amendment A: a skip and no pass is named, like zero tests."""

    def test_each_signature_names_its_all_skipped_output(self) -> None:
        for sig, skipped, exit_code, _partial, _partial_exit in ALL_SKIPPED_CASES:
            with self.subTest(sig=sig):
                self.assertEqual(runcheck.ran_no_tests(skipped, "", exit_code), sig)
                self.assertEqual(runcheck.ran_no_tests("", skipped, exit_code), sig)

    def test_a_partial_skip_is_never_named(self) -> None:
        for sig, _skipped, _exit, partial, partial_exit in ALL_SKIPPED_CASES:
            with self.subTest(sig=sig):
                self.assertIsNone(runcheck.ran_no_tests(partial, "", partial_exit))

    def test_a_failing_exit_is_not_named(self) -> None:
        for sig, skipped, _exit, _partial, _partial_exit in ALL_SKIPPED_CASES:
            with self.subTest(sig=sig):
                self.assertIsNone(runcheck.ran_no_tests(skipped, "", 1))

    def test_zero_test_output_keeps_its_signature(self) -> None:
        for sig, zero, zero_exit, _real, _real_exit in SIGNATURE_CASES:
            with self.subTest(sig=sig):
                self.assertEqual(runcheck.ran_no_tests(zero, "", zero_exit), sig)

    def test_prose_quoting_a_summary_does_not_count(self) -> None:
        for text in ("we saw 3 skipped in 0.1s", "the line `Tests: 3 skipped, 3 total`",
                     "a SKIP --- SKIP: TestA", "the 3 skipped tests",
                     "see test result: ok. 0 passed; 0 failed; 2 ignored;"):
            with self.subTest(text=text):
                self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_pytest_variants(self) -> None:
        for text in ("3 skipped in 0.00s\n", "2 skipped, 1 deselected in 0.00s\n",
                     "==== 3 skipped, 2 warnings in 0.10s ====\n",
                     "==== 1 skipped, 1 deselected, 1 warning in 61.00s (0:01:01) ====\n"):
            with self.subTest(text=text):
                self.assertEqual(runcheck.ran_no_tests(text, "", 0), "pytest-all-skipped")

    def test_pytest_expected_failures_count_as_run(self) -> None:
        for text in ("==== 3 skipped, 1 xfailed in 0.10s ====\n",
                     "==== 3 skipped, 1 xpassed in 0.10s ====\n",
                     "==== 1 xfailed in 0.10s ====\n"):
            with self.subTest(text=text):
                self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_pytest_qq_prints_no_summary_and_is_undetectable(self) -> None:
        self.assertIsNone(runcheck.ran_no_tests("sss                [100%]\n", "", 0))

    def test_unittest_variants(self) -> None:
        sep = "-" * 70
        named = (
            ("s" * 12 + "\n" + sep + "\nRan 12 tests in 0.004s\n\nOK (skipped=12)\n", 0),
            ("ss\r\n" + sep + "\r\nRan 2 tests in 0.000s\r\n\r\nOK (skipped=2)\r\n", 0),
            ("s\n" + sep + "\nRan 0 tests in 0.000s\n\nOK (skipped=1)\n", 0),
            ("s\n" + sep + "\nRan 0 tests in 0.000s\n\nNO TESTS RAN (skipped=1)\n", 5),
            ("ss\n" + sep + "\nRan 2 tests in 0.000s\n\nOK (skipped=2)\n", 5),
            # verbose; a reason holding a quote is printed with double quotes
            ("test_a (m.T.test_a) ... skipped \"don't\"\n\n" + sep +
             "\nRan 1 test in 0.000s\n\nOK (skipped=1)\n", 0),
        )
        for text, code in named:
            with self.subTest(text=text):
                self.assertEqual(runcheck.ran_no_tests("", text, code), "unittest-all-skipped")
        for text in ("Ran 3 tests in 0.000s\n\nOK (skipped=2, expected failures=1)\n",
                     "Ran 22 tests in 0.000s\n\nOK (skipped=2)\n",
                     "Ran 2 tests in 0.000s\n\nOK (skipped=22)\n",
                     # setUpClass SkipTest: more skips than runs; documented as undetectable
                     "Ran 2 tests in 0.000s\n\nOK (skipped=3)\n"):
            with self.subTest(text=text):
                self.assertIsNone(runcheck.ran_no_tests("", text, 0))

    def test_jest_and_vitest_todo_counts_with_skipped(self) -> None:
        self.assertEqual(runcheck.ran_no_tests("Tests:       2 skipped, 1 todo, 3 total\n", "", 0),
                         "jest-all-skipped")
        self.assertEqual(runcheck.ran_no_tests("Tests:       1 todo, 1 total\n", "", 0),
                         "jest-all-skipped")
        self.assertEqual(runcheck.ran_no_tests("      Tests  2 skipped | 1 todo (3)\n", "", 0),
                         "vitest-all-skipped")
        self.assertEqual(runcheck.ran_no_tests("      Tests 1 todo (1)\n", "", 0),
                         "vitest-all-skipped")
        self.assertIsNone(runcheck.ran_no_tests(
            "      Tests  1 expected fail | 2 skipped (3)\n", "", 0))

    def test_playwright_flaky_counts_as_run(self) -> None:
        text = "Running 3 tests using 1 worker\n  1 flaky\n  2 skipped\n"
        self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_a_skipped_title_ending_in_ok_is_still_caught(self) -> None:
        # unittest's `ok` positive counts only a bare `ok` line or one after
        # ` ... `, so another runner's skipped test titled "... ok" is no pass.
        cases = (
            ("playwright-all-skipped",
             "\nRunning 2 tests using 1 worker\n\n"
             "  -  1 [chromium] \u203a a.spec.ts:3:5 \u203a status is ok\n"
             "  -  2 [chromium] \u203a a.spec.ts:4:5 \u203a health ok\n\n  2 skipped\n"),
            ("vitest-all-skipped",
             " \u2193 src/a.test.ts > status is ok\n\n Test Files  1 skipped (1)\n"
             "      Tests  1 skipped (1)\n"),
            ("jest-all-skipped",
             "  api\n    \u25cb skipped status is ok\n\nTests:       1 skipped, 1 total\n"),
            ("mocha-all-pending", "  api\n    - status is ok\n\n\n  0 passing (2ms)\n  1 pending\n"),
        )
        for sig, text in cases:
            with self.subTest(sig=sig):
                self.assertEqual(runcheck.ran_no_tests(text, "", 0), sig)

    def test_playwright_needs_its_own_header(self) -> None:
        # A bare `N skipped` line from some other tool is not Playwright's.
        self.assertIsNone(runcheck.ran_no_tests("  5 tests passed\n  2 skipped\n", "", 0))
        self.assertIsNone(runcheck.ran_no_tests("  2 skipped\n", "", 0))

    def test_playwright_list_line_and_dot_reporters(self) -> None:
        for text in (
                "\nRunning 3 tests using 2 workers\n\n  -  1 [chromium] › a.spec.ts:3:5 › x\n"
                "\n  3 skipped\n",
                "\nRunning 1 test using 1 worker\n\n  1 skipped\n",
                "\nRunning 4 tests using 2 workers, shard 1 of 2\n°°°°\n\n  4 skipped\n"):
            with self.subTest(text=text):
                self.assertEqual(runcheck.ran_no_tests(text, "", 0), "playwright-all-skipped")

    def test_node_test_todo_only_and_tap(self) -> None:
        todo = "# tests 2\n# suites 0\n# pass 0\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 2\n"
        self.assertEqual(runcheck.ran_no_tests(todo, "", 0), "node-test-all-skipped")
        nothing = "# tests 0\n# suites 1\n# pass 0\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n"
        self.assertEqual(runcheck.ran_no_tests(nothing, "", 0), "node-test")

    def test_mocha_all_pending_was_already_caught_and_is_now_worded(self) -> None:
        text = "\n  0 passing (2ms)\n  3 pending\n\n"
        self.assertEqual(runcheck.ran_no_tests(text, "", 0), "mocha-all-pending")
        self.assertEqual(runcheck.ran_no_tests("\n  0 passing (1ms)\n\n", "", 0), "mocha")

    def test_go_subtests_and_non_verbose(self) -> None:
        sub = ("=== RUN   TestA\n=== RUN   TestA/x\n    --- SKIP: TestA/x (0.00s)\n"
               "--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n")
        self.assertEqual(runcheck.ran_no_tests(sub, "", 0), "go-all-skipped")
        # The testing package reports a parent whose subtests all skip as PASS.
        parent = ("=== RUN   TestA\n=== RUN   TestA/x\n    --- SKIP: TestA/x (0.00s)\n"
                  "--- PASS: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n")
        self.assertIsNone(runcheck.ran_no_tests(parent, "", 0))
        # Without -v an all-skipped package prints only its ok line: undetectable.
        self.assertIsNone(runcheck.ran_no_tests("ok  \tm/a\t0.01s\n", "", 0))
        # Another package that ran tests (non-verbose ok line) still vetoes.
        mixed = "ok  \tm/b\t0.02s\n--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n"
        self.assertIsNone(runcheck.ran_no_tests(mixed, "", 0))

    def test_cargo_benchmarks_count_as_run(self) -> None:
        text = ("running 0 tests\n\n"
                "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n\n"
                "running 3 tests\ntest b1 ... bench:         120 ns/iter (+/- 3)\n\n"
                "test result: ok. 0 passed; 0 failed; 0 ignored; 3 measured; 0 filtered out\n")
        self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_go_a_later_package_that_passes_vetoes(self) -> None:
        # `go test -v ./a && go test` (local directory mode, no -v): the second
        # prints PASS then ok, which is a pass.
        chained = ("=== RUN   TestA\n--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n"
                   "PASS\nok  \tm/b\t0.02s\n")
        self.assertIsNone(runcheck.ran_no_tests(chained, "", 0))
        first = ("PASS\nok  \tm/b\t0.02s\n"
                 "=== RUN   TestA\n--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n")
        self.assertIsNone(runcheck.ran_no_tests(first, "", 0))
        logged = ("hello from a test\nPASS\nok  \tm/b\t0.02s\n"
                  "--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t0.01s\n")
        self.assertIsNone(runcheck.ran_no_tests(logged, "", 0))

    def test_go_verbose_all_skipped_still_named_after_its_pass_line(self) -> None:
        text = ("=== RUN   TestA\n=== RUN   TestA/x\n    --- SKIP: TestA/x (0.00s)\n"
                "--- SKIP: TestA (0.00s)\nPASS\nok  \tm/a\t(cached)\n")
        self.assertEqual(runcheck.ran_no_tests(text, "", 0), "go-all-skipped")

    def test_a_pass_anywhere_vetoes_a_chained_command(self) -> None:
        # Conservative by design: `a && b` with one side all skipped stays ok.
        text = "==== 3 skipped in 0.01s ====\n  4 passing (9ms)\n"
        self.assertIsNone(runcheck.ran_no_tests(text, "", 0))

    def test_cargo_ignored_units_and_empty_doc_tests(self) -> None:
        text = ("running 2 tests\ntest a ... ignored\ntest b ... ignored\n\n"
                "test result: ok. 0 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out\n\n"
                "   Doc-tests app\n\nrunning 0 tests\n\n"
                "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n")
        self.assertEqual(runcheck.ran_no_tests(text, "", 0), "cargo-all-ignored")

    def test_collected_but_skipped_no_longer_vetoes_a_zero_run(self) -> None:
        # Positives count tests that ran; a skipped unittest run beside an
        # empty pytest run proved nothing.
        text = "Ran 2 tests in 0.000s\n\nOK (skipped=2)\n"
        # Signatures are tried in file order, and pytest's come first.
        self.assertEqual(runcheck.ran_no_tests(text, "no tests ran in 0.01s\n", 0), "pytest")


#: Multi-megabyte outputs shaped to make a careless pattern rescan the rest of
#: the text from every line start (``^\s*`` crosses newlines under MULTILINE).
ADVERSARIAL_OUTPUTS = (
    "\n" * (2 * 1024 * 1024),
    " \n" * (1024 * 1024),
    "\r\n" * (1024 * 1024),
    "=" * (2 * 1024 * 1024),
    "Ran 1 tests in 0.000s\n" * 100000,
    "# pass 0\n# fail 0\n# cancelled 0\n" * 60000,
    "ok  \tm\t" + " " * (2 * 1024 * 1024),
    "1 skipped, " * 200000,
    "--- " * 500000,
    "Running 1 test using 1 worker\n" * 70000,
)
#: Per pattern per output. Linear matching takes milliseconds here; the
#: quadratic `^\s*` form took minutes on the first output.
LINEAR_BOUND_S = 1.0


class TestPatternsAreLinear(unittest.TestCase):
    def test_every_pattern_and_positive_on_huge_output(self) -> None:
        import re
        import time
        path = paths.plugin_root() / "spec-kit" / "no-tests-signatures.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for sig in data["signatures"]:
            for key in ("pattern", "positive", "requires"):
                if key not in sig:
                    continue
                compiled = re.compile(sig[key], re.MULTILINE)
                for index, text in enumerate(ADVERSARIAL_OUTPUTS):
                    with self.subTest(sig=sig["id"], key=key, output=index):
                        started = time.perf_counter()
                        compiled.search(text)
                        self.assertLess(time.perf_counter() - started, LINEAR_BOUND_S)

    def test_ran_no_tests_on_huge_output(self) -> None:
        # Linear, not fast: doubling the output must not much more than double
        # the time. An absolute bound failed on a slow CI runner (4.1 s for
        # 6 MB on Python 3.9); a quadratic pattern grows ~4x per doubling.
        import time

        def timed(megabytes: int) -> float:
            text = "\n" * (megabytes * 1024 * 1024) + "3 skipped in 0.01s\n"
            started = time.perf_counter()
            runcheck.ran_no_tests(text, " \n" * (megabytes * 256 * 1024), 0)
            return time.perf_counter() - started

        timed(1)  # warm the signature cache
        small = min(timed(1) for _ in range(2))
        large = min(timed(2) for _ in range(2))
        self.assertLess(large, 3.0 * small + 0.05)


NPM_ENOENT = (
    "npm error code ENOENT\n"
    "npm error syscall open\n"
    "npm error path {root}/package.json\n"
    "npm error errno -2\n"
    "npm error enoent Could not read package.json: Error: ENOENT: no such file or "
    "directory, open '{root}/package.json'\n"
    "npm error enoent This is related to npm not being able to find a file.\n"
)


class TestMissingPaths(unittest.TestCase):
    def test_the_study_gallery_npm_error(self) -> None:
        text = NPM_ENOENT.format(root="/work/app")
        self.assertEqual(runcheck.missing_paths(text), ["/work/app/package.json"])
        self.assertTrue(runcheck.is_missing_manifest(text))

    def test_python_cannot_open_its_script(self) -> None:
        text = "python3: can't open file '/work/app/tests/run.py': [Errno 2] No such file or directory\n"
        self.assertEqual(runcheck.missing_paths(text), ["/work/app/tests/run.py"])

    def test_a_shell_style_line(self) -> None:
        self.assertEqual(runcheck.missing_paths("cat: src/a.txt: No such file or directory"),
                         ["src/a.txt"])
        self.assertEqual(runcheck.missing_paths("bash: ./run.sh: No such file or directory"),
                         ["./run.sh"])

    def test_a_python_file_not_found_error(self) -> None:
        text = "FileNotFoundError: [Errno 2] No such file or directory: 'data/out.csv'"
        self.assertEqual(runcheck.missing_paths(text), ["data/out.csv"])

    def test_no_module_named_is_not_a_path(self) -> None:
        self.assertEqual(runcheck.missing_paths("ModuleNotFoundError: No module named 'app'"), [])
        self.assertFalse(runcheck.is_missing_manifest("No module named 'app'"))

    def test_windows_style_messages(self) -> None:
        node = "Error: ENOENT: no such file or directory, open 'C:\\work\\app\\package.json'"
        self.assertEqual(runcheck.missing_paths(node), ["C:\\work\\app\\package.json"])
        # Python prints the path through repr(), doubling each backslash.
        py = "python.exe: can't open file 'C:\\\\work\\\\app\\\\run.py': [Errno 2] No such file or directory"
        self.assertEqual(runcheck.missing_paths(py), ["C:\\work\\app\\run.py"])

    def test_node_cannot_find_a_module_path(self) -> None:
        text = "Error: Cannot find module '/work/app/scripts/e2e.js'\n    at Module._resolve"
        self.assertEqual(runcheck.missing_paths(text), ["/work/app/scripts/e2e.js"])
        self.assertEqual(runcheck.missing_paths("Error: Cannot find module './lib/x'"),
                         ["./lib/x"])

    def test_a_bare_package_name_is_not_a_path(self) -> None:
        self.assertEqual(runcheck.missing_paths("Error: Cannot find module 'express'"), [])
        self.assertEqual(runcheck.missing_paths("Error: Cannot find module '@scope/pkg'"), [])

    def test_a_bare_module_named_in_argv_counts(self) -> None:
        text = "Error: Cannot find module 'e2e'"
        self.assertEqual(runcheck.missing_paths(text, argv=["node", "e2e"]), ["e2e"])

    def test_pytest_file_or_directory_not_found(self) -> None:
        text = "ERROR: file or directory not found: tests/test_login.py\n"
        self.assertEqual(runcheck.missing_paths(text), ["tests/test_login.py"])

    def test_an_ambiguous_path_with_spaces_is_not_extracted(self) -> None:
        self.assertEqual(runcheck.missing_paths("cat: my dir/a.txt: No such file or directory"), [])
        self.assertEqual(runcheck.missing_paths("cat: a.txt: No such file or directory"), ["a.txt"])
        self.assertEqual(runcheck.missing_paths("  oops x y.txt: No such file or directory"), [])

    def test_each_path_once(self) -> None:
        text = NPM_ENOENT.format(root="/r") * 2
        self.assertEqual(runcheck.missing_paths(text), ["/r/package.json"])


class TestRelativize(unittest.TestCase):
    def test_under_the_root(self) -> None:
        self.assertEqual(runcheck.relativize("/work/app/package.json", "/work/app"), "package.json")
        self.assertEqual(runcheck.relativize("/work/app/e2e/a.ts", "/work/app/"), "e2e/a.ts")

    def test_relative_paths_are_relative_to_the_root(self) -> None:
        self.assertEqual(runcheck.relativize("package.json", "/work/app"), "package.json")
        self.assertEqual(runcheck.relativize("./src/x.py", "/work/app"), "src/x.py")

    def test_dot_dot_segments_are_normalized(self) -> None:
        self.assertEqual(runcheck.relativize("/r/web/../src/a.ts", "/r"), "src/a.ts")
        self.assertEqual(runcheck.relativize("src/../lib/a.ts", "/r"), "lib/a.ts")
        self.assertIsNone(runcheck.relativize("/r/../etc/x", "/r"))
        self.assertEqual(runcheck.relativize("C:\\r\\web\\..\\src\\a.ts", "C:\\r"), "src/a.ts")

    def test_a_symlinked_path_matches_its_realpath_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(os.path.realpath(tmp), "real")
            os.makedirs(os.path.join(real, "src"))
            link = os.path.join(os.path.realpath(tmp), "link")
            symlink_or_skip(self, real, link)
            # the message names the symlinked form; the root is the real one
            self.assertEqual(runcheck.relativize(link + "/src/missing.json", real),
                             "src/missing.json")

    def test_outside_the_root_is_none(self) -> None:
        self.assertIsNone(runcheck.relativize("/etc/hosts", "/work/app"))
        self.assertIsNone(runcheck.relativize("/work/application/x", "/work/app"))
        self.assertIsNone(runcheck.relativize("../other/x", "/work/app"))
        self.assertIsNone(runcheck.relativize("/work/app", "/work/app"))

    def test_windows_paths(self) -> None:
        self.assertEqual(runcheck.relativize("C:\\work\\app\\package.json", "C:\\work\\app"),
                         "package.json")
        self.assertEqual(runcheck.relativize("c:\\Work\\App\\src\\x.ts", "C:\\work\\app"),
                         "src/x.ts")
        self.assertIsNone(runcheck.relativize("D:\\work\\app\\x", "C:\\work\\app"))
        self.assertEqual(runcheck.relativize("src\\x.ts", "C:\\work\\app"), "src/x.ts")


class TestScopeOwner(unittest.TestCase):
    TASKS = [
        {"id": "shell-login", "write_scope": ["package.json", "src/app/**"]},
        {"id": "e2e", "write_scope": ["e2e/*.spec.ts"]},
        {"id": "survey", "write_scope": "read-only"},
    ]

    def test_the_first_covering_task_is_named(self) -> None:
        self.assertEqual(runcheck.scope_owner("package.json", self.TASKS), "shell-login")
        self.assertEqual(runcheck.scope_owner("src/app/page.tsx", self.TASKS), "shell-login")
        self.assertEqual(runcheck.scope_owner("e2e/login.spec.ts", self.TASKS), "e2e")

    def test_uncovered_paths_have_no_owner(self) -> None:
        self.assertIsNone(runcheck.scope_owner("e2e/nested/x.spec.ts", self.TASKS))
        self.assertIsNone(runcheck.scope_owner("README.md", self.TASKS))
        self.assertIsNone(runcheck.scope_owner("anything", []))
        self.assertIsNone(runcheck.scope_owner("anything", None))

    def test_missing_path_owner_reads_both_streams(self) -> None:
        gate = {"verdict": "fail", "exit": 254, "stdout_tail": "",
                "stderr_tail": NPM_ENOENT.format(root="/work/app")}
        found = runcheck.missing_path_owner(gate, "/work/app", self.TASKS)
        self.assertEqual(found, {"path": "package.json", "owner": "shell-login",
                                 "manifest": True, "argv_named": False})

    def test_missing_path_owner_outside_the_root(self) -> None:
        gate = {"verdict": "fail", "exit": 1, "stdout_tail": "",
                "stderr_tail": "cat: /etc/gatebound.conf: No such file or directory"}
        found = runcheck.missing_path_owner(gate, "/work/app", self.TASKS)
        self.assertEqual(found, {"path": "/etc/gatebound.conf", "owner": None,
                                 "manifest": False, "argv_named": False})

    def test_a_manifest_refusal_names_package_json(self) -> None:
        gate = {"verdict": "fail", "exit": 254, "stdout_tail": "",
                "stderr_tail": "npm error enoent Could not read package.json: Error: ENOENT: "
                               "no such file or directory, open '/work/app/.npmrc'\n"
                               "npm error enoent Error: ENOENT: no such file or directory, "
                               "open '/work/app/package.json'\n"}
        found = runcheck.missing_path_owner(gate, "/work/app", [])
        self.assertEqual(found["path"], "package.json")
        self.assertTrue(found["manifest"])
        bare = {"verdict": "fail", "exit": 254, "stdout_tail": "",
                "stderr_tail": "npm error enoent Could not read package.json\n"
                               "cat: other.txt: No such file or directory\n"}
        self.assertEqual(runcheck.missing_path_owner(bare, "/work/app", [])["path"], "package.json")

    def test_argv_named_is_reported(self) -> None:
        gate = {"verdict": "fail", "exit": 127, "stdout_tail": "",
                "stderr_tail": "bash: scripts/e2e.sh: No such file or directory\n"}
        tasks = [{"id": "e2e", "write_scope": ["scripts/**"]}]
        found = runcheck.missing_path_owner(gate, "/work/app", tasks,
                                            argv=["bash", "scripts/e2e.sh"])
        self.assertEqual((found["path"], found["owner"], found["argv_named"]),
                         ("scripts/e2e.sh", "e2e", True))
        self.assertFalse(runcheck.missing_path_owner(gate, "/work/app", tasks,
                                                     argv=["bash", "-c", "x"])["argv_named"])

    def test_a_program_under_a_dependency_dir(self) -> None:
        tasks = [{"id": "shell", "write_scope": ["package.json", "src/**"]},
                 {"id": "py", "write_scope": ["pyproject.toml"]}]
        dep = runcheck.dependency_program("./node_modules/.bin/playwright", "/work/app", tasks)
        self.assertEqual((dep["dir"], dep["manifest"], dep["owner"]),
                         ("node_modules", "package.json", "shell"))
        dep = runcheck.dependency_program(".venv/bin/pytest", "/work/app", tasks)
        self.assertEqual((dep["dir"], dep["manifest"], dep["owner"]),
                         (".venv", "pyproject.toml", "py"))
        dep = runcheck.dependency_program("web/node_modules/.bin/vite", "/work/app", tasks)
        self.assertEqual((dep["manifest"], dep["owner"]), ("web/package.json", None))
        dep = runcheck.dependency_program("venv/bin/pytest", "/work/app", [])
        self.assertEqual((dep["dir"], dep["owner"]), ("venv", None))
        self.assertIsNone(runcheck.dependency_program("bin/run-e2e", "/work/app", tasks))
        self.assertIsNone(runcheck.dependency_program("playwright", "/work/app", tasks))

    def test_dependency_dirs_are_ones_the_fingerprint_skips(self) -> None:
        from gatebound import contract
        self.assertTrue(set(runcheck.DEPENDENCY_MANIFESTS) <= contract.FINGERPRINT_SKIP_DIRS)

    def test_interpreters(self) -> None:
        for prog in ("bash", "/bin/sh", "zsh", "node", "python3", "/usr/bin/python3.12",
                     "python.exe", "ruby", "deno", "bun", "tsx", "ts-node"):
            self.assertTrue(runcheck.is_interpreter(prog), prog)
        for prog in ("npm", "npx", "pytest", "nonexistentprog", "jest", ""):
            self.assertFalse(runcheck.is_interpreter(prog), prog)

    def test_nothing_extracted_is_none(self) -> None:
        gate = {"verdict": "fail", "exit": 1, "stdout_tail": "1 failed", "stderr_tail": ""}
        self.assertIsNone(runcheck.missing_path_owner(gate, "/work/app", self.TASKS))


class TestGradingFiles(unittest.TestCase):
    """ADR-0023: the files a command names that do the judging."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        os.makedirs(os.path.join(self.root, "tests"))
        os.makedirs(os.path.join(self.root, "scripts"))
        for rel, body in (("tests/test_a.py", "a"), ("scripts/e2e.sh", "e"),
                          ("e2e.spec.ts", "s")):
            with open(os.path.join(self.root, rel), "w") as h:
                h.write(body)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def files(self, argv):
        return runcheck.grading_files(argv, self.root)

    def test_a_script_as_argv0(self) -> None:
        self.assertEqual(self.files(["./scripts/e2e.sh", "--fast"]), ["scripts/e2e.sh"])
        self.assertEqual(self.files(["scripts/e2e.sh"]), ["scripts/e2e.sh"])

    def test_a_spec_path_argument(self) -> None:
        self.assertEqual(self.files(["npx", "playwright", "test", "e2e.spec.ts"]),
                         ["e2e.spec.ts"])
        self.assertEqual(self.files(["python3", "-m", "pytest", "tests/test_a.py::test_x", "-q"]),
                         ["tests/test_a.py"])
        self.assertEqual(self.files(["python3", os.path.join(self.root, "tests", "test_a.py")]),
                         ["tests/test_a.py"])

    def write(self, rel: str, body: str = "x") -> None:
        full = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as h:
            h.write(body)

    def test_files_the_build_edits_are_not_grading_files(self) -> None:
        # F2: a brownfield check names the code it inspects; the build edits
        # or creates those files legitimately, so they do not judge anything.
        for rel in ("src/app.py", "src/x.js", "src/app.js", "src/index.ts", "app.db",
                    "dist/index.html", "scripts/e2e.sh"):
            self.write(rel)
        for argv in (["grep", "-q", "print", "src/app.py"],
                     ["eslint", "src/x.js"],
                     ["node", "--check", "src/app.js"],
                     ["tsc", "src/index.ts"],
                     ["sqlite3", "app.db", "select 1"],
                     ["test", "-f", "dist/index.html"],
                     ["grep", "-q", "<title>", "dist/index.html"],
                     ["python3", "src/app.py", "--selftest"],
                     ["bash", "scripts/e2e.sh"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.files(argv), [])

    def test_test_shaped_files_are_grading_files(self) -> None:
        shapes = ("test/cart.js", "tests/check.py", "src/__tests__/x.js",
                  "spec/models/user_spec.rb", "e2e/login.ts", "pkg/test_util.py",
                  "pkg/util_test.go", "src/app.test.ts", "web/login.spec.ts",
                  "conftest.py", "a/b/test/deep/data.json")
        for rel in shapes:
            self.write(rel)
        for rel in shapes:
            with self.subTest(rel=rel):
                self.assertEqual(self.files(["runner", rel]), [rel])

    def test_gatebound_spec_folder_counts_only_test_shaped_basenames(self) -> None:
        # Review F3: `spec` as a test directory also matched gatebound's own
        # top-level spec/, so a design or token update after approval held
        # back the criteria that read those files.
        for rel in ("spec/tokens.json", "spec/02-design.md", "spec/05-gate.md",
                    "spec/e2e/flow.json", "spec/models/user_spec.rb",
                    "spec/test_login.py", "app/spec/helper.rb", "scripts/check.js"):
            self.write(rel)
        self.assertEqual(self.files(["cat", "spec/tokens.json"]), [])
        self.assertEqual(self.files(["node", "scripts/check.js", "spec/02-design.md"]), [])
        self.assertEqual(self.files(["runner", "spec/05-gate.md", "spec/e2e/flow.json"]), [])
        self.assertEqual(self.files(["rspec", "spec/models/user_spec.rb"]),
                         ["spec/models/user_spec.rb"])
        self.assertEqual(self.files(["pytest", "spec/test_login.py"]), ["spec/test_login.py"])
        # A nested spec/ is still a test directory; argv[0] is still a script.
        self.assertEqual(self.files(["ruby", "app/spec/helper.rb"]), ["app/spec/helper.rb"])
        self.write("spec/check.sh")
        self.assertEqual(self.files(["spec/check.sh"]), ["spec/check.sh"])

    def test_build_and_dependency_directories_never_count(self) -> None:
        for rel in ("dist/tests/app.test.js", "node_modules/.bin/vitest",
                    ".venv/bin/pytest", "build/test_x.py"):
            self.write(rel)
        self.assertEqual(self.files(["node", "dist/tests/app.test.js", "build/test_x.py"]), [])
        self.assertEqual(self.files(["./node_modules/.bin/vitest", "run"]), [])
        self.assertEqual(self.files([".venv/bin/pytest"]), [])

    def test_option_values_and_runner_suffixes(self) -> None:
        # F7: `--opt=path`, pytest `[param]` and `file:line` locations.
        self.write("e2e/login.spec.ts")
        self.write("src/app.test.ts")
        self.assertEqual(self.files(["npx", "playwright", "test", "--spec=e2e/login.spec.ts"]),
                         ["e2e/login.spec.ts"])
        self.assertEqual(self.files(["pytest", "tests/test_a.py::test_x[1-2]"]),
                         ["tests/test_a.py"])
        self.assertEqual(self.files(["pytest", "tests/test_a.py[x]"]), ["tests/test_a.py"])
        self.assertEqual(self.files(["npx", "vitest", "src/app.test.ts:12"]),
                         ["src/app.test.ts"])
        self.assertEqual(self.files(["npx", "jest", "src/app.test.ts:12:5"]),
                         ["src/app.test.ts"])
        self.assertEqual(self.files(["runner", "--config=jest.config.js", "--fast"]), [])

    def test_the_patterns_come_from_the_data_file(self) -> None:
        data = runcheck.grading_patterns()
        self.assertIn("tests", data["dirs"])
        self.assertIn("*.spec.*", data["basenames"])
        self.assertIn("node_modules", data["exclude_dirs"])

    def test_a_bare_program_is_not_a_grading_file(self) -> None:
        # Even when a file of that name sits in the root.
        with open(os.path.join(self.root, "pytest"), "w") as h:
            h.write("x")
        self.assertEqual(self.files(["pytest"]), [])
        self.assertEqual(self.files(["npm", "test"]), [])

    def test_outside_the_root_and_dot_dot(self) -> None:
        outside = os.path.join(os.path.dirname(self.root), "elsewhere.py")
        self.assertEqual(self.files(["python3", outside, "/etc/hosts"]), [])
        self.assertEqual(self.files(["python3", "../x.py", "tests/../../x.py"]), [])
        self.assertEqual(self.files(["python3", "tests/../tests/test_a.py"]), ["tests/test_a.py"])

    def test_a_symlink_out_of_the_root(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False) as h:
            h.write("x")
        try:
            symlink_or_skip(self, h.name, os.path.join(self.root, "tests", "link.py"))
            self.assertEqual(self.files(["python3", "tests/link.py"]), [])
        finally:
            os.unlink(h.name)

    def test_missing_files_and_directories(self) -> None:
        self.assertEqual(self.files(["python3", "tests/nope.py", "tests", "."]), [])

    def test_the_plugin_root_token_is_expanded(self) -> None:
        plugin = os.path.join(self.root, "plug")
        os.makedirs(os.path.join(plugin, ".claude-plugin"))
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w") as h:
            h.write("{}")
        with open(os.path.join(plugin, "test_check.py"), "w") as h:
            h.write("x")
        old = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin
        try:
            self.assertEqual(self.files(["python3", "${CLAUDE_PLUGIN_ROOT}/test_check.py"]),
                             ["plug/test_check.py"])
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old

    def test_each_once_and_hashed(self) -> None:
        hashes = runcheck.grading_hashes(["./scripts/e2e.sh", "./scripts/e2e.sh",
                                          "tests/test_a.py"], self.root)
        import hashlib
        self.assertEqual(hashes, {"scripts/e2e.sh": hashlib.sha256(b"e").hexdigest(),
                                  "tests/test_a.py": hashlib.sha256(b"a").hexdigest()})

    def test_a_large_file_hashes_in_chunks(self) -> None:
        import hashlib
        body = b"x" * (3 * 1024 * 1024 + 7)
        with open(os.path.join(self.root, "tests", "test_big.py"), "wb") as h:
            h.write(body)
        hashes = runcheck.grading_hashes(["pytest", "tests/test_big.py"], self.root)
        self.assertEqual(hashes, {"tests/test_big.py": hashlib.sha256(body).hexdigest()})
        self.assertEqual(runcheck.changed_grading(hashes, self.root), [])

    def test_never_raises(self) -> None:
        self.assertEqual(runcheck.grading_hashes(None, self.root), {})
        self.assertEqual(runcheck.grading_hashes([3, None, "\x00bad"], self.root), {})


class TestDecodeOutput(unittest.TestCase):
    """A command's output is judged as text, so decoding must never lose it.
    UTF-8 first (Node, Playwright), then the locale codec (a child Python or a
    Windows tool printing a cp949 path), then UTF-8 with replacement."""

    def test_utf8(self) -> None:
        self.assertEqual(runcheck.decode_output("✔ 3 passed".encode("utf-8")), "✔ 3 passed")

    def test_locale_codec_when_not_utf8(self) -> None:
        raw = "/data/홍길동/package.json 없음".encode("cp949")
        with mock.patch.object(runcheck.locale, "getpreferredencoding", return_value="cp949"):
            self.assertEqual(runcheck.decode_output(raw), "/data/홍길동/package.json 없음")

    def test_replacement_as_the_last_resort(self) -> None:
        with mock.patch.object(runcheck.locale, "getpreferredencoding", return_value="no-such-codec"):
            self.assertEqual(runcheck.decode_output(b"\xffOK"), "�OK")

    def test_nothing_is_empty_text(self) -> None:
        self.assertEqual(runcheck.decode_output(None), "")
        self.assertEqual(runcheck.decode_output(b""), "")


class TestStalePathHint(unittest.TestCase):
    """A program installed after the session started is on the registry PATH
    but not on this process's (observed: Node installed mid-session, every
    criterion `could not execute: node`). The hint says so; Windows only."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.bindir = self._tmp.name
        name = "gk-fresh-tool" + (".exe" if os.name == "nt" else "")
        path = os.path.join(self.bindir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        os.chmod(path, 0o755)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def hint(self, program: str, windows: bool = True, registry=None) -> str:
        with mock.patch.object(runcheck, "IS_WINDOWS", windows),                 mock.patch.object(runcheck, "_registry_path",
                                  return_value=self.bindir if registry is None else registry):
            return runcheck.stale_path_hint(program)

    def test_installed_but_not_on_this_path(self) -> None:
        text = self.hint("gk-fresh-tool")
        self.assertIn("not on this session's PATH", text)
        self.assertIn("new terminal", text)

    def test_nothing_to_say_elsewhere(self) -> None:
        self.assertEqual(self.hint("gk-fresh-tool", windows=False), "")
        self.assertEqual(self.hint("gk-not-installed-anywhere"), "")
        self.assertEqual(self.hint("gk-fresh-tool", registry=""), "")
        self.assertEqual(self.hint("./gk-fresh-tool"), "")
        self.assertEqual(self.hint(""), "")


if __name__ == "__main__":
    unittest.main()
