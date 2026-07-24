#!/usr/bin/env python3
"""Fixtures for the chat send-deadline static tripwire (#9835)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_chat_send_deadline import CHAT_DIR, find_direct_sends


class ChatSendDeadlineChecker(unittest.TestCase):
    def test_flags_a_direct_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_dir = Path(tmp)
            (chat_dir / "transport.rs").write_text(
                "let resp = builder.send().await;\n", encoding="utf-8"
            )
            violations = find_direct_sends(chat_dir)
        self.assertEqual(len(violations), 1)
        self.assertIn("transport.rs:1", violations[0])

    def test_accepts_the_budgeted_seam(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_dir = Path(tmp)
            (chat_dir / "transport.rs").write_text(
                "let resp = send_with_deadline(builder, deadline).await;\n",
                encoding="utf-8",
            )
            self.assertEqual(find_direct_sends(chat_dir), [])

    def test_real_chat_module_is_clean(self) -> None:
        self.assertTrue(CHAT_DIR.is_dir(), f"{CHAT_DIR} moved; update the checker")
        self.assertEqual(find_direct_sends(CHAT_DIR), [])


if __name__ == "__main__":
    unittest.main()
