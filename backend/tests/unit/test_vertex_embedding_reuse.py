"""Replay real Vertex adapter requests against a synthetic wire corpus."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from llm_gateway.gateway.vertex_embedding_cache import EmbeddingVectorCache, embedding_key, INPUTS, CHARACTERS

CORPUS = json.loads((Path(__file__).parent / 'fixtures/vertex_embedding_reuse.json').read_text())
MODEL = ProviderRef(provider='gemini', model='gemini-embedding-001')


async def token():
    return 'fixture-token'


def credentials(owner='fixture-owner', tenant='fixture-tenant'):
    return build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid=owner, tenant_id=tenant))


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'fixture-project')
    monkeypatch.delenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', raising=False)


async def embed(provider, text, *, owner='fixture-owner', tenant='fixture-tenant', **kwargs):
    return await provider.create_embedding(
        {'input': text, **kwargs}, provider_ref=MODEL, credentials=credentials(owner, tenant), timeout_ms=10_000
    )


@pytest.mark.asyncio
async def test_fixed_corpus_has_identical_vectors_order_and_shape_with_fewer_provider_calls(monkeypatch):
    by_text = {item['text']: item['vector'] for item in CORPUS['documents']}
    calls = []

    def handler(request):
        instance = json.loads(request.content)['instances'][0]
        calls.append(instance)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': by_text[instance['content']]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        legacy = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        trimmed = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        expected = []
        monkeypatch.setenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', 'false')
        for batch in CORPUS['batches']:
            texts = [CORPUS['documents'][index]['text'] for index in batch]
            expected.append((await embed(legacy, texts, task_type='RETRIEVAL_DOCUMENT', title='Pilot')).response)
        assert len(calls) == 9
        calls.clear()
        monkeypatch.delenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', raising=False)
        actual = []
        for batch in CORPUS['batches']:
            texts = [CORPUS['documents'][index]['text'] for index in batch]
            result = await embed(trimmed, texts, task_type='RETRIEVAL_DOCUMENT', title='Pilot')
            actual.append(result.response)
            assert result.accounting.usage is None  # No invented tokens or provider charges on a hit.
        assert actual == expected
        assert len(calls) == 3
        assert all(call['task_type'] == 'RETRIEVAL_DOCUMENT' and call['title'] == 'Pilot' for call in calls)


@pytest.mark.asyncio
async def test_scope_and_every_effective_input_change_force_new_provider_call(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [len(calls)]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        baseline = await embed(provider, 'exact text', task_type='RETRIEVAL_DOCUMENT', title='one')
        assert (
            await embed(provider, 'exact text', task_type='RETRIEVAL_DOCUMENT', title='one')
        ).response == baseline.response
        assert len(calls) == 1
        for changes in [
            {'owner': 'other'},
            {'tenant': 'other'},
            {'title': 'two'},
            {'task_type': 'RETRIEVAL_QUERY'},
            {'title': None},
        ]:
            await embed(provider, 'exact text', **{'task_type': 'RETRIEVAL_DOCUMENT', 'title': 'one', **changes})
        await embed(provider, 'exact text ', task_type='RETRIEVAL_DOCUMENT', title='one')
        monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'another-project')
        await embed(provider, 'exact text', task_type='RETRIEVAL_DOCUMENT', title='one')
        assert len(calls) == 8


@pytest.mark.asyncio
@pytest.mark.parametrize('off', ['false', 'off', '0', 'NO'])
async def test_kill_switch_bypasses_both_batch_and_cross_request_reuse(monkeypatch, off):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        await embed(provider, 'same')
        monkeypatch.setenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', off)
        await embed(provider, ['same', 'same'])
        await embed(provider, 'same')
        assert len(calls) == 4
        monkeypatch.delenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', raising=False)
        await embed(provider, 'same')
        assert len(calls) == 5  # Disabled requests cleared previously warmed entries.


@pytest.mark.asyncio
async def test_missing_owner_bypasses_reuse_and_byok_cannot_read_warmed_cache():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        await embed(provider, ['same', 'same'], owner=None)
        await embed(provider, 'same', owner=None)
        await embed(provider, 'same')
        assert len(calls) == 4
        with pytest.raises(ProviderFailure):
            await provider.create_embedding(
                {'input': 'same'},
                provider_ref=MODEL,
                credentials=build_byok_credential_context(credentials().caller, {'gemini': 'fixture-key'}),
                timeout_ms=1000,
            )
        assert len(calls) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'bad_response',
    [
        httpx.Response(503),
        httpx.Response(429),
        httpx.Response(200, text='invalid'),
        httpx.Response(200, json={'predictions': [{'embeddings': {'values': []}}]}),
        httpx.Response(200, text='{"predictions":[{"embeddings":{"values":[NaN]}}]}'),
    ],
)
async def test_failed_or_malformed_result_is_never_reused(bad_response):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return bad_response
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        with pytest.raises(ProviderFailure):
            await embed(provider, 'retry')
        await embed(provider, 'retry')
        await embed(provider, 'retry')
        assert len(calls) == 2


@pytest.mark.asyncio
async def test_cancelled_call_has_no_reusable_result_or_surviving_worker():
    started = asyncio.Event()
    blocked = asyncio.Event()
    calls = []
    active = 0

    async def handler(request):
        nonlocal active
        calls.append(request)
        active += 1
        try:
            if len(calls) == 1:
                started.set()
                await blocked.wait()
            return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        task = asyncio.create_task(embed(provider, ['same', 'same']))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert active == 0
        await embed(provider, 'same')
        assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['cancel', 'deadline', 'provider_timeout', 'http'])
async def test_completed_item_is_not_published_from_cancelled_or_timed_out_batch(failure):
    succeeded = asyncio.Event()
    sibling_started = asyncio.Event()
    blocked = asyncio.Event()
    calls = []
    active = 0

    # Observe actual wire validation completing; do not replace the adapter or
    # fabricate a successful vector at the cache seam.
    class ObservedProvider(VertexGeminiProvider):
        async def _create_embedding_instance(self, endpoint, instance, **kwargs):
            vector = await super()._create_embedding_instance(endpoint, instance, **kwargs)
            if instance['content'] == 'a':
                succeeded.set()
            return vector

    async def handler(request):
        nonlocal active
        text = json.loads(request.content)['instances'][0]['content']
        calls.append(text)
        active += 1
        try:
            if text == 'b':
                sibling_started.set()
                await succeeded.wait()
                if failure == 'http':
                    return httpx.Response(503)
                if failure == 'provider_timeout':
                    raise httpx.ReadTimeout('fixture timeout', request=request)
                await blocked.wait()
            return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ObservedProvider(http_client=client, access_token_supplier=token)
        task = asyncio.create_task(
            provider.create_embedding(
                {'input': ['a', 'b']},
                provider_ref=MODEL,
                credentials=credentials(),
                timeout_ms=250 if failure == 'deadline' else 10_000,
            )
        )
        await asyncio.wait_for(succeeded.wait(), timeout=1)
        await asyncio.wait_for(sibling_started.wait(), timeout=1)
        if failure == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(ProviderFailure) as error:
                await task
            expected = FailureClass.PROVIDER_5XX_OMI_PAID if failure == 'http' else FailureClass.TIMEOUT_BEFORE_OUTPUT
            assert error.value.failure_class == expected
        assert active == 0
        await embed(provider, 'a')
        assert calls.count('a') == (1 if failure == 'http' else 2)
        # A successful retry may populate the cache normally.
        await embed(provider, 'a')
        assert calls.count('a') == (1 if failure == 'http' else 2)


@pytest.mark.asyncio
async def test_reuse_counters_have_no_owner_or_content_labels():
    def count(counter, outcome):
        return counter.labels(outcome)._value.get()

    before_inputs = {outcome: count(INPUTS, outcome) for outcome in ('submitted', 'cache_hit', 'batch_reuse')}
    before_chars = {outcome: count(CHARACTERS, outcome) for outcome in before_inputs}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.25]}}]})
        )
    ) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        await embed(provider, ['abc', 'abc'])
        await embed(provider, 'abc')
    for outcome in before_inputs:
        assert count(INPUTS, outcome) - before_inputs[outcome] == 1
        assert count(CHARACTERS, outcome) - before_chars[outcome] == 3
    assert INPUTS._labelnames == CHARACTERS._labelnames == ('outcome',)


def test_cache_ttl_bounds_and_returned_vector_mutation():
    now = [1.0]
    cache = EmbeddingVectorCache(now=lambda: now[0], ttl_seconds=10, max_entries=2, max_values=4)
    cache.put('a', [0.25, 0.5])
    returned = cache.get('a')
    returned[0] = 999
    assert cache.get('a') == [0.25, 0.5]
    cache.put('b', [1, 2])
    cache.get('a')
    cache.put('c', [3, 4])
    assert cache.get('b') is None  # LRU count/value bound.
    cache.put('huge', [0] * 5)
    assert cache.get('huge') is None
    now[0] = 11.0
    assert cache.get('a') is cache.get('c') is None  # Hits never extend hard TTL.
    cache.put('d', [1])
    cache.clear()
    assert cache.get('d') is None


def test_keys_are_content_hashes_over_complete_effective_inputs_and_require_owner():
    request = {
        'owner': 'owner',
        'endpoint': 'model-A',
        'instance': {'content': 'x', 'task_type': 'QUERY', 'title': 'a'},
    }
    baseline = embedding_key(**request)
    assert len(baseline) == 64
    assert embedding_key(**{**request, 'owner': None}) is None
    for delta in [
        {'owner': 'other'},
        {'endpoint': 'model-B'},
        {'instance': {'content': 'x ', 'task_type': 'QUERY', 'title': 'a'}},
        {'instance': {'content': 'x', 'task_type': 'DOCUMENT', 'title': 'a'}},
        {'instance': {'content': 'x', 'task_type': 'QUERY', 'title': 'b'}},
    ]:
        assert embedding_key(**{**request, **delta}) != baseline
