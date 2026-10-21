"""A2 shadow: projection writes outside Store.run re-copy every batch row they touch (owner watermark included)."""

from __future__ import annotations

from datetime import datetime, timezone
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


def test_persist_empty_mirrors_after_its_own_commit():
    """Silence, no_recoverable_speech, superseded and empty-word parts commit through persist_empty."""
    from database.batch_pipeline_projection_session import ProjectionSession

    order = []
    session = object.__new__(ProjectionSession)
    session.policy = None
    session.store = SimpleNamespace(
        run=lambda commit, policy=None: order.append('commit') or 'receipt',
        mirror_assignment=lambda s: order.append(('mirror', s)),
    )
    assert session.persist_empty() == 'receipt'
    assert order == ['commit', ('mirror', session)]


# -- other writers of mirrored tables outside Store.run ---------------------------------------------


class Snap:
    def __init__(self, doc, ident='x'):
        self._doc, self.id, self.exists = doc, ident, doc is not None
        self.reference = SimpleNamespace(update=Mock(), delete=Mock())

    def to_dict(self):
        return self._doc


class Ref:
    def __init__(self, doc):
        self.doc = doc

    def get(self, transaction=None):
        return Snap(self.doc)


class Client:
    def __init__(self, docs):
        self.docs = docs  # {(collection, key): doc}

    def collection(self, name):
        return SimpleNamespace(document=lambda key: Ref(self.docs.get((name, key))))

    def transaction(self, **options):  # max_attempts=1 from main's retried retention transaction (sync 15)
        return SimpleNamespace(update=Mock())


@pytest.fixture
def plain_transactions(monkeypatch):
    from google.cloud import firestore

    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)


def test_a_fenced_revocation_refreshes_the_job(monkeypatch, plain_transactions):
    from database import batch_pipeline_recovery as recovery
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    calls = []
    monkeypatch.setattr(recovery, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
    monkeypatch.setattr(recovery, 'assert_batch_write_allowed', Mock(side_effect=BatchPrivacyBlocked('fenced')))
    client = Client({('batch_pipeline_dev_jobs', 'j'): {'state': 'leased', 'owner_id': 'u'}})
    assert recovery.quarantine_fenced(client, 'batch_pipeline_dev', 'j', 1.0) is True
    assert calls == [('batch_pipeline_dev', [('jobs', 'j')])]
    calls.clear()
    monkeypatch.setattr(recovery, 'assert_batch_write_allowed', Mock(return_value=1))  # not fenced: no write
    assert recovery.quarantine_fenced(client, 'batch_pipeline_dev', 'j', 1.0) is False
    assert calls == []


def test_completion_retention_refreshes_every_row_it_stamps(monkeypatch, plain_transactions):
    from utils.batch_pipeline import retention

    calls = []
    monkeypatch.setattr(retention, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
    owner = retention.privacy_owner_key('u')
    client = Client(
        {
            ('batch_pipeline_dev_jobs', 's'): {'owner_id': 'u', 'projection_binding': {'job_id': 'i'}},
            ('batch_pipeline_dev_results', 's'): {'owner_key': owner, 'projection_state': 'completed'},
            ('batch_pipeline_dev_intakes', 'i'): {'n': 1},
        }
    )
    monkeypatch.setattr(retention.queries, 'segment_artifacts', lambda *a: [Snap({'kind': 'result'}, 'a1')])
    store = SimpleNamespace(client=client, namespace='batch_pipeline_dev')
    assert retention.expire_completed_segment(store, 'u', 's', 1.0) is True
    assert calls == [('batch_pipeline_dev', [('jobs', 's'), ('results', 's'), ('intakes', 'i'), ('artifacts', 'a1')])]


def test_artifact_cleanup_refreshes_what_it_touched(monkeypatch):
    from utils.batch_pipeline import retention

    calls = []
    monkeypatch.setattr(retention, 'mirror_refresh', lambda ns, keys: calls.append((ns, keys)))
    artifacts = [Snap({'owner_id': 'u', 'uri': 'gs://b/1'}, 'a1'), Snap({'owner_id': 'u', 'uri': 'gs://b/2'}, 'a2')]
    artifacts[1]._doc['erasure_requested'] = True
    monkeypatch.setattr(retention.queries, 'due_artifacts', lambda *a: artifacts)
    store = SimpleNamespace(client=None, namespace='batch_pipeline_dev')
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert retention.cleanup_completed_artifacts(store, now, delete_uri=lambda *a: None) == 2
    assert calls == [('batch_pipeline_dev', [('artifacts', 'a1'), ('artifacts', 'a2')])]
