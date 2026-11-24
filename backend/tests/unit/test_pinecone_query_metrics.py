"""Query accounting preserves outcomes and never exports tenant identifiers."""

import ast
from pathlib import Path
import re
from types import SimpleNamespace

from pinecone.core.openapi.db_data.model.query_response import QueryResponse
from pinecone.core.openapi.db_data.model.usage import Usage
import pytest
from prometheus_client import CollectorRegistry, Counter, generate_latest
import yaml

from database import pinecone_partition_index as adapter
from database import pinecone_query_metrics as metrics


@pytest.fixture
def registry(monkeypatch):
    registry = CollectorRegistry()
    for name, original in (
        ('QUERIES', metrics.QUERIES),
        ('READ_UNITS', metrics.READ_UNITS),
        ('MISSING_USAGE', metrics.MISSING_USAGE),
        ('METERING_ERRORS', metrics.METERING_ERRORS),
    ):
        monkeypatch.setattr(
            metrics, name, Counter(original._name, original._documentation, original._labelnames, registry=registry)
        )
    return registry


def sample(registry, name, family='ns1', route_mode='legacy', caller='query_vectors'):
    return registry.get_sample_value(name, {'family': family, 'route_mode': route_mode, 'caller': caller})


@pytest.mark.parametrize('partitioned', [False, True])
@pytest.mark.parametrize(
    'response',
    [
        {'matches': [], 'usage': {'read_units': 2}},
        SimpleNamespace(usage=SimpleNamespace(read_units=2)),
    ],
)
def test_response_shapes_and_units(registry, response, partitioned):
    route = 'ns1-p1-private-bucket' if partitioned else 'ns1'
    metrics.record_query('ns1', route, 'query_vectors', response, succeeded=True)
    mode = 'partitioned' if partitioned else 'legacy'
    assert sample(registry, 'omi_pinecone_queries_total', route_mode=mode) == 1
    assert sample(registry, 'omi_pinecone_read_units_total', route_mode=mode) == 2
    assert b'private-bucket' not in generate_latest(registry)


@pytest.mark.parametrize(
    'response',
    [{}, {'usage': None}, {'usage': {}}, SimpleNamespace(), QueryResponse(matches=[]), QueryResponse(usage=Usage())],
)
def test_missing_usage_counts_query_without_inventing_units(registry, response):
    metrics.record_query('ns1', 'ns1', 'query_vectors', response, succeeded=True)
    assert sample(registry, 'omi_pinecone_queries_total') == 1
    assert sample(registry, 'omi_pinecone_query_missing_usage_total') == 1
    assert sample(registry, 'omi_pinecone_read_units_total') is None


@pytest.mark.parametrize('units', [-1, 0.25, 1.5, 1.0, float('inf'), float('nan'), '1', True])
def test_invalid_usage_is_swallowed_and_counted(registry, units):
    metrics.record_query('ns1', 'ns1', 'query_vectors', {'usage': {'read_units': units}}, succeeded=True)
    assert sample(registry, 'omi_pinecone_queries_total') == 1
    assert sample(registry, 'omi_pinecone_read_units_total') is None
    assert registry.get_sample_value('omi_pinecone_query_metering_errors_total') == 1


def test_zero_units_is_not_missing(registry):
    metrics.record_query('ns1', 'ns1', 'query_vectors', {'usage': {'read_units': 0}}, succeeded=True)
    assert sample(registry, 'omi_pinecone_read_units_total') == 0
    assert sample(registry, 'omi_pinecone_query_missing_usage_total') is None


def test_pinned_sdk_usage_object(registry):
    response = QueryResponse(matches=[], namespace='ns1', usage=Usage(read_units=2))
    metrics.record_query('ns1', 'ns1', 'query_vectors', response, succeeded=True)
    assert sample(registry, 'omi_pinecone_read_units_total') == 2


def test_unknown_labels_are_bounded(registry):
    for number in range(100):
        metrics.record_query(
            f'owner-family-{number}', f'private-route-{number}', f'private-caller-{number}', {}, succeeded=True
        )
    assert sample(registry, 'omi_pinecone_queries_total', 'other', 'partitioned', 'other') == 100
    output = generate_latest(registry)
    assert b'private-' not in output and b'owner-family-' not in output


@pytest.mark.parametrize('failure', [False, True])
def test_owner_boundary_preserves_result_or_exception_and_consumes_caller(registry, monkeypatch, failure):
    response = {'matches': [], 'usage': {'read_units': 3}}
    error = RuntimeError('provider unavailable')
    calls = []

    def query(**kwargs):
        calls.append(kwargs)
        if failure:
            raise error
        return response

    scoped = adapter.OwnerIndex(SimpleNamespace(query=query), 'synthetic-owner', index_name='test-index')
    monkeypatch.setattr(scoped, '_route', lambda family: 'ns1-p1-bucket')
    if failure:
        with pytest.raises(RuntimeError) as caught:
            scoped.query(namespace='ns1', caller='query_vectors', filter={'uid': 'synthetic-owner'}, top_k=1)
        assert caught.value is error
    else:
        assert (
            scoped.query(namespace='ns1', caller='query_vectors', filter={'uid': 'synthetic-owner'}, top_k=1)
            is response
        )
    assert calls == [{'namespace': 'ns1-p1-bucket', 'filter': {'uid': 'synthetic-owner'}, 'top_k': 1}]
    assert sample(registry, 'omi_pinecone_queries_total', route_mode='partitioned') == 1
    assert sample(registry, 'omi_pinecone_read_units_total', route_mode='partitioned') == (None if failure else 3)
    assert sample(registry, 'omi_pinecone_query_missing_usage_total', route_mode='partitioned') is None


def test_exporter_failure_cannot_break_query(registry, monkeypatch):
    response = {'usage': {'read_units': 1}}
    scoped = adapter.OwnerIndex(SimpleNamespace(query=lambda **kwargs: response), 'synthetic-owner', index_name='test')
    monkeypatch.setattr(scoped, '_route', lambda family: family)

    def broken(*args, **kwargs):
        raise RuntimeError('meter unavailable')

    monkeypatch.setattr(metrics, 'record_query', broken)
    assert scoped.query(namespace='ns1', filter={'uid': 'synthetic-owner'}) is response
    assert registry.get_sample_value('omi_pinecone_query_metering_errors_total') == 1
    monkeypatch.setattr(metrics.METERING_ERRORS, 'inc', broken)
    assert scoped.query(namespace='ns1', filter={'uid': 'synthetic-owner'}) is response


def test_all_vector_db_query_calls_have_closed_explicit_callers():
    path = Path(__file__).resolve().parents[2] / 'database/vector_db.py'
    calls = []
    for function in ast.walk(ast.parse(path.read_text())):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(function):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'query':
                caller = next(keyword.value for keyword in call.keywords if keyword.arg == 'caller')
                assert isinstance(caller, ast.Constant) and caller.value == function.name
                assert caller.value in metrics.CALLERS
                calls.append(caller.value)
    assert len(calls) == 11


def test_cloud_run_profiles_admit_meter_counters():
    root = Path(__file__).resolve().parents[2]
    names = [
        'omi_pinecone_queries_total',
        'omi_pinecone_read_units_total',
        'omi_pinecone_query_missing_usage_total',
        'omi_pinecone_query_metering_errors_total',
    ]
    for profile in ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'):
        config = yaml.safe_load((root / 'deploy' / profile).read_text())
        rules = config['spec']['endpoints'][0]['metricRelabeling']
        for name in names:
            assert all(
                re.fullmatch(rule['regex'], name)
                for rule in rules
                if rule['action'] == 'keep' and rule['sourceLabels'] == ['__name__']
            ), (profile, name)
