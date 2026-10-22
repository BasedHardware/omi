import asyncio
import logging
from types import SimpleNamespace

from utils.stt import vocabulary as vocab
from utils.stt import soniox
from config import refactor_modes


def test_sources_are_interleaved_deduplicated_and_frequent():
    terms = vocab.build_terms(
        [{'name': 'Riley Vale'}],
        [{'content': 'QuasarTool supports jobs.'}, {'content': 'QuasarTool supports queues.'}],
        [{'name': 'OrbitApp'}],
        [{'spelling': 'micro1'}],
    )
    assert terms == ['Riley Vale', 'OrbitApp', 'micro1', 'QuasarTool']
    assert 'Transient' not in vocab.build_terms([], [{'content': 'Transient appears once.'}], [])


def test_limits_and_pii_shaped_terms():
    terms = vocab.bounded_terms(
        [
            'person@example.com',
            'https://example.com',
            'A' * 61,
            'Orbit',
            'orbit',
            '123',
            *[f'Name{i}' for i in range(150)],
        ]
    )
    assert terms[0] == 'Orbit'
    assert len(terms) == vocab.MAX_TERMS
    assert sum(map(len, terms)) <= vocab.MAX_CHARS


def test_cache_ttl_capacity_and_user_partition(monkeypatch):
    vocab._cache.clear()
    now = [100.0]
    calls = []
    monkeypatch.setattr(vocab.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(vocab, '_sources', lambda uid: calls.append(uid) or ['Term' + uid])
    assert vocab.cached_terms('a') == ['Terma']
    assert vocab.cached_terms('b') == ['Termb']
    assert vocab.cached_terms('a') == ['Terma']
    assert len(calls) == 2
    now[0] += vocab.TTL + 1
    vocab.cached_terms('a')
    assert len(calls) == 3
    for i in range(vocab.MAX_USERS + 5):
        vocab.cached_terms(str(i))
    assert len(vocab._cache) <= vocab.MAX_USERS
    vocab._cache.clear()


def test_real_soniox_config_shadow_serve_and_off_preserve_language(monkeypatch, caplog):
    configs = []
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-key')
    monkeypatch.setenv('SONIOX_IDLE_CLOSE_SECONDS', '0')
    monkeypatch.setattr(vocab, 'cached_terms', lambda *_: ['PrivateSpelling'])

    async def opened(config, *args):
        configs.append(dict(config))
        return SimpleNamespace()

    monkeypatch.setattr(soniox, '_open_soniox', opened)

    async def run():
        await soniox.process_audio_soniox(lambda _: None, 16000, 'en', uid='synthetic-owner')
        monkeypatch.setenv(vocab.FLAG, 'serve')
        await soniox.process_audio_soniox(lambda _: None, 16000, 'en', uid='synthetic-owner')
        monkeypatch.setenv(vocab.FLAG, 'off')
        await soniox.process_audio_soniox(lambda _: None, 16000, 'en', uid='synthetic-owner')

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert 'context' not in configs[0] and 'context' not in configs[2]
    assert configs[1]['context'] == {'terms': ['PrivateSpelling']}
    assert all(config['language_hints'] == configs[0]['language_hints'] for config in configs)
    assert 'PrivateSpelling' not in caplog.text and 'synthetic-owner' not in caplog.text


def test_invalid_flags_keep_shadow(monkeypatch):
    for name in ('CALLS_RECAP_MODE', 'ACTION_ITEMS_V2_MODE', 'STT_VOCAB_MODE'):
        monkeypatch.setenv(name, 'srve')
        assert refactor_modes.mode(name) == 'shadow'
        assert not refactor_modes.serving_for(name, 'synthetic-owner')
