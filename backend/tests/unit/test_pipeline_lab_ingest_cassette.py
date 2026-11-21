"""Pipeline lab ingest: STT cassette key, store, recorder (ledger + vendor log) and player.

Synthetic audio only; no vendor is reached (the prerecorded entry point is patched).
"""

import json
from unittest import mock

import numpy as np
import pytest

from testing.pipeline_lab.cassette import adapters
from testing.pipeline_lab.cassette.adapters import PrerecordedAdapter, StubAdapter, STTRequest, words_from_prerecorded
from testing.pipeline_lab.cassette.format import Cassette, CassetteKey, Word, load, speaker_turns
from testing.pipeline_lab.cassette.player import CassetteMiss, PlaybackConfig, Player, SpanSource
from testing.pipeline_lab.cassette.recorder import BudgetExceeded, InMemoryLedger, Recorder


def pcm(seconds=2.0, seed=0):
    return np.random.default_rng(seed).normal(0, 2000, int(16000 * seconds)).astype('<i2').tobytes()


def script(request):
    duration = request.audio_seconds
    return [Word(0.1, 0.4, 'alpha', 'SPEAKER_00'), Word(duration - 0.5, duration - 0.2, 'omega', 'SPEAKER_01')]


@pytest.fixture
def root(tmp_path):
    return tmp_path / 'lab'


def test_key_changes_with_each_component_and_not_with_order_of_nothing():
    audio = pcm()
    base = CassetteKey.for_audio(audio, provider='p', model='m', language='en', vocabulary=['Omi', 'x'])
    assert base == CassetteKey.for_audio(audio, provider='p', model='m', language='en', vocabulary=['Omi', 'x'])
    variants = [
        CassetteKey.for_audio(pcm(seed=1), provider='p', model='m', language='en', vocabulary=['Omi', 'x']),
        CassetteKey.for_audio(audio, provider='q', model='m', language='en', vocabulary=['Omi', 'x']),
        CassetteKey.for_audio(audio, provider='p', model='n', language='en', vocabulary=['Omi', 'x']),
        CassetteKey.for_audio(audio, provider='p', model='m', language='de', vocabulary=['Omi', 'x']),
        CassetteKey.for_audio(audio, provider='p', model='m', language='en', vocabulary=['x', 'Omi']),
    ]
    assert len({base.digest, *(v.digest for v in variants)}) == 6
    assert CassetteKey.for_audio(audio, provider='p', model='m', language=None, vocabulary=None).language == 'multi'


def test_cassette_round_trip_and_layout(root):
    audio = pcm()
    key = CassetteKey.for_audio(audio, provider='p', model='m', language='en', vocabulary=[])
    cassette = Cassette(key, 2.0, [Word(0.1, 0.3, 'hi', 'SPEAKER_00')], detected_language='en')
    path = cassette.save(root)
    assert path == root / 'cache' / 'stt_cassette' / key.digest[:2] / f'{key.digest}.json'
    assert oct(path.stat().st_mode & 0o777) == '0o600'
    loaded = load(key, root)
    assert loaded.words == cassette.words and loaded.detected_language == 'en'
    assert json.loads(path.read_text())['segments'][0]['text'] == 'hi'
    body = json.loads(path.read_text())
    body['key']['model'] = 'tampered'
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        load(key, root)


def test_recorder_reserves_logs_and_caches(root):
    adapter = StubAdapter(script, provider='vendor', model='v1', usd_per_hour=3.6)
    ledger = InMemoryLedger(cap_usd=1.0)
    log = root / 'runs' / 'r1' / 'vendor_log.jsonl'
    recorder = Recorder(adapter, ledger, vendor_log=log, root=root, clock=lambda: 1_700_000_000)
    audio = pcm(10)
    first = recorder.ensure(audio, language='en', vocabulary=('Omi',))
    second = recorder.ensure(audio, language='en', vocabulary=('Omi',))
    assert len(adapter.calls) == 1 and (recorder.misses, recorder.hits) == (1, 1)
    assert first.words == second.words and first.usd == pytest.approx(0.01)
    assert ledger.spent == pytest.approx(0.01) and not ledger.held
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows == [
        {
            'at': '2023-11-14T22:13:20Z',
            'vendor': 'vendor',
            'purpose': 'stt_cassette',
            'audio_seconds': 10.0,
            'usd': 0.01,
            'destination': 'local stub (no vendor)',
            'outcome': 'ok',
        }
    ]


def test_cap_refuses_before_any_audio_leaves(root):
    adapter = StubAdapter(script, usd_per_hour=3600)
    recorder = Recorder(adapter, InMemoryLedger(cap_usd=0.5), vendor_log=root / 'v.jsonl', root=root)
    with pytest.raises(BudgetExceeded):
        recorder.ensure(pcm(1), language='en')
    assert adapter.calls == [] and not (root / 'v.jsonl').exists()


def test_failed_call_is_charged_and_logged_but_not_cached(root):
    class Boom(StubAdapter):
        def transcribe(self, request):
            raise TimeoutError('synthetic')

    ledger = InMemoryLedger(cap_usd=1.0)
    recorder = Recorder(Boom(usd_per_hour=36), ledger, vendor_log=root / 'v.jsonl', root=root)
    with pytest.raises(TimeoutError):
        recorder.ensure(pcm(10), language='en')
    assert ledger.spent == pytest.approx(0.1)
    assert json.loads((root / 'v.jsonl').read_text())['outcome'] == 'error'
    assert recorder.key_for(pcm(10), language='en').path(root).exists() is False


def test_player_exact_and_span(root):
    audio = pcm(4)
    recorder = Recorder(
        StubAdapter(script, provider='p', model='m'), InMemoryLedger(1), vendor_log=root / 'v', root=root
    )
    recorded = recorder.ensure(audio, language='en')
    player = Player(PlaybackConfig('p', 'm', 'en'), root=root)
    assert player.get(audio).words == recorded.words
    with pytest.raises(CassetteMiss):
        player.get(pcm(4, seed=9))
    with pytest.raises(CassetteMiss):
        Player(PlaybackConfig('p', 'm', 'de'), root=root).get(audio)
    span = SpanSource(recorded)
    assert [w.text for w in span.words(3.0, 1.0)] == ['omega']
    assert span.words(3.0, 1.0)[0].start == pytest.approx(0.5)
    assert speaker_turns(recorded.words) == [
        {'start': 0.1, 'end': 0.4, 'speaker': 'SPEAKER_00'},
        {'start': 3.5, 'end': 3.8, 'speaker': 'SPEAKER_01'},
    ]


def test_prerecorded_adapter_calls_product_entry_point_with_wav(monkeypatch):
    calls = []

    def fake(audio_bytes, **kwargs):
        calls.append((audio_bytes[:4], kwargs))
        raw = [{'timestamp': [0.2, 0.5], 'speaker': 'SPEAKER_00', 'text': 'hello'}]
        return (raw, 'en'), 'modulate', 'velma-2'

    monkeypatch.setattr('utils.stt.pre_recorded.prerecorded_from_bytes', fake)
    adapter = PrerecordedAdapter(provider='modulate', model='velma-2', estimate=lambda request: 0.0)
    response = adapter.transcribe(STTRequest(pcm(1), 'multi', ('Omi',)))
    assert calls[0][0] == b'RIFF'
    assert calls[0][1]['keywords'] == ['Omi'] and calls[0][1]['return_provider'] is True
    assert response.words == [Word(0.2, 0.5, 'hello', 'SPEAKER_00')] and response.detected_language == 'en'

    monkeypatch.setattr(
        'utils.stt.pre_recorded.prerecorded_from_bytes', lambda *a, **k: (([], 'en'), 'soniox', 'stt-async')
    )
    with pytest.raises(RuntimeError, match='different provider'):
        adapter.transcribe(STTRequest(pcm(1), 'multi'))


def test_card_estimate_reads_repo_price_file():
    hour = adapters.modulate_card_usd(3600, with_lid=False)
    assert 0 < hour < adapters.modulate_card_usd(3600, with_lid=True)
    assert words_from_prerecorded([{'timestamp': [1, None], 'text': 'x', 'speaker': None}]) == [Word(1.0, 1.0, 'x')]


def test_no_network_reachable_from_stub_path(root):
    # The recorder path with a stub must not construct any HTTP client.
    with mock.patch('httpx.Client', side_effect=AssertionError('network')):
        Recorder(StubAdapter(script), InMemoryLedger(1), vendor_log=root / 'v', root=root).ensure(pcm(1), language='en')
