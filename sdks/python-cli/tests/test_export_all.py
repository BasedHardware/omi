"""Hermetic tests for export_all.py.

Runs the exporter against a fake `omi` CLI (a small Python driver script
routed by resource name via env vars) covering: bundle shape and counts,
malformed output aborting before any write, CLI failure, and overwrite
refusal.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "export_all.py"
spec = importlib.util.spec_from_file_location("export_all", script_path)
ea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ea)

FAKE_OMI_DRIVER = r"""
import json, os, sys
resource = sys.argv[2]  # argv: [fake_omi.py, "--json", resource, "list", ...]
mode = os.environ.get("OMI_TEST_MODE", "ok")
data = {
    "memory": [{"id": "m1"}],
    "conversation": [{"id": "c1"}, {"id": "c2"}],
    "action-item": [{"id": "a1"}],
    "goal": [],
}
if mode == "fail" and resource == "goal":
    print("boom", file=sys.stderr)
    sys.exit(7)
if mode == "badjson" and resource == "action-item":
    sys.stdout.write("{not json")
    sys.exit(0)
json.dump(data[resource], sys.stdout)
"""


class TestExportAll(unittest.TestCase):
    def _fake_omi(self, tmp_dir, mode="ok"):
        driver = os.path.join(tmp_dir, "fake_omi.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(FAKE_OMI_DRIVER)
        omi_bin = f"{shlex.quote(sys.executable)} {shlex.quote(driver)}"
        return {"OMI_BIN": omi_bin, "OMI_TEST_MODE": mode}

    def _run(self, destination, env_extra, limit=100):
        old_env = {k: os.environ.get(k) for k in env_extra}
        os.environ.update(env_extra)
        try:
            return ea.export_all(destination, limit)
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_bundle_shape_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir)
            dest = os.path.join(tmp_dir, "out.json")
            counts = self._run(dest, env)
            self.assertEqual(counts, {"memories": 1, "conversations": 2, "action_items": 1, "goals": 0})

            bundle = json.loads(Path(dest).read_text(encoding="utf-8"))
            self.assertEqual(len(bundle["conversations"]), 2)
            self.assertIn("exported_at", bundle)
            self.assertEqual(bundle["counts"], counts)

    def test_cli_failure_aborts_before_write(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, mode="fail")
            dest = os.path.join(tmp_dir, "out.json")
            with self.assertRaises(ea.ExportError):
                self._run(dest, env)
            self.assertFalse(os.path.exists(dest))

    def test_malformed_json_aborts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir, mode="badjson")
            dest = os.path.join(tmp_dir, "out.json")
            with self.assertRaises(ea.ExportError):
                self._run(dest, env)
            self.assertFalse(os.path.exists(dest))

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._fake_omi(tmp_dir)
            dest = os.path.join(tmp_dir, "out.json")
            Path(dest).write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                self._run(dest, env)


if __name__ == "__main__":
    unittest.main()
