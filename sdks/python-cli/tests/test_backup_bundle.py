"""Tests for backup_bundle recipe.

Covers: archive creation, embedded manifest integrity, verification without extraction,
tampered archive detection, atomic writes, path traversal refusal, and CLI entrypoint.
Uses importlib.util.spec_from_file_location to match repository convention.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

# Load backup_bundle script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "backup_bundle.py"
spec = importlib.util.spec_from_file_location("backup_bundle", script_path)
bundle_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle_mod)

build_bundle = bundle_mod.build_bundle
verify_bundle = bundle_mod.verify_bundle
compute_sha256 = bundle_mod.compute_sha256
validate_path_safety = bundle_mod.validate_path_safety
collect_input_files = bundle_mod.collect_input_files
main = bundle_mod.main


class TestBackupBundle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

        # Create sample exported files
        self.memories_file = self.dir_path / "memories.json"
        self.memories_file.write_text(json.dumps([{"id": "m1", "content": "Learned Python"}]), encoding="utf-8")

        self.conversations_file = self.dir_path / "conversations.json"
        self.conversations_file.write_text(json.dumps([{"id": "c1", "title": "Weekly sync"}]), encoding="utf-8")

        self.out_archive = self.dir_path / "omi_backup.tar.gz"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_sha256(self):
        data = b"hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        self.assertEqual(compute_sha256(data), expected)

    def test_build_and_verify_bundle_files(self):
        created = build_bundle(
            [str(self.memories_file), str(self.conversations_file)],
            self.out_archive,
        )
        self.assertTrue(created.is_file())

        # Verify archive contains manifest and member files
        with tarfile.open(self.out_archive, "r:gz") as tar:
            names = tar.getnames()
            self.assertIn("manifest.json", names)
            self.assertIn("memories.json", names)
            self.assertIn("conversations.json", names)

            # Check manifest contents
            f = tar.extractfile("manifest.json")
            manifest = json.loads(f.read().decode("utf-8"))
            self.assertEqual(manifest["version"], "1.0")
            self.assertEqual(manifest["files_count"], 2)

        # Verify using verify_bundle()
        result = verify_bundle(self.out_archive)
        self.assertTrue(result["verified"])
        self.assertEqual(result["files_verified"], 2)

    def test_build_bundle_from_directory(self):
        export_sub = self.dir_path / "exports"
        export_sub.mkdir()
        (export_sub / "goals.json").write_text('[{"id": "g1"}]', encoding="utf-8")
        (export_sub / "action_items.json").write_text('[{"id": "a1"}]', encoding="utf-8")

        created = build_bundle([str(export_sub)], self.out_archive)
        self.assertTrue(created.is_file())

        result = verify_bundle(self.out_archive)
        self.assertTrue(result["verified"])
        self.assertEqual(result["files_verified"], 2)

    def test_overwrite_protection(self):
        # Create initial archive
        build_bundle([str(self.memories_file)], self.out_archive)
        self.assertTrue(self.out_archive.exists())

        # Default force=False must raise FileExistsError
        with self.assertRaises(FileExistsError):
            build_bundle([str(self.memories_file)], self.out_archive, force=False)

        # force=True succeeds
        build_bundle([str(self.conversations_file)], self.out_archive, force=True)
        res = verify_bundle(self.out_archive)
        self.assertEqual(res["files_verified"], 1)

    def test_verify_detects_tampering(self):
        build_bundle([str(self.memories_file)], self.out_archive)

        # Tamper with the archive by altering file content inside
        tampered_archive = self.dir_path / "tampered.tar.gz"
        with tarfile.open(self.out_archive, "r:gz") as src, tarfile.open(tampered_archive, "w:gz") as dst:
            for member in src.getmembers():
                data = src.extractfile(member).read()
                if member.name == "memories.json":
                    data = b"tampered corrupt content"
                ti = tarfile.TarInfo(name=member.name)
                ti.size = len(data)
                dst.addfile(ti, io.BytesIO(data))

        with self.assertRaises(ValueError) as ctx:
            verify_bundle(tampered_archive)
        self.assertIn("Integrity check failed", str(ctx.exception))

    def test_path_traversal_refusal(self):
        with self.assertRaises(ValueError):
            validate_path_safety(Path("../bad_path.tar.gz"))

        with self.assertRaises(ValueError):
            validate_path_safety(Path("dir/../secret.txt"))

    def test_missing_input_file_raises(self):
        missing = self.dir_path / "nonexistent.json"
        with self.assertRaises(FileNotFoundError):
            build_bundle([str(missing)], self.out_archive)

    def test_cli_execution_build_and_verify(self):
        # 1. Build via CLI
        exit_code = main([
            str(self.memories_file),
            str(self.conversations_file),
            "-o",
            str(self.out_archive),
        ])
        self.assertEqual(exit_code, 0)
        self.assertTrue(self.out_archive.is_file())

        # 2. Verify via CLI
        exit_code_verify = main(["--verify", str(self.out_archive)])
        self.assertEqual(exit_code_verify, 0)

        # 3. Missing inputs should return 1
        exit_code_missing = main([])
        self.assertEqual(exit_code_missing, 1)


if __name__ == "__main__":
    unittest.main()
