"""Domain adapters must implement the storage-neutral protocol surfaces."""

import ast
import inspect
from pathlib import Path

import pytest

from database.cells.adapters import CellSpaceStore
from database.cells.adapters.action_items import CellActionItems
from database.cells.adapters.goals import CellGoals
from database.cells.adapters.workstreams import CellWorkstreams
from database.cells.adapters.folders import CellFolders
from database.cells.adapters.people import CellPeople
from database.action_items import FirestoreActionItems
from database.goals import FirestoreGoals
from database.workstreams import FirestoreWorkstreams
from database.ports.action_items import ActionItemsTx, ActionItemsRepo
from database.ports.goals import GoalsTx, GoalsRepo
from database.ports.workstreams import WorkstreamsTx, WorkstreamsRepo
from testing.domain_sim.store import SimActionItems, SimGoals, SimWorkstreams
from database.folders import FirestoreFolders
from database.people import FirestorePeople
from database.ports.base import SpaceStore
from database.ports.folders import FoldersRepo, FoldersTx
from database.ports.people import PeopleRepo, PeopleTx
from database.space_store import FirestoreSpaceStore
from testing.domain_sim.store import SimFolders, SimPeople, SimSpaceStore
from tests.support.firestore_query_driver_registry import COVERED_BY, DRIVERS, PORT_CALLER_DRIVERS
from tests.support.firestore_query_drivers import calling_key, run_driver
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, ReadAfterWriteError


@pytest.mark.parametrize(
    'protocol,adapter',
    [
        (ActionItemsTx, CellActionItems),
        (ActionItemsRepo, CellActionItems),
        (GoalsTx, CellGoals),
        (GoalsRepo, CellGoals),
        (WorkstreamsTx, CellWorkstreams),
        (WorkstreamsRepo, CellWorkstreams),
        (FoldersTx, CellFolders),
        (FoldersRepo, CellFolders),
        (PeopleTx, CellPeople),
        (PeopleRepo, CellPeople),
        (SpaceStore, CellSpaceStore),
        (ActionItemsTx, FirestoreActionItems),
        (ActionItemsRepo, FirestoreActionItems),
        (GoalsTx, FirestoreGoals),
        (GoalsRepo, FirestoreGoals),
        (WorkstreamsTx, FirestoreWorkstreams),
        (WorkstreamsRepo, FirestoreWorkstreams),
        (ActionItemsRepo, SimActionItems),
        (GoalsRepo, SimGoals),
        (WorkstreamsRepo, SimWorkstreams),
        (FoldersRepo, FirestoreFolders),
        (FoldersTx, FirestoreFolders),
        (PeopleTx, FirestorePeople),
        (PeopleRepo, FirestorePeople),
        (SpaceStore, FirestoreSpaceStore),
        (SpaceStore, SimSpaceStore),
        (FoldersRepo, SimFolders),
        (PeopleRepo, SimPeople),
    ],
)
def test_protocol_signatures(protocol, adapter):
    methods = {
        name
        for parent in protocol.__mro__
        for name, member in vars(parent).items()
        if not name.startswith('_') and inspect.isfunction(member)
    }
    for name in methods:
        expected = inspect.signature(getattr(protocol, name)).parameters
        actual = inspect.signature(getattr(adapter, name)).parameters
        assert list(actual) == list(expected), (adapter, name)
        assert [p.kind for p in actual.values()] == [p.kind for p in expected.values()]
        assert [p.default for p in actual.values()] == [p.default for p in expected.values()]


def test_ports_are_pure():
    import sys

    root = Path(__file__).resolve().parents[2] / 'database' / 'ports'
    allowed = sys.stdlib_module_names | {'pydantic'}
    for path in root.glob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (
                    node.level == 1
                    and node.module in {'base', 'folders', 'people', 'action_items', 'goals', 'workstreams'}
                ) or (node.level == 0 and (node.module or '').split('.')[0] in allowed), (path, node.module)
            elif isinstance(node, ast.Import):
                assert all(alias.name.split('.')[0] in allowed for alias in node.names), path
    sim = root.parents[1] / 'testing' / 'domain_sim' / 'store.py'
    assert 'google.' not in sim.read_text()


def test_firestore_uow_keeps_sdk_read_before_write_rule():
    client = StrictFirestore({('users', 's', 'people', 'p'): {'id': 'p', 'name': 'Synthetic'}})
    store = FirestoreSpaceStore('s', firestore_client=client)

    def body(tx):
        tx.people.set_pinned('p', True)
        tx.people.read_generation()

    with pytest.raises(ReadAfterWriteError):
        store.run(body)


@pytest.mark.parametrize('key', sorted(PORT_CALLER_DRIVERS))
def test_retained_module_entry_points_execute(key):
    result = run_driver(PORT_CALLER_DRIVERS[key])
    assert not result.errors, (key, result.errors)
    assert result.shapes, key


_PORT_QUERY_KEYS = sorted(
    key for key in DRIVERS if key.startswith(('database.folders.FirestoreFolders.', 'database.people.FirestorePeople.'))
)


@pytest.fixture(scope='module')
def port_query_results():
    return {key: run_driver(DRIVERS[key]) for key in _PORT_QUERY_KEYS}


@pytest.mark.parametrize('key', _PORT_QUERY_KEYS)
def test_repository_query_recipes_execute(port_query_results, key):
    result = port_query_results[key]
    assert not result.errors, (key, result.errors)
    assert result.shapes, key


def test_repository_query_helpers_are_observed(port_query_results):
    for key, entry in COVERED_BY.items():
        if not key.startswith('database.folders.FirestoreFolders.'):
            continue
        assert any(
            calling_key(shape.calling_function) == key
            for owner in entry.covered_by
            for shape in port_query_results[owner].shapes
        ), key
