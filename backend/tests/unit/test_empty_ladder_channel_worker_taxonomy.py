# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The worker boundary reports the empty ladder's handoff instead of a worker fault.

A ``BatchValidationError`` with ``empty_asr``/``no_owned_words`` at
``assemble_words`` is the designed recovery handoff: typed empty recognition,
the bounded context-bearing retry already run, the ``RecoveryWork`` handoff
carrying retry and VAD evidence, fenced recovery lane waiting below. The
``finish()`` logging loop reports it as ``event=batch_empty_ladder
outcome=recovery_handoff`` at INFO and books nothing on the fault channel —
under every handoff-flag combination, with or without a recognizer wired, and
in the pre-safety shape. Every typed fault class, every synthetic
cross-stage family token, and every generic exception keeps
``event=batch_worker_failed`` at ERROR. Durable outcomes, counters, and the
failure callback are pinned unchanged next to the new line.
"""

import logging
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, RecoveryWork, ValidationFailureWork, WorkResult
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

HANDOFF_TRUE = [
    (True, True, True),
    (True, False, True),
    (False, True, True),
    (False, False, True),
    (True, True, False),
    (True, False, False),
    (False, True, False),
]
HANDOFF_TRUE_NO_OWNED = [
    (True, True, True),
    (True, False, True),
    (False, True, True),
    (False, False, True),
    (True, True, False),
    (True, False, False),
]
SERVABLE = ['en', 'es', 'fr']


def _flags(monkeypatch, safety="true", recovery="false", disposition="false", validation="true", silence="false"):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", safety)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", recovery)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", validation)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", silence)


def _split(caplog):
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    shadow = [r for r in caplog.records if "event=batch_shadow_worker_failure" in r.getMessage()]
    return ladder, fault, guard, shadow


def _empty_worker(
    monkeypatch,
    caplog,
    *,
    duration=2,
    vad=None,
    decode=None,
    recover=None,
    shadow=False,
    language=None,
    on_failure=None,
    flags=None,
):
    """One empty-recognition unit through the real worker, with INFO captured."""
    _flags(monkeypatch, **(flags or {}))
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    kwargs = dict(
        decode=(
            decode
            if decode is not None
            else (lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32))
        ),
        vad=vad if vad is not None else (lambda _: [(0.2, 0.8)]),
        words_providers={"parakeet": provider},
    )
    if language is not None:
        kwargs["language_of"] = lambda _item, _lang=language: _lang
    if recover is not None:
        kwargs["recover_words"] = recover
    if on_failure is not None:
        kwargs["on_failure"] = on_failure
    worker, _, saved, _, _, failures = setup_worker(**kwargs)
    unit = item(duration=duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    return worker, results, saved, failures


def _no_owned_worker(monkeypatch, caplog, *, duration=10.02, recover=None, shadow=False, flags=None):
    _flags(monkeypatch, **(flags or {}))
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[{"word": "heard", "timestamp": [4.5, 4.8]}]]
    kwargs = dict(
        decode=lambda _: np.zeros(160320, dtype=np.float32),
        vad=lambda _: [(1, 2)],
        words_providers={"parakeet": provider},
    )
    if recover is not None:
        kwargs["recover_words"] = recover
    worker, _, saved, _, _, failures = setup_worker(**kwargs)
    unit = item(duration=duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    return worker, results, saved, failures


def test_empty_handoff_safety1_recovery1_disposition1_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=1, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition1_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=1, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition1_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=1, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition1_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=1, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition1_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=1, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition1_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=1, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition1_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=1, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition1_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=1, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition1_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=1, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition1_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=1, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition1_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=1, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition1_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=1, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery0_disposition1_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=0_disposition=1, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery0_disposition1_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=0_disposition=1, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery0_disposition1_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=0_disposition=1, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery0_disposition1_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=0_disposition=1, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition0_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=0, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition0_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=0, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition0_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=0, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery1_disposition0_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=1_disposition=0, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition0_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=0, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition0_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=0, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition0_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=0, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety1_recovery0_disposition0_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1_recovery=0_disposition=0, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition0_duration_1_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=0, 1s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=1,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition0_duration_2_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=0, 2s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=2,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition0_duration_4_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=0, 4s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=4,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_empty_handoff_safety0_recovery1_disposition0_duration_30_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=0_recovery=1_disposition=0, 30s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=30,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety1_recovery1_disposition1_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=1_recovery=1_disposition=1, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety1_recovery0_disposition1_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=1_recovery=0_disposition=1, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety0_recovery1_disposition1_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=0_recovery=1_disposition=1, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "True", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety0_recovery0_disposition1_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=0_recovery=0_disposition=1, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "False", "recovery": "False", "disposition": "True"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety1_recovery1_disposition0_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=1_recovery=1_disposition=0, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "True", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_no_owned_handoff_safety1_recovery0_disposition0_reports_the_handoff(monkeypatch, caplog):
    """no_owned_words, safety=1_recovery=0_disposition=0, 10.02s context ghost -> INFO recovery_handoff."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "True", "recovery": "False", "disposition": "False"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    record = ladder[0]
    assert record.levelno == logging.INFO
    message = record.getMessage()
    assert "outcome=recovery_handoff" in message
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in message
    assert "asr_words=1 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "no_owned_words"
    assert not saved
    assert worker.counts["failed"] == 1


def test_shadow_empty_reports_the_shadow_line_only(monkeypatch, caplog):
    _worker, results, saved, failures = _empty_worker(monkeypatch, caplog, shadow=True)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not fault and not guard and len(shadow) == 1
    assert "stage=assemble_words reason=empty_asr" in shadow[0].getMessage()
    assert shadow[0].levelno == logging.INFO


def test_shadow_no_owned_reports_the_shadow_line_only(monkeypatch, caplog):
    _worker, results, saved, failures = _no_owned_worker(monkeypatch, caplog, shadow=True)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not fault and not guard and len(shadow) == 1
    assert "reason=no_owned_words" in shadow[0].getMessage()


def test_empty_without_a_recognizer_still_reports_the_handoff(monkeypatch, caplog):
    """No wired recognizer: the handoff cannot ride, the verdict stays designed."""
    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, recover=None)
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert results == [ValidationFailureWork("a", "assemble_words", "empty_asr")]


def test_no_owned_without_a_recognizer_still_reports_the_handoff(monkeypatch, caplog):
    worker, results, saved, failures = _no_owned_worker(monkeypatch, caplog, recover=None)
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert "reason=no_owned_words" in ladder[0].getMessage()
    assert results == [ValidationFailureWork("a", "assemble_words", "no_owned_words")]


def test_empty_pre_safety_shape_still_reports_the_handoff(monkeypatch, caplog):
    """Every ladder switch off: no work result (the historical ladder), designed verdict."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        flags={"safety": "false", "recovery": "false", "disposition": "false", "validation": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert results == []


def test_no_owned_pre_safety_shape_still_reports_the_handoff(monkeypatch, caplog):
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        flags={"safety": "false", "recovery": "false", "disposition": "false", "validation": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert "reason=no_owned_words" in ladder[0].getMessage()
    assert results == []


def test_vad_fault_word_shape_stays_error(monkeypatch, caplog):
    """word_shape at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=word_shape" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "word_shape"}


def test_vad_fault_word_clock_stays_error(monkeypatch, caplog):
    """word_clock at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=word_clock" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "word_clock"}


def test_vad_fault_word_sequence_stays_error(monkeypatch, caplog):
    """word_sequence at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=word_sequence" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "word_sequence"}


def test_vad_fault_vad_nonfinite_stays_error(monkeypatch, caplog):
    """vad_nonfinite at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=vad_nonfinite" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "vad_nonfinite"}


def test_vad_fault_vad_order_stays_error(monkeypatch, caplog):
    """vad_order at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=vad_order" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "vad_order"}


def test_vad_fault_vad_bounds_stays_error(monkeypatch, caplog):
    """vad_bounds at vad_windows keeps the worker-fault channel and the ladder."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert f"stage=vad_windows segment_id=a reason=vad_bounds" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "vad_windows", "reason": "vad_bounds"}


def test_staged_audio_invalid_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise StagedAudioInvalid("staged")

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, decode=decode)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=fetch_decode segment_id=a reason=staged_audio_invalid" in fault[0].getMessage()


def test_retained_audio_invalid_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise RetainedAudioInvalid("retained")

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, decode=decode)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert "stage=fetch_decode segment_id=a reason=retained_audio_invalid" in fault[0].getMessage()


def test_decoded_duration_mismatch_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise DecodedDurationMismatch("extent")

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, decode=decode)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert "stage=fetch_decode segment_id=a reason=decoded_duration_mismatch" in fault[0].getMessage()


def test_unclassified_decode_valueerror_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise ValueError("synthetic-private-must-not-be-logged")

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, decode=decode)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "error_class=ValueError stage=fetch_decode segment_id=a reason=unclassified" in fault[0].getMessage()
    assert "synthetic-private-must-not-be-logged" not in caplog.text


def test_word_clock_fault_stays_error(monkeypatch, caplog):
    """A bad word clock in the provider output faults at word_clocks."""
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[{"word": "x", "timestamp": [1.0, 0.5]}] for _ in samples]
    _flags(monkeypatch, validation="false")
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    results = worker.process_batch([item(duration=60)])
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=word_clocks segment_id=a reason=word_clock" in fault[0].getMessage()
    assert results[0].worker_failure == {"stage": "word_clocks", "reason": "word_clock"}


def test_synthetic_empty_asr_at_vad_windows_stays_error(monkeypatch, caplog):
    """A synthetic empty_asr raise at vad_windows keeps its fault channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=vad_windows segment_id=a reason=empty_asr" in fault[0].getMessage()


def test_synthetic_no_owned_words_at_vad_windows_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, vad=vad, flags={"validation": "false"})
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert "stage=vad_windows segment_id=a reason=no_owned_words" in fault[0].getMessage()


def test_synthetic_empty_asr_at_decode_stays_error(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, decode=decode)
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert "stage=fetch_decode segment_id=a reason=empty_asr" in fault[0].getMessage()


def test_servable_es_reaches_assemble_empty_not_the_guard(monkeypatch, caplog):
    """A es unit the word provider serves reaches assemble_words empty, not the guard."""
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        language_of=lambda _item, _lang="es": _lang,
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
        recover_words=Mock(return_value=[]),
    )
    worker.process_batch([item(duration=2)])
    ladder, fault, guard, shadow = _split(caplog)
    assert not guard and not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()


def test_servable_fr_reaches_assemble_empty_not_the_guard(monkeypatch, caplog):
    """A fr unit the word provider serves reaches assemble_words empty, not the guard."""
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        language_of=lambda _item, _lang="fr": _lang,
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
        recover_words=Mock(return_value=[]),
    )
    worker.process_batch([item(duration=2)])
    ladder, fault, guard, shadow = _split(caplog)
    assert not guard and not fault and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()


def test_guard_none_language_at_vad_windows_uses_the_guard_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[]]
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        language_of=lambda _item: None,
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    worker.process_batch([item(duration=2)])
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not fault and len(guard) == 1
    assert "outcome=redrive_held" in guard[0].getMessage()


def test_failure_callback_still_sees_the_batch_validation_error(monkeypatch, caplog):
    seen = []
    worker, results, saved, _ignored = _empty_worker(
        monkeypatch, caplog, recover=Mock(return_value=[]), on_failure=lambda i, e: seen.append((i.segment_id, e))
    )
    assert seen == [("a", "BatchValidationError")]


def test_failure_callback_still_sees_the_synthetic_vad_error(monkeypatch, caplog):
    seen = []

    def vad(_samples):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, saved, _ignored = _empty_worker(
        monkeypatch, caplog, vad=vad, on_failure=lambda i, e: seen.append((i.segment_id, e))
    )
    assert seen == [("a", "BatchValidationError")]


def test_empty_asr_attempt_correctness_meter_fires_for_empty_non_shadow(monkeypatch, caplog):
    calls = []
    from diarizer import batch_pipeline as worker_module

    monkeypatch.setattr(
        worker_module,
        "record_correctness",
        lambda name, source=None, seconds=None: calls.append((name, source, seconds)),
    )
    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, duration=7.9)
    assert calls == [("empty_asr_attempt", "gpu_worker", 7.9)]


def test_empty_asr_attempt_correctness_meter_skips_no_owned(monkeypatch, caplog):
    calls = []
    from diarizer import batch_pipeline as worker_module

    monkeypatch.setattr(
        worker_module,
        "record_correctness",
        lambda name, source=None, seconds=None: calls.append((name, source, seconds)),
    )
    worker, results, saved, failures = _no_owned_worker(monkeypatch, caplog)
    assert calls == []


def test_empty_asr_attempt_correctness_meter_skips_shadow(monkeypatch, caplog):
    calls = []
    from diarizer import batch_pipeline as worker_module

    monkeypatch.setattr(
        worker_module,
        "record_correctness",
        lambda name, source=None, seconds=None: calls.append((name, source, seconds)),
    )
    worker, results, saved, failures = _empty_worker(monkeypatch, caplog, shadow=True)
    assert calls == []


def test_healthy_sibling_survives_alongside_the_handoff(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def transcribe(samples):
        return [[] if len(s) == 32000 else [{"word": "hello", "timestamp": [0.1, 0.2]}] for s in samples]

    provider = Mock()
    provider.transcribe_batch.side_effect = transcribe
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    results = worker.process_batch([item(duration=2), item("b", 4)])
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert "segment_id=a reason=empty_asr" in ladder[0].getMessage()
    healthy = [r for r in results if isinstance(r, WorkResult)]
    assert [r.segment_id for r in healthy] == ["b"]
    assert isinstance(results[0], ValidationFailureWork) or isinstance(results[1], ValidationFailureWork)
    assert set(saved) == {"b"}


def test_no_owned_handoff_safety0_recovery1_disposition0_stays_the_designed_empty(monkeypatch, caplog):
    """no_owned_words, safety=0, recovery=1: no_owned rides on disposition alone, so the
    handoff cannot ride, but the channel still reports the designed verdict, not a fault."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        recover=Mock(return_value=[]),
        flags={"safety": "false", "recovery": "true", "disposition": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "stage=assemble_words segment_id=a reason=no_owned_words" in ladder[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork) and results[0].reason == "no_owned_words"
    assert not saved


def test_no_owned_handoff_safety0_recovery1_disposition0_shadow_stays_on_the_shadow_line(monkeypatch, caplog):
    """Shadow units keep the shadow line ahead of the classification."""
    worker, results, saved, failures = _no_owned_worker(
        monkeypatch,
        caplog,
        shadow=True,
        recover=Mock(return_value=[]),
        flags={"safety": "false", "recovery": "true", "disposition": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not ladder and not fault and not guard and len(shadow) == 1
    assert "reason=no_owned_words" in shadow[0].getMessage()


def test_empty_handoff_safety1_recovery0_disposition0_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1, 7.9s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=7.9,
        recover=Mock(return_value=[]),
        flags={"safety": "true", "recovery": "false", "disposition": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "samples=126400" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_empty_handoff_safety1_recovery0_disposition0_duration_20_04_reports_the_handoff(monkeypatch, caplog):
    """empty_asr, safety=1, 20.04s -> INFO recovery_handoff, no fault line."""
    worker, results, saved, failures = _empty_worker(
        monkeypatch,
        caplog,
        duration=20.04,
        recover=Mock(return_value=[]),
        flags={"safety": "true", "recovery": "false", "disposition": "false"},
    )
    ladder, fault, guard, shadow = _split(caplog)
    assert not fault and not guard and not shadow and len(ladder) == 1
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "samples=320640" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
