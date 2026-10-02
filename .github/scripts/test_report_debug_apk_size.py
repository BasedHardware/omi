#!/usr/bin/env python3
"""Tests for the coarse debug-APK size reporter. The reporter is never a gate."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("report_debug_apk_size", SCRIPT_DIR / "report_debug_apk_size.py")
assert SPEC and SPEC.loader
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class ReportDebugApkSizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_apk(self) -> Path:
        apk = self.root / "app-dev-debug.apk"
        with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("lib/arm64-v8a/libapp.so", "n" * 4000)
            archive.writestr("assets/flutter_assets/AssetManifest.bin", "a" * 800)
            archive.writestr("classes.dex", "d" * 2000)
            archive.writestr("META-INF/MANIFEST.MF", "m" * 100)
            archive.writestr("kotlin/kotlin.kotlin_builtins", "k" * 50)
        return apk

    def test_buckets_top_level_zip_entries_and_never_gates_on_size(self) -> None:
        apk = self.write_apk()
        report = REPORT.analyze_apk(apk)

        self.assertEqual(report["schema"], "omi-debug-apk-size-v1")
        self.assertFalse(report["representative"])
        self.assertGreater(int(report["apk_bytes"]), 0)
        names = [bucket["name"] for bucket in report["top_level"]]
        self.assertEqual(names[0], "lib")
        self.assertIn("assets", names)
        self.assertIn("classes.dex", names)
        lib = next(bucket for bucket in report["top_level"] if bucket["name"] == "lib")
        self.assertEqual(lib["entries"], 1)
        self.assertGreaterEqual(lib["uncompressed_bytes"], 4000)

    def test_cli_writes_json_and_summary_and_exits_zero(self) -> None:
        apk = self.write_apk()
        json_path = self.root / "report.json"
        summary = self.root / "summary.md"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = REPORT.main(["--apk", str(apk), "--json", str(json_path), "--summary", str(summary)])

        self.assertEqual(status, 0)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["apk_bytes"], apk.stat().st_size)
        markdown = summary.read_text(encoding="utf-8")
        self.assertIn("not a gate", markdown)
        self.assertIn("`lib`", markdown)
        self.assertIn(stdout.getvalue().splitlines()[0], markdown)

    def test_missing_apk_fails_closed_without_becoming_a_size_gate(self) -> None:
        missing = self.root / "nope.apk"
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            status = REPORT.main(["--apk", str(missing)])
        self.assertEqual(status, 2)
        self.assertIn("APK not found", stderr.getvalue())

    def test_source_has_no_size_threshold(self) -> None:
        source = (SCRIPT_DIR / "report_debug_apk_size.py").read_text(encoding="utf-8")
        self.assertNotIn("THRESHOLD", source)
        self.assertNotIn("max_bytes", source)
        self.assertIn("Never a gate", source)


if __name__ == "__main__":
    unittest.main()
