"""Hermetic tests for export_conversations.py.

Runs the exporter against a fake `omi` CLI (a small Python driver script,
fixture pages supplied via an env var pointing at a file — no argv length
limits, no real network or install needed) covering: multi-page pagination,
empty result, Unicode preservation, malformed/invalid CLI output, CLI
failure, the --include-transcript flag reaching the subprocess, and that a
second-page failure leaves a previous export file untouched with no leaked
temp file.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "export_conversations.py"
spec = importlib.util.spec_from_file_location("export_conversations", script_path)
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

FAKE_OMI_DRIVER = r"""
import json, os, sys
fixture = os.environ["OMI_TEST_FIXTURE"]
mode = os.environ.get("OMI_TEST_MODE", "ok")
offset = int(sys.argv[sys.argv.index("--offset") + 1])
if "--include-transcript" in sys.argv and "OMI_TEST_FLAG_MARKER" in os.environ:
    with open(os.environ["OMI_TEST_FLAG_MARKER"], "w", encoding="utf-8") as marker:
        marker.write("seen")
with open(fixture, encoding="utf-8") as fh:
    pages = json.load(fh)
page_index = offset // 200
if mode == "badjson":
    sys.stdout.write("{not json")
    sys.exit(0)
if mode == "notarray":
    json.dump({"oops": 1}, sys.stdout)
    sys.exit(0)
if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(7)
if mode == "badpage2" and page_index == 1:
    sys.stdout.write("{not json")
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

ITEM = {"id": "c1", "title": "Standup", "started_at": "2026-09-11T00:00:00Z"}


class TestExportConversations(unittest.TestCase):
    def _fake_omi(self, tmp_dir, pages, mode="ok"):
        driver = os.path.join(tmp_dir, "fake_omi.py")
        fixture = os.path.join(tmp_dir, "fixture.json")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(FAKE_OMI_DRIVER)
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump(pages, fh, ensure_ascii=False)
        omi_bin = f"{shlex.quote(sys.executable)} {shlex.quote(driver)}"
        return {"OMI_BIN": omi_bin, "OMI_TEST_FIXTURE": fixture, "OMI_TEST_MODE": mode}

    def _run_module(self, destination, include_transcript, env_extra):
        """Invoke export_conversations() in-process against a fake CLI subprocess."""
        old_env = {k: os.environ.get(k) for k in env_extra}
        os.environ.update(env_extra)
        try:
            return ec.export_conversations(destination, include_transcript)
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_multipage_pagination(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            page1 = [dict(ITEM, id=f"c{i:03d}") for i in range(200)]
            page2 = [dict(ITEM, id=f"d{i:03d}") for i in range(37)]
            env = self._fake_omi(tmp_dir, [page1, page2])
            dest = os.path.join(tmp_dir, "out.jsonl")

            count = self._run_module(dest, False, env)
            self.assertEqual(count, 237)

            with open(dest, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), 237)
            self.assertEqual(json.loads(lines[0])["id"], "c000")
            self.assertEqual(json.loads(lines[-1])["id"], "d036")

    def test_empty_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, [[]])
            dest = os.path.join(tmp_dir, "out.jsonl")
            count = self._run_module(dest, False, env)
            self.assertEqual(count, 0)
            self.assertEqual(Path(dest).read_text(encoding="utf-8"), "")

    def test_unicode_preserved(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            items = [dict(ITEM, title="日本語のタイトル — café 🎧")]
            env = self._fake_omi(tmp_dir, [items])
            dest = os.path.join(tmp_dir, "out.jsonl")
            self._run_module(dest, False, env)
            raw = Path(dest).read_bytes()
            self.assertNotIn(b"\\u", raw)
            back = json.loads(Path(dest).read_text(encoding="utf-8"))
            self.assertEqual(back["title"], items[0]["title"])

    def test_include_transcript_flag_reaches_cli(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, [[dict(ITEM)]])
            marker = os.path.join(tmp_dir, "flag_seen")
            env["OMI_TEST_FLAG_MARKER"] = marker
            dest = os.path.join(tmp_dir, "out.jsonl")
            proc = subprocess.run(
                [sys.executable, str(script_path), dest, "--include-transcript"],
                env={**os.environ, **env},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(marker), "fake CLI did not see --include-transcript")

    def test_malformed_json_aborts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, [[dict(ITEM)]], mode="badjson")
            dest = os.path.join(tmp_dir, "out.jsonl")
            with self.assertRaises(ec.ExportError):
                self._run_module(dest, False, env)
            self.assertFalse(os.path.exists(dest))
            leftovers = [f for f in os.listdir(tmp_dir) if f.startswith(".export_conversations.")]
            self.assertEqual(leftovers, [])

    def test_non_array_body_aborts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, [[dict(ITEM)]], mode="notarray")
            dest = os.path.join(tmp_dir, "out.jsonl")
            with self.assertRaises(ec.ExportError):
                self._run_module(dest, False, env)

    def test_cli_failure_propagates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, [[dict(ITEM)]], mode="fail")
            dest = os.path.join(tmp_dir, "out.jsonl")
            with self.assertRaises(ec.ExportError) as ctx:
                self._run_module(dest, False, env)
            self.assertEqual(ctx.exception.exit_code, ec.EXIT_CLI_FAILED)

    def test_second_page_failure_leaves_previous_export_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = os.path.join(tmp_dir, "out.jsonl")
            Path(dest).write_text('{"id": "previous"}\n', encoding="utf-8")

            page1 = [dict(ITEM, id=f"c{i:03d}") for i in range(200)]
            page2 = [dict(ITEM, id="d000")]
            env = self._fake_omi(tmp_dir, [page1, page2], mode="badpage2")

            with self.assertRaises(ec.ExportError):
                self._run_module(dest, False, env)

            self.assertEqual(Path(dest).read_text(encoding="utf-8"), '{"id": "previous"}\n')
            leftovers = [f for f in os.listdir(tmp_dir) if f.startswith(".export_conversations.")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
