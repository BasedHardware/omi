import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Load audio_chunks_to_manifest dynamically using importlib.util
script_path = Path(__file__).resolve().parent.parent / "examples" / "audio_chunks_to_manifest.py"
spec = importlib.util.spec_from_file_location("audio_chunks_to_manifest", script_path)
ac2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac2m)


class TestAudioChunksToManifest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.recordings_dir = Path(self.test_dir) / "recordings"
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

        self.chunk1 = self.recordings_dir / "chunk_001.wav"
        self.chunk1.write_bytes(b"RIFF....WAVEfmt ....data....test_payload_chunk1")

        subdir = self.recordings_dir / "2026-09-23"
        subdir.mkdir(parents=True, exist_ok=True)
        self.chunk2 = subdir / "chunk_002.opus"
        self.chunk2.write_bytes(b"OpusHead....opus_payload_chunk2")

        self.notes = self.recordings_dir / "notes.txt"
        self.notes.write_text("Meeting notes, ignore this file.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_convert_generates_valid_manifest(self):
        dest = Path(self.test_dir) / "manifest.json"
        ac2m.convert(str(self.recordings_dir), str(dest))

        self.assertTrue(dest.exists())
        data = json.loads(dest.read_text(encoding="utf-8"))

        self.assertEqual(data["total_files"], 2)
        self.assertEqual(len(data["chunks"]), 2)

        expected_hash1 = hashlib.sha256(self.chunk1.read_bytes()).hexdigest()
        chunk1_entry = next(c for c in data["chunks"] if c["filename"] == "chunk_001.wav")
        self.assertEqual(chunk1_entry["sha256"], expected_hash1)
        self.assertEqual(chunk1_entry["format"], "wav")
        self.assertEqual(chunk1_entry["size_bytes"], len(self.chunk1.read_bytes()))

        expected_hash2 = hashlib.sha256(self.chunk2.read_bytes()).hexdigest()
        chunk2_entry = next(c for c in data["chunks"] if c["filename"] == "chunk_002.opus")
        self.assertEqual(chunk2_entry["sha256"], expected_hash2)
        self.assertEqual(chunk2_entry["format"], "opus")
        self.assertEqual(chunk2_entry["relative_path"], "2026-09-23/chunk_002.opus")

    def test_destination_already_exists_raises(self):
        dest = Path(self.test_dir) / "existing_manifest.json"
        dest.write_text("{}", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ac2m.convert(str(self.recordings_dir), str(dest))

    def test_invalid_source_dir_raises(self):
        dest = Path(self.test_dir) / "manifest.json"
        with self.assertRaises(ValueError):
            ac2m.convert(str(Path(self.test_dir) / "nonexistent_dir"), str(dest))


if __name__ == "__main__":
    unittest.main()
