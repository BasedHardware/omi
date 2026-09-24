"""Regression tests for database.user_usage flat plan_usage extraction and null counter guards."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from database import user_usage  # noqa: E402

NOW = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


class _Snap:
    def __init__(self, data, doc_id=None):
        self._d = data
        self.id = doc_id
        self.exists = True

    def to_dict(self):
        return self._d


class _Query:
    def __init__(self, docs):
        self._docs = list(docs)

    def where(self, **_kwargs):
        return self

    def stream(self):
        return iter([_Snap(d) for d in self._docs])


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock(name='db')
    monkeypatch.setattr(user_usage, 'db', db)
    monkeypatch.setattr(user_usage, 'record_firestore_read', lambda *_a, **_kw: None)
    return db


def test_get_usage_by_plan_attributes_flat_dotted_hourly_usage_written_by_update_hourly_usage(mock_db, monkeypatch):
    """update_hourly_usage writes flat dotted `plan_usage.<plan>.*` keys via set(merge=True).

    Firestore set(merge=True) stores dotted keys as literal top-level field names rather than a
    nested `plan_usage` dict. get_usage_by_plan must reconstruct those flat keys under the recorded
    plan (`plus`) instead of misclassifying the entire document as `_unattributed` and dropping cost.
    """
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *_a, **_kw: 'plus')
    hourly_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = hourly_ref

    user_usage.update_hourly_usage(
        'uid',
        NOW,
        {'transcription_seconds': 180, 'words_transcribed': 450},
        cost_usd=0.045,
        cost_status='complete',
    )
    written_doc = hourly_ref.set.call_args.args[0]

    monkeypatch.setattr(user_usage, 'get_monthly_chat_usage', lambda *_a, **_kw: {'usage_by_plan': {}})
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = _Query([written_doc])

    report = user_usage.get_usage_by_plan('uid', now=NOW, firestore_client=client)

    assert 'plus' in report
    assert '_unattributed' not in report
    assert report['plus']['transcription_seconds'] == 180
    assert report['plus']['words_transcribed'] == 450
    assert report['plus']['cost_usd'] == pytest.approx(0.045)
    assert report['plus']['cost_status'] == 'complete'


def test_get_usage_by_plan_mixed_hourly_doc_attributes_only_residual_to_unattributed(monkeypatch):
    """When an hourly doc has pre-attribution root counters plus partial flat plan_usage counters,
    only the unaccounted residual belongs to `_unattributed`."""
    monkeypatch.setattr(user_usage, 'get_monthly_chat_usage', lambda *_a, **_kw: {'usage_by_plan': {}})
    mixed_doc = {
        'year': 2026,
        'month': 6,
        'transcription_seconds': 300,
        'plan_usage.plus.transcription_seconds': 120,
        'plan_usage.plus._metadata.cost_status_counts.missing': 1,
        'plan_usage.plus._metadata.cost_exclusions.provider_cost_not_recorded': 1,
    }
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value = _Query([mixed_doc])

    report = user_usage.get_usage_by_plan('uid', now=NOW, firestore_client=client)

    assert report['plus']['transcription_seconds'] == 120
    assert report['plus']['cost_exclusions'] == {'provider_cost_not_recorded': 1}
    assert report['_unattributed']['transcription_seconds'] == 180
    assert report['_unattributed']['cost_exclusions'] == {'plan_snapshot_missing': 1}


def test_get_monthly_chat_usage_recognizes_flat_dotted_plan_usage_keys(monkeypatch):
    """Flat `plan_usage.<plan>.*` keys on llm_usage docs must be attributed to `<plan>` without
    creating a phantom `_unattributed` row."""
    flat_llm_doc = {
        'desktop_chat.quota_questions': 3,
        'plan_usage.operator.desktop_chat.quota_questions': 3,
        'plan_usage.operator.desktop_chat.cost_usd': 0.12,
        'plan_usage.operator._metadata.cost_status_counts.complete': 3,
    }
    monkeypatch.setattr(
        user_usage,
        '_current_month_llm_usage_docs',
        lambda *_a, **_kw: iter([_Snap(flat_llm_doc, '2026-06-23')]),
    )
    client = MagicMock()

    usage = user_usage.get_monthly_chat_usage('uid', now=NOW, firestore_client=client)

    assert usage['questions'] == 3
    assert usage['usage_by_plan']['operator']['questions'] == 3
    assert usage['usage_by_plan']['operator']['cost_usd'] == pytest.approx(0.12)
    assert usage['usage_by_plan']['operator']['cost_status'] == 'complete'
    assert '_unattributed' not in usage['usage_by_plan']


def test_null_counters_and_malformed_bucket_coordinates_do_not_crash_usage_aggregators(mock_db):
    """Explicit None/boolean counters or out-of-range hour/day/month/year values in hourly_usage
    docs must not raise TypeError/ValueError or emit invalid date strings."""
    malformed_docs = [
        {
            'year': 2026,
            'month': 6,
            'day': 23,
            'hour': 12,
            'transcription_seconds': None,
            'words_transcribed': True,
            'insights_gained': -5,
            'memories_created': 4,
            'speech_seconds': None,
        },
        {
            'year': None,
            'month': None,
            'day': None,
            'hour': None,
            'transcription_seconds': 50,
            'words_transcribed': 10,
        },
        {
            'year': 0,
            'month': 13,
            'day': 0,
            'hour': 25,
            'transcription_seconds': 20,
        },
    ]
    mock_db.collection.return_value.document.return_value.collection.return_value = _Query(malformed_docs)

    start = datetime(2026, 6, 23, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 24, 0, 0, tzinfo=timezone.utc)

    today_stats = user_usage.get_today_usage_stats('uid', start, end)
    assert today_stats['memories_created'] == 4
    assert today_stats['transcription_seconds'] == 50
    assert today_stats['words_transcribed'] == 10

    today_history = user_usage.get_hourly_history_for_today('uid', start, end)
    assert [row['date'] for row in today_history] == ['2026-06-23T00:00:00Z', '2026-06-23T12:00:00Z']
    assert today_history[1]['memories_created'] == 4

    monthly_stats = user_usage.get_monthly_usage_stats('uid', NOW)
    assert monthly_stats['transcription_seconds'] == 70
    assert monthly_stats['memories_created'] == 4

    daily_history = user_usage.get_daily_history_for_month('uid', NOW)
    assert [row['date'] for row in daily_history] == ['2026-06-23']

    monthly_history = user_usage.get_monthly_history_for_year('uid', NOW)
    assert [row['date'] for row in monthly_history] == ['2026-06-01']

    yearly_history = user_usage.get_yearly_history('uid')
    assert [row['date'] for row in yearly_history] == ['2026-01-01']

    all_time = user_usage.get_current_user_usage('uid', 'all_time', now=NOW)
    assert all_time['all_time']['transcription_seconds'] == 70
    assert [row['date'] for row in all_time['history']] == ['2026-01-01']
