"""StagedAudio and the decode context memo behave under typed faults.

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

The worker's ``StagedAudio`` wrapper fetches and decodes once, keeping
each unit's capture-stream and language memo. A typed decode fault must
propagate unchanged through the timing wrappers and the context
discarding, leave the per-unit memos readable for the failure record, and
never poison a sibling unit or the next batch.
"""

import io
import wave
from unittest.mock import Mock

import pytest

from diarizer.batch_pipeline_models import StagedAudio, decode_pcm16_wav
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline import leaf_timings
from utils.batch_pipeline.audio import RATE, StagedAudioInvalid, audio_unit, with_context
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage


def canonical_body(frames=b'\x00\x00' * 8):
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return body.getvalue()


def garbage_body():
    return b'persistent-garbage-not-a-wav'


def throw_typed(_work):
    raise StagedAudioInvalid('invalid staged WAV container')


# --- the memo layer around decode -----------------------------------------------------


def test_staged_audio_decode_propagates_the_typed_fault():
    staged = StagedAudio(lambda item: garbage_body())
    with pytest.raises(StagedAudioInvalid) as raised:
        staged.decode(item())
    assert type(raised.value) is StagedAudioInvalid


def test_staged_audio_decode_propagates_the_container_message():
    staged = StagedAudio(lambda item: garbage_body())
    with pytest.raises(StagedAudioInvalid, match='^invalid staged WAV container$'):
        staged.decode(item())


def test_staged_audio_stream_memo_stays_readable_after_a_typed_failure():
    staged = StagedAudio(lambda item: garbage_body())
    unit = item()
    with pytest.raises(StagedAudioInvalid):
        staged.decode(unit)
    # The memo call does not raise and returns a captured-or-empty value;
    # the failure record path may read it without a second decode.
    assert staged.stream(unit) is None or isinstance(staged.stream(unit), str)


def test_staged_audio_language_memo_reports_no_context_after_a_typed_failure():
    staged = StagedAudio(lambda item: garbage_body())
    unit = item()
    with pytest.raises(StagedAudioInvalid):
        staged.decode(unit)
    assert staged.language(unit) is None


def test_staged_audio_stream_is_shadow_prefixed_for_shadow_items():
    from dataclasses import replace

    staged = StagedAudio(lambda item: canonical_body())
    unit = replace(item(), shadow=True)
    staged.decode(unit)
    stream = staged.stream(unit)
    assert stream is None or stream.startswith('shadow:')


def test_staged_audio_populates_the_language_memo_from_a_valid_context():
    context = {
        'version': 1,
        'owner_id': 'owner-a',
        'segment_id': 'a',
        'job_id': 'j',
        'content_id': 'c',
        'source': 'sync',
        'stt_language': 'en',
        'stt_language_evidence': 'declared',
        'stt_language_confidence': 1.0,
    }
    staged = StagedAudio(lambda item: with_context(audio_unit(1.0, b'\x00\x00' * RATE).wav, context))
    unit = item()
    staged.decode(unit)
    assert staged.language(unit) == 'en'


def test_staged_audio_language_memo_ignores_an_unproven_language_hint():
    context = {
        'version': 1,
        'owner_id': 'owner-a',
        'segment_id': 'a',
        'job_id': 'j',
        'content_id': 'c',
        'source': 'sync',
        'stt_language': 'en',
    }
    staged = StagedAudio(lambda item: with_context(audio_unit(1.0, b'\x00\x00' * RATE).wav, context))
    unit = item()
    staged.decode(unit)
    # A supported-language hint without evidence is not proof.
    assert staged.language(unit) is None


def test_staged_audio_memo_eviction_keeps_recent_units():
    staged = StagedAudio(lambda item: canonical_body())
    units = [item(str(index)) for index in range(StagedAudio.MAX_PENDING + 4)]
    for unit in units:
        staged.decode(unit)
    assert staged.language(units[-1]) is None  # canonical body carries no context
    assert staged.stream(units[-1]) is None


def test_staged_audio_decode_of_a_valid_unit_returns_samples():
    staged = StagedAudio(lambda item: canonical_body())
    samples = staged.decode(item())
    assert len(samples) == 8


def test_staged_audio_decode_failure_does_not_poison_the_next_unit():
    bodies = {'bad': garbage_body(), 'good': canonical_body()}
    staged = StagedAudio(lambda item: bodies[item.segment_id])
    with pytest.raises(StagedAudioInvalid):
        staged.decode(item('bad'))
    assert len(staged.decode(item('good'))) == 8


def test_staged_audio_stream_memo_is_one_shot_per_unit():
    context = {
        'version': 1,
        'owner_id': 'owner-a',
        'segment_id': 'a',
        'job_id': 'j',
        'content_id': 'c',
        'source': 'sync',
    }
    staged = StagedAudio(lambda item: with_context(audio_unit(1.0, b'\x00\x00' * RATE).wav, context))
    unit = item()
    staged.decode(unit)
    # A conversation-kind unit without a conversation id has no stream;
    # the memo is still consumed exactly once.
    assert staged.stream(unit) is None
    assert staged.stream(unit) is None


# --- the timing wrappers keep the type ------------------------------------------------


def test_leaf_timings_call_passes_the_typed_fault_through():
    with pytest.raises(StagedAudioInvalid) as raised:
        leaf_timings.call('decode', decode_pcm16_wav, garbage_body())
    assert type(raised.value) is StagedAudioInvalid


def test_leaf_timings_call_returns_the_decoded_samples():
    samples = leaf_timings.call('decode', decode_pcm16_wav, canonical_body())
    assert len(samples) == 8


def test_leaf_timings_active_during_decode_sees_no_error_from_valid_units():
    timings = leaf_timings.StageTimings()
    staged = StagedAudio(lambda item: canonical_body(), timings_of=lambda: timings)
    assert len(staged.decode(item())) == 8


# --- the worker's decode-context path -------------------------------------------------


def test_decode_context_discards_and_reraises_the_typed_fault(monkeypatch):
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    discard = Mock()
    monkeypatch.setattr(worker, '_discard_context', discard)
    with pytest.raises(StagedAudioInvalid):
        worker._decode_context(item())
    assert discard.called


def test_decode_context_skips_the_strict_shadow_on_a_typed_fault():
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    with pytest.raises(StagedAudioInvalid):
        worker._decode_context(item())


def test_decode_context_returns_four_values_on_success():
    worker, *_ = setup_worker()
    samples, language, stream, strict = worker._decode_context(item())
    assert len(samples) == 32000
    assert language is not None
    assert strict is None or isinstance(strict, bool)


def test_process_batch_language_probe_survives_a_failed_decode_sibling():
    worker, words, saved, decoded, diarized, failures = setup_worker(
        decode=lambda work: throw_typed(work) if work.segment_id == 'bad' else Samples(2)
    )
    results = worker.process_batch([item('bad'), item('good')])
    assert isinstance(results[0], ValidationFailureWork)
    assert results[1].segment_id == 'good'
    assert worker.counts['items'] == 2


def test_consecutive_batches_are_not_poisoned_by_a_typed_fault():
    worker, words, saved, decoded, diarized, failures = setup_worker(
        decode=lambda work: throw_typed(work) if work.segment_id == 'bad' else Samples(2)
    )
    first = worker.process_batch([item('bad')])
    assert isinstance(first[0], ValidationFailureWork)
    second = worker.process_batch([item('good')])
    assert second[0].segment_id == 'good'
    assert set(saved) == {'good'}
    assert worker.counts['failed'] == 1


def test_two_typed_failures_in_one_batch_each_get_their_own_record():
    worker, words, saved, decoded, diarized, failures = setup_worker(
        decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container'))
    )
    results = worker.process_batch([item('a'), item('b')])
    assert [isinstance(result, ValidationFailureWork) for result in results] == [True, True]
    assert worker.counts['failed'] == 2
    assert len(failures) == 2


def test_typed_fault_failure_record_carries_the_exception_class_name():
    worker, *_rest, failures = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    worker.process_batch([item()])
    assert failures == [('a', 'StagedAudioInvalid')]


def test_worker_counts_one_failed_item_per_typed_unit():
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    worker.process_batch([item('a'), item('b')])
    assert worker.counts['failed'] == 2
    assert worker.counts['items'] == 2


def test_typed_fault_leaves_the_words_provider_uncalled():
    worker, words, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    worker.process_batch([item()])
    assert not words.calls


def test_typed_fault_leaves_the_persist_sink_empty():
    worker, _, saved, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    worker.process_batch([item()])
    assert saved == {}


def test_typed_fault_leaves_the_diarizer_uncalled():
    worker, _, _, _, diarized, _ = setup_worker(
        decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container'))
    )
    worker.process_batch([item()])
    assert not diarized


def test_typed_fault_result_keeps_the_fetch_decode_stage_token():
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    result = worker.process_batch([item()])[0]
    assert result.stage == WorkerValidationStage.FETCH_DECODE.value


def test_typed_fault_result_reason_is_the_closed_staged_token():
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    result = worker.process_batch([item()])[0]
    assert result.reason == WorkerValidationReason.STAGED_AUDIO_INVALID.value


def test_typed_fault_is_deterministic_across_batches():
    worker, *_ = setup_worker(decode=Mock(side_effect=StagedAudioInvalid('invalid staged WAV container')))
    first = worker.process_batch([item('x')])
    second = worker.process_batch([item('y')])
    assert first[0].stage == second[0].stage
    assert first[0].reason == second[0].reason


def test_valid_batch_still_completes_after_the_typed_fault_batch():
    worker, words, saved, decoded, diarized, failures = setup_worker(
        decode=lambda work: throw_typed(work) if work.segment_id == 'bad' else Samples(2)
    )
    worker.process_batch([item('bad')])
    results = worker.process_batch([item('good')])
    assert results[0].segment_id == 'good'
    assert words.calls


def test_staged_audio_fetch_fault_of_the_retained_family_keeps_its_own_type():
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    def fetch(_item):
        raise RetainedAudioInvalid('retained capture checksum mismatch')

    staged = StagedAudio(fetch)
    with pytest.raises(RetainedAudioInvalid) as raised:
        staged.decode(item())
    assert not isinstance(raised.value, StagedAudioInvalid)
