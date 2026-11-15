"""Summary retrieval must work with the deployed providers and admission gate."""

import json
import ssl
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import httpx
import pytest
import urllib3
from pinecone import Pinecone

from config import summary_context
from database import vector_db
from database.pinecone_partition_index import OwnerIndex
from utils import generated_compute
from utils.episodes import composer_context
from utils.llm import summary_embeddings
from utils.memory import read_resilience
from utils.memory.memory_service import MemoryService
from utils.other.list_budget import ListReadBudget


@pytest.fixture
def locked_transports(monkeypatch):
    """Only replace HTTP; keep Pinecone name discovery, SDKs and service real."""
    calls = {'discovery': 0, 'embedding': 0, 'vector': 0}
    ssl_context = ssl.create_default_context()
    monkeypatch.setattr(ssl, 'create_default_context', lambda **_kwargs: ssl_context)

    def describe(_self, method, url, **kwargs):
        assert method == 'GET' and url.endswith('/indexes/memories-backend')
        calls['discovery'] += 1
        return urllib3.HTTPResponse(
            status=200,
            body=json.dumps(
                {
                    'name': 'memories-backend',
                    'dimension': 2,
                    'metric': 'cosine',
                    'host': 'summary-unit.svc.invalid',
                    'deletion_protection': 'disabled',
                    'spec': {'serverless': {'cloud': 'aws', 'region': 'us-east-1'}},
                    'status': {'ready': True, 'state': 'Ready'},
                }
            ).encode(),
            headers={'content-type': 'application/json'},
        )

    async def embedding(request):
        assert request.url.path == '/v1/embeddings'
        assert json.loads(request.content)['model'] == 'omi:auto:openai-embeddings'
        assert request.headers['authorization'] == 'Bearer synthetic-service-token'
        calls['embedding'] += 1
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [0.1, 0.2]}]})

    async def vector(_self, method, url, **kwargs):
        assert method == 'POST' and str(url).endswith('/query')
        assert kwargs['allow_redirects'] is False
        assert kwargs['trace_request_ctx']['current_attempt'] == 1
        assert kwargs['json']['filter']['$and'][0] == {'uid': {'$eq': 'synthetic'}}
        calls['vector'] += 1
        response = Mock(spec=aiohttp.ClientResponse)
        response.status, response.reason, response.closed = 200, 'OK', True
        response.headers = {'content-type': 'application/json'}
        response.read = AsyncMock(return_value=b'{"matches": [], "namespace": "ns2", "usage": {"read_units": 1}}')
        return response

    def transport(**kwargs):
        assert kwargs['retries'] == 0
        return httpx.MockTransport(embedding)

    monkeypatch.setattr(urllib3.PoolManager, 'request', describe)
    monkeypatch.setattr(aiohttp.ClientSession, '_request', vector)
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', transport)
    monkeypatch.setattr(OwnerIndex, '_route', lambda _self, family: family)
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    monkeypatch.setattr(summary_embeddings, 'get_byok_key', lambda _provider: None)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    monkeypatch.setenv('OMI_LLM_GATEWAY_FEATURE_MODE', 'gateway')
    monkeypatch.setenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', 'true')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'https://gateway-unit.svc.invalid')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.setenv('LLM_GATEWAY_ACCOUNTING_ENABLED', 'true')
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(key, raising=False)
    controller = Pinecone(api_key='synthetic-api-key')
    index = controller.Index('memories-backend')
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, '_pinecone_index_name', 'memories-backend')
    yield calls
    index.close()
    controller.db._index_api.api_client.close()


def test_owner_retrieval_with_locked_sdks_and_production_settings(locked_transports):
    members = [
        {
            'structured': {'title': 'Atlas launch', 'overview': 'Release commitments'},
            'transcript_segments': [{'text': 'Priya ships Atlas.'}, {'text': 'Priya reviews Atlas.'}],
        }
    ]
    assert generated_compute.generated_compute_configured()
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 8, max_documents=640)
    assert composer_context._search_memories('synthetic', members, budget=budget) == []
    assert locked_transports == {'discovery': 1, 'embedding': 6, 'vector': 6}


def test_three_owner_searches_keep_the_overall_budget(monkeypatch):
    repo = MemoryService(db_client=Mock())
    repo._canonical.search = Mock(return_value=[])
    repo.history.search = Mock(return_value=[])
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 8, max_documents=640)
    for _ in range(3):
        assert (
            repo.search('synthetic', 'garden', owner_summary=True, vector_only=True, budget=budget, single_attempt=True)
            == []
        )
    assert repo._canonical.search.call_count == 3


def test_owner_search_admission_uses_context_deadline_not_retry_window(monkeypatch):
    now = [100.0]
    policy = read_resilience.MemoryReadResilience(clock=lambda: now[0])
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance(clock=lambda: now[0]))
    budget = ListReadBudget(deadline_monotonic=108, max_documents=640, clock=lambda: now[0])
    assert policy.call('search', lambda: [], budget=budget, single_attempt=True) == []
    now[0] += 2
    assert policy.call('search', lambda: [], budget=budget, single_attempt=True) == []


class _SealedError(Exception):
    """A provider exception type that rejects attribute writes."""

    def __setattr__(self, name, value):
        if name.startswith('__'):
            return super().__setattr__(name, value)
        raise AttributeError(name)


def test_stage_marking_never_replaces_an_exception_that_rejects_attributes():
    original = _SealedError('provider failure')
    with pytest.raises(_SealedError) as caught:
        with summary_context.context_stage('vector'):
            raise original
    assert caught.value is original
    # Unmarked failures still report their class, with the default stage.
    assert summary_context.failure_details(original) == ('hydrate', '_SealedError')
