#!/usr/bin/env python3
"""Standalone checks for export_open_action_items.py (no omi install needed).

Runs the exporter against a fake `omi` implemented as a Python driver script
(fixture passed via a file path in the environment, so there is no
command-line length limit), covering: multi-page pagination, empty result,
Unicode preservation, malformed JSON, non-array body, non-object records,
CLI failure, a second-page failure proving the previous export file is left
unchanged with no temp file left behind, and a real subprocess fixture
producing Unicode.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORTER = os.path.join(HERE, "export_open_action_items.py")
if not os.path.exists(EXPORTER):  # when the test lives outside examples/
    EXPORTER = os.path.join(
        HERE, "sdks", "python-cli", "examples", "export_open_action_items.py"
    )

FAKE_OMI_DRIVER = r"""
import json, os, sys
fixture = os.environ["OMI_TEST_FIXTURE"]
mode = os.environ.get("OMI_TEST_MODE", "ok")
offset = int(sys.argv[sys.argv.index("--offset") + 1])
with open(fixture, encoding="utf-8") as fh:
    pages = json.load(fh)
page_index = offset // 500
emit_bad_json = (
    mode == "badjson"
    or (mode == "badpage2" and page_index == 1)
)
if emit_bad_json:
    sys.stdout.write("{not json")
    sys.exit(0)
if mode == "notarray":
    json.dump({"oops": 1}, sys.stdout)
    sys.exit(0)
if page_index >= len(pages):
    print("page out of range", file=sys.stderr)
    sys.exit(4)
page = pages[page_index]
if mode == "badrecord":
    json.dump(page + ["not-an-object"], sys.stdout)
    sys.exit(0)
json.dump(page, sys.stdout, ensure_ascii=False)
"""

ITEM = {
    "id": "a1b2c3d4",
    "description": "Fetch the weekly report",
    "created_at": "2026-09-11T00:00:00Z",
    "completed": False,
}


def run_export(args: list[str], env_extra: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, EXPORTER] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=120,
    )


class ExportOpenActionItemsTests(unittest.TestCase):
    def _setup_fake(self) -> tuple[str, str, str]:
        """Create driver script + fixture file in a temp dir.

        Returns (omi_bin, fixture_path, tmp_dir).
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        driver = os.path.join(tmp.name, "fake_omi.py")
        fixture = os.path.join(tmp.name, "fixture.json")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(FAKE_OMI_DRIVER)
        omi_bin = f"{shlex.quote(sys.executable)} {shlex.quote(driver)}"
        return omi_bin, fixture, tmp.name

    def _run(self, pages, mode="ok"):
        omi_bin, fixture, _ = self._setup_fake()
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump(pages, fh, ensure_ascii=False)
        dest = os.path.join(tempfile.gettempdir(), f"out_{id(self)}.jsonl")
        self.addCleanup(lambda: os.path.exists(dest) and os.unlink(dest))
        if os.path.exists(dest):
            os.unlink(dest)
        proc = run_export(
            [dest],
            {
                "OMI_BIN": omi_bin,
                "OMI_TEST_FIXTURE": fixture,
                "OMI_TEST_MODE": mode,
                "PYTHONIOENCODING": "utf-8",
            },
        )
        return proc, dest

    def test_multipage_pagination(self):
        page1 = [dict(ITEM, id=f"i{i:03d}") for i in range(500)]
        page2 = [dict(ITEM, id=f"j{i:03d}") for i in range(123)]
        proc, dest = self._run([page1, page2])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(dest, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 623)
        self.assertEqual(json.loads(lines[0])["id"], "i000")
        self.assertEqual(json.loads(lines[-1])["id"], "j122")

    def test_empty_result(self):
        proc, dest = self._run([[]])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(dest, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "")

    def test_unicode_preserved(self):
        items = [
            dict(ITEM, description="élément café — 日本語テキスト 🎧"),
            dict(ITEM, description="हिन्दी विवरण"),
        ]
        proc, dest = self._run([items])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(dest, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\\u", raw)  # ensure_ascii=False round-trip
        with open(dest, encoding="utf-8") as fh:
            back = [json.loads(line) for line in fh]
        self.assertEqual(back[0]["description"], items[0]["description"])
        self.assertEqual(back[1]["description"], items[1]["description"])

    def test_bad_json_aborts(self):
        proc, dest = self._run([[ITEM]], mode="badjson")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(dest))

    def test_non_array_body_aborts(self):
        proc, dest = self._run([[ITEM]], mode="notarray")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(dest))

    def test_non_object_record_aborts(self):
        proc, dest = self._run([[ITEM]], mode="badrecord")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(dest))

    def test_nan_infinity_json_rejected(self):
        """NaN/Infinity literals in CLI output must abort with exit 3, not emit exit-0 JSONL that strict parsers reject."""
        omi_bin, fixture, tmpname = self._setup_fake()
        dest = os.path.join(tmpname, "out.jsonl")
        with open(fixture, "w", encoding="utf-8") as fh:
            fh.write('[{"id": "x", "score": NaN}]')  # non-standard JSON literal
        env = os.environ.copy()
        env.update(
            {
                "OMI_BIN": omi_bin,
                "OMI_TEST_FIXTURE": fixture,
                "OMI_TEST_MODE": "ok",
                "PYTHONIOENCODING": "utf-8",
            }
        )
        proc = subprocess.run(
            [sys.executable, EXPORTER, dest],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(os.path.exists(dest))

    def test_cli_failure_aborts(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = os.path.join(tmp.name, "out.jsonl")
        proc = run_export([dest], {"OMI_BIN": "definitely-not-a-real-binary-xyz"})
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(os.path.exists(dest))

    def test_second_page_failure_leaves_previous_export_intact(self):
        omi_bin, fixture, tmpname = self._setup_fake()
        dest = os.path.join(tmpname, "out.jsonl")

        # first export: two pages succeed (500 + 10)
        good = [
            [dict(ITEM, id=f"a{i:03d}") for i in range(500)],
            [dict(ITEM, id=f"b{i:03d}") for i in range(10)],
        ]
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump(good, fh)
        proc1 = run_export(
            [dest],
            {"OMI_BIN": omi_bin, "OMI_TEST_FIXTURE": fixture, "OMI_TEST_MODE": "ok"},
        )
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        with open(dest, encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().splitlines()), 510)

        # second export: page 2 fails -> previous file untouched, no temp left
        bad = [
            [dict(ITEM, id=f"c{i:03d}") for i in range(500)],
            [dict(ITEM, id=f"d{i:03d}") for i in range(10)],
        ]
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        proc2 = run_export(
            [dest],
            {
                "OMI_BIN": omi_bin,
                "OMI_TEST_FIXTURE": fixture,
                "OMI_TEST_MODE": "badpage2",
            },
        )
        self.assertEqual(proc2.returncode, 3)
        with open(dest, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 510)
        self.assertEqual(json.loads(lines[0])["id"], "a000")
        leftovers = [
            f for f in os.listdir(tmpname) if f.startswith(".export_open_action_items.")
        ]
        self.assertEqual(leftovers, [])

    def test_real_subprocess_unicode_fixture(self):
        # end-to-end through a real subprocess stdout producing Unicode
        omi_bin, fixture, tmpname = self._setup_fake()
        dest = os.path.join(tmpname, "out.jsonl")
        items = [dict(ITEM, description="naïve — café 日本語 🎧")]
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump([items], fh, ensure_ascii=False)
        proc = run_export(
            [dest],
            {
                "OMI_BIN": omi_bin,
                "OMI_TEST_FIXTURE": fixture,
                "OMI_TEST_MODE": "ok",
                "PYTHONIOENCODING": "utf-8",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(dest, encoding="utf-8") as fh:
            back = json.loads(fh.readline())
        self.assertEqual(back["description"], "naïve — café 日本語 🎧")


if __name__ == "__main__":
    unittest.main(verbosity=2)
