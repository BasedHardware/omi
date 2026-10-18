"""Count SDK-boundary reads and preserve sync bridge/lifecycle decisions."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope='module')
def modules():
    # These external-effect modules are not under test; retain the actual
    # conversation getters/decorators and bridge orchestration.
    from testing.import_isolation import AutoMockModule, stub_modules

    names = ('utils.conversations.merge_conversations', 'utils.conversations.action_item_refresh')
    with stub_modules({name: AutoMockModule(name) for name in names}):
        from database import conversations
        from utils.agent_capabilities import transcripts
        from utils.sync import bridge, provenance
        from utils.sync import fsr_metadata

        yield SimpleNamespace(db=conversations, bridge=bridge, provenance=provenance, metadata=fsr_metadata)


class Snapshot:
    def __init__(self, row):
        self.row = deepcopy(row)
        self.exists = row is not None
        self.update_time = None

    def to_dict(self):
        return deepcopy(self.row)


class Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, name):
        return Ref(self.store, self.path + (name,))

    def document(self, name):
        return Ref(self.store, self.path + (name,))

    def get(self, *, field_paths=None):
        self.store.doc_reads += 1
        self.store.projections.append(field_paths)
        row = deepcopy(self.store.rows.get(self.path))
        if field_paths is not None and row is not None:
            projected = {}
            for field in field_paths:
                if '.' in field:
                    parent, child = field.split('.')
                    if child in (row.get(parent) or {}):
                        projected.setdefault(parent, {})[child] = row[parent][child]
                elif field in row:
                    projected[field] = row[field]
            row = projected
        return Snapshot(row)

    def stream(self):
        assert self.path[-1] == 'photos'
        rows = self.store.photos.get(self.path[-2], [])
        self.store.photo_reads += max(1, len(rows))
        return iter(Snapshot(row) for row in rows)


class Store:
    def __init__(self, rows, photos=None):
        self.rows = {('users', 'u', 'conversations', key): deepcopy(row) for key, row in rows.items()}
        self.photos = photos or {}
        self.doc_reads = self.photo_reads = 0
        self.projections = []

    def collection(self, name):
        return Ref(self, (name,))


@pytest.fixture
def wire(monkeypatch, modules):
    def connect(rows, photos=None):
        store = Store(rows, photos)
        monkeypatch.setattr(modules.db, 'db', store)
        monkeypatch.setattr(modules.db, 'get_firestore_client', lambda: store)
        monkeypatch.setattr(modules.bridge, 'smart_merge_flatten_enabled', lambda: True)
        return store

    return connect


def enable(monkeypatch, enabled):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}' if enabled else '')


@pytest.mark.parametrize('photo_count', [0, 3])
@pytest.mark.parametrize('marker', [None, False, True])
def test_per_task_bridge_read_proof_and_identical_cleanup(monkeypatch, modules, wire, photo_count, marker):
    rows = {
        'survivor': {'id': 'survivor', 'sync_merged_from': ['donor'], 'private_cloud_sync_enabled': True},
        'donor': {'id': 'donor', 'deleted': True, 'sync_merged_into': 'survivor', 'sync_content_revision': 4},
    }
    if marker is not None:
        for row in rows.values():
            row['has_photos'] = marker
    photos = {key: [{'base64': 'image'}] * photo_count for key in rows}
    results = []
    for enabled in (False, True):
        enable(monkeypatch, enabled)
        store = wire(rows, photos)
        effects = []
        monkeypatch.setattr(modules.bridge, 'transfer_donor', lambda *a: effects.append(('transfer', a)))
        monkeypatch.setattr(modules.bridge, 'retract_sync_bridge_source', lambda *a: effects.append(('retract', a)))
        monkeypatch.setattr(modules.bridge, 'copy_sync_bridge_audio', lambda *a: effects.append(('audio', a)))
        monkeypatch.setattr(
            modules.bridge, 'mark_sync_bridge_cleaned', lambda *a: effects.append(('checkpoint', a)) or True
        )
        result = modules.bridge.finish_sync_bridges('u', 'survivor')
        results.append((result, effects, store.doc_reads, store.photo_reads))
    assert results[0][:3] == results[1][:3]
    assert results[0][2] == 3  # survivor + donor + fresh survivor recheck
    assert results[1][3] == 0
    assert results[0][3] == (0 if marker is False else 3 * max(1, photo_count))
    assert [effect[0] for effect in results[1][1]] == ['transfer', 'retract', 'audio', 'checkpoint']


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('change', ['deleted', 'redirect', 'revision', 'copy_failure'])
def test_no_stale_bridge_snapshot_after_external_effect(monkeypatch, modules, wire, enabled, change):
    enable(monkeypatch, enabled)
    store = wire(
        {
            'survivor': {'id': 'survivor', 'sync_merged_from': ['donor'], 'private_cloud_sync_enabled': True},
            'donor': {'id': 'donor', 'deleted': True, 'sync_merged_into': 'survivor', 'sync_content_revision': 4},
            'next': {'id': 'next'},
        }
    )
    monkeypatch.setattr(modules.bridge, 'transfer_donor', lambda *a: None)
    monkeypatch.setattr(modules.bridge, 'retract_sync_bridge_source', lambda *a: None)
    marks = []

    def copy(*args):
        if change == 'copy_failure':
            raise RuntimeError('copy failed')
        if change == 'revision':
            store.rows[('users', 'u', 'conversations', 'donor')]['sync_content_revision'] = 5
        else:
            row = store.rows[('users', 'u', 'conversations', 'survivor')]
            row['deleted'] = True
            if change == 'redirect':
                row['sync_merged_into'] = 'next'

    def mark(uid, source, revision, target):
        marks.append((source, revision, target))
        return store.rows[('users', uid, 'conversations', source)]['sync_content_revision'] == revision

    monkeypatch.setattr(modules.bridge, 'copy_sync_bridge_audio', copy)
    monkeypatch.setattr(modules.bridge, 'mark_sync_bridge_cleaned', mark)
    if change == 'redirect':
        assert modules.bridge.finish_sync_bridges('u', 'survivor') == 'next'
    elif change == 'deleted':
        with pytest.raises(modules.bridge.SyncAssignmentSuperseded):
            modules.bridge.finish_sync_bridges('u', 'survivor')
    else:
        with pytest.raises(RuntimeError, match='copy failed|completion revision changed'):
            modules.bridge.finish_sync_bridges('u', 'survivor')
    if change == 'copy_failure':
        assert marks == []


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('case', ['missing', 'deleted', 'cycle', 'bad_donor', 'wrong_flatten_target'])
def test_bridge_rejects_unsafe_lifecycle_shapes(monkeypatch, modules, wire, enabled, case):
    enable(monkeypatch, enabled)
    rows = {'survivor': {'id': 'survivor'}}
    if case == 'missing':
        rows = {}
    elif case == 'deleted':
        rows['survivor']['deleted'] = True
    elif case == 'cycle':
        rows['survivor']['sync_merged_into'] = 'survivor'
    else:
        rows['survivor'].update(sync_merged_from=['donor'], smart_merge={'role': 'survivor'})
        rows['donor'] = {'id': 'donor', 'deleted': case != 'bad_donor', 'sync_merged_into': 'wrong'}
    wire(rows)
    with pytest.raises((modules.bridge.SyncAssignmentSuperseded, modules.bridge.SyncAssignmentConflict)):
        modules.bridge.finish_sync_bridges('u', 'survivor')


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('device', ['device', 'other', None])
def test_provenance_keeps_device_and_time_decisions(monkeypatch, modules, wire, enabled, device):
    enable(monkeypatch, enabled)
    moment = datetime.fromtimestamp(1000, timezone.utc)
    store = wire({'c': {'id': 'c', 'client_device_id': 'device', 'started_at': moment}})
    monkeypatch.setattr(
        modules.provenance, 'capture_times_within_window', lambda files, lo, hi: lo == -800 and hi == 2800
    )
    assert modules.provenance.capture_matches_server_conversation('u', 'c', ['file'], device) is (device == 'device')
    assert store.doc_reads == (0 if device is None else 1)
    assert store.photo_reads == (1 if device is not None and not enabled else 0)


def test_metadata_is_uid_gated_and_does_not_read_transcripts(monkeypatch, modules):
    calls = []
    monkeypatch.setattr(modules.metadata, 'lever_enabled', lambda name, uid: calls.append((name, uid)) or uid == 'on')
    db = SimpleNamespace(
        get_conversation=MagicMock(return_value={'id': 'c'}), get_conversation_raw_snapshot=MagicMock(return_value={})
    )
    assert modules.metadata.read_metadata(db, 'on', 'c', operation='bridge') == {'id': 'c'}
    modules.metadata.read_metadata(db, 'off', 'c', operation='bridge')
    assert calls == [('backfill_task_reads', 'on'), ('backfill_task_reads', 'off')]
    fields = db.get_conversation_raw_snapshot.call_args.kwargs['field_paths']
    assert 'transcript_segments' not in fields and 'photos' not in fields
    db.get_conversation.assert_called_once_with('off', 'c')
