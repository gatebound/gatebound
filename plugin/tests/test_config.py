"""Tests for gatebound.config — .gatebound/config.json loading with defaults."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# Make the `gatebound` package importable however this suite is discovered:
# `discover -s plugin/tests` loads tests as top-level modules and puts only
# `plugin/tests` on sys.path, so `plugin/` has to be added explicitly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatebound import config


class TempProject(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(os.path.realpath(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, obj: object) -> None:
        (self.root / ".gatebound").mkdir(exist_ok=True)
        (self.root / ".gatebound" / "config.json").write_text(
            json.dumps(obj), encoding="utf-8"
        )


class TestDefaults(TempProject):
    def test_missing_file_returns_defaults(self) -> None:
        cfg = config.load(self.root)
        self.assertEqual(cfg["version"], 1)
        self.assertTrue(cfg["enforce_spec_before_code"])
        self.assertEqual(cfg["worker"]["default"], "claude")
        self.assertTrue(cfg["worker"]["backends"]["claude"]["enabled"])
        self.assertFalse(cfg["worker"]["backends"]["codex"]["enabled"])
        self.assertEqual(cfg["build"]["max_retries"], 2)
        self.assertEqual(cfg["build"]["parallel"], 3)
        self.assertEqual(cfg["build"]["task_timeout_s"], 900)
        self.assertEqual(cfg["questions"]["interview_max_calls"], 2)
        self.assertEqual(cfg["questions"]["items_per_call"], 4)

    def test_load_does_not_mutate_module_defaults(self) -> None:
        cfg = config.load(self.root)
        cfg["worker"]["backends"]["claude"]["enabled"] = False
        cfg["build"]["max_retries"] = 99
        fresh = config.load(self.root)
        self.assertTrue(fresh["worker"]["backends"]["claude"]["enabled"])
        self.assertEqual(fresh["build"]["max_retries"], 2)
        self.assertEqual(config.DEFAULTS["build"]["max_retries"], 2)

    def test_defaults_never_disable_sandbox(self) -> None:
        for backend in config.DEFAULTS["worker"]["backends"].values():
            self.assertFalse(backend.get("unsafe", False))


class TestDeepMerge(TempProject):
    def test_partial_override_keeps_sibling_defaults(self) -> None:
        self.write_config({"build": {"parallel": 8}})
        cfg = config.load(self.root)
        self.assertEqual(cfg["build"]["parallel"], 8)
        self.assertEqual(cfg["build"]["max_retries"], 2)
        self.assertEqual(cfg["worker"]["default"], "claude")

    def test_nested_backend_override(self) -> None:
        self.write_config(
            {"worker": {"backends": {"codex": {"enabled": True}}}}
        )
        cfg = config.load(self.root)
        self.assertTrue(cfg["worker"]["backends"]["codex"]["enabled"])
        # argv default survives the partial override
        self.assertEqual(
            cfg["worker"]["backends"]["codex"]["argv"],
            config.DEFAULTS["worker"]["backends"]["codex"]["argv"],
        )
        self.assertTrue(cfg["worker"]["backends"]["claude"]["enabled"])

    def test_user_backend_is_added(self) -> None:
        self.write_config(
            {"worker": {"backends": {"mine": {"argv": ["mytool"], "enabled": True}}}}
        )
        cfg = config.load(self.root)
        self.assertEqual(cfg["worker"]["backends"]["mine"]["argv"], ["mytool"])
        self.assertIn("claude", cfg["worker"]["backends"])

    def test_list_is_replaced_not_merged(self) -> None:
        self.write_config({"worker": {"backends": {"claude": {"argv": ["x"]}}}})
        cfg = config.load(self.root)
        self.assertEqual(cfg["worker"]["backends"]["claude"]["argv"], ["x"])

    def test_enforce_flag_can_be_turned_off(self) -> None:
        self.write_config({"enforce_spec_before_code": False})
        self.assertFalse(config.load(self.root)["enforce_spec_before_code"])


class TestCorruptInput(TempProject):
    def test_invalid_json_falls_back_to_defaults(self) -> None:
        (self.root / ".gatebound").mkdir()
        (self.root / ".gatebound" / "config.json").write_text("{not json", encoding="utf-8")
        cfg = config.load(self.root)
        self.assertEqual(cfg["build"]["max_retries"], 2)

    def test_non_object_json_falls_back_to_defaults(self) -> None:
        self.write_config([1, 2, 3])
        self.assertTrue(config.load(self.root)["enforce_spec_before_code"])


class TestReplaceRetry(TempProject):
    """Windows refuses `os.replace` onto a file another process holds open
    (a worker or hook reading status.json or a ledger), with PermissionError
    (WinError 5). That is transient there, so every atomic write retries it;
    on POSIX a PermissionError is a real one and is raised at once."""

    def setUp(self) -> None:
        super().setUp()
        self.target = self.root / "state" / "x.json"
        self._saved = (config._REPLACE_ATTEMPTS, config._REPLACE_DELAY_S)
        config._REPLACE_ATTEMPTS, config._REPLACE_DELAY_S = 5, 0.0
        self.real_replace = os.replace
        self.calls = 0

    def tearDown(self) -> None:
        config._REPLACE_ATTEMPTS, config._REPLACE_DELAY_S = self._saved
        super().tearDown()

    def failing(self, times: int, exc: type = PermissionError):
        def replace(src, dst):
            self.calls += 1
            if self.calls <= times:
                raise exc(13, "simulated: file in use")
            return self.real_replace(src, dst)
        return mock.patch.object(config.os, "replace", side_effect=replace)

    def leftovers(self) -> list:
        return [p.name for p in self.target.parent.iterdir() if p.name.endswith(".tmp")]

    def test_a_transient_refusal_is_retried(self) -> None:
        with self.failing(2):
            config.write_json_atomic(self.target, {"a": 1})
        self.assertEqual(self.calls, 3)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), {"a": 1})
        self.assertEqual(self.leftovers(), [])

    def test_a_lasting_refusal_raises_and_keeps_the_old_file(self) -> None:
        config.write_json_atomic(self.target, {"old": True})
        with self.failing(99):
            with self.assertRaises(PermissionError):
                config.write_json_atomic(self.target, {"new": True})
        self.assertEqual(self.calls, 5)
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), {"old": True})
        self.assertEqual(self.leftovers(), [])

    def test_other_errors_are_not_retried(self) -> None:
        with self.failing(99, exc=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                config.write_json_atomic(self.target, {"a": 1})
        self.assertEqual(self.calls, 1)

    def test_a_single_attempt_raises_at_once(self) -> None:
        # The POSIX setting: one attempt, no retry.
        config._REPLACE_ATTEMPTS = 1
        with self.failing(1):
            with self.assertRaises(PermissionError):
                config.write_json_atomic(self.target, {"a": 1})
        self.assertEqual(self.calls, 1)

    def test_retries_only_on_windows_by_default(self) -> None:
        self.assertEqual(self._saved[0] > 1, os.name == "nt")


class TestSave(TempProject):
    def test_save_creates_dir_and_roundtrips(self) -> None:
        cfg = config.load(self.root)
        cfg["build"]["parallel"] = 5
        config.save(self.root, cfg)
        target = self.root / ".gatebound" / "config.json"
        self.assertTrue(target.is_file())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["build"]["parallel"], 5)
        self.assertEqual(config.load(self.root)["build"]["parallel"], 5)

    def test_save_leaves_no_tmp_files(self) -> None:
        config.save(self.root, config.load(self.root))
        leftovers = list((self.root / ".gatebound").glob("*.tmp*"))
        self.assertEqual(leftovers, [])

    def test_save_is_atomic_replace(self) -> None:
        config.save(self.root, {"version": 1, "marker": "first"})
        config.save(self.root, {"version": 1, "marker": "second"})
        data = json.loads((self.root / ".gatebound" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(data["marker"], "second")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
