"""Count actual lookups and exercise the ordinary codecs with synthetic speech."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import zlib

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations
    from routers import conversations as routes
    from utils.sync import bridge


@pytest.fixture
def world(monkeypatch):
    from database import conversations
    from database.firestore_read_origin import current_read_origin

    store, reads = StrictFirestore(), []
    original = StrictFirestoreDocument.get
    revision = datetime(2026, 10, 23, tzinfo=timezone.utc)

    def get(reference, *args, **kwargs):
        reads.append((reference.path, current_read_origin()))
        snapshot = original(reference, *args, **kwargs)
        snapshot.update_time = revision
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(conversations, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(conversations, 'db', store)
    donor = {'id': 'donor', 'deleted': True, 'sync_merged_into': 'survivor', 'has_photos': False}
    segments = [
        {'id': 's', 'text': 'Synthetic speech.', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0, 'end': 1}
    ]
    survivor = {
        'id': 'survivor',
        'owner_uid': 'u',
        'data_protection_level': 'standard',
        'transcript_segments': zlib.compress(json.dumps(segments).encode()),
        'transcript_segments_compressed': True,
        'has_photos': False,
        'sync_content_revision': 7,
        'created_at': revision,
        'started_at': revision,
        'finished_at': revision,
        'structured': {'title': 'Synthetic', 'overview': 'Synthetic summary', 'emoji': '📝', 'category': 'other'},
    }
    store.rows[('users', 'u', 'conversations', 'donor')] = donor
    store.rows[('users', 'u', 'conversations', 'survivor')] = survivor
    return conversations, store, reads, revision


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_redirect_hydration_uses_four_reads_instead_of_five_with_identical_content(world, monkeypatch, level):
    conversations, store, reads, revision = world
    if level == 'enhanced':
        row = deepcopy(store.rows[('users', 'u', 'conversations', 'survivor')])
        row['transcript_segments'] = json.loads(zlib.decompress(row['transcript_segments']))
        row.pop('transcript_segments_compressed')
        row['data_protection_level'] = level
        store.rows[('users', 'u', 'conversations', 'survivor')] = conversations._prepare_conversation_for_write(
            row, 'u', level
        )
    before = deepcopy(store.rows)
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', 'false')
    legacy = conversations.get_sync_redirected_conversation('u', 'donor')
    assert len(reads) == 5
    old_paths = [path for path, _ in reads]
    reads.clear()
    monkeypatch.delenv('SYNC_OPERATION_SNAPSHOT_ENABLED')
    current = conversations.get_sync_redirected_conversation('u', 'donor')
    assert len(reads) == 4
    assert [path for path, _ in reads] == old_paths[:-1]
    assert {origin for _, origin in reads} == {'job:sync_operation_snapshot'}
    assert current == legacy
    assert current['updated_at'] == revision
    assert current['sync_content_revision'] == 7
    assert current['transcript_segments'][0]['text'] == 'Synthetic speech.'
    assert current['transcript_segments'][0]['speaker'] == 'SPEAKER_00'
    assert store.rows == before  # Stored compressed bytes never change.
    current['transcript_segments'][0]['text'] = 'Changed only in the caller.'
    assert conversations.get_sync_redirected_conversation('u', 'donor') == legacy


def test_legacy_photo_hydration_is_identical(world, monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection, StrictFirestoreSnapshot

    conversations, store, _, _ = world
    store.rows[('users', 'u', 'conversations', 'survivor')].pop('has_photos')
    photo = {'id': 'photo', 'data_protection_level': 'standard', 'description': 'Synthetic photo'}
    monkeypatch.setattr(StrictFirestoreCollection, 'stream', lambda *args: iter([StrictFirestoreSnapshot(photo)]))
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', 'false')
    legacy = conversations.get_sync_redirected_conversation('u', 'donor')
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', 'true')
    assert conversations.get_sync_redirected_conversation('u', 'donor') == legacy
    assert legacy['photos'] == [photo]


@pytest.mark.parametrize('mode,expected_reads', [('true', 4), ('false', 5)])
@pytest.mark.parametrize('injected', [True, False])
def test_one_client_covers_resolution_hydration_and_legacy_photos(world, monkeypatch, mode, expected_reads, injected):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreCollection, StrictFirestoreSnapshot

    conversations, store, reads, _ = world
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
    store.rows[('users', 'u', 'conversations', 'survivor')].pop('has_photos')
    before = deepcopy(store.rows)
    photo = {'id': 'photo', 'data_protection_level': 'standard', 'description': 'Scoped synthetic photo'}
    factory_calls, photo_reads = [], []

    class UnusableLegacyClient:
        def collection(self, name):
            pytest.fail('redirect hydration escaped to the legacy client')

    def factory():
        assert not injected, 'an explicitly injected client must bypass the global factory'
        factory_calls.append(True)
        return store

    def photos(collection):
        assert collection._database is store
        photo_reads.append(collection._path)
        return iter([StrictFirestoreSnapshot(photo)])

    monkeypatch.setattr(conversations, 'db', UnusableLegacyClient())
    monkeypatch.setattr(conversations, 'get_firestore_client', factory)
    monkeypatch.setattr(StrictFirestoreCollection, 'stream', photos)
    kwargs = {'firestore_client': store} if injected else {}
    result = conversations.get_sync_redirected_conversation('u', 'donor', **kwargs)
    assert len(reads) == expected_reads
    assert factory_calls == ([] if injected else [True])
    assert photo_reads == [('users', 'u', 'conversations', 'survivor', 'photos')]
    assert result['photos'] == [photo]
    assert result['transcript_segments'][0]['text'] == 'Synthetic speech.'
    assert store.rows == before


def test_redirect_resolver_accepts_scoped_client_without_global_lookup(world, monkeypatch):
    conversations, store, reads, _ = world

    def unexpected_factory():
        pytest.fail('explicit client must bypass the global factory')

    monkeypatch.setattr(conversations, 'get_firestore_client', unexpected_factory)
    assert conversations.resolve_sync_conversation_redirect('u', 'donor', firestore_client=store) == 'survivor'
    assert len(reads) == 4
    store.rows[('users', 'u', 'deleted_conversations', 'survivor')] = {'deleted': True}
    assert conversations.resolve_sync_conversation_redirect('u', 'donor', firestore_client=store) is None


@pytest.mark.parametrize('mode', ['true', 'false'])
def test_invalid_redirect_id_does_not_initialize_a_client(world, monkeypatch, mode):
    conversations, _, reads, _ = world
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)

    def unexpected_factory():
        pytest.fail('invalid path must be rejected before client initialization')

    monkeypatch.setattr(conversations, 'get_firestore_client', unexpected_factory)
    assert conversations.get_sync_redirected_conversation('u', 'invalid/path') is None
    assert reads == []


@pytest.mark.parametrize('mode', ['true', 'false'])
def test_legacy_survivor_routes_by_resolved_path_without_stored_id(world, monkeypatch, mode):
    conversations, store, _, _ = world
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
    store.rows[('users', 'u', 'conversations', 'survivor')].pop('id')
    row = conversations.get_sync_redirected_conversation('u', 'donor')
    assert row['id'] == 'survivor'
    assert row['transcript_segments'][0]['text'] == 'Synthetic speech.'
    assert 'id' not in store.rows[('users', 'u', 'conversations', 'survivor')]


@pytest.mark.parametrize('mode', ['true', 'false'])
@pytest.mark.parametrize('defect', ['donor_marker', 'survivor_marker', 'deleted', 'owner', 'path', 'cycle', 'missing'])
def test_all_redirect_rejections_are_identical(world, monkeypatch, mode, defect):
    conversations, store, _, _ = world
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
    survivor = store.rows[('users', 'u', 'conversations', 'survivor')]
    if defect.endswith('_marker'):
        key = 'donor' if defect == 'donor_marker' else 'survivor'
        store.rows[('users', 'u', 'deleted_conversations', key)] = {'deleted': True}
    elif defect == 'deleted':
        survivor['deleted'] = True
    elif defect == 'owner':
        survivor['owner_uid'] = 'another-owner'
    elif defect == 'path':
        survivor['id'] = 'another-id'
    elif defect == 'cycle':
        survivor.update(deleted=True, sync_merged_into='donor')
    else:
        del store.rows[('users', 'u', 'conversations', 'survivor')]
    assert conversations.get_sync_redirected_conversation('u', 'donor') is None


def test_new_operation_refreshes_after_delete_redirect_or_source_mutation(world):
    conversations, store, reads, _ = world
    assert conversations.get_sync_redirected_conversation('u', 'donor')['sync_content_revision'] == 7
    survivor = store.rows[('users', 'u', 'conversations', 'survivor')]
    survivor['sync_content_revision'] = 8
    assert conversations.get_sync_redirected_conversation('u', 'donor')['sync_content_revision'] == 8
    survivor.update(deleted=True, sync_merged_into='new')
    store.rows[('users', 'u', 'conversations', 'new')] = {
        'id': 'new',
        'has_photos': False,
        'data_protection_level': 'standard',
    }
    assert conversations.get_sync_redirected_conversation('u', 'donor')['id'] == 'new'
    store.rows[('users', 'u', 'deleted_conversations', 'new')] = {}
    assert conversations.get_sync_redirected_conversation('u', 'donor') is None
    assert len(reads) > 4


@pytest.mark.parametrize('cid,max_hops', [('', 16), ('bad/path', 16), ('x' * 257, 16), ('valid', 0)])
def test_invalid_redirect_never_constructs_a_client(world, monkeypatch, cid, max_hops):
    conversations, _, reads, _ = world

    def unavailable():
        raise AssertionError('invalid ids must be rejected before client resolution')

    monkeypatch.setattr(conversations, 'get_firestore_client', unavailable)
    assert conversations.resolve_sync_conversation_redirect('u', cid, max_hops=max_hops) is None
    assert reads == []


def test_real_detail_route_has_identical_response_and_refreshes_deletion(world, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import conversations as routes

    _, store, reads, _ = world
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    responses = []
    with TestClient(app) as client:
        for mode in ('false', 'true'):
            monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
            reads.clear()
            response = client.get('/v1/conversations/donor')
            assert response.status_code == 200, response.text
            responses.append(response.json())
        assert responses[0] == responses[1]
        assert responses[1]['id'] == 'survivor'
        assert responses[1]['transcript_segments'][0]['text'] == 'Synthetic speech.'
        store.rows[('users', 'u', 'deleted_conversations', 'survivor')] = {}
        assert client.get('/v1/conversations/donor').status_code == 404


@pytest.mark.parametrize('mode,metadata,expected', [('true', True, 1), ('false', True, 2), ('true', False, 2)])
def test_bridge_without_effects_reads_survivor_once(world, monkeypatch, mode, metadata, expected):
    from utils.sync import bridge

    conversations, _, reads, _ = world
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
    monkeypatch.setattr(bridge, 'lever_enabled', lambda *args: metadata)
    monkeypatch.setattr(
        bridge, 'read_metadata', lambda database, uid, cid, **kw: database.get_conversation_raw_snapshot(uid, cid)
    )
    assert bridge.finish_sync_bridges('u', 'survivor') == 'survivor'
    assert len(reads) == expected
    assert {path[-1] for path, _ in reads} == {'survivor'}


@pytest.mark.parametrize('mode', ['true', 'false'])
@pytest.mark.parametrize('redirect', [True, False])
def test_bridge_refreshes_after_donor_reads_even_without_effects(monkeypatch, mode, redirect):
    from utils.sync import bridge

    reads = []
    changed = False
    monkeypatch.setenv('SYNC_OPERATION_SNAPSHOT_ENABLED', mode)
    monkeypatch.setattr(bridge, 'lever_enabled', lambda *args: True)

    def read(_database, _uid, cid, **kwargs):
        nonlocal changed
        reads.append(cid)
        if cid == 'donor':
            changed = True
            return {
                'id': cid,
                'deleted': True,
                'sync_merged_into': 'survivor',
                'sync_content_revision': 1,
                'sync_bridge_cleaned_revision': 1,
            }
        if cid == 'new':
            return {'id': cid}
        if changed:
            return {'id': cid, 'deleted': True, **({'sync_merged_into': 'new'} if redirect else {})}
        return {'id': cid, 'sync_merged_from': ['donor']}

    def unexpected(*args, **kwargs):
        raise AssertionError('settled lineage must perform no effects')

    monkeypatch.setattr(bridge, 'read_metadata', read)
    for name in ('transfer_donor', 'retract_sync_bridge_source', 'copy_sync_bridge_audio', 'mark_sync_bridge_cleaned'):
        monkeypatch.setattr(bridge, name, unexpected)
    if redirect:
        assert bridge.finish_sync_bridges('u', 'survivor') == 'new'
        assert reads[:4] == ['survivor', 'donor', 'survivor', 'new']
    else:
        with pytest.raises(bridge.SyncAssignmentSuperseded):
            bridge.finish_sync_bridges('u', 'survivor')
        assert reads == ['survivor', 'donor', 'survivor']


@pytest.mark.parametrize('effect', ['transfer', 'retract', 'copy', 'receipt', 'failed_transfer'])
def test_bridge_refreshes_after_every_effect_including_refused_transfer(monkeypatch, effect):
    from utils.sync import bridge

    reads = []
    changed = False
    survivor = {'id': 'survivor', 'sync_merged_from': ['donor'], 'private_cloud_sync_enabled': effect == 'copy'}
    donor = {'id': 'donor', 'deleted': True, 'sync_merged_into': 'survivor', 'sync_content_revision': 1}

    def read(_database, _uid, cid, **kwargs):
        reads.append(cid)
        if cid == 'donor':
            return deepcopy(donor)
        return {'id': cid, 'deleted': True} if changed else deepcopy(survivor)

    def mutate(*args, **kwargs):
        nonlocal changed
        changed = True
        return True

    def fail_transfer(*args, **kwargs):
        mutate()
        raise RuntimeError('synthetic partial effect')

    monkeypatch.setattr(bridge, 'sync_finalize_target_recovery_enabled', lambda: True)
    monkeypatch.setattr(bridge, 'lever_enabled', lambda *args: True)
    monkeypatch.setattr(bridge, 'read_metadata', read)
    monkeypatch.setattr(
        bridge,
        'transfer_donor',
        fail_transfer if effect == 'failed_transfer' else mutate if effect == 'transfer' else lambda *a: None,
    )
    monkeypatch.setattr(bridge, 'retract_sync_bridge_source', mutate if effect == 'retract' else lambda *a: None)
    monkeypatch.setattr(bridge, 'copy_sync_bridge_audio', mutate if effect == 'copy' else lambda *a: None)
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', mutate if effect == 'receipt' else lambda *a: True)
    with pytest.raises(bridge.SyncAssignmentSuperseded):
        bridge.finish_sync_bridges('u', 'survivor')
    assert reads == ['survivor', 'donor', 'survivor']
