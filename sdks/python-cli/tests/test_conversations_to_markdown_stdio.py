"""Exercise UTF-8 conversation exports through the real script entry point."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_markdown.py"


class TestConversationMarkdownStdio(unittest.TestCase):
    def test_cli_exports_unicode_batch_with_legacy_stdio(self):
        """A redirected legacy console must not abort or corrupt UTF-8 exports."""
        items = [
            {"id": "c1", "structured": {"title": "中文会议", "overview": "保留中文内容"}},
            {"id": "c2", "structured": {"title": "Second meeting", "overview": "Second note"}},
        ]
        # Exercising the script entry point catches input decoding and the progress
        # message that previously aborted the batch after writing only one file.
        for encoding in ("ascii", "cp1252"):
            for source in ("file", "stdin"):
                with self.subTest(encoding=encoding, source=source), tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    input_path = root / "input.json"
                    input_bytes = json.dumps(items, ensure_ascii=False).encode("utf-8-sig")
                    input_path.write_bytes(input_bytes)
                    output_dir = root / "notes"
                    env = dict(os.environ, PYTHONIOENCODING=encoding, PYTHONUTF8="0")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(script_path),
                            "-" if source == "stdin" else str(input_path),
                            "--output-dir",
                            str(output_dir),
                        ],
                        input=input_bytes if source == "stdin" else None,
                        capture_output=True,
                        env=env,
                        timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                    notes = list(output_dir.glob("*.md"))
                    self.assertEqual(len(notes), 2)
                    contents = "\n".join(p.read_text(encoding="utf-8") for p in notes)
                    self.assertIn("# 中文会议", contents)
                    self.assertIn("保留中文内容", contents)
                    self.assertIn("Second note", contents)
                    self.assertIn("中文会议", result.stdout.decode("utf-8"))
                    self.assertIn("Successfully exported 2 conversation(s)", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
