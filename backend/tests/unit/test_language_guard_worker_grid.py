"""The worker-boundary grid: every blocked language, every duration, one transition.

A language the batch Parakeet model cannot serve crosses the barrier with an INFO transition that carries the measured samples and the terminal chain end. This grid sweeps every blocked language token across eight durations at vad_windows, the decode-stage guard with its never-measured sentinels, typed and noisy-subclass fences, sub-frame captures, shadow custody, and silence coexistence.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from dataclasses import replace

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

GUARD = ValidationReason.UNSUPPORTED_LANGUAGE
LANGS = ['vi', None, '', 'und', 'multi', 'unknown']
DURS = [0.5, 1, 2, 4, 10, 30, 90, 600]


def _env(monkeypatch, disposition='true', safety='false'):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', disposition)
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def _run(
    monkeypatch,
    caplog,
    *,
    language='vi',
    vad=None,
    decode=None,
    shadow=False,
    disposition='true',
    safety='false',
    duration=2,
    key='a'
):
    _env(monkeypatch, disposition, safety)
    caplog.set_level(logging.INFO)
    kwargs = {}
    if vad is not None:
        kwargs['vad'] = vad
    if decode is not None:
        kwargs['decode'] = decode
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _: language, **kwargs)
    unit = item(key, duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    guard = [r for r in caplog.records if 'event=batch_language_guard' in r.getMessage()]
    fault = [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    return worker, results, words, saved, guard, fault


class NoisyGuard(BatchValidationError):
    def __str__(self):
        return 'SECRET-AUDIO-BYTES ' + super().__str__()


def test_grid_vi_0_5s_guard_transitions(monkeypatch, caplog):
    """vi language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_1s_guard_transitions(monkeypatch, caplog):
    """vi language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_2s_guard_transitions(monkeypatch, caplog):
    """vi language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_4s_guard_transitions(monkeypatch, caplog):
    """vi language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_10s_guard_transitions(monkeypatch, caplog):
    """vi language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_30s_guard_transitions(monkeypatch, caplog):
    """vi language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_90s_guard_transitions(monkeypatch, caplog):
    """vi language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_vi_600s_guard_transitions(monkeypatch, caplog):
    """vi language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_0_5s_guard_transitions(monkeypatch, caplog):
    """none language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_1s_guard_transitions(monkeypatch, caplog):
    """none language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_2s_guard_transitions(monkeypatch, caplog):
    """none language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_4s_guard_transitions(monkeypatch, caplog):
    """none language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_10s_guard_transitions(monkeypatch, caplog):
    """none language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_30s_guard_transitions(monkeypatch, caplog):
    """none language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_90s_guard_transitions(monkeypatch, caplog):
    """none language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_none_600s_guard_transitions(monkeypatch, caplog):
    """none language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_0_5s_guard_transitions(monkeypatch, caplog):
    """blank language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_1s_guard_transitions(monkeypatch, caplog):
    """blank language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_2s_guard_transitions(monkeypatch, caplog):
    """blank language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_4s_guard_transitions(monkeypatch, caplog):
    """blank language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_10s_guard_transitions(monkeypatch, caplog):
    """blank language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_30s_guard_transitions(monkeypatch, caplog):
    """blank language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_90s_guard_transitions(monkeypatch, caplog):
    """blank language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_blank_600s_guard_transitions(monkeypatch, caplog):
    """blank language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='', duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_0_5s_guard_transitions(monkeypatch, caplog):
    """und language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_1s_guard_transitions(monkeypatch, caplog):
    """und language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_2s_guard_transitions(monkeypatch, caplog):
    """und language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_4s_guard_transitions(monkeypatch, caplog):
    """und language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_10s_guard_transitions(monkeypatch, caplog):
    """und language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_30s_guard_transitions(monkeypatch, caplog):
    """und language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_90s_guard_transitions(monkeypatch, caplog):
    """und language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_und_600s_guard_transitions(monkeypatch, caplog):
    """und language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='und', duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_0_5s_guard_transitions(monkeypatch, caplog):
    """multi language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_1s_guard_transitions(monkeypatch, caplog):
    """multi language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_2s_guard_transitions(monkeypatch, caplog):
    """multi language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_4s_guard_transitions(monkeypatch, caplog):
    """multi language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_10s_guard_transitions(monkeypatch, caplog):
    """multi language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_30s_guard_transitions(monkeypatch, caplog):
    """multi language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_90s_guard_transitions(monkeypatch, caplog):
    """multi language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_multi_600s_guard_transitions(monkeypatch, caplog):
    """multi language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='multi', duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_0_5s_guard_transitions(monkeypatch, caplog):
    """unknown language at 0.5s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=0.5, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=8000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_1s_guard_transitions(monkeypatch, caplog):
    """unknown language at 1s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=1, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_2s_guard_transitions(monkeypatch, caplog):
    """unknown language at 2s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=2, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_4s_guard_transitions(monkeypatch, caplog):
    """unknown language at 4s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=4, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_10s_guard_transitions(monkeypatch, caplog):
    """unknown language at 10s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=10, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=160000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_30s_guard_transitions(monkeypatch, caplog):
    """unknown language at 30s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=30, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_90s_guard_transitions(monkeypatch, caplog):
    """unknown language at 90s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=90, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=1440000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_unknown_600s_guard_transitions(monkeypatch, caplog):
    """unknown language at 600s crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='unknown', duration=600, key="g")
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'samples=9600000' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')


def test_grid_decode_guard_0_5s_transition(monkeypatch, caplog):
    """The decode-stage guard at 0.5s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=0.5)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_1s_transition(monkeypatch, caplog):
    """The decode-stage guard at 1s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=1)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_2s_transition(monkeypatch, caplog):
    """The decode-stage guard at 2s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=2)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_4s_transition(monkeypatch, caplog):
    """The decode-stage guard at 4s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=4)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_10s_transition(monkeypatch, caplog):
    """The decode-stage guard at 10s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=10)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_30s_transition(monkeypatch, caplog):
    """The decode-stage guard at 30s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=30)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_90s_transition(monkeypatch, caplog):
    """The decode-stage guard at 90s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=90)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_guard_600s_transition(monkeypatch, caplog):
    """The decode-stage guard at 600s carries the never-measured sentinels."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=600)
    assert len(guard) == 1 and not fault
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_word_shape_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_shape under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_shape' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_word_clock_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_clock under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_clock' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_word_sequence_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_sequence under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_sequence' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_vad_nonfinite_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """vad_nonfinite under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=vad_nonfinite' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_vad_order_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """vad_order under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=vad_order' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_vad_bounds_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """vad_bounds under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=vad_bounds' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_empty_asr_flag_on_terminal_and_error(monkeypatch, caplog):
    """empty_asr under the disposition flag terminates — on the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_decode_no_owned_words_flag_on_terminal_and_error(monkeypatch, caplog):
    """no_owned_words under the disposition flag terminates — on the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_typed_staged_invalid_reports_disposition(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise StagedAudioInvalid("bytes")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=staged_audio_invalid' in disposition[0].getMessage()


def test_grid_typed_retained_invalid_reports_disposition(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise RetainedAudioInvalid("bytes")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=retained_audio_invalid' in disposition[0].getMessage()


def test_grid_typed_duration_mismatch_reports_disposition(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise DecodedDurationMismatch("extent")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=decoded_duration_mismatch' in disposition[0].getMessage()


def test_grid_noisy_guard_at_decode_demotes_without_payload(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def decode(work):
        raise NoisyGuard(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert len(guard) == 1 and not fault
    assert "SECRET-AUDIO-BYTES" not in guard[0].getMessage()


def test_grid_noisy_non_guard_at_vad_stays_error_without_payload(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    class NoisyBounds(BatchValidationError):
        def __str__(self):
            return 'SECRET-AUDIO-BYTES ' + super().__str__()

    def vad(samples):
        raise NoisyBounds(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert "SECRET-AUDIO-BYTES" not in fault[0].getMessage()


def test_grid_sub_frame_guard_still_transitions(monkeypatch, caplog):
    """A 0.02s guarded capture still crosses the barrier with its measured samples."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, duration=0.02, key="tiny")
    assert len(guard) == 1
    assert 'samples=320' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_sub_frame_with_no_spans_is_silence(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=lambda _s: [], duration=0.02, key='tiny'
    )
    assert not guard and not fault
    assert results[0].outcome == "silence"


def test_grid_shadow_guard_at_vad_keeps_shadow_line(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, shadow=True)
    assert not guard and not fault
    assert isinstance(results[0], ValidationFailureWork)


def test_grid_silence_and_guard_batch_silence_first(monkeypatch, caplog):
    """Silence and the guard coexist in one batch without cross-talk."""
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda _u: "vi",
        vad=lambda s: [] if len(s) == 16000 else [(0.1, 0.9)],
    )
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    results = worker.process_batch([item("q", 1), item("g", 2)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    assert len(guard) == 1 and not fault
    assert sum(isinstance(r, WorkResult) and r.outcome == "silence" for r in results) == 1
    assert sum(isinstance(r, ValidationFailureWork) for r in results) == 1


def test_grid_silence_and_guard_batch_guard_first(monkeypatch, caplog):
    """Silence and the guard coexist in one batch without cross-talk."""
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda _u: "vi",
        vad=lambda s: [] if len(s) == 16000 else [(0.1, 0.9)],
    )
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    results = worker.process_batch([item("g", 2), item("q", 1)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    assert len(guard) == 1 and not fault
    assert sum(isinstance(r, WorkResult) and r.outcome == "silence" for r in results) == 1
    assert sum(isinstance(r, ValidationFailureWork) for r in results) == 1
