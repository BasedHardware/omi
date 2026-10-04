"""Receiver -> transcript ticks -> StrictFirestore; no external replay or clients."""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from database import conversations as db
from routers.listen.receiver import _RecordingSTTSocket
from routers.listen.stt_callbacks import build_stt_callbacks
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_timeline_round3 import _processor, _seed_row, _async_noop, RATE, T0, UID
from tests.unit.test_live_capture_retention import setup
from utils.manual_speaker_assignments import merge_live_segments
from utils.stt.soniox import SafeSonioxSocket
from models.capture_window_proof import CaptureWindowProof

FLAG = 'LIVE_CAPTURE_WINDOW_MERGE_UNION'


def raw(sid, text, start, end, speaker='SPEAKER_00'):
    return dict(id=sid, text=text, start=start, end=end, speaker=speaker, is_user=False)


def harness(monkeypatch, enabled, provider='modulate'):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', 'false')
    receiver, callback, epoch, sender = setup(monkeypatch, False, provider)
    store = StrictFirestore()
    _seed_row(store, 'c', started_at=datetime.fromtimestamp(T0, tz=timezone.utc))
    processor, _ = _processor(monkeypatch, store, current='c')
    processor.host.use_custom_stt = processor.host.is_multi_channel = False
    processor.host.state.active = False
    processor.host.wait = lambda seconds: asyncio.sleep(0, result=False)
    processor.host.speakers.tasks = []
    processor.host.speakers.drain = _async_noop
    processor.flush_speaker_assignments = _async_noop
    processor._deliver_live_updates = _async_noop
    processor._speaker_detection = _async_noop
    return receiver, callback, epoch, sender, processor, store


def accept(receiver, sender, first, seconds, wall_end=None, success=True):
    pcm = b'\0\0' * round(seconds * RATE)
    wall = first + seconds if wall_end is None else wall_end
    start, _, _ = receiver.capture_timeline.accept(pcm, T0 + wall, wall)
    assert sender.send(pcm, start_sample=start) is success


async def tick(receiver, processor, store):
    processor.segment_buffer.extend(receiver.collected)
    receiver.collected.clear()
    await processor.process_loop()
    row = store.rows[('users', UID, 'conversations', 'c')]
    assert '_capture_merge_proof' not in str(row)
    return db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], row.get('transcript_segments_compressed', False)
    )


def known(rows):
    return sum('audio_capture_start' in row for row in rows)


@pytest.mark.parametrize('provider', ['modulate', 'soniox', 'deepgram'])
@pytest.mark.parametrize('one_batch', [True, False])
@pytest.mark.parametrize('enabled', [False, True])
async def test_received_silence_unions_words_without_new_rows(monkeypatch, provider, one_batch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, provider)
    accept(receiver, sender, 0, 1)
    a, b = raw('a', 'Hello', 0.1, 0.4), raw('b', 'world.', 1.2, 1.6)
    if not one_batch:
        callback([a])
        assert known(await tick(receiver, processor, store)) == 1
    # The newer proof snapshot must expand beyond the older accepted-run end.
    accept(receiver, sender, 1, 1)
    callback([a, b] if one_batch else [b])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['Hello world.']
    assert [s['id'] for s in rows] == ['a']
    assert known(rows) == int(enabled)
    if enabled:
        assert (rows[0]['audio_capture_start'], rows[0]['audio_capture_end']) == (T0 + 0.1, T0 + 1.6)
        assert len(processor._capture_merge_tails['c']) == 1


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('loss', ['failed', 'missing', 'wall', 'reconnect', 'stale_snapshot', 'restart'])
async def test_positive_gap_requires_complete_same_epoch_send_proof(monkeypatch, enabled, loss):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    accept(receiver, sender, 0, 1)
    callback([raw('a', 'Hello', 0.1, 0.4)])
    await tick(receiver, processor, store)
    if loss == 'stale_snapshot':
        # A concurrent transaction changed this tail's window; an old local
        # proof cannot be attached just because its surviving ID matches.
        row = store.rows[('users', UID, 'conversations', 'c')]
        segments = db._decode_transcript_segments_strict(
            UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
        )
        segments[0]['audio_capture_start'] = T0 - 1
        row['transcript_segments'] = segments
        row['transcript_segments_compressed'] = False
    if loss == 'restart':
        processor._capture_merge_tails = {}
    if loss == 'missing':
        receiver.capture_timeline.accept(b'\0\0' * RATE, T0 + 2, 2)
    if loss == 'failed':
        failed = _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **k: False), epoch)
        accept(receiver, failed, 1, 1, success=False)
    if loss == 'reconnect':
        _, callback, epoch = build_stt_callbacks(receiver)
        sender = _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **k: True), epoch)
    accept(receiver, sender, 2 if loss in ('failed', 'missing') else 1, 1, wall_end=7 if loss == 'wall' else None)
    callback([raw('b', 'world.', 0.2 if loss == 'reconnect' else 1.2, 0.6 if loss == 'reconnect' else 1.6)])
    rows = await tick(receiver, processor, store)
    assert known(rows) == (2 if loss == 'reconnect' else 0)
    assert len(rows) == (2 if loss == 'reconnect' else 1)


@pytest.mark.parametrize('enabled', [False, True])
async def test_unknown_absorption_keeps_legacy_rows(monkeypatch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    accept(receiver, sender, 0, 5)
    callback([raw('unknown', 'Lost', 0, 0)])
    await tick(receiver, processor, store)
    for i, text in enumerate(['old', 'sentence.', 'Now', 'we', 'have', 'audio.']):
        callback([raw(str(i), text, 0.2 + i * 0.5, 0.5 + i * 0.5)])
        rows = await tick(receiver, processor, store)
    # Unknown contributors retain exact legacy absorption across punctuation.
    assert [s['text'] for s in rows] == ['Lost old sentence. Now we have audio.']
    assert known(rows) == 0


@pytest.mark.parametrize('ender', ['.', '!', '?', '。', '！', '？', '؟', '۔', '।', '॥'])
async def test_unknown_sentence_boundary_locales(monkeypatch, ender):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    callback([raw('unknown', 'Lost sentence' + ender, 0.1, 1.5)])
    await tick(receiver, processor, store)
    accept(receiver, sender, 0, 4)
    callback([raw('b', 'Next sentence' + ender, 2, 3.5)])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['Lost sentence' + ender + ' Next sentence' + ender]
    assert known(rows) == 0


@pytest.mark.parametrize('enabled', [False, True])
async def test_partial_speaker_sentence_repair_still_abstains(monkeypatch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    accept(receiver, sender, 0, 4)
    callback([raw('a', 'A long unfinished phrase', 0.1, 1), raw('b', 'yes. Another sentence.', 1.2, 2, 'SPEAKER_01')])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['A long unfinished phrase yes.', 'Another sentence.']
    assert known(rows) == 0


async def test_attribution_of_recovered_union_is_known_window(monkeypatch):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    accept(receiver, sender, 0, 2)

    def counters():
        return {
            tuple(sorted(s.labels.items())): s.value
            for f in REGISTRY.collect()
            for s in f.samples
            if s.name == 'omi_live_audio_capture_attribution_total'
        }

    before = counters()
    callback([raw('a', 'Hello', 0.1, 0.4), raw('b', 'world.', 0.6, 0.9)])
    assert known(await tick(receiver, processor, store)) == 1
    after = counters()
    assert (
        after[tuple(sorted(dict(population='segment', reason='known_window').items()))]
        - before.get(tuple(sorted(dict(population='segment', reason='known_window').items())), 0)
        == 1
    )
    assert all(after.get(k, 0) == v for k, v in before.items() if dict(k)['reason'] != 'known_window')


@pytest.mark.parametrize('provider', ['modulate', 'soniox', 'deepgram'])
async def test_simulated_word_stream_coverage_and_rows(monkeypatch, provider):
    report = {}
    for enabled in (False, True):
        receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, provider)
        for sentence in range(12):
            if sentence in (4, 8):
                offset = receiver.capture_timeline.next_sample / RATE

                class RebaseGate:
                    def remap_segments(self, segments):
                        for segment in segments:
                            segment['start'] += offset
                            segment['end'] += offset

                receiver.vad_gate = RebaseGate()
                callback, _, epoch = build_stt_callbacks(receiver)
                sender = _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **k: True), epoch)
            p = (epoch.send_map.last_provider_sample or 0) / RATE
            # Four seconds of received PCM per six-word sentence; pauses are
            # received silence. One callback before send acceptance is unknown.
            if sentence == 2:
                callback([raw('2-0', 'Unknown', p + 0.1, p + 0.4)])
                await tick(receiver, processor, store)
            accept(receiver, sender, sentence * 4, 4)
            words = ['We', 'heard', 'these', 'six', 'spoken', 'words.']
            if sentence == 2:
                words[0] = 'Unknown'
            for i, word in enumerate(words):
                if sentence == 2 and i == 0:
                    continue
                if provider == 'soniox':
                    adapter = object.__new__(SafeSonioxSocket)
                    adapter._pending_segment = None
                    adapter._preseconds = 0

                    def emit(segments):
                        for segment in segments:
                            segment['id'] = f'{sentence}-{i}'
                        callback(segments)

                    adapter._stream_transcript = emit
                    token = dict(
                        text=word + ' ',
                        start_ms=round((p + i * 0.6 + 0.1) * 1000),
                        end_ms=round((p + i * 0.6 + 0.4) * 1000),
                        speaker=1,
                    )
                    adapter._handle_tokens([dict(token, is_final=False)])
                    assert not receiver.collected
                    adapter._handle_tokens([dict(token, is_final=True)])
                else:
                    callback([raw(f'{sentence}-{i}', word, p + i * 0.6 + 0.1, p + i * 0.6 + 0.4)])
                # Providers emit committed finals; interims do not enter the
                # receiver buffer (adapter-finality tests cover this upstream).
                rows = await tick(receiver, processor, store)
        report['on' if enabled else 'off'] = dict(
            rows=len(rows),
            known_window=known(rows),
            known_words=sum(len(s['text'].split()) for s in rows if 'audio_capture_start' in s),
            words=sum(len(s['text'].split()) for s in rows),
            texts=[s['text'] for s in rows],
            durations=[s['end'] - s['start'] for s in rows],
        )
    assert report['on']['words'] == report['off']['words'] == 72
    assert report['on']['known_window'] > report['off']['known_window']
    assert report['on']['rows'] == report['off']['rows']
    assert report['on']['texts'] == report['off']['texts']
    assert report['on']['durations'] == report['off']['durations']
    assert all(len(t.split()) >= 6 for t in report['on']['texts'])
    assert all(d >= 1 for d in report['on']['durations'])
    if os.getenv('CAPTURE_R5_SIMULATION_OUTPUT'):
        Path(os.environ['CAPTURE_R5_SIMULATION_OUTPUT'] + '.' + provider + '.json').write_text(
            json.dumps(report, indent=2) + '\n'
        )


@pytest.mark.parametrize('enabled', [False, True])
def test_same_speaker_scope_cannot_hide_a_new_send_epoch(monkeypatch, enabled):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    a = dict(raw('a', 'Hello', 0, 0.4), audio_capture_start=T0, audio_capture_end=T0 + 0.4)
    b = dict(raw('b', 'world.', 0.6, 1), audio_capture_start=T0 + 0.6, audio_capture_end=T0 + 1)
    proofs = {
        'a': CaptureWindowProof('old', (T0, T0 + 0.4), (T0, T0 + 2)),
        'b': CaptureWindowProof('new', (T0 + 0.6, T0 + 1), (T0, T0 + 2)),
    }
    result = merge_live_segments([a], [b], {}, capture_proofs=proofs)
    assert [s['text'] for s in result.segments] == ['Hello world.']
    assert known(result.segments) == 0
    assert result.capture_reasons['a'] == 'merge_gap'
    assert result.capture_proofs == {}


@pytest.mark.parametrize('enabled', [False, True])
async def test_zero_length_unknown_is_not_replaced_by_duplicate_id(monkeypatch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    accept(receiver, sender, 0, 2)
    callback([raw('a', 'Lost text.', 0, 0)])
    await tick(receiver, processor, store)
    callback([raw('a', 'Changed text.', 0.1, 0.4), raw('b', 'Next sentence.', 0.6, 1)])
    rows = await tick(receiver, processor, store)
    assert 'Changed' not in ' '.join(s['text'] for s in rows)
    assert rows[0]['text'] == 'Lost text.'
    # The durable replay receipt takes precedence over grouping on both paths.
    assert [s['id'] for s in rows] == ['a', 'b']
    assert known(rows) == 1


async def test_private_proof_cap_and_runtime_disable(monkeypatch):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    accept(receiver, sender, 0, 2)
    # Synthetic old conversation entries exercise the session cap without
    # constructing clients, extra clocks or retaining provider connections.
    processor._capture_merge_tails = {str(i): {} for i in range(40)}
    callback([raw('a', 'Hello', 0.1, 0.4)])
    await tick(receiver, processor, store)
    assert len(processor._capture_merge_tails) == 32
    monkeypatch.setenv(FLAG, 'false')
    callback([raw('b', 'world.', 0.6, 1)])
    assert known(await tick(receiver, processor, store)) == 0
    assert processor._capture_merge_tails == {}


@pytest.mark.parametrize('end', [1.0, 1.1])
async def test_half_open_exclusive_anchor_never_authorizes_hiatus_union(monkeypatch, end):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    accept(receiver, sender, 0, 1)
    accept(receiver, sender, 1, 1, wall_end=7)
    callback([raw('a', 'Hello', 0.1, end), raw('b', 'world.', 1.2, 1.6)])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['Hello world.']
    assert known(rows) == 0


@pytest.mark.parametrize(
    'value,enabled',
    [
        (None, False),
        ('', False),
        ('false', False),
        ('0', False),
        ('garbage', False),
        ('true', True),
        ('1', True),
        ('yes', True),
        ('on', True),
        (' TRUE ', True),
    ],
)
def test_union_default_off_parser(monkeypatch, value, enabled):
    from config.audio_timeline import live_capture_window_merge_union_enabled

    if value is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, value)
    assert live_capture_window_merge_union_enabled() == enabled


async def test_proof_is_absent_from_model_storage_and_client_projection(monkeypatch):
    from models.transcript_segment import TranscriptSegment

    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, True)
    accept(receiver, sender, 0, 2)
    callback([raw('a', 'Hello', 0.1, 0.4)])
    (incoming,) = receiver.collected
    proof = incoming['_capture_merge_proof']
    segment = TranscriptSegment(**raw('a', 'Hello', 0.1, 0.4), audio_capture_start=T0 + 0.1, audio_capture_end=T0 + 0.4)
    segment.capture_merge_proof = proof
    for payload in (segment.model_dump(), segment.model_dump(mode='json')):
        assert '_capture_merge_proof' not in payload
        assert 'accepted_run' not in payload and 'epoch' not in payload
    assert 'audio_capture_start' not in segment.model_dump(mode='json')
    assert known(await tick(receiver, processor, store)) == 1


@pytest.mark.parametrize('enabled', [False, True])
async def test_first_gap_becomes_unknown_side_inside_one_provider_batch(monkeypatch, enabled):
    receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled)
    accept(receiver, sender, 0, 2)

    def value(reason):
        return sum(
            s.value
            for f in REGISTRY.collect()
            for s in f.samples
            if s.name == 'omi_live_audio_capture_attribution_total'
            and s.labels == dict(population='segment', reason=reason)
        )

    reason = 'known_window' if enabled else 'merge_unknown_side'
    before = value(reason)
    callback([raw('a', 'We', 0.1, 0.4), raw('b', 'heard', 0.6, 0.9), raw('c', 'audio.', 1.1, 1.4)])
    rows = await tick(receiver, processor, store)
    assert [s['text'] for s in rows] == ['We heard audio.']
    assert known(rows) == int(enabled)
    assert value(reason) == before + 1
