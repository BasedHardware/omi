"""Unit tests for get_monthly_chat_usage — the freemium chat-question quota source.

Regression coverage for the nested-vs-flat bug: the Rust desktop-backend commits
desktop_chat usage via dotted Firestore fieldPaths, which Firestore materializes as a
NESTED map ({desktop_chat: {call_count, ...}}), whereas the Python backend writes flat
dotted keys ("chat.<model>.call_count"). The reader must count both, count the
grand-total `desktop_chat` map only (not its `desktop_chat_*` per-account/realtime
breakdowns, which would double-count), and exclude company-driven keys (conv_*, memories.*).

These tests drive the neutral storage port (WP2, ADR-0002): they monkeypatch the module's
``_store`` seam with an in-memory ``FakeDocumentStore`` and seed documents by their logical
path, then assert on returned values — no Firestore call mechanics.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from database import user_usage  # noqa: E402
from database.firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode  # noqa: E402
from routers import users as users_router  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(user_usage, "_store", lambda: fake)
    return fake


def _setup_docs(monkeypatch, docs):
    """Seed llm_usage docs under users/uid/llm_usage/{id} preserving literal field names.

    llm_usage documents hold flat dotted field names ("chat.<model>.call_count") exactly as
    Firestore's ``.set()`` stores them (dots literal, not field paths). We therefore inject a
    raw path->data backing dict instead of going through ``store.set`` — whose dotted-key
    semantics mirror ``.update()`` field paths and would nest those keys.
    """
    backing = {f"users/uid/llm_usage/{doc_id}": data for doc_id, data in docs.items()}
    fake = FakeDocumentStore(backing=backing)
    monkeypatch.setattr(user_usage, "_store", lambda: fake)
    return fake


NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_counts_nested_desktop_chat_plus_flat_backend_chat(monkeypatch):
    _setup_docs(
        monkeypatch,
        {
            "2026-06-23": {
                "desktop_chat": {
                    "call_count": 5,  # internal generations — must NOT count as questions
                    "quota_questions": 5,  # visible user turns — counted
                    "cost_usd": 1.5,
                },
                "desktop_chat_omi": {"call_count": 3},  # breakdown — must NOT double-count
                "desktop_chat_realtime": {
                    "call_count": 2,
                    "quota_questions": 2,
                },  # PTT breakdown — must NOT double-count
                "chat.gpt-4.call_count": 4,  # flat backend chat — counted
                "conv_apps.gpt-5.call_count": 100,  # proactive/processing — excluded
                "memories.gpt-4.call_count": 50,  # excluded
                "date": "2026-06-23",
            },
            "2026-05-30": {"desktop_chat": {"quota_questions": 999}},  # other month — excluded
        },
    )
    r = user_usage.get_monthly_chat_usage("uid", now=NOW)
    # 5 (desktop quota_questions) + 4 (flat chat.*); breakdowns excluded (have quota_questions, no
    # legacy fallback double-count); internal call_count + proactive excluded; other month excluded
    assert r["questions"] == 9, r
    assert r["cost_usd"] == 1.5, r


def test_realtime_ptt_included_via_grand_total(monkeypatch):
    # A pure-PTT month: only realtime turns. record_llm_usage always bumps the grand-total
    # desktop_chat too, so it must be counted even with zero typed chat.
    _setup_docs(
        monkeypatch,
        {
            "2026-06-10": {
                "desktop_chat": {"call_count": 7, "cost_usd": 0.4},
                "desktop_chat_realtime": {"call_count": 7},
            }
        },
    )
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 7


def test_only_proactive_counts_zero(monkeypatch):
    _setup_docs(monkeypatch, {"2026-06-23": {"conv_apps.gpt-5.call_count": 100, "memories.gpt-4.call_count": 50}})
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 0


def test_monthly_usage_since_observes_every_scanned_hourly_document(store, monkeypatch):
    # Both docs land in June 2026 with ids >= the start cursor, so the year/month/id filters
    # select them; the read-metrics telemetry must observe the count of scanned documents.
    store.set(
        "users/uid/hourly_usage/2026-06-10-00",
        {"year": 2026, "month": 6, "id": "2026-06-10-00", "transcription_seconds": 15},
    )
    store.set(
        "users/uid/hourly_usage/2026-06-15-00",
        {"year": 2026, "month": 6, "id": "2026-06-15-00", "transcription_seconds": 25},
    )

    observed = []
    monkeypatch.setattr(user_usage, 'record_firestore_read', lambda *args: observed.append(args))

    usage = user_usage.get_monthly_usage_stats_since(
        'uid',
        datetime(2026, 6, 23, tzinfo=timezone.utc),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert usage['transcription_seconds'] == 40
    assert observed == [(FirestoreReadFamily.LISTEN_MONTHLY_USAGE, FirestoreReadMode.UNBOUNDED, 2)]


# ---------------------------------------------------------------------------
# get_current_user_usage(period='today') — local-day vs UTC-day boundary
#
# hourly_usage docs are written keyed by UTC date (utils/analytics.py always
# stamps `datetime.now(timezone.utc)`). A user behind UTC (e.g. LA, UTC-7 in
# summer) has the first ~17 hours of their local calendar day stored under the
# PREVIOUS UTC date. Querying only "the UTC date matching now" silently drops
# that morning/afternoon usage from what the app displays as "Today".
# ---------------------------------------------------------------------------


def _setup_hourly_docs(store, docs):
    for d in docs:
        doc_id = f"{d['year']}-{d['month']:02d}-{d['day']:02d}-{d['hour']:02d}"
        store.set(f"users/uid/hourly_usage/{doc_id}", d)


# 8pm local time on LA-calendar-day June 23rd, which is already 3am UTC on June 24th.
_LA_EVENING_NOW = datetime(2026, 6, 24, 3, 0, tzinfo=timezone.utc)

_LA_HOURLY_DOCS = [
    # LA-local 2026-06-23 07:00 (7am) -- written under UTC 2026-06-23, the day
    # BEFORE `now`'s UTC date. A UTC-day-only query misses this entirely.
    {'year': 2026, 'month': 6, 'day': 23, 'hour': 14, 'transcription_seconds': 600},
    # LA-local 2026-06-23 18:00 (6pm) -- written under UTC 2026-06-24, which
    # happens to match `now`'s UTC date.
    {'year': 2026, 'month': 6, 'day': 24, 'hour': 1, 'transcription_seconds': 300},
    # LA-local 2026-06-22 20:00 (8pm the day BEFORE) -- must stay excluded from
    # "today" no matter which boundary logic is used.
    {'year': 2026, 'month': 6, 'day': 23, 'hour': 3, 'transcription_seconds': 12345},
]


def test_today_usage_local_day_spans_two_utc_dates_for_user_west_of_utc(store):
    _setup_hourly_docs(store, _LA_HOURLY_DOCS)

    result = user_usage.get_current_user_usage('uid', 'today', tz_name='America/Los_Angeles', now=_LA_EVENING_NOW)

    # Correct local-day total: 600 (7am bucket) + 300 (6pm bucket) = 900.
    # The pre-fix UTC-day-equality query only ever found the 300 bucket.
    assert result['today']['transcription_seconds'] == 900, result['today']


def test_today_usage_without_timezone_still_falls_back_to_utc_day(store):
    """No stored timezone -> unchanged UTC-day behavior (no regression for
    users who never granted notification permissions / have no time_zone)."""
    _setup_hourly_docs(store, _LA_HOURLY_DOCS)

    result = user_usage.get_current_user_usage('uid', 'today', tz_name=None, now=_LA_EVENING_NOW)

    assert result['today']['transcription_seconds'] == 300, result['today']


def test_usage_endpoint_serves_the_users_local_day_not_the_utc_day(store, monkeypatch):
    """Behavioural proof through the route the app actually calls.

    The two tests above exercise the helper directly and so can only be written against the
    tz-aware signature. This one goes through GET /v1/users/me/usage, which is the surface the
    Flutter usage page hits, and therefore fails on unfixed source with a wrong total rather
    than a signature error: the handler there never consults the stored timezone at all.

    `routers.users` is imported at module scope like the other router-level unit tests. The
    router graph is a heavy import, and paying it inside the test body charges ~26s of CPU to
    this one test and trips the fast-unit duration guard.
    """

    _setup_hourly_docs(store, _LA_HOURLY_DOCS)
    monkeypatch.setattr(users_router.notification_db, 'get_user_time_zone', lambda uid: 'America/Los_Angeles')

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _LA_EVENING_NOW if tz is not None else _LA_EVENING_NOW.replace(tzinfo=None)

    monkeypatch.setattr(user_usage, 'datetime', _FrozenDatetime)

    result = users_router.get_user_usage_stats_endpoint(uid='uid')

    # 600 (7am local, filed under the previous UTC date) + 300 (6pm local, filed under today's
    # UTC date). Serving the UTC day alone finds only the 300.
    assert result['today']['transcription_seconds'] == 900, result['today']


def test_all_time_usage_builds_totals_and_history_from_one_stream(store, monkeypatch):
    # Upstream #11062: get_current_user_usage('all_time') reads hourly_usage ONCE, building both the
    # all-time total and the yearly history in a single pass. Exercised on the neutral store seam;
    # the single-read (dedup) invariant is proved by record_firestore_read being called once with the
    # document count (2), not by asserting the raw adapter's .stream() call.
    store.set('users/uid/hourly_usage/2025-01-01-00', {'year': 2025, 'transcription_seconds': 10, 'speech_seconds': 8})
    store.set(
        'users/uid/hourly_usage/2026-01-01-00',
        {'year': 2026, 'transcription_seconds': 20, 'words_transcribed': 4, 'speech_seconds': 16},
    )
    record_read = MagicMock()
    monkeypatch.setattr(user_usage, 'record_firestore_read', record_read)

    result = user_usage.get_current_user_usage('uid', 'all_time')

    assert result['all_time']['transcription_seconds'] == 30
    assert result['all_time']['words_transcribed'] == 4
    assert result['all_time']['speech_seconds'] == 24
    assert result['history'] == [
        {
            'date': '2025-01-01',
            'transcription_seconds': 10,
            'words_transcribed': 0,
            'insights_gained': 0,
            'memories_created': 0,
        },
        {
            'date': '2026-01-01',
            'transcription_seconds': 20,
            'words_transcribed': 4,
            'insights_gained': 0,
            'memories_created': 0,
        },
    ]
    record_read.assert_called_once_with(FirestoreReadFamily.ALL_TIME_USAGE, FirestoreReadMode.UNBOUNDED, 2)
