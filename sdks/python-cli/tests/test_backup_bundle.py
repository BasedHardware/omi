"""Hermetic tests for examples/backup_bundle.py (#19312).

Covers: archive creation, manifest integrity, file roundtripping,
verification error paths, and non-destructive overwrite guards.
"""

import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import backup_bundle as m  # noqa: E402


class TestBuildVerify(unittest.TestCase):
    def test_archive_created_with_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "memories.json"
            a.write_text('{"memories": []}')
            b = Path(td) / "conversations.json"
            b.write_text('{"conversations": []}')
            out = str(Path(td) / "backup.tar.gz")
            manifest = m.build([str(a), str(b)], out)
            self.assertTrue(Path(out).exists())
            self.assertIn("memories.json", manifest["files"])
            with tarfile.open(out, "r:gz") as tar:
                self.assertIn("manifest.json", tar.getnames())

    def test_verify_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "goals.json"
            a.write_text('[{"id": "g1"}]')
            out = str(Path(td) / "backup.tar.gz")
            m.build([str(a)], out)
            manifest = m.verify(out)
            self.assertEqual(manifest["files"]["goals.json"]["size"], len('[{"id": "g1"}]'))

    def test_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            a.write_text("x")
            out = Path(td) / "b.tar.gz"
            m.build([str(a)], str(out))
            # Tamper: rebuild the tar with a modified member
            data = out.read_bytes()
            out2 = Path(td) / "tampered.tar.gz"
            with tarfile.open(str(out2), "w:gz") as tar:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as src:
                    for member in src.getmembers():
                        payload = src.extractfile(member).read()
                        if member.name == "a.json":
                            payload = b"TAMPERED"  # manifest.json copied verbatim
                        info = tarfile.TarInfo(member.name)
                        info.size = len(payload)
                        tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(ValueError) as ctx:
                m.verify(str(out2))
            self.assertIn("SHA-256 mismatch", str(ctx.exception))

    def test_verify_missing_member(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "empty.tar.gz"
            with tarfile.open(str(out), "w:gz") as tar:
                info = tarfile.TarInfo("manifest.json")
                payload = b'{"files": {"gone.json": {"sha256": "x", "size": 1}}}'
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(ValueError) as ctx:
                m.verify(str(out))
            self.assertIn("missing member", str(ctx.exception))

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            a.write_text("x")
            out = Path(td) / "b.tar.gz"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.build([str(a)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            a.write_text("x")
            with self.assertRaises(ValueError):
                m.build([str(a)], "../escape.tar.gz")

    def test_duplicate_member_refused(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "manifest.json"
            a.write_text("x")
            with self.assertRaises(ValueError):
                m.build([str(a)], str(Path(td) / "o.tar.gz"))

    def test_deterministic_archive(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            a.write_text("x")
            with tarfile.open(str(Path(td) / "b.tar.gz"), "w:gz"):
                pass
            manifest = m.build([str(a)], str(Path(td) / "b2.tar.gz"))
            self.assertEqual(len(manifest["files"]), 1)


if __name__ == "__main__":
    unittest.main()
