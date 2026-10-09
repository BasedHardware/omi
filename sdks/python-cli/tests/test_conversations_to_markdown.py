"""Unit tests for conversations_to_markdown.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import unittest

SCRIPT = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_markdown.py"


class TestConversationsToMarkdown(unittest.TestCase):
    """Tests for the CLI export script."""

    def _run_script(
        self,
        source: str | Path,
        tmpdir: Path,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        output_dir = tmpdir / "notes"
        cmd = [sys.executable, str(SCRIPT), str(source), "--output-dir", str(output_dir)]
        env = {**os.environ, **(env_overrides or {})}
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_file_input_ascii_env(self) -> None:
        items = [
            {"id": "c1", "structured": {"title": "\u4e2d\u6587\u4f1a\u8bae", "overview": "First note"}},
            {"id": "c2", "structured": {"title": "Second meeting", "overview": "Second note"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "input.json"
            src.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            env = {"PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
            result = self._run_script(src, root, env_overrides=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            notes = list((root / "notes").glob("*.md"))
            self.assertEqual(len(notes), 2)
            texts = {n.read_text(encoding="utf-8") for n in notes}
            self.assertTrue(any("中文会议" in t for t in texts))
            self.assertTrue(any("First note" in t for t in texts))

    def test_file_input_cp1252_env(self) -> None:
        items = [
            {"id": "c1", "structured": {"title": "\u4e2d\u6587\u4f1a\u8bae", "overview": "First note"}},
            {"id": "c2", "structured": {"title": "Second meeting", "overview": "Second note"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "input.json"
            src.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            env = {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
            result = self._run_script(src, root, env_overrides=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            notes = list((root / "notes").glob("*.md"))
            self.assertEqual(len(notes), 2)

    def test_stdin_pipe_ascii_env(self) -> None:
        items = [
            {"id": "c1", "structured": {"title": "\u4e2d\u6587\u4f1a\u8bae", "overview": "First note"}},
            {"id": "c2", "structured": {"title": "Second meeting", "overview": "Second note"}},
        ]
        payload = json.dumps(items, ensure_ascii=False).encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = {"PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "-", "--output-dir", str(root / "notes")],
                input=payload,
                capture_output=True,
                env={**os.environ, **env},
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            notes = list((root / "notes").glob("*.md"))
            self.assertEqual(len(notes), 2)

    def test_stdin_pipe_cp1252_env(self) -> None:
        items = [
            {"id": "c1", "structured": {"title": "\u4e2d\u6587\u4f1a\u8bae", "overview": "First note"}},
            {"id": "c2", "structured": {"title": "Second meeting", "overview": "Second note"}},
        ]
        payload = json.dumps(items, ensure_ascii=False).encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "-", "--output-dir", str(root / "notes")],
                input=payload,
                capture_output=True,
                env={**os.environ, **env},
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            notes = list((root / "notes").glob("*.md"))
            self.assertEqual(len(notes), 2)


if __name__ == "__main__":
    unittest.main()
