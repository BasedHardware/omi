"""Hermetic HTTP contract tests for the standalone PyPI Omi plugin."""

import importlib.util
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture
def plugin():
    path = Path(__file__).resolve().parents[3] / 'plugins' / 'omi-pypi-app' / 'main.py'
    assert path.is_file(), 'The PyPI plugin implementation must exist'
    spec = importlib.util.spec_from_file_location('omi_pypi_plugin', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(plugin):
    with TestClient(plugin.app) as client:
        yield client


def upstream(plugin, monkeypatch, handler):
    real_client = ASYNC_CLIENT

    def factory(**kwargs):
        assert 0 < kwargs['timeout'] <= 20
        assert kwargs['follow_redirects'] is False
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(plugin.httpx, 'AsyncClient', factory)


def test_health_and_discovery(client):
    assert client.get('/health').json() == {'status': 'ok'}
    tools = client.get('/.well-known/omi-tools.json').json()['tools']
    assert [tool['name'] for tool in tools] == ['get_pypi_package', 'get_pypi_release']
    for tool in tools:
        assert tool['method'] == 'POST'
        assert tool['auth_required'] is False
        assert tool['endpoint'] == '/tools/' + tool['name']
        assert 'package' in tool['parameters']['required']
    assert tools[1]['parameters']['required'] == ['package', 'version']


@pytest.mark.parametrize('version', [None, '1!2.3rc1.post2.dev3+cpu.1'])
def test_lookup_metadata(client, plugin, monkeypatch, version):
    expected_version = version or '2.3'

    def handler(request):
        suffix = f'/{expected_version}' if version else ''
        assert request.url.host == 'pypi.org'
        assert request.url.scheme == 'https'
        assert request.url.path == f'/pypi/demo-pkg{suffix}/json'
        assert request.method == 'GET'
        return httpx.Response(
            200,
            json={
                'info': {
                    'name': 'Demo-Pkg',
                    'version': expected_version,
                    'summary': 'A demo',
                    'requires_python': '>=3.9',
                    'license_expression': 'MIT',
                    'license': 'legacy',
                    'project_urls': {'Source': 'https://example.com/repo'},
                    'requires_dist': ['httpx>=0.28; python_version >= "3.9"'],
                    'yanked': True,
                    'yanked_reason': 'Broken release',
                }
            },
        )

    upstream(plugin, monkeypatch, handler)
    body = {'package': 'Demo_Pkg'}
    if version:
        body['version'] = version
    result = client.post('/tools/get_pypi_release' if version else '/tools/get_pypi_package', json=body).json()
    assert result['error'] is None
    for text in [
        'Demo-Pkg',
        expected_version,
        'A demo',
        '>=3.9',
        'MIT',
        'https://example.com/repo',
        'httpx>=0.28',
        'Yanked: yes',
        'Broken release',
        'publisher-supplied',
        'not a safety verification',
    ]:
        assert text in result['result']
    assert 'legacy' not in result['result']
    suffix = "/" + quote(version, safe="") if version else ''
    assert f'PyPI source: https://pypi.org/project/demo-pkg{suffix}/' in result['result']


@pytest.mark.parametrize(
    'body,route',
    [
        ({'package': '../x'}, 'package'),
        ({'package': 'https://example.com'}, 'package'),
        ({'package': 'x?foo'}, 'package'),
        ({'package': ''}, 'package'),
        ({'package': 'a' * 201}, 'package'),
        ({'package': ['x']}, 'package'),
        ({}, 'package'),
        ({'package': 'x', 'version': '../1'}, 'release'),
        ({'package': 'x', 'version': '1/2'}, 'release'),
        ({'package': 'x', 'version': '1%2f2'}, 'release'),
        ({'package': 'x', 'version': 'banana'}, 'release'),
        ({'package': 'x'}, 'release'),
    ],
)
def test_invalid_inputs_do_not_contact_pypi(client, plugin, monkeypatch, body, route):
    def handler(request):
        pytest.fail('Invalid inputs must not contact an upstream')

    upstream(plugin, monkeypatch, handler)
    response = client.post('/tools/get_pypi_' + route, json=body)
    assert response.status_code in (200, 422)
    assert response.json()['error']
    assert len(response.text) < 300


@pytest.mark.parametrize(
    'failure,expected',
    [
        (404, 'not found'),
        (503, 'unavailable'),
        (302, 'unavailable'),
        ('timeout', 'timed out'),
        ('network', 'unavailable'),
        ('json', 'invalid metadata'),
        ('shape', 'invalid metadata'),
    ],
)
def test_upstream_errors_are_concise(client, plugin, monkeypatch, failure, expected):
    def handler(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('PRIVATE DETAILS', request=request)
        if failure == 'network':
            raise httpx.ConnectError('PRIVATE DETAILS', request=request)
        if failure == 'json':
            return httpx.Response(200, text='PRIVATE DETAILS')
        if failure == 'shape':
            return httpx.Response(200, json={'info': []})
        return httpx.Response(failure, headers={'Location': 'https://example.com'}, text='PRIVATE DETAILS')

    upstream(plugin, monkeypatch, handler)
    body = client.post('/tools/get_pypi_package', json={'package': 'demo'}).json()
    assert body['result'] is None
    assert expected in body['error']
    assert 'PRIVATE DETAILS' not in body['error']


def test_missing_metadata_and_bounded_output(client, plugin, monkeypatch):
    upstream(
        plugin, monkeypatch, lambda request: httpx.Response(200, json={'info': {'name': 'demo', 'version': '1.0'}})
    )
    result = client.post('/tools/get_pypi_package', json={'package': 'demo'}).json()['result']
    for label in [
        'Summary',
        'Requires Python',
        'License',
        'Project links',
        'Declared dependencies',
        'Yanked',
    ]:
        assert f'{label}: unknown' in result

    upstream(
        plugin,
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                'info': {
                    'name': 'demo',
                    'version': '1.0',
                    'summary': 'x' * 10000,
                    'license': 'BSD',
                    'requires_dist': ['d' * 1000] * 100,
                    'project_urls': {f'link{i}': 'u' * 1000 for i in range(100)},
                    'yanked': False,
                }
            },
        ),
    )
    result = client.post('/tools/get_pypi_package', json={'package': 'demo'}).json()['result']
    assert len(result) <= 6000
    assert 'truncated' in result
    assert 'License: BSD' in result
    assert 'Yanked: no' in result


@pytest.mark.parametrize(
    'info', [{}, {'name': 'demo'}, {'name': 'demo', 'version': []}, {'name': ' ', 'version': '1.0'}]
)
def test_missing_identity_is_invalid_metadata(client, plugin, monkeypatch, info):
    upstream(plugin, monkeypatch, lambda request: httpx.Response(200, json={'info': info}))
    body = client.post('/tools/get_pypi_package', json={'package': 'demo'}).json()
    assert body['result'] is None
    assert body['error'] == 'PyPI returned invalid metadata.'
