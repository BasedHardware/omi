# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The empty ladder's handoff flags and the channel decision are independent axes.

``empty_ladder_handoff`` is pinned cell-by-cell across the reason x flag
matrix (its custody routing is untouched by the demotion), the worker's
custody shapes are pinned under handoff-true and pre-safety combos, the
scheduler's channel decision is proven not to read the flags, and every
environment parse of the five ladder switches keeps its documented default.
"""

import logging
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_pipeline import (
    empty_asr_disposition_enabled,
    empty_asr_recovery_enabled,
    recovery_dispatch_batch_size,
    recovery_policy_refresh_enabled,
    recovery_wake_lease_seconds,
    second_multilingual_enabled,
    worker_silence_disposition_enabled,
    worker_validation_disposition_enabled,
)
from config.batch_pipeline_empty_asr import empty_ladder_handoff, safety_net_enabled, terminal_empty_allowed
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import FailedWork, Priority, RecoveryWork, ValidationFailureWork

COMBOS = (
    (True, True, True),
    (True, True, False),
    (True, False, True),
    (True, False, False),
    (False, True, True),
    (False, True, False),
    (False, False, True),
    (False, False, False),
)


def test_handoff_empty_asr_recovery_1_disposition_1_safety_1_is_true():
    """empty_ladder_handoff('empty_asr', r=True, d=True, s=True) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=True, disposition_enabled=True, safety_enabled=True) is True
    )


def test_handoff_empty_asr_recovery_1_disposition_1_safety_0_is_true():
    """empty_ladder_handoff('empty_asr', r=True, d=True, s=False) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=True, disposition_enabled=True, safety_enabled=False) is True
    )


def test_handoff_empty_asr_recovery_1_disposition_0_safety_1_is_true():
    """empty_ladder_handoff('empty_asr', r=True, d=False, s=True) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=True, disposition_enabled=False, safety_enabled=True) is True
    )


def test_handoff_empty_asr_recovery_1_disposition_0_safety_0_is_true():
    """empty_ladder_handoff('empty_asr', r=True, d=False, s=False) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=True, disposition_enabled=False, safety_enabled=False)
        is True
    )


def test_handoff_empty_asr_recovery_0_disposition_1_safety_1_is_true():
    """empty_ladder_handoff('empty_asr', r=False, d=True, s=True) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=True, safety_enabled=True) is True
    )


def test_handoff_empty_asr_recovery_0_disposition_1_safety_0_is_true():
    """empty_ladder_handoff('empty_asr', r=False, d=True, s=False) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=True, safety_enabled=False)
        is True
    )


def test_handoff_empty_asr_recovery_0_disposition_0_safety_1_is_true():
    """empty_ladder_handoff('empty_asr', r=False, d=False, s=True) -> True."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=False, safety_enabled=True)
        is True
    )


def test_handoff_empty_asr_recovery_0_disposition_0_safety_0_is_false():
    """empty_ladder_handoff('empty_asr', r=False, d=False, s=False) -> False."""
    assert (
        empty_ladder_handoff("empty_asr", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_no_owned_words_recovery_1_disposition_1_safety_1_is_true():
    """empty_ladder_handoff('no_owned_words', r=True, d=True, s=True) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=True, disposition_enabled=True, safety_enabled=True)
        is True
    )


def test_handoff_no_owned_words_recovery_1_disposition_1_safety_0_is_true():
    """empty_ladder_handoff('no_owned_words', r=True, d=True, s=False) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=True, disposition_enabled=True, safety_enabled=False)
        is True
    )


def test_handoff_no_owned_words_recovery_1_disposition_0_safety_1_is_true():
    """empty_ladder_handoff('no_owned_words', r=True, d=False, s=True) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=True, disposition_enabled=False, safety_enabled=True)
        is True
    )


def test_handoff_no_owned_words_recovery_1_disposition_0_safety_0_is_false():
    """empty_ladder_handoff('no_owned_words', r=True, d=False, s=False) -> False."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=True, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_no_owned_words_recovery_0_disposition_1_safety_1_is_true():
    """empty_ladder_handoff('no_owned_words', r=False, d=True, s=True) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=True, safety_enabled=True)
        is True
    )


def test_handoff_no_owned_words_recovery_0_disposition_1_safety_0_is_true():
    """empty_ladder_handoff('no_owned_words', r=False, d=True, s=False) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=True, safety_enabled=False)
        is True
    )


def test_handoff_no_owned_words_recovery_0_disposition_0_safety_1_is_true():
    """empty_ladder_handoff('no_owned_words', r=False, d=False, s=True) -> True."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=True)
        is True
    )


def test_handoff_no_owned_words_recovery_0_disposition_0_safety_0_is_false():
    """empty_ladder_handoff('no_owned_words', r=False, d=False, s=False) -> False."""
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_word_shape_never_rides_even_every_flag_on():
    assert (
        empty_ladder_handoff("word_shape", recovery_enabled=True, disposition_enabled=True, safety_enabled=True)
        is False
    )


def test_handoff_vad_bounds_never_rides_even_every_flag_on():
    assert (
        empty_ladder_handoff("vad_bounds", recovery_enabled=True, disposition_enabled=True, safety_enabled=True)
        is False
    )


def test_handoff_unsupported_language_never_rides_even_every_flag_on():
    assert (
        empty_ladder_handoff(
            "unsupported_language", recovery_enabled=True, disposition_enabled=True, safety_enabled=True
        )
        is False
    )


def test_worker_pre_safety_custody_emits_no_work_for_empty_units(monkeypatch, caplog):
    _flags(monkeypatch, safety="false", recovery="false", disposition="false", validation="false")
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    results = worker.process_batch([item(duration=2)])
    assert results == []
    assert not saved


def test_worker_validation_custody_hands_off_terminal_for_empty_units(monkeypatch, caplog):
    _flags(monkeypatch, safety="false", recovery="false", disposition="false", validation="true")
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    results = worker.process_batch([item(duration=2)])
    assert results == [ValidationFailureWork("a", "assemble_words", "empty_asr")]
    assert not saved


def test_worker_handoff_custody_emits_recovery_work_with_default_flags(monkeypatch, caplog):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item(duration=2)])
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved


def _flags(monkeypatch, safety="true", recovery="false", disposition="false", validation="true", silence="false"):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", safety)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", recovery)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", validation)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", silence)


def test_scheduler_channel_demotes_under_safety_off(monkeypatch, caplog):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a", lease.token, 1100.0, quarantine=True, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}
        )
        is True
    )
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO


def test_scheduler_channel_demotes_under_recovery_and_disposition_off(monkeypatch, caplog):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a",
            lease.token,
            1100.0,
            quarantine=True,
            worker_failure={"stage": "assemble_words", "reason": "no_owned_words"},
        )
        is True
    )
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert not quar and len(ladder) == 1


def test_scheduler_fault_channel_unchanged_under_safety_off(monkeypatch, caplog):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a",
            lease.token,
            1100.0,
            quarantine=True,
            worker_failure={"stage": "fetch_decode", "reason": "outside_admitted_source"},
        )
        is True
    )
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR


from utils.batch_pipeline.scheduler import Scheduler


def test_safety_flag_unset_defaults_on(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", raising=False)
    assert safety_net_enabled() is True


def test_safety_flag_explicit_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    assert safety_net_enabled() is True


def test_safety_flag_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert safety_net_enabled() is False


def test_safety_flag_garbage_defaults_on(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "garbage")
    assert safety_net_enabled() is True


def test_recovery_flag_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", raising=False)
    assert empty_asr_recovery_enabled() is False


def test_recovery_flag_explicit_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "true")
    assert empty_asr_recovery_enabled() is True


def test_recovery_flag_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "false")
    assert empty_asr_recovery_enabled() is False


def test_recovery_flag_garbage_defaults_off(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "garbage")
    assert empty_asr_recovery_enabled() is False


def test_disposition_flag_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", raising=False)
    assert empty_asr_disposition_enabled() is False


def test_disposition_flag_explicit_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "true")
    assert empty_asr_disposition_enabled() is True


def test_disposition_flag_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "false")
    assert empty_asr_disposition_enabled() is False


def test_disposition_flag_garbage_defaults_off(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "garbage")
    assert empty_asr_disposition_enabled() is False


def test_validation_flag_unset_defaults_on(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    assert worker_validation_disposition_enabled() is True


def test_validation_flag_explicit_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    assert worker_validation_disposition_enabled() is True


def test_validation_flag_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "false")
    assert worker_validation_disposition_enabled() is False


def test_validation_flag_garbage_behaves_like_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "garbage")
    assert worker_validation_disposition_enabled() is False


def test_silence_flag_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", raising=False)
    assert worker_silence_disposition_enabled() is False


def test_silence_flag_explicit_true(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", "true")
    assert worker_silence_disposition_enabled() is True


def test_silence_flag_explicit_false(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", "false")
    assert worker_silence_disposition_enabled() is False


def test_silence_flag_garbage_defaults_off(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", "garbage")
    assert worker_silence_disposition_enabled() is False


def test_recovery_failure_vocabulary_shapes_never_demote_at_the_scheduler():
    from utils.batch_pipeline.errors import empty_ladder_recovery_failure

    assert empty_ladder_recovery_failure({"stage": "provider", "reason": "empty_asr"}) is False
    assert empty_ladder_recovery_failure({"stage": "strict_vad", "reason": "no_speech"}) is False


def test_family_frozenset_is_immutable_against_add_and_discard():
    from utils.batch_pipeline.errors import EMPTY_LADDER_RECOVERY_REASONS

    try:
        EMPTY_LADDER_RECOVERY_REASONS.add("word_shape")
    except AttributeError:
        return
    raise AssertionError("family set must not grow")


def test_family_frozenset_discard_is_also_refused():
    from utils.batch_pipeline.errors import EMPTY_LADDER_RECOVERY_REASONS

    try:
        EMPTY_LADDER_RECOVERY_REASONS.discard("empty_asr")
    except AttributeError:
        return
    raise AssertionError("family set must not shrink")


def test_scheduler_guard_channel_unchanged_under_safety_off(monkeypatch, caplog):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a",
            lease.token,
            1100.0,
            quarantine=True,
            worker_failure={"stage": "vad_windows", "reason": "unsupported_language"},
        )
        is True
    )
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    assert not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO


def test_scheduler_guard_channel_unchanged_under_recovery_and_disposition_off(monkeypatch, caplog):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a",
            lease.token,
            1100.0,
            quarantine=True,
            worker_failure={"stage": "vad_windows", "reason": "unsupported_language"},
        )
        is True
    )
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    assert not ladder and len(guard) == 1


def test_family_defer_records_the_retry_metric():
    from types import SimpleNamespace

    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    assert calls == ["retry"]


def test_no_owned_defer_records_the_retry_metric():
    from types import SimpleNamespace

    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail(
            "a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "no_owned_words"}
        )
        is True
    )
    assert calls == ["retry"]


def test_fault_defer_records_the_retry_metric():
    from types import SimpleNamespace

    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item("a", owner="rollback-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"})
        is True
    )
    assert calls == ["retry"]


def test_handoff_reads_no_environment_inside_no_owned_recovery_arg(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("no_owned_words", recovery_enabled=True, disposition_enabled=False, safety_enabled=False)
        is False
    )


def test_handoff_reads_no_environment_inside_word_shape_everything_off(monkeypatch):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    assert (
        empty_ladder_handoff("word_shape", recovery_enabled=False, disposition_enabled=False, safety_enabled=False)
        is False
    )
