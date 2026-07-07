import importlib
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

import pytest

MODULE_NAME = 'utils.conversations.search'


@pytest.fixture(autouse=True)
def cleanup_search_module():
    sys.modules.pop(MODULE_NAME, None)
    yield
    sys.modules.pop(MODULE_NAME, None)


def _import_search_module(monkeypatch, client_delay=0):
    client_configs = []

    class FakeClient:
        def __init__(self, config):
            if client_delay:
                time.sleep(client_delay)
            client_configs.append(config)
            documents = types.SimpleNamespace(search=lambda _params: {'hits': []})
            self.collections = {'conversations': types.SimpleNamespace(documents=documents)}

    fake_typesense = types.ModuleType('typesense')
    fake_typesense.Client = FakeClient
    monkeypatch.setitem(sys.modules, 'typesense', fake_typesense)
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME), client_configs


def test_import_does_not_require_typesense_env(monkeypatch):
    for name in ('TYPESENSE_HOST', 'TYPESENSE_HOST_PORT', 'TYPESENSE_API_KEY'):
        monkeypatch.delenv(name, raising=False)

    _, client_configs = _import_search_module(monkeypatch)

    assert client_configs == []


def test_search_requires_typesense_api_key_when_used(monkeypatch):
    monkeypatch.setenv('TYPESENSE_HOST', 'localhost')
    monkeypatch.setenv('TYPESENSE_HOST_PORT', '8108')
    monkeypatch.delenv('TYPESENSE_API_KEY', raising=False)
    search_module, client_configs = _import_search_module(monkeypatch)

    with pytest.raises(Exception, match='TYPESENSE_API_KEY is required to search conversations'):
        search_module.search_conversations(uid='user-1', query='meeting')

    assert client_configs == []


def test_search_constructs_typesense_client_on_first_use(monkeypatch):
    monkeypatch.setenv('TYPESENSE_HOST', 'localhost')
    monkeypatch.setenv('TYPESENSE_HOST_PORT', '8108')
    monkeypatch.setenv('TYPESENSE_API_KEY', 'dev-key')
    search_module, client_configs = _import_search_module(monkeypatch)

    result = search_module.search_conversations(uid='user-1', query='meeting')

    assert result == {'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10}
    assert client_configs == [
        {
            'nodes': [{'host': 'localhost', 'port': '8108', 'protocol': 'https'}],
            'api_key': 'dev-key',
            'connection_timeout_seconds': 2,
        }
    ]


def test_search_preserves_typesense_protocol_override(monkeypatch):
    monkeypatch.setenv('TYPESENSE_HOST', 'localhost')
    monkeypatch.setenv('TYPESENSE_HOST_PORT', '8108')
    monkeypatch.setenv('TYPESENSE_API_KEY', 'dev-key')
    monkeypatch.setenv('TYPESENSE_PROTOCOL', 'http')
    search_module, client_configs = _import_search_module(monkeypatch)

    search_module.search_conversations(uid='user-1', query='meeting')

    assert client_configs[0]['nodes'][0]['protocol'] == 'http'


def test_typesense_client_initializes_once_for_concurrent_first_use(monkeypatch):
    monkeypatch.setenv('TYPESENSE_HOST', 'localhost')
    monkeypatch.setenv('TYPESENSE_HOST_PORT', '8108')
    monkeypatch.setenv('TYPESENSE_API_KEY', 'dev-key')
    search_module, client_configs = _import_search_module(monkeypatch, client_delay=0.02)

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: search_module._get_typesense_client(), range(8)))

    assert len({id(client) for client in clients}) == 1
    assert len(client_configs) == 1
