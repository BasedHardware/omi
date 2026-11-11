"""Flag metamorphism through provider adapters, receiver, ticks and StrictFirestore."""

import copy
import random
from types import SimpleNamespace

import pytest

from routers.listen.receiver import _RecordingSTTSocket
from routers.listen.stt_callbacks import build_stt_callbacks
from tests.unit.test_audio_timeline_round3 import RATE, T0
from tests.unit.test_capture_window_merge_union_r5 import accept, harness, known, raw, tick
from utils.stt import streaming
from utils.stt.soniox import SafeSonioxSocket

PROVIDERS = ['modulate', 'soniox', 'deepgram']
TITLES = [
    ('We met Capt.', 'Smith at noon.'),
    ('We climbed Mt.', 'Everest last year.'),
    ('Vimos a Dra.', 'García esta mañana.'),
    ('We selected No.', 'V for victory.'),
    ('We met Dr.', 'Smith arrived today.'),
]


def without_windows(rows):
    # Compare every persisted field, including ID, speaker scope, text and timing.
    return [{k: v for k, v in row.items() if k not in ('audio_capture_start', 'audio_capture_end')} for row in rows]


async def adapter(monkeypatch, provider, callback):
    """Actual parser methods; no constructors, clients, sockets or network IO."""
    sid = None

    def emit(segments):
        for i, segment in enumerate(segments):
            segment['id'] = sid if i == 0 else f'{sid}-{i}'
        callback(segments)

    if provider == 'deepgram':
        captured = {}

        async def local_connect(on_message, *args, **kwargs):
            captured['on_message'] = on_message
            return None  # Extract the real callback without a socket/keepalive thread.

        monkeypatch.setattr(streaming, 'connect_to_deepgram_with_backoff', local_connect)
        assert await streaming.process_audio_dg(emit, 'en', RATE, 1) is None
    else:
        cls = SafeSonioxSocket if provider == 'soniox' else streaming.SafeModulateSocket
        parser = object.__new__(cls)
        parser._preseconds = 0
        parser._stream_transcript = emit
        if provider == 'soniox':
            parser._pending_segment = None
        else:
            parser._observe_served = lambda: None
            parser._prev_partial_text = ''
            parser._prev_partial_word_count = 0
            parser._prev_partial_start_ms = 0

    def deliver(segment, interim=False):
        nonlocal sid
        sid = segment['id']
        text, start, end = segment['text'], segment['start'], segment['end']
        speaker = int(segment['speaker'].split('_')[-1])
        if provider == 'soniox':
            parser._handle_tokens(
                [
                    dict(
                        text=text + ' ',
                        start_ms=round(start * 1000),
                        end_ms=round(end * 1000),
                        speaker=speaker + 1,
                        is_final=not interim,
                    )
                ]
            )
        elif provider == 'modulate':
            message = dict(
                text=text, start_ms=round(start * 1000), duration_ms=round((end - start) * 1000), speaker=speaker + 1
            )
            if interim:
                parser._handle_partial_utterance(message)
            else:
                parser._handle_utterance(message)
        else:
            # Deepgram is subscribed with interim_results=False. An empty event
            # still exercises the real callback's no-transcript path; previews
            # never enter its final-only subscription.
            words = [] if interim else [SimpleNamespace(punctuated_word=text, start=start, end=end, speaker=speaker)]
            result = SimpleNamespace(
                channel=SimpleNamespace(alternatives=[SimpleNamespace(transcript='' if interim else text, words=words)])
            )
            captured['on_message'](None, result)

    return deliver


@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('known_first', [False, True])
@pytest.mark.parametrize('left,right', TITLES + [('Lost sentence.', 'Next sentence.')])
async def test_mixed_windows_always_use_exact_legacy_rows(monkeypatch, provider, known_first, left, right):
    snapshots = []
    for enabled in (False, True):
        receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, provider)
        receiver.speaker_provider_epoch._connection_scope = 'fixed'
        if known_first:
            accept(receiver, sender, 0, 1.8)
        callback([raw('a', left, 0.1, 1.5)])
        await tick(receiver, processor, store)
        if not known_first:
            accept(receiver, sender, 0, 4)
        callback([raw('b', right, 2, 3.5)])
        snapshots.append(await tick(receiver, processor, store))
    assert snapshots[0] == snapshots[1]
    assert [row['text'] for row in snapshots[1]] == [left + ' ' + right]
    assert known(snapshots[1]) == 0


@pytest.mark.parametrize('provider', PROVIDERS)
@pytest.mark.parametrize('seed', range(30))
async def test_random_provider_stream_changes_only_proven_windows(monkeypatch, provider, seed):
    histories = []
    proofs = []
    for enabled in (False, True):
        rng = random.Random(seed)
        receiver, callback, epoch, sender, processor, store = harness(monkeypatch, enabled, provider)
        receiver.speaker_provider_epoch._connection_scope = 'epoch-0'
        deliver = await adapter(monkeypatch, provider, callback)
        history, witnesses, witness_history = [], [], []

        async def commit(segment, preview=True):
            batch = segment if isinstance(segment, list) else [segment]
            if preview:
                for piece in batch:
                    deliver(piece, interim=True)
                    assert not receiver.collected
            for piece in batch:
                deliver(piece)
            for incoming in receiver.collected:
                if incoming.get('_capture_merge_proof'):
                    witnesses.append(incoming['_capture_merge_proof'])
            history.append(copy.deepcopy(await tick(receiver, processor, store)))
            witness_history.append(list(witnesses))

        # Force every reviewer title, in both unknown directions, across seeds.
        left, right = TITLES[seed % len(TITLES)]
        if seed % 2:
            accept(receiver, sender, 0, 1.8)
        await commit(raw('a', left, 0.1, 1.5))
        if not seed % 2:
            accept(receiver, sender, 0, 4)
        await commit(raw('b', right, 2, 3.5))

        async def reconnect(index):
            nonlocal callback, epoch, sender, deliver
            offset = receiver.capture_timeline.next_sample / RATE

            class RebaseGate:
                def remap_segments(self, segments):
                    for segment in segments:
                        segment['start'] += offset
                        segment['end'] += offset

            receiver.vad_gate = RebaseGate()
            callback, _, epoch = build_stt_callbacks(receiver)
            receiver.speaker_provider_epoch._connection_scope = f'epoch-{index}'
            sender = _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **k: True), epoch)
            deliver = await adapter(monkeypatch, provider, callback)

        await reconnect(1)
        wall = receiver.capture_timeline.next_sample / RATE
        accept(receiver, sender, wall, 4)
        wall += 4
        # Every stream has a positive-gap known pair with received silence.
        await commit(raw('c', 'Received words.', 0.1, 1.5))
        await commit(raw('d', 'More received words.', 2, 3.5))
        for index in range(16):
            if index == 8:
                await reconnect(2)
            seconds = rng.choice([0.5, 1, 2, 4])
            mode = rng.choice(['accepted', 'accepted', 'failed', 'missing', 'hiatus'])
            wall += seconds + (5 if mode == 'hiatus' else 0)
            first = receiver.capture_timeline.next_sample / RATE
            if mode == 'missing':
                receiver.capture_timeline.accept(b'\0\0' * round(seconds * RATE), T0 + wall, wall)
            else:
                transport = (
                    sender
                    if mode != 'failed'
                    else _RecordingSTTSocket(SimpleNamespace(send=lambda *a, **k: False), epoch)
                )
                accept(receiver, transport, first, seconds, wall_end=wall, success=mode != 'failed')
            tail = (epoch.send_map.last_provider_sample or 0) / RATE
            start = max(0, round(tail - rng.choice([0.4, 0.8, 1.6]), 3))
            end = round(start + rng.choice([0, 0.3, 1.2, 2]), 3)
            text = rng.choice(
                [
                    left,
                    right,
                    'Next sentence.',
                    'continuing words',
                    'J. R. R.',
                    '3.5',
                    'wait...',
                    'omi.me.',
                    'Next .',
                    '下一句话。',
                    'A long unfinished phrase',
                ]
            )
            segment = raw(f'r-{index}', text, start, end, rng.choice(['SPEAKER_00', 'SPEAKER_01']))
            batch = [segment]
            if rng.getrandbits(1):
                batch.append(
                    raw(
                        f'r-{index}-extra',
                        rng.choice(['Smith arrived.', 'More words.', 'next words']),
                        end + 0.1,
                        end + 0.4,
                        segment['speaker'],
                    )
                )
            await commit(batch, preview=bool(rng.getrandbits(1)))
        histories.append(history)
        proofs.append(witness_history)

    off, on = histories
    assert len(off) == len(on) == 20
    changed = 0
    for off_rows, on_rows, witnesses in zip(off, on, proofs[1]):
        assert without_windows(off_rows) == without_windows(on_rows), (provider, seed)
        for old, new in zip(off_rows, on_rows):
            old_window = (old.get('audio_capture_start'), old.get('audio_capture_end'))
            new_window = (new.get('audio_capture_start'), new.get('audio_capture_end'))
            if old_window == new_window:
                continue
            changed += 1
            assert old_window == (None, None)
            assert new_window[0] < new_window[1]
            # A single actual receiver snapshot must cover the entire retained
            # union. Never infer coverage by stitching disconnected witnesses.
            assert any(p.accepted_run[0] <= new_window[0] < new_window[1] <= p.accepted_run[1] for p in witnesses)
    assert changed > 0  # The property cannot pass with recovery accidentally disabled.
