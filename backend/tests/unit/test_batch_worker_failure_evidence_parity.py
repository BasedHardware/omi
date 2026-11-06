"""The GPU worker closes every ordinary failure into evidence at the source.

The worker's fail() closure knows the stage and the closed reason of every
failure it records, but the transient FailedWork handoff used to carry none of
it, so the scheduler's ladder burned blind and quarantined
``stage=unknown worker_reason=unclassified``. This suite pins the extraction
matrix: closed stages produce closed evidence (generic exceptions collapse to
the enum's unknown token, BatchValidationError reasons pass through), the
untyped provider/persist stages stay unevidenced, the terminal validation
families keep their existing typed handoff, and no exception text ever
reaches the evidence or the logs.

Failure-Class: FC-batch-transient-worker-failure-quarantines-blind-without-stage-or-reason-evidence
"""

import struct
import wave
from unittest.mock import Mock

import pytest

from diarizer.batch_pipeline import transient_failure_evidence
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.observability.reasons import WorkerValidationStage
from tests.unit.test_batch_pipeline_worker import item, setup_worker

EVIDENCE_STAGES = ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']
UNTYPED_STAGES = ['asr', 'persist', 'diarize']


@pytest.fixture(autouse=True)
def _evidence_pipeline(monkeypatch):
    # The ordinary-failure handoff requires the safety net; the disposition
    # flag stays off so closed validation reasons stay on the transient path
    # this suite pins (their typed terminal routing has its own suites).
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def _first_failed_work(worker_results):
    assert len(worker_results) == 1
    result = worker_results[0]
    assert isinstance(result, FailedWork)
    return result


# --- Generic exceptions close to stage + unknown ---------------------------------


@pytest.mark.parametrize('error', [RuntimeError('boom'), OSError('disk bad'), TimeoutError('slow'), KeyError('mood')])
def test_fetch_decode_generic_exception_carries_stage_evidence(error, monkeypatch):
    worker, *_ = setup_worker(decode=Mock(side_effect=error))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


@pytest.mark.parametrize('error', [RuntimeError('boom'), wave.Error('bad wav')])
def test_vad_windows_generic_exception_carries_stage_evidence(error, monkeypatch):
    worker, *_ = setup_worker(vad=Mock(side_effect=error))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_fetch_decode_generic_exception_evidence_is_stage_only():
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('exact private provider text')))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert 'exact private provider text' not in str(result.worker_failure)


def test_same_stage_different_exception_payloads_produce_identical_evidence():
    one = _first_failed_work(setup_worker(decode=Mock(side_effect=RuntimeError('a')))[0].process_batch([item()]))
    two = _first_failed_work(setup_worker(decode=Mock(side_effect=OSError('b')))[0].process_batch([item()]))
    assert one.worker_failure == two.worker_failure


def test_repeated_identical_failures_produce_identical_evidence():
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    first = _first_failed_work(worker.process_batch([item()]))
    second = _first_failed_work(worker.process_batch([item()]))
    assert first.worker_failure == second.worker_failure


# --- Closed validation reasons pass through the evidence ------------------------


def _broken_words(words):
    class BrokenWords:
        def transcribe_batch(self, samples):
            return [words for _ in samples]

    return {'words_providers': {'parakeet': BrokenWords()}}


def test_word_clock_validation_error_evidence_carries_the_closed_reason(monkeypatch):
    worker, *_ = setup_worker(**_broken_words([{'word': 'hi', 'timestamp': [-1, 0]}]))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'word_clocks', 'reason': 'word_clock'}


def test_word_shape_validation_error_evidence_carries_the_closed_reason(monkeypatch):
    worker, *_ = setup_worker(**_broken_words([{'word': 'hi', 'timestamp': ['a', 'b']}]))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'word_clocks', 'reason': 'word_shape'}


def test_word_sequence_validation_error_evidence_carries_the_closed_reason(monkeypatch):
    worker, *_ = setup_worker(
        **_broken_words([{'word': 'a', 'timestamp': [0.5, 1.0]}, {'word': 'b', 'timestamp': [0.2, 0.3]}])
    )
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'word_clocks', 'reason': 'word_sequence'}


def test_word_clocks_evidence_failure_counts_once(monkeypatch):
    worker, *_ = setup_worker(**_broken_words([{'word': 'hi', 'timestamp': [-1, 0]}]))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert worker.counts['failed'] == 1
    assert result.worker_failure['stage'] == 'word_clocks'


# --- Untyped stages stay unevidenced ---------------------------------------------


def test_asr_stage_generic_exception_stays_unevidenced():
    class BrokenWords:
        def transcribe_batch(self, samples):
            raise RuntimeError('provider down')

    worker, *_ = setup_worker(words_providers={'parakeet': BrokenWords()})
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure is None


def test_asr_stage_cardinality_mismatch_stays_unevidenced():
    class ShortWords:
        def transcribe_batch(self, samples):
            return []  # one item batched, zero hypotheses: cardinality mismatch

    worker, *_ = setup_worker(words_providers={'parakeet': ShortWords()})
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure is None
    assert worker.counts['failed'] == 1


def test_persist_stage_generic_exception_stays_unevidenced():
    worker, *_ = setup_worker(persist=Mock(side_effect=OSError('upload failed')))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure is None


def test_diarize_stage_generic_exception_stays_unevidenced():
    worker, *_ = setup_worker(diarizers={'pyannote': Mock(side_effect=RuntimeError('pyannote down'))})
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure is None


# --- The helper's own matrix ------------------------------------------------------


def test_helper_closes_every_closed_stage():
    for stage in EVIDENCE_STAGES:
        assert transient_failure_evidence(stage, 'unknown') == {'stage': stage, 'reason': 'unknown'}


def test_helper_passes_closed_reasons_through_for_closed_stages():
    assert transient_failure_evidence('word_clocks', 'word_clock') == {'stage': 'word_clocks', 'reason': 'word_clock'}
    assert transient_failure_evidence('fetch_decode', 'staged_audio_invalid') == {
        'stage': 'fetch_decode',
        'reason': 'staged_audio_invalid',
    }


def test_helper_collapses_open_reasons_to_unknown_for_closed_stages():
    assert transient_failure_evidence('fetch_decode', 'unclassified') == {'stage': 'fetch_decode', 'reason': 'unknown'}
    assert transient_failure_evidence('assemble_words', 'mystery') == {'stage': 'assemble_words', 'reason': 'unknown'}


def test_helper_returns_none_for_every_untyped_stage():
    for stage in UNTYPED_STAGES:
        assert transient_failure_evidence(stage, 'unknown') is None
        assert transient_failure_evidence(stage, 'word_clock') is None


def test_helper_never_echoes_exception_text():
    evidence = transient_failure_evidence('fetch_decode', 'synthetic-private-marker')
    assert 'synthetic-private-marker' not in str(evidence)


def test_helper_stage_vocabulary_is_the_shared_closed_set():
    from utils.batch_pipeline.errors import validate_worker_failure_evidence

    for stage in EVIDENCE_STAGES:
        assert validate_worker_failure_evidence({'stage': stage, 'reason': 'unknown'}) is None
    for stage in UNTYPED_STAGES:
        with pytest.raises(ValueError, match='closed worker failure evidence required'):
            validate_worker_failure_evidence({'stage': stage, 'reason': 'unknown'})


# --- Terminal validation families keep their typed routing -----------------------


def test_staged_audio_message_keeps_the_typed_terminal_handoff(monkeypatch):
    from utils.batch_pipeline.audio import StagedAudioInvalid

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('staging requires 16kHz mono PCM16 WAV')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'staged_audio_invalid')]


def test_retained_audio_invalid_keeps_the_typed_terminal_handoff(monkeypatch):
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(decode=Mock(side_effect=RetainedAudioInvalid('gone')))
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_decoded_duration_mismatch_keeps_the_typed_terminal_handoff(monkeypatch):
    from diarizer.batch_pipeline import DecodedDurationMismatch

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(
        decode=Mock(side_effect=DecodedDurationMismatch('decoded duration differs from admitted capture'))
    )
    results = worker.process_batch([item()])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'decoded_duration_mismatch')]


def test_no_failed_work_evidence_is_produced_for_the_terminal_families(monkeypatch):
    # The evidence field belongs to FailedWork only; the typed terminal
    # handoff already carries stage+reason as first-class fields.
    from utils.batch_pipeline.audio import StagedAudioInvalid

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('staging requires 16kHz mono PCM16 WAV')))
    result = worker.process_batch([item()])[0]
    assert isinstance(result, ValidationFailureWork)
    assert not hasattr(result, 'worker_failure')


def test_unsupported_language_keeps_its_typed_terminal_handoff(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    worker, *_ = setup_worker(language_of=lambda work: 'xx')
    results = worker.process_batch([item(duration=60)])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]


def test_language_blocked_stays_terminal_even_with_disposition_off(monkeypatch):
    # unsupported_language is unconditionally terminal in fail(): the fixed
    # vocabulary recognizer can never serve the unit, on any flag state.
    worker, *_ = setup_worker(language_of=lambda work: 'xx')
    results = worker.process_batch([item(duration=60)])
    assert results == [ValidationFailureWork('a', 'vad_windows', 'unsupported_language')]
    assert not isinstance(results[0], FailedWork)


# --- Fatal CUDA and privacy guards -------------------------------------------------


def test_fatal_cuda_decode_error_raises_and_never_becomes_failed_work():
    from utils.batch_pipeline.errors import FatalGpuError

    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('CUDA error: device-side assert triggered')))
    with pytest.raises(FatalGpuError):
        worker.process_batch([item()])


def test_fatal_cuda_error_leaves_no_evidence_payload():
    from utils.batch_pipeline.errors import FatalGpuError

    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('CUDA error: device-side assert triggered')))
    with pytest.raises(FatalGpuError):
        worker.process_batch([item()])
    assert worker._unavailable is True


def test_worker_failed_log_keeps_its_shape_and_stays_message_free(monkeypatch, caplog):
    marker = 'synthetic-private-content-must-not-be-logged'
    worker, *_ = setup_worker(decode=Mock(side_effect=ValueError(marker)))
    with caplog.at_level(0):
        result = _first_failed_work(worker.process_batch([item()]))
    records = [record for record in caplog.records if 'event=batch_worker_failed' in record.getMessage()]
    assert len(records) == 1
    assert (
        records[0]
        .getMessage()
        .startswith(
            'event=batch_worker_failed error_class=ValueError stage=fetch_decode segment_id=a reason=unclassified '
        )
    )
    assert marker not in caplog.text
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_closed_reason_log_keeps_its_shape(monkeypatch, caplog):
    worker, *_ = setup_worker(**_broken_words([{'word': 'hi', 'timestamp': [-1, 0]}]))
    with caplog.at_level(0):
        _first_failed_work(worker.process_batch([item(duration=60)]))
    records = [record for record in caplog.records if 'event=batch_worker_failed' in record.getMessage()]
    assert (
        records[0]
        .getMessage()
        .startswith(
            'event=batch_worker_failed error_class=BatchValidationError stage=word_clocks segment_id=a reason=word_clock '
        )
    )


def test_evidence_never_appears_in_the_worker_failed_log(caplog):
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    with caplog.at_level(0):
        _first_failed_work(worker.process_batch([item()]))
    assert 'worker_failure' not in caplog.text


# --- Flag-off parity: the drop path stays a drop -----------------------------------


def test_safety_net_off_leaves_no_work_item(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    assert worker.process_batch([item()]) == []
    assert worker.counts['failed'] == 1


def test_safety_net_off_produces_no_evidence_payload(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    assert worker.process_batch([item()]) == []
    assert worker.process_batch([item('b')]) == []


def test_safety_net_off_word_clocks_still_drops_without_disposition(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(**_broken_words([{'word': 'hi', 'timestamp': [-1, 0]}]))
    assert worker.process_batch([item(duration=60)]) == []


def test_shadow_items_carry_the_same_evidence(monkeypatch):
    from dataclasses import replace

    worker, *_ = setup_worker(decode=Mock(side_effect=RuntimeError('boom')))
    result = _first_failed_work(worker.process_batch([replace(item(), shadow=True)]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


# --- Wider generic-exception matrix --------------------------------------------------


@pytest.mark.parametrize('error', [wave.Error('bad wav'), struct.error('unpack failed'), EOFError('truncated')])
def test_fetch_decode_library_decode_errors_carry_stage_evidence(error, monkeypatch):
    worker, *_ = setup_worker(decode=Mock(side_effect=error))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


@pytest.mark.parametrize('error', [MemoryError('gpu oom'), EOFError('truncated'), OSError('read failed')])
def test_fetch_decode_resource_errors_carry_stage_evidence(error, monkeypatch):
    worker, *_ = setup_worker(decode=Mock(side_effect=error))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


@pytest.mark.parametrize('error', [MemoryError('gpu oom'), EOFError('truncated')])
def test_vad_windows_resource_errors_carry_stage_evidence(error, monkeypatch):
    worker, *_ = setup_worker(vad=Mock(side_effect=error))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}


def test_import_error_at_decode_still_evidences_the_stage():
    worker, *_ = setup_worker(decode=Mock(side_effect=ImportError('missing codec')))
    result = _first_failed_work(worker.process_batch([item()]))
    assert result.worker_failure == {'stage': 'fetch_decode', 'reason': 'unknown'}


def test_attribute_error_at_vad_still_evidences_the_stage():
    worker, *_ = setup_worker(vad=Mock(side_effect=AttributeError('no spans attr')))
    result = _first_failed_work(worker.process_batch([item(duration=60)]))
    assert result.worker_failure == {'stage': 'vad_windows', 'reason': 'unknown'}
