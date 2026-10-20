"""A2 shadow: projection writes outside Store.run re-copy every batch row they touch (owner watermark included)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import database.batch_pipeline_projection as projection_store
from utils.batch_pipeline import projection as projector_module
from utils.batch_pipeline.scheduler import owner_key


def binding(owner='owner-1'):
    return SimpleNamespace(owner_id=owner, segment_ids=('s1', 's2'))


@pytest.fixture
def refreshed(monkeypatch):
    calls = []
    monkeypatch.setattr(projection_store, 'mirror_refresh', lambda ns, keys: calls.append((ns, list(keys))))
    return calls


def test_every_projection_mirror_names_the_owner_row(refreshed):
    store = projection_store.ProjectionStore(Mock(namespace='batch_pipeline_dev'))
    store._mirror(binding())
    ((namespace, keys),) = refreshed
    assert namespace == 'batch_pipeline_dev'
    assert keys == [
        ('jobs', 's1'), ('results', 's1'), ('jobs', 's2'), ('results', 's2'), ('owners', owner_key('owner-1')),
    ]  # fmt: skip


def test_assignment_mirror_adds_the_erased_predecessors(refreshed):
    store = projection_store.ProjectionStore(Mock(namespace='batch_pipeline_dev'))
    session = SimpleNamespace(
        binding=binding(), erased_predecessors=[SimpleNamespace(id='p0'), SimpleNamespace(id='p1')]
    )
    store.mirror_assignment(session)
    ((_, keys),) = refreshed
    assert keys[-3:] == [('owners', owner_key('owner-1')), ('results', 'p0'), ('results', 'p1')]


def test_record_silence_assignment_mirrors_even_when_the_transaction_fails(monkeypatch):
    mirrored = []
    projector = object.__new__(projector_module.Projector)
    projector.store = SimpleNamespace(client=None, mirror_assignment=mirrored.append)

    def fail(*args, **kwargs):
        raise RuntimeError('contention')

    monkeypatch.setattr(projector_module.conversations_db, 'assign_sync_conversation', fail)
    session = SimpleNamespace(
        prepare=None, validate_plan=None, policy=SimpleNamespace(projection_contention=False, projection_timing=None)
    )
    item = SimpleNamespace(capture_at=1.0, duration_seconds=2.0)
    bound = SimpleNamespace(target_conversation_id='c', data_protection_level='standard', owner_id='o')
    with pytest.raises(RuntimeError):
        projector.assign_record_silence(item, bound, session)
    assert mirrored == [session]


def test_the_assignment_hook_never_raises():
    projector = object.__new__(projector_module.Projector)
    projector.store = SimpleNamespace(mirror_assignment=Mock(side_effect=RuntimeError('boom')))
    projector._mirror_assignment(SimpleNamespace())  # swallowed and logged
    projector.store = SimpleNamespace()  # a store without the hook (fakes, older seams)
    projector._mirror_assignment(SimpleNamespace())
