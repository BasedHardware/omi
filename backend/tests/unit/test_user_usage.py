"""Unit tests for get_monthly_chat_usage — the freemium chat-question quota source.

Regression coverage for the nested-vs-flat bug: the Rust desktop-backend commits
desktop_chat usage via dotted Firestore fieldPaths, which Firestore materializes as a
NESTED map ({desktop_chat: {call_count, ...}}), whereas the Python backend writes flat
dotted keys ("chat.<model>.call_count"). The reader must count both, count the
grand-total `desktop_chat` map only (not its `desktop_chat_*` per-account/realtime
breakdowns, which would double-count), and exclude company-driven keys (conv_*, memories.*).
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


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock(name="db")
    monkeypatch.setattr(user_usage, "db", db)
    return db


class _Snap:
    def __init__(self, data, doc_id=None):
        self._d = data
        self.id = doc_id
        self.exists = True

    def to_dict(self):
        return self._d


class _DocRef:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def get(self):
        return _Snap(self._data, self.id)


class _LlmUsageCollection:
    """Firestore collection fake that actually applies the `__name__` range
    filters the month query issues, so the first/last day of the month and the
    adjacent months are exercised rather than assumed. `list_documents` raises:
    the quota reader must never fall back to scanning the account's whole
    llm_usage history."""

    def __init__(self, docs, filters=()):
        self._docs = docs
        self._filters = filters

    def document(self, doc_id):
        return _DocRef(doc_id, self._docs.get(doc_id, {}))

    def list_documents(self):
        raise AssertionError("chat-quota reads must stay bounded to the current month")

    def where(self, filter):
        return _LlmUsageCollection(self._docs, (*self._filters, filter))

    def stream(self):
        def _match(doc_id):
            for f in self._filters:
                assert f.field_path == "__name__"  # Firestore's document-id sentinel
                if f.op_string == ">=" and doc_id < f.value.id:
                    return False
                if f.op_string == "<" and doc_id >= f.value.id:
                    return False
            return True

        return iter([_Snap(data, doc_id) for doc_id, data in self._docs.items() if _match(doc_id)])


def _setup_docs(mock_db, docs):
    mock_db.collection.return_value.document.return_value.collection.return_value = _LlmUsageCollection(docs)


NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def test_counts_nested_desktop_chat_plus_flat_backend_chat(mock_db):
    _setup_docs(
        mock_db,
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


def test_monthly_usage_exposes_plan_cost_status_without_zero_filling(mock_db):
    _setup_docs(
        mock_db,
        {
            "2026-06-23": {
                "plan_usage": {
                    "operator": {
                        "desktop_chat": {"quota_questions": 2, "input_tokens": 10},
                        "_metadata": {
                            "cost_status_counts": {"missing": 1},
                            "cost_exclusions": {"provider_token_cost_not_recorded": 1},
                        },
                    }
                },
                "desktop_chat": {"quota_questions": 2},
            }
        },
    )

    usage = user_usage.get_monthly_chat_usage("uid", now=NOW)

    assert usage["usage_by_plan"]["operator"]["questions"] == 2
    assert usage["usage_by_plan"]["operator"]["cost_usd"] is None
    assert usage["cost_by_plan"]["operator"] is None
    assert usage["cost_status_by_plan"]["operator"] == "missing"
    assert usage["usage_by_plan"]["operator"]["cost_exclusions"] == {"provider_token_cost_not_recorded": 1}


def test_realtime_ptt_included_via_grand_total(mock_db):
    # A pure-PTT month: only realtime turns. record_llm_usage always bumps the grand-total
    # desktop_chat too, so it must be counted even with zero typed chat.
    _setup_docs(
        mock_db,
        {
            "2026-06-10": {
                "desktop_chat": {"call_count": 7, "cost_usd": 0.4},
                "desktop_chat_realtime": {"call_count": 7},
            }
        },
    )
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 7


def test_only_proactive_counts_zero(mock_db):
    _setup_docs(mock_db, {"2026-06-23": {"conv_apps.gpt-5.call_count": 100, "memories.gpt-4.call_count": 50}})
    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 0


def test_month_read_is_bounded_to_the_current_month(mock_db, monkeypatch):
    # `enforce_chat_quota` calls this on every chat request. Reading the whole
    # llm_usage collection made the cost of asking a question grow with how long
    # the account had existed.
    _setup_docs(
        mock_db,
        {
            "2025-06-23": {"desktop_chat": {"quota_questions": 500}},  # last year
            "2026-05-31": {"desktop_chat": {"quota_questions": 400}},  # day before the month
            "2026-06-01": {"desktop_chat": {"quota_questions": 1}},  # first day, inclusive
            "2026-06-30": {"desktop_chat": {"quota_questions": 2}},  # last day, inclusive
            "2026-07-01": {"desktop_chat": {"quota_questions": 300}},  # day after the month
        },
    )
    observed = []
    monkeypatch.setattr(user_usage, "record_firestore_read", lambda *args: observed.append(args))

    assert user_usage.get_monthly_chat_usage("uid", now=NOW)["questions"] == 3
    assert observed == [(FirestoreReadFamily.CHAT_QUOTA_MONTHLY_USAGE, FirestoreReadMode.BOUNDED, 2)]


def test_december_month_read_stops_at_the_january_boundary(mock_db):
    _setup_docs(
        mock_db,
        {
            "2026-12-01": {"desktop_chat": {"quota_questions": 4}},
            "2026-12-31": {"desktop_chat": {"quota_questions": 6}},
            "2027-01-01": {"desktop_chat": {"quota_questions": 900}},
        },
    )
    usage = user_usage.get_monthly_chat_usage("uid", now=datetime(2026, 12, 15, tzinfo=timezone.utc))
    assert usage["questions"] == 10
    assert usage["reset_at"] == int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())


def test_monthly_usage_since_observes_every_scanned_hourly_document(mock_db, monkeypatch):
    docs = [
        _Snap({'transcription_seconds': 15}),
        _Snap({'transcription_seconds': 25}),
    ]
    query = MagicMock()
    query.where.return_value = query
    query.stream.return_value = iter(docs)
    mock_db.collection.return_value.document.return_value.collection.return_value = query

    observed = []
    monkeypatch.setattr(user_usage, 'record_firestore_read', lambda *args: observed.append(args))

    usage = user_usage.get_monthly_usage_stats_since(
        'uid',
        datetime(2026, 6, 23, tzinfo=timezone.utc),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert usage['transcription_seconds'] == 40
    assert observed == [(FirestoreReadFamily.LISTEN_MONTHLY_USAGE, FirestoreReadMode.UNBOUNDED, 2)]


def test_hourly_transcription_writer_keeps_plan_and_missing_cost_explicit(mock_db, monkeypatch):
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *_args, **_kwargs: 'plus')
    hourly_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = hourly_ref

    user_usage.update_hourly_usage(
        'uid',
        datetime(2026, 6, 23, 10, tzinfo=timezone.utc),
        {'transcription_seconds': 12},
    )

    update = hourly_ref.set.call_args.args[0]
    assert getattr(update['plan_usage.plus.transcription_seconds'], '_value', None) == 12
    assert getattr(update['plan_usage.plus._metadata.cost_status_counts.missing'], '_value', None) == 1
    assert all('cost_usd' not in key for key in update)


def test_usage_by_plan_joins_chat_and_hourly_rows_without_cost_zero(monkeypatch):
    monthly = {
        'usage_by_plan': {
            'plus': {
                'questions': 2,
                'input_tokens': 10,
                'output_tokens': 5,
                'total_tokens': 0,
                'cost_usd': None,
                'cost_status': 'missing',
                'cost_exclusions': {'provider_token_cost_not_recorded': 1},
            }
        }
    }
    monkeypatch.setattr(user_usage, 'get_monthly_chat_usage', lambda *_args, **_kwargs: monthly)
    query = MagicMock()
    query.where.return_value = query
    query.stream.return_value = iter(
        [
            _Snap(
                {
                    'plan_usage': {
                        'plus': {
                            'transcription_seconds': 120,
                            '_metadata': {
                                'cost_status_counts': {'missing': 1},
                                'cost_exclusions': {'provider_cost_not_recorded': 1},
                            },
                        }
                    }
                }
            )
        ]
    )
    user_ref = MagicMock()
    user_ref.collection.return_value = query
    client = MagicMock()
    client.collection.return_value.document.return_value = user_ref

    report = user_usage.get_usage_by_plan('uid', now=NOW, firestore_client=client)

    assert report['plus']['questions'] == 2
    assert report['plus']['transcription_seconds'] == 120
    assert report['plus']['cost_usd'] is None
    assert report['plus']['cost_status'] == 'missing'
    assert report['plus']['cost_exclusions']['provider_cost_not_recorded'] == 1


# ---------------------------------------------------------------------------
# get_current_user_usage(period='today') — local-day vs UTC-day boundary
#
# hourly_usage docs are written keyed by UTC date (utils/analytics.py always
# stamps `datetime.now(timezone.utc)`). A user behind UTC (e.g. LA, UTC-7 in
# summer) has the first ~17 hours of their local calendar day stored under the
# PREVIOUS UTC date. Querying only "the UTC date matching now" silently drops
# that morning/afternoon usage from what the app displays as "Today".
# ---------------------------------------------------------------------------


class _HourlyQuery:
    """Firestore query fake that actually applies '==' filters (unlike a bare
    MagicMock), because get_today_usage_stats now issues a fresh where-chain
    per UTC calendar day inside a loop and the two chains must select disjoint
    subsets of `docs` for this test to mean anything."""

    def __init__(self, docs, filters=()):
        self._docs = docs
        self._filters = filters

    def where(self, filter):
        return _HourlyQuery(self._docs, (*self._filters, filter))

    def stream(self):
        def _match(doc):
            return all(doc.get(f.field_path) == f.value for f in self._filters)

        return iter([_Snap(d) for d in self._docs if _match(d)])


def _setup_hourly_docs(mock_db, docs):
    mock_db.collection.return_value.document.return_value.collection.return_value = _HourlyQuery(docs)


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


def test_today_usage_local_day_spans_two_utc_dates_for_user_west_of_utc(mock_db):
    _setup_hourly_docs(mock_db, _LA_HOURLY_DOCS)

    result = user_usage.get_current_user_usage('uid', 'today', tz_name='America/Los_Angeles', now=_LA_EVENING_NOW)

    # Correct local-day total: 600 (7am bucket) + 300 (6pm bucket) = 900.
    # The pre-fix UTC-day-equality query only ever found the 300 bucket.
    assert result['today']['transcription_seconds'] == 900, result['today']


def test_today_usage_without_timezone_still_falls_back_to_utc_day(mock_db):
    """No stored timezone -> unchanged UTC-day behavior (no regression for
    users who never granted notification permissions / have no time_zone)."""
    _setup_hourly_docs(mock_db, _LA_HOURLY_DOCS)

    result = user_usage.get_current_user_usage('uid', 'today', tz_name=None, now=_LA_EVENING_NOW)

    assert result['today']['transcription_seconds'] == 300, result['today']


def test_usage_endpoint_serves_the_users_local_day_not_the_utc_day(mock_db, monkeypatch):
    """Behavioural proof through the route the app actually calls.

    The two tests above exercise the helper directly and so can only be written against the
    tz-aware signature. This one goes through GET /v1/users/me/usage, which is the surface the
    Flutter usage page hits, and therefore fails on unfixed source with a wrong total rather
    than a signature error: the handler there never consults the stored timezone at all.

    `routers.users` is imported at module scope like the other router-level unit tests. The
    router graph is a heavy import, and paying it inside the test body charges ~26s of CPU to
    this one test and trips the fast-unit duration guard.
    """

    _setup_hourly_docs(mock_db, _LA_HOURLY_DOCS)
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


def test_all_time_usage_builds_totals_and_history_from_one_stream(mock_db, monkeypatch):
    query = MagicMock()
    query.stream.return_value = iter(
        [
            _Snap({'year': 2025, 'transcription_seconds': 10, 'speech_seconds': 8}),
            _Snap({'year': 2026, 'transcription_seconds': 20, 'words_transcribed': 4, 'speech_seconds': 16}),
        ]
    )
    mock_db.collection.return_value.document.return_value.collection.return_value = query
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
    query.stream.assert_called_once_with()
    record_read.assert_called_once_with(FirestoreReadFamily.ALL_TIME_USAGE, FirestoreReadMode.UNBOUNDED, 2)


def test_fully_attributed_document_creates_no_phantom_unattributed_row(mock_db):
    """A document whose plan_usage accounts for all its questions must not also
    report those questions as unattributed.

    Writers store questions at plan_usage.{plan}.{bucket}.quota_questions -- there is
    no top-level plan_usage.{plan}.questions field. Reading the attributed total from
    that non-existent field made it always 0, so the residual was the document's FULL
    root count and every post-deploy document counted twice: once against its real
    plan and once against _unattributed.
    """
    _setup_docs(
        mock_db,
        {
            "2026-06-23": {
                "desktop_chat": {"quota_questions": 2},
                "plan_usage": {"operator": {"desktop_chat": {"quota_questions": 2}}},
            }
        },
    )

    usage = user_usage.get_monthly_chat_usage("uid", now=NOW)
    by_plan = usage["usage_by_plan"]

    assert by_plan["operator"]["questions"] == 2
    assert usage["questions"] == 2
    assert "_unattributed" not in by_plan, f"phantom unattributed row: {by_plan}"
    assert sum(r["questions"] for r in by_plan.values()) == usage["questions"]


def test_mixed_document_attributes_only_the_unaccounted_residual(mock_db):
    """The genuine MIXED case: pre-deploy root counters plus post-deploy plan_usage.

    Only the portion plan_usage does not account for belongs to _unattributed.
    """
    _setup_docs(
        mock_db,
        {
            "2026-06-23": {
                "desktop_chat": {"quota_questions": 5},
                "plan_usage": {"operator": {"desktop_chat": {"quota_questions": 2}}},
            }
        },
    )

    usage = user_usage.get_monthly_chat_usage("uid", now=NOW)
    by_plan = usage["usage_by_plan"]

    assert by_plan["operator"]["questions"] == 2
    assert by_plan["_unattributed"]["questions"] == 3, "only the 3 unaccounted questions"
    assert sum(r["questions"] for r in by_plan.values()) == usage["questions"] == 5
