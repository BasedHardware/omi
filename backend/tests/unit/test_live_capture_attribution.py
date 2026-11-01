"""Attribution is transaction-local and does not alter the stored segment shape."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config.live_capture import CAPTURE_WINDOW_REASONS, capture_window_reason
from models.transcript_segment import TranscriptSegment
from tests.unit.test_audio_timeline_round3 import RATE, T0
from tests.unit.test_live_capture_retention import drain, setup
from tests.unit.test_live_capture_windows import _processor, segment, speech
from tests.unit.test_manual_speaker_assignments import world, read
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator, SendMap
from utils.manual_speaker_assignments import merge_live_segments
from utils.metrics import OMI_LIVE_AUDIO_CAPTURE_ATTRIBUTION_TOTAL as METRIC


def count(population, reason):
    return METRIC.labels(population=population, reason=reason)._value.get()


def test_reason_vocabulary_is_bounded():
    assert capture_window_reason('arbitrary-provider-or-user-value') == 'missing_window'
    assert capture_window_reason([]) == 'missing_window'
    assert len(CAPTURE_WINDOW_REASONS) < 25


@pytest.mark.parametrize(
    'start,end,reason',
    [
        (0, 0, 'translator_zero_length'),
        (5, 6, 'translator_outside_accepted_sends'),
        (0.5, 1.5, 'translator_discontinuous_interval'),
        (2.1, 2.2, 'translator_collapsed_interval'),
    ],
)
def test_translator_refusal_metadata_preserves_legacy_text(start, end, reason):
    timeline = CaptureTimeline(100)
    timeline.accept(b'\0' * 600, 103, 3)
    translator = ProviderEpochTranslator(timeline, 100, project_times=False)
    translator.note_accepted_spans([(0, 100), (200, 100)])
    raw = dict(text='synthetic', start=start, end=end)
    (result,) = translator.translate([raw])
    assert result['_capture_window_reason'] == reason
    assert all(result[k] == v for k, v in raw.items())
    assert '_capture_window_reason' not in raw


def test_eviction_is_distinguished_from_out_of_range():
    timeline = CaptureTimeline(100)
    timeline.accept(b'\0' * 1000, 105, 5)
    translator = ProviderEpochTranslator(timeline, 100, project_times=False)
    translator.send_map = SendMap(100, max_spans=1)
    translator.note_accepted_spans([(0, 100), (200, 100)])
    assert (
        translator.translate([dict(text='early', start=0, end=0.5)])[0]['_capture_window_reason'] == 'send_map_evicted'
    )
    assert (
        translator.translate([dict(text='future', start=9, end=10)])[0]['_capture_window_reason']
        == 'translator_outside_accepted_sends'
    )


@pytest.mark.parametrize('window,reason', [(None, 'merge_unknown_side'), ((103, 104), 'merge_gap')])
def test_merge_reason_and_inherited_amplification(window, reason):
    a = speech('a', 'hello', audio_capture_start=100, audio_capture_end=101)
    b = speech('b', 'world', start=1, end=2)
    if window:
        b.update(audio_capture_start=window[0], audio_capture_end=window[1])
    first = merge_live_segments([a], [b], {})
    assert first.capture_reasons['a'] == reason
    assert first.created_ids == set()  # absorbed b was never a stored segment
    second = merge_live_segments(first.segments, [speech('c', 'again', start=2, end=3)], {})
    assert second.capture_reasons['a'] == 'inherited_unknown'
    assert '_audio_capture_reason' not in str(second.segments)


def test_partial_redistribution_reason_is_returned_for_both_survivors():
    a = speech('a', 'A long unfinished phrase', audio_capture_start=100, audio_capture_end=101)
    b = speech('b', 'yes. Another sentence.', speaker=1, start=1, end=2, audio_capture_start=101, audio_capture_end=102)
    result = merge_live_segments([a], [b], {})
    assert result.capture_reasons == {'a': 'partial_redistribution', 'b': 'partial_redistribution'}
    assert result.created_ids == {'b'}


async def test_transaction_counts_first_stored_id_once_and_versions_separately(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = []
    processor = _processor(world)
    current = SimpleNamespace(id='c', transcript_segments=[])
    fresh = segment('a', 'hello')
    fresh.capture_window_reason = 'translator_outside_accepted_sends'
    first = count('segment', fresh.capture_window_reason)
    versions = count('version', fresh.capture_window_reason)
    await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert count('segment', fresh.capture_window_reason) == first + 1
    assert count('version', fresh.capture_window_reason) == versions + 1
    inherited = count('version', 'inherited_unknown')
    await processor._update_live_conversation(
        current, [segment('b', 'world', start=1, end=2)], [], datetime.now(timezone.utc), None
    )
    assert count('version', 'inherited_unknown') == inherited + 1
    assert count('segment', 'inherited_unknown') == 0
    assert len(read(world)['transcript_segments']) == 1
    # Retry of an already committed ID must not create a distinct observation.
    before = sum(count('segment', reason) for reason in CAPTURE_WINDOW_REASONS)
    await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert sum(count('segment', reason) for reason in CAPTURE_WINDOW_REASONS) == before


@pytest.mark.parametrize(
    'reason',
    [
        'translator_zero_length',
        'translator_outside_accepted_sends',
        'kill_switch',
        'custom_stt',
        'multi_channel',
        'anchor_compacted',
    ],
)
async def test_original_loss_reason_reaches_committed_metric(monkeypatch, reason):
    receiver, callback, epoch, sender = setup(monkeypatch, False, 'modulate')
    pcm = b'\0\0' * RATE
    for i in range(70 if reason == 'anchor_compacted' else 1):
        first, _, _ = receiver.capture_timeline.accept(pcm, T0 + i * 4 + 1, i * 4 + 1)
        assert sender.send(pcm, start_sample=first)
    raw = dict(id='loss', text='Synthetic final.', start=0.1, end=0.9, speaker='SPEAKER_00', is_user=False)
    before_version, before_segment = count('version', reason), count('segment', reason)
    if reason == 'custom_stt':
        receiver.host.use_custom_stt = True
        receiver._enqueue_stt_segments([raw], provider='custom')
    elif reason == 'multi_channel':
        receiver.host.is_multi_channel = True
        receiver._enqueue_stt_segments([raw])
    else:
        if reason == 'kill_switch':
            monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', 'false')
        elif reason == 'translator_zero_length':
            raw['end'] = raw['start']
        elif reason == 'translator_outside_accepted_sends':
            raw.update(start=5, end=6)
        callback([raw])
    (stored,) = await drain(monkeypatch, receiver)
    assert 'audio_capture_start' not in stored
    assert count('version', reason) == before_version + 1
    assert count('segment', reason) == before_segment + 1
