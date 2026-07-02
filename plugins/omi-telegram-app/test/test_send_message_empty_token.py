"""Regression test: send_message with empty bot_token must NOT hit Telegram.

P2 from cubic AI review (PR #8682): the webhook handler's
"_bot_token_for_unknown_chat" path returns "" when there's no record of
the chat_id. The previous code passed that empty token straight to
httpx, producing a request to https://api.telegram.org/bot/sendMessage
(note the empty bot segment) which Telegram answers with a 404 and a
loud ERROR log — wasted round trip + log spam for an expected edge
case. send_message must short-circuit on empty token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

# Match the path setup used by other Telegram tests so this file runs
# in isolation as well as in the full suite.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "..", "_shared"))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_SHARED, _PLUGIN_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# Match the plugin's own env defaults so telegram_client module-loads
# without exploding.
os.environ.setdefault("OMI_DEV_MODE", "1")
os.environ.setdefault("AI_CLONE_PLUGIN_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")

import telegram_client


class TestSendMessageEmptyToken:
    def test_returns_none_without_hitting_httpx(self):
        """An empty bot_token must return None and never call the
        transport. Without the early-return guard the call would have
        hit httpx.AsyncClient.post and produced a 404 from Telegram."""
        with patch("telegram_client.httpx.AsyncClient") as mock_async_client:
            result = asyncio.run(telegram_client.send_message(bot_token="", chat_id="12345", text="hi"))
        assert result is None
        # Crucially: the underlying httpx client must NEVER have been
        # constructed (the empty-token path skips transport entirely).
        mock_async_client.assert_not_called()

    def test_empty_token_does_not_log_error(self, caplog):
        """The empty-token case is an expected edge case — log at
        DEBUG, not ERROR. We assert caplog records no ERROR-level
        message so a regression that re-introduces an ERROR log on
        the 404-from-empty-token path fails the test."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="telegram_client"):
            asyncio.run(telegram_client.send_message(bot_token="", chat_id="12345", text="hi"))
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records == [], f"empty-token path must not log ERROR: {error_records}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
