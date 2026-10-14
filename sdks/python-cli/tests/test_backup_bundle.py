import json
import tarfile
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import backup_bundle


class TestBackupBundle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.bundle = self.dir_path / "backup.tar.gz"
        self.a = self._write("memories.json", [{"id": "m1", "content": "a"}])
        self.b = self._write("conversations.json", [{"id": "c1"}])

    def _write(self, name, payload):
        p = self.dir_path / name
        p.write_bytes(json.dumps(payload).encode("utf-8"))
        return p

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_and_verify_roundtrip(self):
        count = backup_bundle.build_bundle(self.bundle, [self.a, self.b])
        self.assertEqual(count, 2)
        self.assertEqual(backup_bundle.verify_bundle(self.bundle), 2)

    def test_manifest_hashes_all_members(self):
        backup_bundle.build_bundle(self.bundle, [self.a, self.b])
        with tarfile.open(self.bundle, "r:gz") as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        names = {f["name"] for f in manifest["files"]}
        self.assertEqual(names, {"memories.json", "conversations.json"})
        self.assertTrue(all(len(f["sha256"]) == 64 for f in manifest["files"]))

    def test_verify_detects_tampered_member(self):
        backup_bundle.build_bundle(self.bundle, [self.a])
        # Rebuild a bundle whose member bytes were swapped after hashing.
        evil = self.dir_path / "evil.tar.gz"
        with tarfile.open(self.bundle, "r:gz") as src, tarfile.open(evil, "w:gz") as dst:
            for name in src.getnames():
                data = src.extractfile(name).read()
                if name == "memories.json":
                    data = b'[{"id":"tampered"}]'
                info = tarfile.TarInfo(name)
                info.size = len(data)
                import io
                dst.addfile(info, io.BytesIO(data))
        with self.assertRaises(ValueError):
            backup_bundle.verify_bundle(evil)

    def test_verify_rejects_missing_manifest(self):
        bare = self.dir_path / "bare.tar.gz"
        with tarfile.open(bare, "w:gz") as tar:
            info = tarfile.TarInfo("memories.json")
            blob = b"[]"
            info.size = len(blob)
            import io
            tar.addfile(info, io.BytesIO(blob))
        with self.assertRaises(ValueError):
            backup_bundle.verify_bundle(bare)

    def test_output_rejects_traversal(self):
        with self.assertRaises(ValueError):
            backup_bundle._validate_output("../escape.tar.gz")

    def test_output_rejects_non_archive_overwrite(self):
        existing = self.dir_path / "existing.tar.gz"
        existing.write_bytes(b"not a gzip")
        with self.assertRaises(ValueError):
            backup_bundle._validate_output(str(existing))


if __name__ == "__main__":
    unittest.main()
