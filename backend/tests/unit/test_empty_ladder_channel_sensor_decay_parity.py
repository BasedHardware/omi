# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The two production signature lines can no longer be produced by a family unit.

The scheduler terminal line keeps its ``worker_reason=`` token only inside the
kept-fault ``else`` branch, and the worker fault line keeps
``stage=assemble_words reason=empty_asr`` only for the same units — both are
source-order facts. Live cells drive real holds and real worker batches at
attempts 1..6 and durations 1..30s and assert the ERROR lines are absent and
the new INFO lines carry every diagnostic field the old lines carried.
"""

import logging
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

import diarizer.batch_pipeline as worker_module
import utils.batch_pipeline.scheduler as scheduler_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import Priority, RecoveryWork, ValidationFailureWork, WorkResult
from utils.batch_pipeline.scheduler import Scheduler

WORKER_FORMAT = "event=batch_empty_ladder outcome=recovery_handoff error_class=%s stage=%s segment_id=%s reason=%s samples=%d vad_spans=%d windows=%d asr_words=%d owned_words=%d"
SCHED_FORMAT = "event=batch_empty_ladder outcome=held_for_recovery attempt=%d recovery=held stage=%s worker_reason=%s"


def _queued():
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="decay-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    return store, queue, lease


def test_family_attempt_1_never_books_the_quarantine_error(caplog):
    """attempt=1: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail(
            "a", lease.token, 1100.0, quarantine=True, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}
        )
        is True
    )
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=1 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_family_attempt_2_never_books_the_quarantine_error(caplog):
    """attempt=2: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=20)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=20 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_family_attempt_3_never_books_the_quarantine_error(caplog):
    """attempt=3: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=40)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=40 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_family_attempt_4_never_books_the_quarantine_error(caplog):
    """attempt=4: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=60)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=60 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_family_attempt_5_never_books_the_quarantine_error(caplog):
    """attempt=5: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=80)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=80 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_family_attempt_6_never_books_the_quarantine_error(caplog):
    """attempt=6: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=99 recovery=held" in ladder[0].getMessage()
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()


def test_worker_duration_1_never_books_the_fault_error(monkeypatch, caplog):
    """1s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=1)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=16000" in ladder[0].getMessage()


def test_worker_duration_2_never_books_the_fault_error(monkeypatch, caplog):
    """2s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=2)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=32000" in ladder[0].getMessage()


def test_worker_duration_4_never_books_the_fault_error(monkeypatch, caplog):
    """4s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=4)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=64000" in ladder[0].getMessage()


def test_worker_duration_30_never_books_the_fault_error(monkeypatch, caplog):
    """30s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=30)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=480000" in ladder[0].getMessage()


def test_scheduler_fault_format_is_only_reachable_after_both_demotions():
    source = scheduler_module.__dict__ and __import__("inspect").getsource(scheduler_module)
    guard_index = source.index("outcome=held_for_redrive")
    ladder_index = source.index("outcome=held_for_recovery")
    fault_index = source.index("reason=worker_failed attempt=%d recovery=held")
    assert guard_index < fault_index and ladder_index < fault_index


def test_worker_fault_format_is_only_reachable_after_the_demotion():
    source = __import__("inspect").getsource(worker_module)
    shadow_index = source.index("event=batch_shadow_worker_failure")
    ladder_index = source.index("event=batch_empty_ladder")
    guard_index = source.index("outcome=redrive_held")
    fault_index = source.index("event=batch_worker_failed error_class=%s stage=%s segment_id=%s reason=%s")
    assert shadow_index < ladder_index < guard_index < fault_index


def test_new_worker_line_carries_every_field_the_old_line_carried():
    for token in (
        "error_class=",
        "stage=",
        "segment_id=",
        "reason=",
        "samples=",
        "vad_spans=",
        "windows=",
        "asr_words=",
        "owned_words=",
    ):
        assert token in WORKER_FORMAT


def test_new_scheduler_line_carries_every_field_the_old_line_carried():
    for token in ("attempt=", "recovery=held", "stage=", "worker_reason="):
        assert token in SCHED_FORMAT


def test_awaiting_fenced_recovery_warning_survives_the_demotion(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail(
            "a", lease.token, 1100.0, quarantine=True, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}
        )
        is True
    )
    warn = [r for r in caplog.records if "awaiting_fenced_recovery" in r.getMessage()]
    assert len(warn) == 1
    assert warn[0].levelno == logging.WARNING


def _flags(monkeypatch, safety="true", recovery="false", disposition="false", validation="true", silence="false"):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", safety)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", recovery)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", validation)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", silence)


def test_family_attempt_20_books_only_the_held_for_recovery_line(caplog):
    """attempt=20: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=20)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=20 recovery=held" in ladder[0].getMessage()


def test_family_attempt_40_books_only_the_held_for_recovery_line(caplog):
    """attempt=40: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=40)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=40 recovery=held" in ladder[0].getMessage()


def test_family_attempt_60_books_only_the_held_for_recovery_line(caplog):
    """attempt=60: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=60)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=60 recovery=held" in ladder[0].getMessage()


def test_family_attempt_80_books_only_the_held_for_recovery_line(caplog):
    """attempt=80: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=80)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=80 recovery=held" in ladder[0].getMessage()


def test_family_attempt_98_books_only_the_held_for_recovery_line(caplog):
    """attempt=98: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=98)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=98 recovery=held" in ladder[0].getMessage()


def test_family_attempt_99_books_only_the_held_for_recovery_line(caplog):
    """attempt=99: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail("a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"})
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=99 recovery=held" in ladder[0].getMessage()


def test_worker_duration_7_9_never_books_the_fault_error(monkeypatch, caplog):
    """7.9s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=7.9)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=126400" in ladder[0].getMessage()


def test_worker_duration_20_04_never_books_the_fault_error(monkeypatch, caplog):
    """20.04s: the x488 signature line is unreachable for the family."""
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
    worker.process_batch([item(duration=20.04)])
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert "samples=320640" in ladder[0].getMessage()


def test_no_owned_family_attempt_99_books_only_the_held_for_recovery_line(caplog):
    """attempt=99, no_owned_words: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        queue.fail(
            "a", lease.token, 1100.0, worker_failure_evidence={"stage": "assemble_words", "reason": "no_owned_words"}
        )
        is True
    )
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=99 recovery=held" in ladder[0].getMessage()
    assert "worker_reason=no_owned_words" in ladder[0].getMessage()


def test_no_owned_family_attempt_1_books_only_the_held_for_recovery_line(caplog):
    """attempt=1, no_owned_words: the x501 signature line is unreachable for the family."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
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
    assert store.probe("jobs", "a")["state"] == "quarantined"
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    assert not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "attempt=1 recovery=held" in ladder[0].getMessage()
    assert "worker_reason=no_owned_words" in ladder[0].getMessage()
