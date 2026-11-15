"""Harness teardown removes coordination rows only inside its own namespace."""

from functools import partial
from types import SimpleNamespace

import pytest

from testing import store_fixtures


class Client:
    _emulator_host = '127.0.0.1:1'

    def __init__(self):
        self.rows = set()
        self.closed = False

    def collection(self, name):
        def stream():
            return [
                SimpleNamespace(reference=SimpleNamespace(delete=partial(self.rows.remove, path)))
                for path in tuple(self.rows)
                if path[0] == name
            ]

        return SimpleNamespace(stream=stream)

    def close(self):
        self.closed = True


@pytest.mark.parametrize('table', ['pull_claims', 'merge_holds'])
def test_emulator_teardown_removes_owned_coordination_rows_and_preserves_foreign_namespaces(monkeypatch, table):
    client = Client()
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', client._emulator_host)
    monkeypatch.setattr(store_fixtures, '_emulator_client', lambda: client)
    harness = store_fixtures.make_emulator()
    owned = (f'{harness.namespace}_{table}', 'same-key')
    foreign = (f'{harness.namespace}_foreign_{table}', 'same-key')
    customer = ('users', 'synthetic-customer')
    client.rows.update((owned, foreign, customer))
    harness.close()
    assert client.rows == {foreign, customer}
    assert client.closed
