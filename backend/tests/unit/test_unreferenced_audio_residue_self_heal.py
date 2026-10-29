"""Residue the sweep could not reclaim gets its own bounded re-attack.

Failure-Class: FC-post-commit-index-maintenance-terminal — work that runs after
the authoritative write has already committed is best-effort, and its failure
may not rewrite the committed outcome as a failure. The empty-generation sweep
deletes the Firestore row first and reclaims its private-cloud audio second;
when the purge verifier still sees residue after its settle passes (a same-key
late chunk upload racing the sweep), the boundary classifies the signal as
retained audio — but until now it stopped there: the racing object stayed on
the bucket with no owner and no re-attack, and the merge-side sweep caller
logged the same signal as a plain ``logger.error`` line. In production the
deployed sweep has no settle pass at all, so every late-writer race walks
straight into the failed-write arm: a full ERROR traceback plus an
``omi_fallback_total`` exhaustion event on each occurrence (prod backend-listen
2026-10-29 09:00-12:11Z: ``Failed to reclaim unreferenced audio`` ramping
185 -> 269 per 30-minute window, 1000 distinct conversations / 268 uids in
three hours, zero conversation repeats — the race, not a poisoned prefix).

The fix extends the deferral the storage-blip arm already owns to the residual
signal: the boundary arms the same bounded daemon-thread re-attack (deduped
per ``uid`` + ``conversation`` so concurrent sweeps of one conversation share
one budget), and exhaustion stays inside the retained-audio classification —
the same INFO message the sensor already knows, the last fault demoted to
DEBUG, no ERROR, no degradation event. The purge verifier keeps its fail-closed
verdict for the account wipe; only the post-commit sweep's reaction changes.

Guards:
- the residual deferral arms the sweep retry exactly like a blip, with the
  same budget and the same owned convergence;
- exhaustion never reclassifies the committed delete: INFO retained-audio
  family, fault at DEBUG, no ``omi_fallback_total`` event;
- concurrent sweeps of one conversation arm one retry; different conversations
  (and the merge-side caller) keep independent budgets;
- permanent failures during the retry stay loud, the verifier's terminal
  raise is untouched, and the merge-side permanent arm keeps its ERROR.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import (
    BadGateway,
    Forbidden,
    GatewayTimeout,
    ServiceUnavailable,
    TooManyRequests,
)

from utils.conversations import lifecycle as lifecycle_service
from utils.conversations import merge_conversations as merge_service
from utils.other import storage as storage_mod

_RESIDUAL = RuntimeError('owner storage purge left 1 objects under chunks/uid/conv/')


def _residual(objects: int = 1, prefix: str = 'chunks/uid/conv/') -> RuntimeError:
    return RuntimeError(f'owner storage purge left {objects} objects under {prefix}')


class _RetrySpy:
    """Capture ``_schedule_sweep_retry`` calls instead of arming threads."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple]] = []

    def __call__(self, attempt: Any, args: tuple, **kwargs: Any) -> bool:
        self.calls.append((attempt, args))
        return True


@pytest.fixture()
def retry_spy(monkeypatch) -> _RetrySpy:
    spy = _RetrySpy()
    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', spy, raising=False)
    return spy


def _fallback_spy(monkeypatch) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    monkeypatch.setattr(
        lifecycle_service,
        'record_fallback',
        lambda **kwargs: events.append(kwargs),
        raising=False,
    )
    return events


def _failing_sweep(monkeypatch, error: BaseException) -> None:
    def failing(*a: Any, **k: Any) -> None:
        raise error

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', failing, raising=False)


class _SyncThread:
    """Run the retry body inline: deterministic mechanics without wall time."""

    def __init__(self, target=None, name=None, daemon=None):
        self._target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True
        self._target()


class _ManualThread:
    """Park the retry body until the test runs it: dedupe without timing."""

    instances: list['_ManualThread'] = []

    def __init__(self, target=None, name=None, daemon=None):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.ran = False
        _ManualThread.instances.append(self)

    def start(self) -> None:
        pass

    def run_now(self) -> None:
        self.ran = True
        self.target()


@pytest.fixture(autouse=True)
def _fresh_residue_slots():
    """The inflight set is module state on purpose; tests must not inherit it."""
    with lifecycle_service._residue_sweeps_inflight_lock:
        lifecycle_service._residue_sweeps_inflight.clear()
    _ManualThread.instances.clear()
    yield
    with lifecycle_service._residue_sweeps_inflight_lock:
        lifecycle_service._residue_sweeps_inflight.clear()
    _ManualThread.instances.clear()


# ── A. The residual signal takes the same owned deferral as a blip ──────────


def test_residual_signal_takes_the_owned_deferral(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _RESIDUAL)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'a deferral is a warning, not a traceback'
    assert deferred[0].exc_info is None
    assert 'uid=uid' in deferred[0].getMessage() and 'conversation_id=conv' in deferred[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert retry_spy.calls, 'the residual deferral must arm its own retry'


def test_residual_message_keeps_the_sensor_stable_text(monkeypatch, caplog, retry_spy):
    """Dashboards key on the retained-audio family; the deferral must not
    introduce a new signature for a signal that was already classified."""
    _failing_sweep(monkeypatch, _RESIDUAL)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred[0].getMessage().startswith('Unreferenced audio sweep deferred behind a late writer uid=')


def test_single_object_residue_defers_like_a_blip(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _residual(objects=1))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert retry_spy.calls and any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)


def test_multi_object_residue_defers_like_a_blip(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _residual(objects=3))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert retry_spy.calls and any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)


def test_residual_deferral_emits_no_degradation_event(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert fallbacks == [], 'a deferral is not an omi_fallback_total exhaustion'


def test_residual_exhaustion_keeps_the_retained_classification(monkeypatch, caplog):
    """Exhaustion demotes to the retained-audio family: INFO, no traceback,
    no degradation event — the committed delete is still not a failed write."""
    _failing_sweep(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    assert not [r for r in caplog.records if r.levelno >= 40], 'exhaustion must not reopen the failed-write arm'
    assert fallbacks == [], 'exhaustion is not an omi_fallback_total exhaustion'
    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained and all(r.levelno == 20 for r in retained)


def test_residual_exhaustion_message_keeps_the_sensor_key(monkeypatch, caplog):
    _failing_sweep(monkeypatch, _RESIDUAL)

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained[0].getMessage().startswith('Retained unreferenced audio behind a late writer uid=')


def test_residual_exhaustion_emits_no_degradation_event(monkeypatch, caplog):
    _failing_sweep(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    assert fallbacks == []


def test_residual_exhaustion_reports_the_last_fault_at_debug(monkeypatch, caplog):
    """The final fault is not swallowed: it lands one level down, with its
    traceback, for anyone debugging the residue afterwards."""
    _failing_sweep(monkeypatch, _RESIDUAL)

    with caplog.at_level('DEBUG'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    exhausted = [r for r in caplog.records if 'residue retry exhausted' in r.getMessage()]
    assert exhausted and exhausted[0].levelno == 10
    assert exhausted[0].exc_info is not None, 'the last fault is reported, not swallowed'


def test_converged_message_is_info_level_and_names_the_sweep(monkeypatch, caplog):
    calls: list[tuple] = []

    def converging(*a: Any, **k: Any) -> None:
        calls.append(a)

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', converging, raising=False)

    with caplog.at_level('DEBUG'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained == [], 'a converged retry is a success, not a retention report'
    assert calls == [('uid', 'conv')], 'the retry re-attacked the same conversation'


def test_clean_sweep_arms_no_retry(monkeypatch, caplog, retry_spy):
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert retry_spy.calls == []
    assert not [r for r in caplog.records if r.levelno >= 30]


def test_registered_audio_retention_never_arms_a_retry(monkeypatch, caplog, retry_spy):
    touched: list[tuple] = []
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append(a),
        raising=False,
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {'audio_files': [{'path': 'chunks/x'}]})

    assert touched == []
    assert retry_spy.calls == [], 'retention is a decision, not a fault — nothing to retry'


def test_each_residual_deferral_arms_its_own_retry(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _RESIDUAL)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv-a', {})
        lifecycle_service._discard_unreferenced_audio('uid', 'conv-b', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    announced = sorted(r.getMessage().split('conversation_id=')[1].split()[0] for r in deferred)
    assert announced == ['conv-a', 'conv-b'], 'each conversation arms its own retry'
    assert len(retry_spy.calls) == 2


def test_deferred_log_carries_uid_and_conversation_fields(monkeypatch, caplog, retry_spy):
    _failing_sweep(monkeypatch, _RESIDUAL)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid-42', 'conv-7', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert 'uid=uid-42' in deferred[0].getMessage()
    assert 'conversation_id=conv-7' in deferred[0].getMessage()


def test_exhaustion_log_carries_uid_and_conversation_fields(monkeypatch, caplog):
    _failing_sweep(monkeypatch, _RESIDUAL)

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid-42', 'conv-7', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert 'uid=uid-42' in retained[0].getMessage()
    assert 'conversation_id=conv-7' in retained[0].getMessage()


# ── B. Concurrent sweeps of one conversation share one budget ───────────────


def test_same_conversation_racing_sweeps_arm_one_retry(monkeypatch):
    """Two sweeps racing on the same residue dedupe onto one retry thread."""
    armed: list[tuple] = []
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: armed.append(a),
        raising=False,
    )

    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')
    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')

    assert len(_ManualThread.instances) == 1, 'one conversation, one retry thread'


def test_deduped_second_sweep_still_classifies_as_retained(monkeypatch, caplog):
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')
        lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')

    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert len(retained) == 1, 'the deduped sweep keeps the retained classification'
    assert len(deferred) == 1, 'only the first sweep announces the deferral'


def test_dedup_slot_frees_when_the_retry_thread_ends(monkeypatch):
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )

    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')
    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')
    assert len(_ManualThread.instances) == 1

    _ManualThread.instances[0].run_now()
    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')
    assert len(_ManualThread.instances) == 2, 'a finished retry frees the conversation for the next race'


def test_dedup_key_is_per_uid_and_conversation(monkeypatch):
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )

    lifecycle_service._defer_or_keep_residual_sweep('uid-a', 'conv')
    lifecycle_service._defer_or_keep_residual_sweep('uid-b', 'conv')
    lifecycle_service._defer_or_keep_residual_sweep('uid-a', 'conv-2')

    assert len(_ManualThread.instances) == 3, 'the dedupe key is the (uid, conversation) pair'


def test_failed_thread_start_leaves_the_slot_free(monkeypatch, caplog):
    def broken_thread(*a: Any, **k: Any) -> None:
        raise RuntimeError('thread factory exhausted')

    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )

    with caplog.at_level('INFO'):
        lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv', start_thread=broken_thread)
        retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
        assert retained, 'a sweep that could not arm keeps the retained classification'
        assert not [r for r in caplog.records if r.levelno >= 40]

    # The failed arm must not wedge the conversation: the next race can arm.
    armed: list[tuple] = []
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: armed.append(a),
        raising=False,
    )
    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv', start_thread=_ManualThread, sleep=lambda s: None)
    assert len(_ManualThread.instances) == 1, 'the next race can arm after a failed start'


def test_dedup_applies_across_merge_and_empty_generation_boundaries(monkeypatch):
    """Both sweep callers share the inflight set: a merge cleanup and an
    empty-generation sweep racing on one conversation arm one retry."""
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: None,
        raising=False,
    )

    lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})
    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')

    assert len(_ManualThread.instances) == 1, 'the inflight set is shared across boundaries'


def test_blip_deferral_is_never_deduped_against_residue(monkeypatch, retry_spy):
    """The blip arm has no inflight set: two blips on the same conversation
    each arm their own retry, exactly as before this change."""
    _failing_sweep(monkeypatch, TooManyRequests('429'))
    _fallback_spy(monkeypatch)

    lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})
    lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert len(retry_spy.calls) == 2, 'the blip deferral keeps its per-crossing ownership'


# ── C. The retry mechanics treat residue as the same bounded transient ──────


def test_retry_reattacks_residue_and_converges(monkeypatch, caplog):
    attempts: list[int] = []
    fallbacks = _fallback_spy(monkeypatch)

    def converging(uid, conversation_id):
        attempts.append(1)
        if len(attempts) == 1:
            raise _residual(objects=1)

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', converging, raising=False)

    with caplog.at_level('DEBUG'):
        lifecycle_service._defer_or_keep_residual_sweep(
            'uid', 'conv', passes=2, delay=0.0, start_thread=_SyncThread, sleep=lambda s: None
        )

    assert len(attempts) == 2, 'one more pass reclaimed the residue'
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == []


def test_retry_treats_residue_as_bounded_transient_mid_passes(monkeypatch):
    """Residue inside the retry must not read as permanent: the loop keeps
    its remaining passes instead of stopping after the first re-attack."""
    attempts: list[int] = []
    sleeps: list[float] = []

    def flippy(uid, conversation_id):
        attempts.append(1)
        if len(attempts) == 1:
            raise _residual(objects=2)
        if len(attempts) == 2:
            raise ServiceUnavailable('blip on the second pass')

    lifecycle_service._schedule_sweep_retry(
        flippy,
        ('uid', 'conv'),
        passes=3,
        delay=1.0,
        start_thread=_SyncThread,
        sleep=sleeps.append,
    )

    assert len(attempts) == 3, 'both transient flavours re-attacked within one budget'
    assert len(sleeps) == 3


def test_retry_residue_exhaustion_uses_the_quiet_reporter(monkeypatch, caplog):
    attempts: list[int] = []

    def always_residue(uid, conversation_id):
        attempts.append(1)
        raise _residual(objects=1)

    with caplog.at_level('DEBUG'):
        lifecycle_service._schedule_sweep_retry(
            always_residue,
            ('uid', 'conv'),
            passes=2,
            delay=0.0,
            start_thread=_SyncThread,
            sleep=lambda s: None,
            on_exhausted=lambda error: None,
        )

    assert len(attempts) == 2, 'the budget bounds the re-attacks'
    assert not [r for r in caplog.records if r.levelno >= 40], 'no loud arm behind the quiet reporter'


def test_retry_without_reporter_keeps_the_loud_exhaustion(monkeypatch, caplog):
    attempts: list[int] = []

    def always_blip(uid, conversation_id):
        attempts.append(1)
        raise TooManyRequests('429 forever')

    with caplog.at_level('ERROR'):
        lifecycle_service._schedule_sweep_retry(
            always_blip,
            ('uid', 'conv'),
            passes=2,
            delay=0.0,
            start_thread=_SyncThread,
            sleep=lambda s: None,
        )

    exhausted = [r for r in caplog.records if 'Unreferenced audio sweep retry exhausted' in r.getMessage()]
    assert exhausted and exhausted[0].levelno >= 40, 'the default exhaustion stays loud'
    assert exhausted[0].exc_info is not None


def test_retry_custom_reporter_receives_the_final_fault(monkeypatch):
    seen: list[BaseException] = []
    attempts: list[int] = []

    def always_residue(uid, conversation_id):
        attempts.append(1)
        raise _residual(objects=4)

    lifecycle_service._schedule_sweep_retry(
        always_residue,
        ('uid', 'conv'),
        passes=2,
        delay=0.0,
        start_thread=_SyncThread,
        sleep=lambda s: None,
        on_exhausted=seen.append,
    )

    assert len(attempts) == 2
    assert len(seen) == 1 and 'owner storage purge left 4 objects' in str(seen[0])


def test_retry_permanent_failure_stops_early_with_custom_reporter(monkeypatch):
    attempts: list[int] = []
    seen: list[BaseException] = []

    def refusing(uid, conversation_id):
        attempts.append(1)
        raise Forbidden('bucket policy refuses the delete')

    lifecycle_service._schedule_sweep_retry(
        refusing,
        ('uid', 'conv'),
        passes=3,
        delay=0.0,
        start_thread=_SyncThread,
        sleep=lambda s: None,
        on_exhausted=seen.append,
    )

    assert len(attempts) == 1, 'a permanent failure is not re-attacked'
    assert len(seen) == 1 and isinstance(seen[0], Forbidden)


def test_retry_reporter_exception_never_escapes_the_thread(monkeypatch, caplog):
    def exploding_reporter(error: BaseException) -> None:
        raise RuntimeError('reporter blew up')

    def always_blip(uid, conversation_id):
        raise TooManyRequests('429 forever')

    with caplog.at_level('DEBUG'):
        lifecycle_service._schedule_sweep_retry(
            always_blip,
            ('uid', 'conv'),
            passes=1,
            delay=0.0,
            start_thread=_SyncThread,
            sleep=lambda s: None,
            on_exhausted=exploding_reporter,
        )

    assert not [r for r in caplog.records if r.levelno >= 40], 'a reporter fault must not fabricate a new ERROR'


def test_retry_custom_reporter_called_once_not_per_attempt(monkeypatch):
    seen: list[BaseException] = []
    attempts: list[int] = []

    def always_blip(uid, conversation_id):
        attempts.append(1)
        raise ServiceUnavailable('503')

    lifecycle_service._schedule_sweep_retry(
        always_blip,
        ('uid', 'conv'),
        passes=3,
        delay=0.0,
        start_thread=_SyncThread,
        sleep=lambda s: None,
        on_exhausted=seen.append,
    )

    assert len(attempts) == 3
    assert len(seen) == 1, 'exhaustion is one terminal report, not one per pass'


def test_retry_thread_name_distinguishes_residue_from_blip():
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    def clean(uid, conversation_id) -> None:
        return None

    lifecycle_service._schedule_sweep_retry(
        clean,
        ('uid', 'conv'),
        start_thread=RecordingThread,
        thread_name=lifecycle_service._RESIDUAL_RETRY_THREAD_NAME,
    )

    assert holders[0].name == 'unreferenced-audio-residue-retry'
    assert holders[0].daemon is True


def _tombstone_returning(deleted: bool, conversation: dict[str, Any] | None = None):
    """Stand in for the transaction, honouring its published-snapshot contract."""

    def _tombstone(
        uid: str,
        conversation_id: str,
        recording_session_id: str | None,
        *,
        firestore_client: Any = None,
        deleted_conversation: dict[str, Any] | None = None,
    ) -> bool:
        if deleted and deleted_conversation is not None:
            deleted_conversation.clear()
            deleted_conversation.update(conversation or {})
        return deleted

    return _tombstone


# ── D. The committed outcome keeps its classification end to end ────────────


def test_empty_generation_delete_completes_when_the_sweep_races(monkeypatch, caplog, retry_spy):
    """End to end: the public delete returns True while its sweep raced a late
    writer — one bounded deferral, the retry armed, no ERROR anywhere."""
    monkeypatch.setattr(
        lifecycle_service.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(True, {'id': 'conv', 'status': 'in_progress'}),
        raising=False,
    )
    from utils.conversations import typesense_index

    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'delete_conversation_photos',
        lambda *a, **k: None,
        raising=False,
    )

    _failing_sweep(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conv', 'session')

    assert deleted is True, 'the committed delete keeps its outcome'
    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= 40], 'no traceback, no ERROR'
    assert fallbacks == []
    assert retry_spy.calls, 'the deferral owns its convergence'


def test_empty_generation_delete_stays_committed_when_residue_exhausts(monkeypatch, caplog):
    """End to end at exhaustion: the delete still returns True and the only
    trace is the retained-audio family the sensor already knows."""
    monkeypatch.setattr(
        lifecycle_service.recording_sessions_db,
        'tombstone_and_delete_empty_conversation',
        _tombstone_returning(True, {'id': 'conv', 'status': 'in_progress'}),
        raising=False,
    )
    from utils.conversations import typesense_index

    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'delete_conversation_photos',
        lambda *a, **k: None,
        raising=False,
    )

    _failing_sweep(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    real_defer = lifecycle_service._defer_or_keep_residual_sweep

    def defer_with_parked_thread(uid, conversation_id, **kwargs):
        kwargs.setdefault('start_thread', _ManualThread)
        kwargs.setdefault('sleep', lambda s: None)
        return real_defer(uid, conversation_id, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_defer_or_keep_residual_sweep', defer_with_parked_thread)

    with caplog.at_level('INFO'):
        deleted = lifecycle_service.delete_empty_recording_conversation('uid', 'conv', 'session')

    assert deleted is True
    assert fallbacks == []
    assert not [r for r in caplog.records if r.levelno >= 40]


def test_real_storage_path_residue_defers_and_arms_the_retry(monkeypatch, caplog, retry_spy):
    """End to end through the actual ``delete_conversation_audio_files``: a
    lost delete's residue verdict reaches the lifecycle boundary and is
    classified as an owned deferral — never the catch-all."""
    from google.cloud.exceptions import NotFound

    class _StuckBlob:
        def __init__(self, bucket: '_StuckBucket', name: str) -> None:
            self._bucket = bucket
            self.name = name

        def delete(self) -> None:
            self._bucket.delete_calls += 1
            raise NotFound(f'No such object: {self.name}') if False else None

    class _StuckBucket:
        """The deletes never take effect: the residue verdict is real."""

        def __init__(self, names: set[str]) -> None:
            self.names = set(names)
            self.delete_calls = 0

        def blob(self, name: str) -> Any:
            blob = SimpleNamespace(name=name)
            outer = self

            def _delete() -> None:
                outer.delete_calls += 1

            blob.delete = _delete
            return blob

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    private = _StuckBucket({'chunks/uid/conv/a.opus'})
    derived = _StuckBucket(set())
    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: SimpleNamespace(bucket=lambda name: private if name == 'private' else derived),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and deferred[0].levelno == 30, 'the real path\u2019s residue defers without a traceback'
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == []
    assert retry_spy.calls, 'the deferral arms its own retry'
    assert private.delete_calls == 2, 'the verifier spent its settle budget before deferring'


def test_real_storage_path_settles_before_deferring(monkeypatch, caplog, retry_spy):
    """A race the verifier's own settle pass absorbs never reaches the
    boundary: clean sweep, no deferral, no retry."""

    class _SelfHealingBucket:
        """One ghost survives the first verify re-list, then converges."""

        def __init__(self, names: set[str]) -> None:
            self.names = set(names)
            self.ghosts = 1

        def blob(self, name: str) -> Any:
            outer = self
            blob = SimpleNamespace(name=name)

            def _delete() -> None:
                outer.names.discard(name)
                if outer.ghosts:
                    outer.ghosts -= 1
                    outer.names.add(f'chunks/uid/conv/ghost-{outer.ghosts}.opus')

            blob.delete = _delete
            return blob

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    private = _SelfHealingBucket({'chunks/uid/conv/a.opus'})
    derived = _SelfHealingBucket(set())
    monkeypatch.setattr(
        storage_mod,
        '_get_storage_client',
        lambda: SimpleNamespace(bucket=lambda name: private if name == 'private' else derived),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, 'private_cloud_sync_bucket', 'private', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'derived')
    monkeypatch.delenv('BUCKET_CANONICAL_AUDIO', raising=False)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert private.names == set(), 'the settle pass absorbed the race'
    assert retry_spy.calls == [], 'a converged race needs no deferral'
    assert not [r for r in caplog.records if r.levelno >= 30]


def test_delete_with_registered_audio_and_residue_never_sweeps(monkeypatch, caplog, retry_spy):
    """Retention by registration is decided before storage is touched: even a
    bucket that would fail the verify is never reached."""
    touched: list[str] = []
    monkeypatch.setattr(
        storage_mod,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append('touched'),
        raising=False,
    )
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {'audio_files': [{'path': 'chunks/x'}]})

    assert touched == []
    assert retry_spy.calls == []
    assert not [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]


# ── E. The merge-side sweep caller joins the same boundary ──────────────────


class _MergeHarness:
    """Patches around ``_cleanup_merged_target_after_failure``'s dependencies."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, audio_error: BaseException | None) -> None:
        merge = merge_service

        self.merge = merge

        class _StubMemoryService:
            def __init__(self, db_client: Any = None) -> None:
                pass

            def retract_conversation_memories(self, *a: Any, **k: Any) -> None:
                pass

        monkeypatch.setattr(merge, 'MemoryService', _StubMemoryService, raising=False)
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation_photos', lambda *a, **k: None)
        monkeypatch.setattr(merge.conversations_db, 'delete_conversation', lambda *a, **k: None)
        monkeypatch.setattr(merge, 'delete_vector', lambda *a, **k: None)
        if audio_error is not None:

            def failing(*a: Any, **k: Any) -> None:
                raise audio_error

            monkeypatch.setattr(merge, 'delete_conversation_audio_files', failing, raising=False)
        else:
            monkeypatch.setattr(merge, 'delete_conversation_audio_files', lambda *a, **k: None, raising=False)


def test_merged_target_residue_defers_instead_of_logging_an_error(monkeypatch, caplog, retry_spy):
    harness = _MergeHarness(monkeypatch, _RESIDUAL)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        done = harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert done is True
    errors = [r for r in caplog.records if 'Error deleting merged conversation audio' in r.getMessage()]
    assert errors == [], 'a converging residue must not ride the failed-cleanup ERROR arm'
    assert retry_spy.calls, 'the merge boundary arms the same owned retry'
    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred and 'conversation_id=merged-conv' in deferred[0].getMessage()


def test_merged_target_deferral_arms_the_retry_for_the_merged_target(monkeypatch, caplog, retry_spy):
    harness = _MergeHarness(monkeypatch, _residual(prefix='chunks/uid/merged-conv/'))
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    deferred = [r for r in caplog.records if 'Unreferenced audio sweep deferred' in r.getMessage()]
    assert deferred, 'the merge boundary announces the deferral with the same message'
    assert 'conversation_id=merged-conv' in deferred[0].getMessage()


def test_merged_target_residue_exhaustion_stays_quiet(monkeypatch, caplog):
    """Exhaustion behind the merge boundary keeps the retained-audio family —
    the merged row is already terminal, the delete is not a failed write."""
    harness = _MergeHarness(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)
    real_defer = lifecycle_service._defer_or_keep_residual_sweep

    def defer_with_parked_thread(uid, conversation_id, **kwargs):
        kwargs.setdefault('start_thread', _SyncThread)
        kwargs.setdefault('sleep', lambda s: None)
        return real_defer(uid, conversation_id, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_defer_or_keep_residual_sweep', defer_with_parked_thread)

    with caplog.at_level('INFO'):
        done = harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert done is True
    assert not [r for r in caplog.records if r.levelno >= 40]
    assert fallbacks == []
    retained = [r for r in caplog.records if 'Retained unreferenced audio behind a late writer' in r.getMessage()]
    assert retained, 'exhaustion reports in the retained-audio family'


def test_merged_target_permanent_audio_failure_stays_loud(monkeypatch, caplog, retry_spy):
    harness = _MergeHarness(monkeypatch, Forbidden('bucket policy refuses the delete'))
    _fallback_spy(monkeypatch)

    with caplog.at_level('ERROR'):
        done = harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert done is True
    errors = [r for r in caplog.records if 'Error deleting merged conversation audio' in r.getMessage()]
    assert errors, 'a permanent refusal keeps the failed-cleanup arm'
    assert retry_spy.calls == [], 'a permanent refusal is not deferrable'


def test_merged_target_success_arm_unchanged(monkeypatch, caplog, retry_spy):
    harness = _MergeHarness(monkeypatch, None)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        done = harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert done is True
    assert retry_spy.calls == []
    assert not [r for r in caplog.records if r.levelno >= 30]


def test_merged_target_deferral_emits_no_degradation_event(monkeypatch, caplog, retry_spy):
    harness = _MergeHarness(monkeypatch, _RESIDUAL)
    fallbacks = _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert fallbacks == []


def test_merged_target_retry_thread_is_detached_and_named(monkeypatch, caplog):
    harness = _MergeHarness(monkeypatch, _RESIDUAL)
    holders: list[Any] = []

    class RecordingThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.name = name
            self.daemon = daemon
            holders.append(self)

        def start(self) -> None:
            pass

    real_defer = lifecycle_service._defer_or_keep_residual_sweep

    def defer_with_recording_thread(uid, conversation_id, **kwargs):
        kwargs.setdefault('start_thread', RecordingThread)
        kwargs.setdefault('sleep', lambda s: None)
        return real_defer(uid, conversation_id, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_defer_or_keep_residual_sweep', defer_with_recording_thread)

    with caplog.at_level('INFO'):
        harness.merge._cleanup_merged_target_after_failure('uid', 'merged-conv')

    assert holders and holders[0].daemon is True, 'the retry must never block interpreter exit'
    assert holders[0].name == 'unreferenced-audio-residue-retry'


# ── F. Regression guards: the neighbours this change must not disturb ───────


def test_verifier_signal_is_not_a_storage_blip():
    """The residual arm keeps its own identity: the blip classifier must not
    absorb the verifier's verdict (the boundary checks residue first, but the
    classifiers stay independent)."""
    assert not lifecycle_service._is_storage_blip(_RESIDUAL)
    assert lifecycle_service._is_residual_audio_sweep(_RESIDUAL)


def test_purge_verifier_still_fails_closed_for_the_account_wipe(monkeypatch):
    """A lost delete still terminates the verifier: the settle re-attack runs,
    then the fail-closed raise the wipe depends on."""
    calls: list[int] = []

    class _LostDeleteBucket:
        def __init__(self, names: set[str]) -> None:
            self.names = set(names)

        def blob(self, name: str) -> Any:
            stuck = SimpleNamespace(name=name)

            def _delete() -> None:
                calls.append(1)

            stuck.delete = _delete
            return stuck

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    bucket = _LostDeleteBucket({'chunks/uid/conv/a.opus'})
    with pytest.raises(RuntimeError, match='owner storage purge left'):
        storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')
    assert len(calls) == 2, 'the settle re-attack happened before giving up'


def test_404_race_still_converges_inside_the_verifier():
    """A 404 from a concurrent sweep is the delete's success half: the verify
    re-list comes back empty and no residue verdict fires at all."""
    from google.cloud.exceptions import NotFound

    class _GoneRaceBucket:
        def __init__(self, names: set[str]) -> None:
            self.names = set(names)

        def blob(self, name: str) -> Any:
            outer = self
            blob = SimpleNamespace(name=name)

            def _delete() -> None:
                outer.names.discard(name)
                raise NotFound(f'No such object: {name}')

            blob.delete = _delete
            return blob

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    bucket = _GoneRaceBucket({'chunks/uid/conv/a.opus'})
    assert storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/') == 0
    assert bucket.names == set()


@pytest.mark.parametrize(
    'error',
    [
        TooManyRequests('429'),
        BadGateway('502'),
        GatewayTimeout('504'),
        ServiceUnavailable('503'),
    ],
)
def test_google_sdk_blip_shapes_still_take_the_blip_deferral(monkeypatch, caplog, retry_spy, error):
    """The blip arm is untouched by the residual change: same message, same
    retry ownership."""
    _failing_sweep(monkeypatch, error)
    _fallback_spy(monkeypatch)

    with caplog.at_level('INFO'):
        lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert any('Unreferenced audio sweep deferred' in r.getMessage() for r in caplog.records)
    assert retry_spy.calls, 'every blip deferral owns its convergence'


def test_residual_then_blip_budgets_are_independent(monkeypatch, retry_spy):
    """A conversation with a residue retry in flight still gets a fresh blip
    deferral: the inflight set only dedupes the residual arm."""
    real_schedule = lifecycle_service._schedule_sweep_retry

    def schedule(attempt, args, **kwargs):
        kwargs.pop('start_thread', None)
        kwargs.pop('sleep', None)
        return real_schedule(attempt, args, start_thread=_ManualThread, sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', schedule, raising=False)

    def residue(*a: Any, **k: Any) -> None:
        raise _RESIDUAL

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', residue, raising=False)
    _fallback_spy(monkeypatch)

    lifecycle_service._defer_or_keep_residual_sweep('uid', 'conv')

    # Restore the spy: the blip boundary call must still arm.
    spy = _RetrySpy()
    monkeypatch.setattr(lifecycle_service, '_schedule_sweep_retry', spy, raising=False)

    def blip(*a: Any, **k: Any) -> None:
        raise TooManyRequests('429')

    monkeypatch.setattr(lifecycle_service, 'delete_conversation_audio_files', blip, raising=False)
    lifecycle_service._discard_unreferenced_audio('uid', 'conv', {})

    assert spy.calls, 'the blip deferral ignores the residue inflight set'


def test_purge_settle_budget_is_untouched():
    """The verifier's two-pass settle still counts each object once."""
    calls: list[str] = []

    class _CountingBucket:
        def __init__(self, names: set[str]) -> None:
            self.names = set(names)

        def blob(self, name: str) -> Any:
            outer = self
            blob = SimpleNamespace(name=name)

            def _delete() -> None:
                outer.names.discard(name)
                calls.append(name)

            blob.delete = _delete
            return blob

        def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
            return [self.blob(name) for name in sorted(self.names) if name.startswith(prefix)]

    bucket = _CountingBucket({'chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus'})
    deleted = storage_mod._delete_owner_bucket_prefix(bucket, 'chunks/uid/conv/')
    assert deleted == 2
    assert sorted(calls) == ['chunks/uid/conv/a.opus', 'chunks/uid/conv/b.opus']
