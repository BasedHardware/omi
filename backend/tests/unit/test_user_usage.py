"""Unit tests for get_monthly_chat_usage — the freemium chat-question quota source.

Regression coverage for the nested-vs-flat bug: the Rust desktop-backend commits
desktop_chat usage via dotted Firestore fieldPaths, which Firestore materializes as a
NESTED map ({desktop_chat: {call_count, ...}}), whereas the Python backend writes flat
dotted keys ("chat.<model>.call_count"). The reader must count both, count the
grand-total `desktop_chat` map only (not its `desktop_chat_*` per-account/realtime
breakdowns, which would double-count), and exclude company-driven keys (conv_*, memories.*).
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

mock_db = MagicMock()
_mock_client_module = MagicMock()
_mock_client_module.db = mock_db
sys.modules["database._client"] = _mock_client_module
sys.modules["stripe"] = MagicMock()

from database import user_usage  # noqa: E402


class _Snap:
    def __init__(self, data):
        self._d = data
        self.exists = True

    def to_dict(self):
        return self._d


class _DocRef:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def get(self):
        return _Snap(self._data)


def _setup_docs(docs):
    refs = [_DocRef(k, v) for k, v in docs.items()]
    llm_usage_ref = MagicMock()
    llm_usage_ref.list_documents.return_value = refs
    mock_db.collection.return_value.document.return_value.collection.return_value = llm_usage_ref


NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_counts_nested_desktop_chat_plus_flat_backend_chat():
    _setup_docs(
        {
            "2026-06-23": {
                "desktop_chat": {"call_count": 5, "cost_usd": 1.5},  # nested (Rust) — counted
                "desktop_chat_omi": {"call_count": 3},  # breakdown — must NOT double-count
                "desktop_chat_realtime": {"call_count": 2},  # PTT breakdown — must NOT double-count
                "chat.gpt-4.call_count": 4,  # flat backend chat — counted
                "conv_apps.gpt-5.call_count": 100,  # proactive/processing — excluded
                "memories.gpt-4.call_count": 50,  # excluded
                "date": "2026-06-23",
            },
            "2026-05-30": {"desktop_chat": {"call_count": 999}},  # other month — excluded
        }
    )
    r = user_usage.get_monthly_chat_usage("uid", now=NOW)
    # 5 (grand-total desktop_chat) + 4 (flat chat.*); breakdowns + proactive excluded; other month excluded
    assert r["questions"] == 9, r
    assert r["cost_usd"] == 1.5, r


def test_realtime_ptt_included_via_grand_total():
    # A pure-PTT month: only realtime turns. record_llm_usage always bumps the grand-total
    # desktop_chat too, so it must be counted even with zero typed chat.
    _setup_docs(
        {
            "2026-06-10": {
                "desktop_chat": {"call_count": 7, "cost_usd": 0.4},
                "desktop_chat_realtime": {"call_count": 7},
            }
        }
    )
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 7


def test_only_proactive_counts_zero():
    _setup_docs({"2026-06-23": {"conv_apps.gpt-5.call_count": 100, "memories.gpt-4.call_count": 50}})
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 0
