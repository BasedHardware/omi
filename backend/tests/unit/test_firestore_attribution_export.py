"""Exercise the SDK and the deployed scrape filters without cloud access."""

from datetime import datetime, timezone
import asyncio
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import AsyncClient, Client
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, Document, RunQueryResponse
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families
import pytest
import yaml

from database import firestore_document_probe as probe
from database import firestore_tier_context as tiers
from utils import read_cache_shadow

BACKEND = Path(__file__).resolve().parents[2]


def totals():
    return tuple(
        sum(s.value for family in counter.collect() for s in family.samples if s.name.endswith('_total'))
        for counter in (probe.FIRESTORE_BILLED_READS, probe.FIRESTORE_BILLED_READS_BY_CALLER)
    )


@pytest.fixture
def sdk(monkeypatch):
    # Real constructors/builders/stream conversion; only the RPC is replaced.
    # A second raw Client is deliberately constructed after class installation.
    probe.install_document_read_probe()
    client = Client(project='demo-attribution', credentials=AnonymousCredentials())
    responses = []
    api = Mock()
    api.run_query.side_effect = lambda **kwargs: iter(responses)
    monkeypatch.setattr(client, '_firestore_api_internal', api)
    return client, api, responses


@pytest.mark.parametrize(
    'mode', ['stream', 'get', 'transaction', 'collection', 'collection_group', 'limit', 'last', 'offset']
)
@pytest.mark.parametrize('size', [0, 1, 7])
def test_real_sdk_query_documents_count_once(sdk, mode, size):
    client, api, responses = sdk
    collection = client.collection('users/u/conversations')
    query = collection.order_by('__name__')
    if mode == 'collection_group':
        query = client.collection_group('conversations')
    if mode == 'limit':
        query = query.limit(7)
    if mode == 'last':
        query = query.limit_to_last(7)
    if mode == 'offset':
        query = query.offset(4)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    responses.extend(
        RunQueryResponse(
            document=Document(name=f'{client._database_string}/documents/users/u/conversations/c{i}'), read_time=stamp
        )
        for i in range(size)
    )
    before = totals()
    if mode == 'transaction':
        transaction = client.transaction()
        transaction._id = b'synthetic-transaction'
        rows = list(transaction.get(query))
        assert api.run_query.call_args.kwargs['request']['transaction'] == b'synthetic-transaction'
    elif mode in ('get', 'last'):
        rows = query.get()
    elif mode == 'collection':
        rows = list(collection.stream())
    else:
        rows = list(query.stream())
    assert len(rows) == size
    amount = max(1, size + (4 if mode == 'offset' else 0))
    assert totals() == tuple(value + amount for value in before)
    assert api.run_query.call_count == 1
    request = api.run_query.call_args.kwargs['request']['structured_query']
    if mode in ('limit', 'last'):
        assert request.limit == 7
    if mode == 'offset':
        assert request.offset == 4
    if mode == 'collection_group':
        assert request.from_[0].all_descendants


def test_partial_iteration_preserves_laziness_and_counts_consumed_documents(sdk):
    client, api, responses = sdk
    responses.extend(
        RunQueryResponse(document=Document(name=f'{client._database_string}/documents/users/u/conversations/c{i}'))
        for i in range(7)
    )
    before = totals()
    stream = client.collection('users/u/conversations').stream()
    assert api.run_query.call_count == 0
    next(stream)
    stream.close()
    assert totals() == tuple(value + 1 for value in before)
    assert api.run_query.call_count == 1
    # Observing the other six would require consuming a closed RPC. The probe
    # cannot infer how many responses Firestore billed but the caller abandoned.


@pytest.mark.parametrize('transactional', [False, True])
def test_real_sdk_batch_get_counts_server_results_not_duplicate_requests(sdk, transactional):
    client, api, _ = sdk
    present = client.document('users/u/conversations/present')
    absent = client.document('users/u/conversations/absent')
    api.batch_get_documents.return_value = iter(
        [
            BatchGetDocumentsResponse(found=Document(name=present._document_path)),
            BatchGetDocumentsResponse(missing=absent._document_path),
        ]
    )
    before = totals()
    refs = [present, absent, present]
    if transactional:
        transaction = client.transaction()
        transaction._id = b'synthetic-transaction'
        rows = list(transaction.get_all(refs))
    else:
        rows = list(client.get_all(refs))
    assert [row.exists for row in rows] == [True, False]
    assert totals() == tuple(value + 2 for value in before)
    assert api.batch_get_documents.call_count == 1


@pytest.mark.parametrize('mode', ['stream', 'get', 'transaction', 'collection_group', 'limit'])
def test_real_async_sdk_query_documents_count_once(monkeypatch, mode):
    probe.install_document_read_probe()
    client = AsyncClient(project='demo-attribution', credentials=AnonymousCredentials())

    async def responses():
        for i in range(7):
            yield RunQueryResponse(
                document=Document(name=f'{client._database_string}/documents/users/u/conversations/c{i}')
            )

    api = Mock()
    api.run_query = AsyncMock(side_effect=lambda **kwargs: responses())
    monkeypatch.setattr(client, '_firestore_api_internal', api)
    query = client.collection('users/u/conversations').order_by('__name__')
    if mode == 'collection_group':
        query = client.collection_group('conversations')
    if mode == 'limit':
        query = query.limit(7)
    before = totals()

    async def read():
        if mode == 'get':
            return await query.get()
        if mode == 'transaction':
            transaction = client.transaction()
            transaction._id = b'synthetic-transaction'
            stream = await transaction.get(query)
        else:
            stream = query.stream()
        return [row async for row in stream]

    assert len(asyncio.run(read())) == 7
    assert totals() == tuple(value + 7 for value in before)
    assert api.run_query.call_count == 1


@pytest.mark.parametrize('tier', [None, 'basic', 'plus', 'not-a-plan'])
@pytest.mark.parametrize('profile', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_billed_counters_agree_after_real_exposition_and_keep_filter(tier, profile):
    token = tiers._request_owner.set(SimpleNamespace(tier=tier, expires_at=float('inf'), closed=False))
    registry = CollectorRegistry()
    for counter in (probe.FIRESTORE_BILLED_READS, probe.FIRESTORE_BILLED_READS_BY_CALLER, read_cache_shadow.SHADOW):
        registry.register(counter)
    config = yaml.safe_load((BACKEND / 'deploy' / profile).read_text())
    keep = next(
        rule['regex'] for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep'
    )

    def exported():
        result = {}
        for family in text_string_to_metric_families(generate_latest(registry).decode()):
            for sample in family.samples:
                if sample.name.endswith('_total') and re.fullmatch(keep, sample.name):
                    result[sample.name] = result.get(sample.name, 0) + sample.value
                    if 'tier' in sample.labels:
                        assert sample.labels['tier'] in tiers.TIER_VALUES
        return result

    try:
        before = exported()
        for kind, exists, amount in [('lookup', True, 1), ('not_found', False, 3), ('query', True, 7)]:
            probe._record(('users', 'u', 'conversations'), exists, amount, kind=kind, caller='tests:export_parity')
        read_cache_shadow._record('usage_month', 'match')
        after = exported()
        for name in ['omi_firestore_billed_reads_total', 'omi_firestore_billed_reads_by_caller_total']:
            assert after.get(name, 0) - before.get(name, 0) == 11, (profile, name)
        assert after.get('omi_read_cache_shadow_total', 0) - before.get('omi_read_cache_shadow_total', 0) == 1
    finally:
        tiers._request_owner.reset(token)


@pytest.mark.parametrize('profile', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_scrape_sample_caps_leave_headroom_for_tier_and_shadow_metrics(profile):
    config = yaml.safe_load((BACKEND / 'deploy' / profile).read_text())
    assert config['spec']['limits']['samples'] == 15000
