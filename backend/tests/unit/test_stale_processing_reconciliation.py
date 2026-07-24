"""Behavioral contract for the stale bare-processing crash-orphan reconciler.

These tests pin the #10461 revision: eligibility is bounded by the
server-owned admission fence, legacy rows migrate rather than complete on
sight, each aged orphan reaches exactly one terminal, query failure is
fail-closed, and outcomes surface on a privacy-safe reconciliation counter.
The deeper saturation / timestamp-authority / index contracts live in
``test_conversation_finalization_jobs.py``; the end-to-end no-fanout proof
lives in the hermetic listen_pusher_stack gauntlet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from services import conversation_finalization as service

_ADMITTED = datetime.now(timezone.utc) - timedelta(seconds=1000)


def _candidate(uid: str, cid: str, *, legacy: bool = False) -> dict:
    return {
        'uid': uid,
        'conversation_id': cid,
        'processing_admitted_at': None if legacy else _ADMITTED,
        'legacy': legacy,
    }


def _install(monkeypatch, candidates) -> tuple[MagicMock, MagicMock]:
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_after', lambda: timedelta(seconds=900))
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_candidates', lambda **kwargs: list(candidates))
    stamp = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'stamp_processing_admission_if_absent', stamp)
    complete = MagicMock()
    monkeypatch.setattr(service.lifecycle_service, 'complete', complete)
    return stamp, complete


def test_legacy_orphan_is_migrated_not_completed(monkeypatch):
    stamp, complete = _install(monkeypatch, [_candidate('uid', 'legacy-1', legacy=True)])

    result = service.reconcile_stale_processing_conversations()

    assert result == {'completed': 0, 'migrated': 1, 'skipped': 0, 'error': 0}
    stamp.assert_called_once_with('uid', 'legacy-1', firestore_client=None)
    # A legacy row is never terminalized on first sight.
    complete.assert_not_called()


def test_aged_orphan_reaches_exactly_one_terminal(monkeypatch):
    _stamp, complete = _install(monkeypatch, [_candidate('uid', 'aged-1', legacy=False)])
    complete.return_value = True

    result = service.reconcile_stale_processing_conversations()

    assert result['completed'] == 1
    complete.assert_called_once_with('uid', 'aged-1')


def test_already_terminal_orphan_is_fenced_without_a_second_terminal(monkeypatch):
    _stamp, complete = _install(monkeypatch, [_candidate('uid', 'fenced-1', legacy=False)])
    complete.return_value = False

    result = service.reconcile_stale_processing_conversations()

    assert result['completed'] == 0
    assert result['skipped'] == 1
    complete.assert_called_once()


def test_query_failure_is_fail_closed_and_records_an_error(monkeypatch):
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_after', lambda: timedelta(seconds=900))

    def _boom(**kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_candidates', _boom)
    complete = MagicMock()
    monkeypatch.setattr(service.lifecycle_service, 'complete', complete)

    result = service.reconcile_stale_processing_conversations()

    assert result['error'] == 1
    # A failed sweep never terminalizes anything.
    complete.assert_not_called()


def test_outcomes_increment_the_privacy_safe_reconciliation_counter(monkeypatch):
    metric = MagicMock()
    monkeypatch.setattr(service, 'LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL', metric)
    _stamp, complete = _install(
        monkeypatch,
        [
            _candidate('uid', 'legacy-1', legacy=True),
            _candidate('uid', 'completed-1', legacy=False),
            _candidate('uid', 'fenced-1', legacy=False),
        ],
    )
    complete.side_effect = [True, False]

    service.reconcile_stale_processing_conversations()

    outcomes = [call.kwargs['outcome'] for call in metric.labels.call_args_list]
    assert outcomes == ['migrated', 'completed', 'skipped']
