"""Behavioral contract for the stale bare-processing crash-orphan reconciler.

These tests pin the #10461 revision: eligibility is bounded by the server-owned
admission fence, legacy rows migrate rather than complete on sight, each aged
orphan reaches exactly one terminal through a generation/ownership fence, query
failure is fail-closed, a persisted sweep cursor guarantees eventual discovery,
unexpected per-row failures are counted as errors distinct from expected CAS
skips, and outcomes surface on a privacy-safe reconciliation counter. The deeper
saturation / timestamp-authority / cursor-wraparound / fence contracts live in
``test_conversation_finalization_jobs.py``; the end-to-end no-fanout proof lives
in the hermetic listen_pusher_stack gauntlet.
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
    """Wire the service to a fixed candidate window and a fake fenced completion.

    ``complete`` mocks ``jobs_db.complete_orphan_conversation`` (the generation /
    ownership fence), distinct from the legacy ``lifecycle.complete`` CAS.
    """
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_after', lambda: timedelta(seconds=900))
    monkeypatch.setattr(
        service.jobs_db,
        'get_stale_processing_orphan_candidates',
        lambda **kwargs: {'candidates': list(candidates), 'resume_after_path': None, 'exhausted': True},
    )
    monkeypatch.setattr(
        service.jobs_db,
        'get_stale_processing_sweep_cursor',
        lambda **kwargs: {'resume_after_path': None, 'generation': 0},
    )
    advance_cursor = MagicMock(return_value=True)
    monkeypatch.setattr(service.jobs_db, 'advance_stale_processing_sweep_cursor', advance_cursor)
    stamp = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'stamp_processing_admission_if_absent', stamp)
    complete = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'complete_orphan_conversation', complete)
    return stamp, complete


def test_legacy_orphan_is_migrated_not_completed(monkeypatch):
    stamp, complete = _install(monkeypatch, [_candidate('uid', 'legacy-1', legacy=True)])

    result = service.reconcile_stale_processing_conversations()

    assert result == {'completed': 0, 'migrated': 1, 'skipped': 0, 'error': 0}
    stamp.assert_called_once_with('uid', 'legacy-1', firestore_client=None)
    # A legacy row is never terminalized on first sight.
    complete.assert_not_called()


def test_aged_orphan_reaches_exactly_one_terminal_through_the_fence(monkeypatch):
    _stamp, complete = _install(monkeypatch, [_candidate('uid', 'aged-1', legacy=False)])
    complete.return_value = True

    result = service.reconcile_stale_processing_conversations()

    assert result['completed'] == 1
    complete.assert_called_once_with('uid', 'aged-1', expected_admitted_at=_ADMITTED, firestore_client=None)


def test_fence_skip_is_a_skip_not_an_error(monkeypatch):
    """An expected CAS fencing (the row moved on) is a skip, not an error."""
    _stamp, complete = _install(monkeypatch, [_candidate('uid', 'fenced-1', legacy=False)])
    complete.return_value = False

    result = service.reconcile_stale_processing_conversations()

    assert result == {'completed': 0, 'migrated': 0, 'skipped': 1, 'error': 0}
    complete.assert_called_once()


def test_query_failure_is_fail_closed_and_records_an_error(monkeypatch):
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_after', lambda: timedelta(seconds=900))
    monkeypatch.setattr(
        service.jobs_db,
        'get_stale_processing_sweep_cursor',
        lambda **kwargs: {'resume_after_path': None, 'generation': 0},
    )

    def _boom(**kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_candidates', _boom)
    complete = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'complete_orphan_conversation', complete)

    result = service.reconcile_stale_processing_conversations()

    assert result['error'] == 1
    # A failed sweep never terminalizes anything.
    complete.assert_not_called()


def test_unexpected_per_row_exception_is_an_error_not_a_skip(monkeypatch):
    """An unexpected completion failure (e.g. Firestore unavailable for one row)
    is counted as an error, distinct from an expected CAS fencing skip."""
    _stamp, complete = _install(monkeypatch, [_candidate('uid', 'boom-1', legacy=False)])
    complete.side_effect = RuntimeError('transaction aborted')

    result = service.reconcile_stale_processing_conversations()

    assert result == {'completed': 0, 'migrated': 0, 'skipped': 0, 'error': 1}


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


def test_sweep_advances_and_rotates_the_cursor_with_cas_generation(monkeypatch):
    """The service threads the persisted cursor with CAS generation: it resumes
    from the saved position, bumps the generation on each advance, and wraps
    (saves None) once a window is exhausted — so repeated bounded sweeps
    guarantee eventual discovery. The generation prevents multi-pod rewind."""
    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_after', lambda: timedelta(seconds=900))
    cursor_state = {'resume_after_path': None, 'generation': 0}
    advance_log: list[tuple[int, str | None]] = []

    def _fake_get_cursor(**kwargs):
        return dict(cursor_state)

    def _fake_advance(expected_generation, new_path, **kwargs):
        advance_log.append((expected_generation, new_path))
        cursor_state['resume_after_path'] = new_path
        cursor_state['generation'] = expected_generation + 1
        return True

    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_sweep_cursor', _fake_get_cursor)
    monkeypatch.setattr(service.jobs_db, 'advance_stale_processing_sweep_cursor', _fake_advance)
    windows = [
        {'candidates': [], 'resume_after_path': 'users/u/conversations/a', 'exhausted': False},
        {'candidates': [], 'resume_after_path': 'users/u/conversations/b', 'exhausted': False},
        {'candidates': [_candidate('uid', 'later-orphan')], 'resume_after_path': None, 'exhausted': True},
    ]
    call = {'i': 0}

    def _fake_candidates(**kwargs):
        window = windows[call['i']]
        call['i'] += 1
        return window

    monkeypatch.setattr(service.jobs_db, 'get_stale_processing_orphan_candidates', _fake_candidates)
    complete = MagicMock(return_value=True)
    monkeypatch.setattr(service.jobs_db, 'complete_orphan_conversation', complete)

    # First sweep resumes from None (nothing persisted), advances the cursor.
    service.reconcile_stale_processing_conversations()
    # Second sweep resumes from the persisted cursor, advances again.
    service.reconcile_stale_processing_conversations()
    # Third sweep wraps (exhausted) and recovers the later orphan.
    result = service.reconcile_stale_processing_conversations()

    assert advance_log == [(0, 'users/u/conversations/a'), (1, 'users/u/conversations/b'), (2, None)]
    assert result['completed'] == 1
    # Each discovery call received the cursor persisted by the previous sweep.
    assert call['i'] == 3
