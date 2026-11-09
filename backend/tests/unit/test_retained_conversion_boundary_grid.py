"""Generated grid: the fetch_decode boundary's closed-fault disposition.

Every cell injects one typed (or deliberately anonymous) fault at one worker seam
under one flag combination and pins the exact booked outcome, evidence dict, log
channel and custody the REAL boundary and scheduler produce. The retained
rate-conversion cohort joins the typed terminal family here; the anonymous
negative space stays on the retry ladder by design.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import logging
import re

import pytest

from diarizer.batch_pipeline import (
    DecodedDurationMismatch,
)
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    RetainedAudioOutsideAdmittedSource,
)
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason


def test_boundary_conversion_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_conversion_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_conversion_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_conversion_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_conversion_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_conversion_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_conversion_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_conversion_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_checksum_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_checksum_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_checksum_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_checksum_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_checksum_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_checksum_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_checksum_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_checksum_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_size_budget_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_size_budget_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_size_budget_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_size_budget_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_size_budget_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_size_budget_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_size_budget_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_size_budget_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_manifest_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_manifest_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_manifest_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_manifest_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_boundary_manifest_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_manifest_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_manifest_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_manifest_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_staged_wav_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_staged_wav_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_staged_wav_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_staged_wav_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_staged_wav_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_staged_wav_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_staged_wav_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_staged_wav_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_artifact_auth_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_artifact_auth_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_artifact_auth_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_artifact_auth_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_boundary_artifact_auth_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_artifact_auth_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_artifact_auth_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_artifact_auth_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_duration_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_boundary_duration_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_boundary_duration_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_boundary_duration_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_boundary_duration_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_duration_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_duration_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_duration_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_outside_source_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def test_boundary_outside_source_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}


def test_boundary_outside_source_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_outside_source_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_outside_source_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}


def test_boundary_outside_source_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}


def test_boundary_outside_source_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_outside_source_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_bve_unsupported_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'unsupported_language')]


def test_boundary_bve_unsupported_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'unsupported_language')]


def test_boundary_bve_unsupported_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'unsupported_language')]


def test_boundary_bve_unsupported_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'unsupported_language')]


def test_boundary_bve_unsupported_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_boundary_bve_unsupported_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_boundary_bve_unsupported_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_boundary_bve_unsupported_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_boundary_bve_vad_bounds_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'vad_bounds')]


def test_boundary_bve_vad_bounds_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'vad_bounds'}


def test_boundary_bve_vad_bounds_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'vad_bounds')]


def test_boundary_bve_vad_bounds_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_bve_vad_bounds_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'vad_bounds')]


def test_boundary_bve_vad_bounds_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'vad_bounds'}


def test_boundary_bve_vad_bounds_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'vad_bounds')]


def test_boundary_bve_vad_bounds_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_bve_empty_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'empty_asr')]


def test_boundary_bve_empty_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'empty_asr'}


def test_boundary_bve_empty_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'empty_asr')]


def test_boundary_bve_empty_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_bve_empty_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'empty_asr')]


def test_boundary_bve_empty_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'empty_asr'}


def test_boundary_bve_empty_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'empty_asr')]


def test_boundary_bve_empty_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_plain_value_error_decode_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_boundary_plain_value_error_decode_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_boundary_plain_value_error_decode_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_plain_value_error_decode_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_plain_value_error_vad_safety_true_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_plain_value_error_vad_safety_true_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert results[0].segment_id == 'a'
    assert results[0].worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_boundary_plain_value_error_vad_safety_false_disposition_true(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_boundary_plain_value_error_vad_safety_false_disposition_false(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    results = worker.process_batch([item()])
    assert results == []


def test_shadow_conversion_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=retained_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_conversion_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_checksum_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=retained_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_checksum_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_size_budget_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=retained_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_size_budget_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_manifest_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=retained_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_manifest_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_staged_wav_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=staged_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_staged_wav_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_artifact_auth_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=staged_audio_invalid' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_artifact_auth_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_duration_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=decoded_duration_mismatch' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_duration_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=unclassified' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_outside_source_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=fetch_decode reason=outside_admitted_source' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_shadow_outside_source_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    from dataclasses import replace

    results = worker.process_batch([replace(item(), shadow=True)])
    assert len(results) == 1 and isinstance(results[0], FailedWork)
    assert 'event=batch_shadow_worker_failure stage=vad_windows reason=outside_admitted_source' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text


def test_log_channel_conversion_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text


def test_log_channel_conversion_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_checksum_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text


def test_log_channel_checksum_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_size_budget_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text


def test_log_channel_size_budget_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=RetainedAudioInvalid' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_manifest_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=InvalidRetainedManifest' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=retained_audio_invalid' in caplog.text


def test_log_channel_manifest_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=InvalidRetainedManifest' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_staged_wav_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=StagedAudioInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=staged_audio_invalid' in caplog.text


def test_log_channel_staged_wav_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=StagedAudioInvalid' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_artifact_auth_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=StagedArtifactInvalid' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=staged_audio_invalid' in caplog.text


def test_log_channel_artifact_auth_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=StagedArtifactInvalid' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_duration_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=DecodedDurationMismatch' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=decoded_duration_mismatch' in caplog.text


def test_log_channel_duration_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=DecodedDurationMismatch' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_outside_source_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=RetainedAudioOutsideAdmittedSource' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=outside_admitted_source' in caplog.text


def test_log_channel_outside_source_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=RetainedAudioOutsideAdmittedSource' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=outside_admitted_source' in caplog.text


def test_log_channel_bve_unsupported_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_language_guard outcome=redrive_held' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=unsupported_language' in caplog.text


def test_log_channel_bve_unsupported_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_language_guard outcome=redrive_held' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unsupported_language' in caplog.text


def test_log_channel_bve_vad_bounds_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=vad_bounds' in caplog.text


def test_log_channel_bve_vad_bounds_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_validation_disposition outcome=recovery_handoff' in caplog.text
    assert 'event=batch_worker_failed' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=vad_bounds' in caplog.text


def test_log_channel_bve_empty_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=empty_asr' in caplog.text


def test_log_channel_bve_empty_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=BatchValidationError' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=empty_asr' in caplog.text


def test_log_channel_plain_value_error_decode(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(decode=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=ValueError' in caplog.text
    assert 'stage=fetch_decode' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_log_channel_plain_value_error_vad(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    def raise_fault(_):
        raise ValueError('different decode failure')

    worker, words, saved, *_ = setup_worker(vad=raise_fault)
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text
    assert 'error_class=ValueError' in caplog.text
    assert 'stage=vad_windows' in caplog.text
    assert 'reason=unclassified' in caplog.text


def test_sibling_survives_conversion():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('invalid retained PCM')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_conversion():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise RetainedAudioInvalid('invalid retained PCM')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_conversion():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(RetainedAudioInvalid('invalid retained PCM'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'RetainedAudioInvalid')]


def test_sibling_survives_checksum():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('retained capture checksum mismatch')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_checksum():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_checksum():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(RetainedAudioInvalid('retained capture checksum mismatch'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'RetainedAudioInvalid')]


def test_sibling_survives_size_budget():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('invalid retained audio size')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_size_budget():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise RetainedAudioInvalid('invalid retained audio size')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_size_budget():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(RetainedAudioInvalid('invalid retained audio size'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'RetainedAudioInvalid')]


def test_sibling_survives_manifest():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise InvalidRetainedManifest('malformed retained audio manifest')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_manifest():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise InvalidRetainedManifest('malformed retained audio manifest')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_manifest():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(InvalidRetainedManifest('malformed retained audio manifest'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'InvalidRetainedManifest')]


def test_sibling_survives_staged_wav():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise StagedAudioInvalid('invalid staged WAV container')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_staged_wav():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise StagedAudioInvalid('invalid staged WAV container')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_staged_wav():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(StagedAudioInvalid('invalid staged WAV container'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'StagedAudioInvalid')]


def test_sibling_survives_artifact_auth():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise StagedArtifactInvalid('staged artifact authentication failed')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_artifact_auth():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise StagedArtifactInvalid('staged artifact authentication failed')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_artifact_auth():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(StagedArtifactInvalid('staged artifact authentication failed'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'StagedArtifactInvalid')]


def test_sibling_survives_duration():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise DecodedDurationMismatch('decoded duration differs from admitted capture')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_duration():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise DecodedDurationMismatch('decoded duration differs from admitted capture')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_duration():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(
            DecodedDurationMismatch('decoded duration differs from admitted capture')
        )
    )
    worker.process_batch([item()])
    assert failures == [('a', 'DecodedDurationMismatch')]


def test_sibling_survives_outside_source():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_outside_source():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_outside_source():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(
            RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
        )
    )
    worker.process_batch([item()])
    assert failures == [('a', 'RetainedAudioOutsideAdmittedSource')]


def test_sibling_survives_bve_unsupported():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_bve_unsupported():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_bve_unsupported():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'BatchValidationError')]


def test_sibling_survives_bve_vad_bounds():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise BatchValidationError(ValidationReason.VAD_BOUNDS)
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_bve_vad_bounds():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_bve_vad_bounds():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(BatchValidationError(ValidationReason.VAD_BOUNDS))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'BatchValidationError')]


def test_sibling_survives_bve_empty():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise BatchValidationError(ValidationReason.EMPTY_ASR)
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_bve_empty():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_bve_empty():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(BatchValidationError(ValidationReason.EMPTY_ASR))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'BatchValidationError')]


def test_sibling_survives_plain_value_error():

    def raise_for_bad(work):
        if work.segment_id == 'bad':
            raise ValueError('different decode failure')
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=raise_for_bad)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_decode_runs_once_plain_value_error():

    decoded = []

    def raise_and_record(work):
        decoded.append(work.segment_id)
        raise ValueError('different decode failure')

    worker, *_ = setup_worker(decode=raise_and_record)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_failure_callback_plain_value_error():

    worker, _, _, _, _, failures = setup_worker(
        decode=lambda work: (_ for _ in ()).throw(ValueError('different decode failure'))
    )
    worker.process_batch([item()])
    assert failures == [('a', 'ValueError')]


def test_fault_line_site_field_is_static_source_location(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(ValueError('different decode failure')))
    worker.process_batch([item()])
    match = re.search(r'site=[A-Za-z0-9_.]+\.py:\d+', caplog.text)
    assert match, caplog.text
    assert 'different decode failure' not in caplog.text


def test_fault_line_never_carries_the_exception_text(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    caplog.set_level(logging.INFO)

    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(ValueError('owner-secret-value')))
    worker.process_batch([item()])
    assert 'owner-secret-value' not in caplog.text
