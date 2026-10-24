#!/usr/bin/env python3
"""
Unit tests for backup_bundle tool.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load backup_bundle example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "backup_bundle.py"
spec = importlib.util.spec_from_file_location("backup_bundle", script_path)
bb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bb)

count_records = bb.count_records
create_backup_bundle = bb.create_backup_bundle
main = bb.main
sha256_bytes = bb.sha256_bytes
verify_backup_bundle = bb.verify_backup_bundle


class TestBackupBundle(unittest.TestCase):

    def test_sha256_bytes(self):
        data = b"hello omi"
        expected = "27872e9d7ffa8d251984b78b98b96d0306a639467c95d0710aacc0bbab048d6e"
        self.assertEqual(sha256_bytes(data), expected)

    def test_count_records(self):
        self.assertEqual(count_records([1, 2, 3]), 3)
        self.assertEqual(count_records({"memories": [{"id": "1"}, {"id": "2"}]}), 2)
        self.assertEqual(count_records({"action_items": []}), 0)
        self.assertEqual(count_records("not a collection"), 0)

    def test_bundle_creation_and_verification(self):
        mem_data = json.dumps([{"id": "m1", "content": "note 1"}]).encode("utf-8")
        task_data = json.dumps([{"id": "t1", "description": "task 1"}]).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_file = Path(tmpdir) / "test_backup.tar.gz"
            resources = {
                "memories": mem_data,
                "action_items": task_data,
            }

            manifest = create_backup_bundle(resources, bundle_file)
            self.assertTrue(bundle_file.is_file())
            self.assertFalse(bundle_file.with_name("test_backup.tar.gz.partial").exists())

            # Verify bundle
            verified_manifest = verify_backup_bundle(bundle_file)
            self.assertEqual(verified_manifest["manifest_version"], "1.0")
            self.assertIn("memories.json", verified_manifest["resources"])
            self.assertEqual(verified_manifest["resources"]["memories.json"]["record_count"], 1)
            self.assertEqual(verified_manifest["resources"]["action_items.json"]["record_count"], 1)

    def test_path_traversal_rejection(self):
        with self.assertRaises(ValueError):
            create_backup_bundle({}, Path("sub/../../escaped.tar.gz"))

    def test_cli_create_and_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            m_path = Path(tmpdir) / "memories.json"
            m_path.write_text(json.dumps([{"id": "m10"}]), encoding="utf-8")
            bundle_path = Path(tmpdir) / "out.tar.gz"

            create_exit = main(["create", "-o", str(bundle_path), "--memories", str(m_path)])
            self.assertEqual(create_exit, 0)
            self.assertTrue(bundle_path.is_file())

            verify_exit = main(["verify", str(bundle_path)])
            self.assertEqual(verify_exit, 0)

    def test_cli_missing_bundle(self):
        exit_code = main(["verify", "nonexistent_bundle.tar.gz"])
        self.assertEqual(exit_code, 1)

    def test_source_date_epoch_reproducibility(self):
        import os
        import tarfile

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_file = Path(tmpdir) / "repro.tar.gz"
            old_val = os.environ.get("SOURCE_DATE_EPOCH")
            try:
                os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
                manifest = create_backup_bundle({"memories": b"[]"}, bundle_file)
                self.assertEqual(manifest["created_at"], "2023-11-14T22:13:20+00:00")
                with tarfile.open(bundle_file, "r:gz") as tar:
                    member = tar.getmember("memories.json")
                    self.assertEqual(member.mtime, 1700000000)
            finally:
                if old_val is not None:
                    os.environ["SOURCE_DATE_EPOCH"] = old_val
                else:
                    os.environ.pop("SOURCE_DATE_EPOCH", None)


if __name__ == "__main__":
    unittest.main()
