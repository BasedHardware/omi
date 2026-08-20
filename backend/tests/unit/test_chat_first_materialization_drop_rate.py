from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from utils.task_intelligence import chat_first_materialization_health as report

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
SCHEDULED_NOW = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)


def _intent(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        'source': 'capture_arrival',
        'delivery_state': 'ready',
        'created_at': NOW - timedelta(hours=72),
        'blocks': [{'type': 'conversationLink'}],
    }
    document.update(overrides)
    return document


def _summarize(documents: list[dict[str, Any]], stale_after_hours: int = 48) -> dict[str, Any]:
    return report.summarize(documents, scope='test', stale_after_hours=stale_after_hours, now=NOW)


def test_unacknowledged_and_old_counts_as_dropped():
    summary = _summarize([_intent()])
    assert summary['dropped'] == 1
    assert summary['delivered'] == 0
    assert summary['drop_rate'] == 1.0
    assert summary['dropped_by_block_type'] == {'conversationLink': 1}


def test_acknowledged_intent_counts_as_delivered():
    summary = _summarize(
        [_intent(delivery_state='delivered', delivered_at=NOW, materialization_receipt_id='r-1')],
    )
    assert summary['delivered'] == 1
    assert summary['dropped'] == 0
    assert summary['drop_rate'] == 0.0


def test_recent_unacknowledged_intent_is_in_flight_not_dropped():
    """An intent younger than the threshold has no decided outcome yet.

    Counting it as a drop would report ~100% on any healthy account, because
    every intent starts life unacknowledged.
    """
    summary = _summarize([_intent(created_at=NOW - timedelta(hours=1))])
    assert summary['in_flight'] == 1
    assert summary['dropped'] == 0
    assert summary['decided'] == 0
    assert summary['drop_rate'] is None


def test_pending_kernel_receipt_is_not_treated_as_delivered():
    """``pending_kernel_receipt`` is a cold-start waiting state, not an acknowledgement."""
    summary = _summarize([_intent(delivery_state='pending_kernel_receipt', source='cold_start_sparse')])
    assert summary['dropped'] == 1
    assert summary['dropped_by_source'] == {'cold_start_sparse': 1}


def test_missing_created_at_is_isolated_rather_than_guessed():
    summary = _summarize([_intent(created_at=None)])
    assert summary['undated'] == 1
    assert summary['dropped'] == 0
    assert summary['in_flight'] == 0


def test_naive_created_at_is_read_as_utc():
    summary = _summarize([_intent(created_at=datetime(2026, 8, 16, 12, 0))])
    assert summary['dropped'] == 1


def test_rate_excludes_in_flight_from_the_denominator():
    documents = [
        _intent(),
        _intent(delivery_state='delivered'),
        _intent(delivery_state='delivered'),
        _intent(created_at=NOW - timedelta(minutes=5)),
    ]
    summary = _summarize(documents)
    assert (summary['dropped'], summary['delivered'], summary['in_flight']) == (1, 2, 1)
    assert summary['decided'] == 3
    assert summary['drop_rate'] == pytest.approx(1 / 3)


def test_repeated_block_type_in_one_intent_counts_once():
    summary = _summarize(
        [_intent(blocks=[{'type': 'conversationLink'}, {'type': 'conversationLink'}, {'type': 'text'}])],
    )
    assert summary['dropped_by_block_type'] == {'conversationLink': 1, 'text': 1}


def test_scheduled_check_does_not_query_outside_its_weekly_slot():
    def unexpected_collector(*_args: Any):
        raise AssertionError('the Firestore scan must not run outside the weekly slot')

    status = report.run_scheduled_check(
        datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        collector=unexpected_collector,
    )

    assert status == 'not_due'


def test_scheduled_check_alarms_on_any_decided_drop(caplog: pytest.LogCaptureFixture):
    def dropped_collector(
        _uid: str | None,
        _limit: int | None,
        stale_after_hours: int,
        now: datetime,
        _min_created_at: datetime | None,
    ) -> report.MaterializationHealthReport:
        return report.summarize(
            [_intent(created_at=now - timedelta(hours=72))],
            scope='all_accounts',
            stale_after_hours=stale_after_hours,
            now=now,
        )

    with caplog.at_level(logging.ERROR, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=dropped_collector)

    assert status == 'unhealthy'
    assert 'chat_first_materialization_health review=true alarm=true status=unhealthy' in caplog.text
    assert 'conversation_link_dropped=1' in caplog.text


def test_scheduled_check_routes_a_healthy_zero_drop_verdict(caplog: pytest.LogCaptureFixture):
    def healthy_collector(
        _uid: str | None,
        _limit: int | None,
        stale_after_hours: int,
        now: datetime,
        _min_created_at: datetime | None,
    ) -> report.MaterializationHealthReport:
        return report.summarize(
            [_intent(delivery_state='delivered', delivered_at=now, materialization_receipt_id='r-1')],
            scope='all_accounts',
            stale_after_hours=stale_after_hours,
            now=now,
        )

    with caplog.at_level(logging.INFO, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=healthy_collector)

    assert status == 'healthy'
    assert 'chat_first_materialization_health review=true alarm=false status=healthy' in caplog.text
    assert 'drop_rate=0.000000' in caplog.text


def test_scheduled_check_alarms_when_the_monitor_cannot_read(caplog: pytest.LogCaptureFixture):
    def failed_collector(
        _uid: str | None,
        _limit: int | None,
        _stale_after_hours: int,
        _now: datetime,
        _min_created_at: datetime | None,
    ) -> report.MaterializationHealthReport:
        raise RuntimeError('credential detail must not reach the log')

    with caplog.at_level(logging.ERROR, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=failed_collector)

    assert status == 'monitor_error'
    assert 'review=true status=monitor_error error_class=RuntimeError' in caplog.text
    assert 'credential detail' not in caplog.text


# ---------------------------------------------------------------------------
# Windowing: HEALTH_CHECK_WINDOW_DAYS bounds both the read and the verdict.
#
# These use a small Firestore stand-in rather than mocking `collect` itself,
# so the assertions exercise the real `_documents` -> `summarize` pipeline,
# including the `where(created_at >=```) filter `_documents` builds. The fake
# reproduces the one Firestore behaviour the design leans on: a document is
# excluded from a field filter's results whenever that field is missing or
# the wrong type, regardless of when the document was written.
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return self._data


class _FakeCollectionGroupQuery:
    def __init__(self, documents: list[dict[str, Any]]):
        self._documents = documents
        self._min_created_at: datetime | None = None
        self._limit: int | None = None

    def where(self, *, filter: Any) -> '_FakeCollectionGroupQuery':
        assert filter.field_path == 'created_at'
        assert filter.op_string == '>='
        self._min_created_at = filter.value
        return self

    def limit(self, count: int) -> '_FakeCollectionGroupQuery':
        self._limit = count
        return self

    def stream(self) -> Any:
        matched = [document for document in self._documents if self._matches(document)]
        if self._limit is not None:
            matched = matched[: self._limit]
        return iter(_FakeSnapshot(document) for document in matched)

    def _matches(self, document: dict[str, Any]) -> bool:
        if self._min_created_at is None:
            return True
        value = document.get('created_at')
        if not isinstance(value, datetime):
            # Firestore drops documents that lack (or mistype) a filtered field.
            return False
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized >= self._min_created_at


class _FakeFirestoreClient:
    def __init__(self, documents: list[dict[str, Any]]):
        self._documents = documents

    def collection_group(self, name: str) -> _FakeCollectionGroupQuery:
        assert name == report.INTENTS_COLLECTION
        return _FakeCollectionGroupQuery(self._documents)


def test_windowed_collect_excludes_a_drop_older_than_the_window():
    window_start = NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS)
    old_drop = _intent(created_at=NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS + 5))
    fresh_drop = _intent(created_at=NOW - timedelta(days=3))
    client = _FakeFirestoreClient([old_drop, fresh_drop])

    result = report.collect(None, None, 48, NOW, window_start, firestore_client=client)

    assert result['dropped'] == 1
    assert result['window_start'] == window_start.isoformat()


def test_unwindowed_collect_still_counts_an_old_drop():
    old_drop = _intent(created_at=NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS + 5))
    client = _FakeFirestoreClient([old_drop])

    result = report.collect(None, None, 48, NOW, None, firestore_client=client)

    assert result['dropped'] == 1
    assert result['window_start'] is None


def test_scheduled_check_computes_the_window_from_its_own_run_time():
    """`run_scheduled_check` must derive the window bound itself, not rely on a collector default."""
    captured: dict[str, Any] = {}

    def spy_collector(
        _uid: str | None,
        _limit: int | None,
        _stale_after_hours: int,
        now: datetime,
        min_created_at: datetime | None,
    ) -> report.MaterializationHealthReport:
        captured['now'] = now
        captured['min_created_at'] = min_created_at
        return report.summarize([], scope='all_accounts', stale_after_hours=48, now=now)

    report.run_scheduled_check(SCHEDULED_NOW, collector=spy_collector)

    assert captured['min_created_at'] == captured['now'] - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS)


def test_scheduled_check_still_alarms_on_a_drop_inside_the_window(caplog: pytest.LogCaptureFixture):
    still_windowed = SCHEDULED_NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS - 1)
    client = _FakeFirestoreClient([_intent(created_at=still_windowed)])
    collector = functools.partial(report.collect, firestore_client=client)

    with caplog.at_level(logging.ERROR, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=collector)

    assert status == 'unhealthy'
    assert 'window_days=14' in caplog.text


def test_scheduled_check_clears_once_the_same_drop_rolls_past_the_window(caplog: pytest.LogCaptureFixture):
    """The latch bug: an all-time scan never recovers once one intent has ever been dropped.

    The same document that alarms the run above must stop alarming once its
    `created_at` falls outside the window, with no change to the intent itself
    -- only time passing. That is what lets a resolved problem return to
    'healthy' instead of staying red forever.
    """
    now_outside_window = SCHEDULED_NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS + 1)
    client = _FakeFirestoreClient([_intent(created_at=now_outside_window)])
    collector = functools.partial(report.collect, firestore_client=client)

    with caplog.at_level(logging.INFO, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=collector)

    assert status == 'healthy'
    assert 'chat_first_materialization_health review=true alarm=false status=healthy' in caplog.text


def test_windowed_scan_cannot_see_an_undated_document_no_matter_how_recent():
    """Documented trade-off: a filter on `created_at` excludes documents missing it outright."""
    window_start = NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS)
    fresh_but_undated = _intent(created_at=None)
    client = _FakeFirestoreClient([fresh_but_undated])

    windowed = report.collect(None, None, 48, NOW, window_start, firestore_client=client)
    unwindowed = report.collect(None, None, 48, NOW, None, firestore_client=client)

    assert windowed['undated'] == 0
    assert unwindowed['undated'] == 1


def test_render_reports_all_time_when_unwindowed():
    summary = _summarize([_intent(delivery_state='delivered')])
    assert 'window               all-time' in report.render(summary)


def test_render_reports_the_window_start_when_windowed():
    window_start = NOW - timedelta(days=report.HEALTH_CHECK_WINDOW_DAYS)
    summary = report.summarize(
        [_intent(delivery_state='delivered')],
        scope='all_accounts',
        stale_after_hours=48,
        now=NOW,
        window_start=window_start,
    )
    assert f'window               since {window_start.isoformat()}' in report.render(summary)
