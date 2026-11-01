import asyncio
import logging
from types import SimpleNamespace

from utils.stt import vocabulary as vocab
from utils.stt import soniox
from utils.memory.memory_service import MemoryService
from config import refactor_modes
from routers.listen import receiver as listen
from tests.unit.test_soniox_capture_axis_r10 import managed, close


def test_sources_are_interleaved_deduplicated_and_frequent():
    terms = vocab.build_terms(
        [{'name': 'Riley Vale'}],
        [{'content': 'QuasarTool supports jobs.'}, {'content': 'QuasarTool supports queues.'}],
        [{'name': 'OrbitApp'}],
        [{'spelling': 'micro1'}],
    )
    assert terms == ['Riley Vale', 'OrbitApp', 'micro1', 'QuasarTool']
    assert 'Transient' not in vocab.build_terms([], [{'content': 'Transient appears once.'}], [])
    assert 'micro1' in vocab.build_terms([], [{'content': 'Uses micro1.'}, {'content': 'Prefers micro1.'}], [])


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


def test_source_fill_concurrency_is_bounded(monkeypatch):
    vocab._cache.clear()
    calls = []
    monkeypatch.setattr(vocab, '_sources', lambda uid: calls.append(uid) or [])
    for _ in range(4):
        assert vocab._fills.acquire(blocking=False)
    try:
        assert vocab.cached_terms('synthetic-owner') == []
        assert calls == []
    finally:
        for _ in range(4):
            vocab._fills.release()


def test_sources_use_the_memory_authority_and_bounded_reads(monkeypatch):
    from database import _client, person_aliases, redis_db, dream_store
    from utils.memory.memory_service import MemoryService

    received = []
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(person_aliases, 'list_people', lambda client, uid, **kw: received.append(kw) or [])
    monkeypatch.setattr(redis_db, 'get_enabled_apps', lambda *_: [])
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *_: [])

    def read(self, uid, **kwargs):
        received.append(kwargs)
        return []

    monkeypatch.setattr(MemoryService, 'read', read)
    assert vocab._sources('synthetic-owner') == []
    assert received[0] == {'limit': 200}
    assert received[1]['limit'] == 80
    assert received[1]['budget'].remaining_documents == 240


def test_shadow_source_work_cannot_delay_the_soniox_dial(monkeypatch):
    monkeypatch.setenv(vocab.STT_VOCAB_SHADOW_PERCENT_ENV, '100')
    pending = []
    from utils import executors

    monkeypatch.setattr(executors, 'start_background_task', lambda coroutine, **kw: pending.append(coroutine))
    config = {'language_hints': ['en']}
    asyncio.run(vocab.apply_context(config, 'synthetic-owner'))
    assert config == {'language_hints': ['en']}
    assert len(pending) == 1
    for coroutine in pending:
        coroutine.close()


def test_vocabulary_identity_is_explicit_and_never_borrowed_from_byok(monkeypatch):
    from utils import byok

    monkeypatch.setenv(vocab.FLAG, 'serve')
    monkeypatch.setattr(byok, 'get_byok_uid', lambda: (_ for _ in ()).throw(AssertionError('ambient identity read')))
    seen = []
    monkeypatch.setattr(vocab, 'cached_terms', lambda uid: seen.append(uid) or ['ExplicitTerm'])

    async def run():
        missing = {}
        await vocab.apply_context(missing)
        assert missing == {}
        config = {}
        await vocab.apply_context(config, 'synthetic-explicit-owner')
        assert config['context']['terms'] == ['ExplicitTerm']

    asyncio.run(run())
    assert seen == ['synthetic-explicit-owner']


def test_vocabulary_parity_label_reports_found_terms(monkeypatch):
    from unittest.mock import Mock

    observed = Mock()
    monkeypatch.setattr(vocab, 'observe', observed)
    monkeypatch.setattr(vocab, 'cached_terms', lambda *_: ['Spelling'])
    assert asyncio.run(vocab._load_terms('synthetic-owner')) == ['Spelling']
    observed.assert_called_once_with('stt_vocab', 'agree', size=1)


def test_legacy_soniox_initial_and_reconnect_pass_authenticated_identity(monkeypatch):
    from unittest.mock import AsyncMock
    from utils.stt.streaming import STTService

    monkeypatch.setattr(listen, 'managed_chain_enabled', lambda *_: False)
    monkeypatch.setattr(listen, 'modulate_is_configured_fallback', lambda *_: False)
    monkeypatch.setattr(listen, 'deepgram_fallback_model', lambda *_: None)
    opened = AsyncMock(return_value=object())
    monkeypatch.setattr(listen, 'process_audio_soniox', opened)

    async def fallback(**kwargs):
        return await kwargs['connect_primary'](), STTService.soniox

    monkeypatch.setattr(listen, 'connect_stt_socket_with_fallback', fallback)
    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic-authenticated-owner'),
        vocabulary=[],
        stt_service=STTService.soniox,
        stt_language='en',
        language_profile=None,
    )
    receiver = SimpleNamespace(host=host, recovery=None, soniox_idle_budget=None)

    async def run():
        for same_provider in (False, True):
            await listen.ListenReceiver._connect_stt_socket(
                receiver, lambda _: None, 16000, same_provider=same_provider
            )

    asyncio.run(run())
    assert opened.await_count == 2
    assert all(call.kwargs['uid'] == host.request.uid for call in opened.await_args_list)


def test_managed_soniox_config_uses_authenticated_identity(monkeypatch):
    import json

    monkeypatch.setenv(vocab.FLAG, 'serve')
    seen = []
    monkeypatch.setattr(vocab, 'cached_terms', lambda uid: seen.append(uid) or ['ManagedTerm'])

    async def run():
        receiver, _, _, _, leg, wire, _ = await managed(monkeypatch, False)
        try:
            assert seen == [receiver.host.request.uid]
            config = json.loads(wire.sent[0])
            assert config['context']['terms'] == ['ManagedTerm']
            assert config['language_hints'] == ['en']
        finally:
            await close(leg)

    asyncio.run(run())
