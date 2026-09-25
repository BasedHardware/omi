"""Real receipt codecs across protection changes; no cloud dependencies."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversations as db
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from tests.unit.test_manual_speaker_assignments import world, read
from utils import encryption


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_stored_protection_level_wins_over_cached_hint(world, level):
    store, path, stale = world
    store.rows[path]['data_protection_level'] = level
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    db.update_conversation_segments(
        'u', 'c', stale, data_protection_level='enhanced' if level == 'standard' else 'standard'
    )
    assert isinstance(store.rows[path]['transcript_segments'], str if level == 'enhanced' else bytes)
    assert read(world)['transcript_segments'][1]['person_id'] == 'new'


@pytest.mark.parametrize('value', [[], 'text', 1, None, False])
def test_invalid_receipt_rejected_only_at_write_boundary(value):
    with pytest.raises(ValueError, match='must be an object'):
        db._prepare_conversation_for_write({'manual_speaker_assignments': value}, 'u', 'standard')
    assert db.decode_manual_speaker_assignments('u', db._protect_json_value(value, 'u', 'standard'), True) == {}


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
@pytest.mark.parametrize('receipt_present', [False, True])
def test_migration_reencodes_receipt_and_transcript_from_current_transaction(
    world, monkeypatch, source, target, receipt_present
):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = source
    if receipt_present:
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    store.rows[path] = db._prepare_conversation_for_write(
        read(world) if receipt_present else store.rows[path], 'u', source
    )
    expected = read(world)
    projection = []

    def get_all(refs, field_paths):
        projection.extend(field_paths)
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = 'c'
            # Simulate an edit committed after the scan's snapshot was obtained.
            if receipt_present:
                db.assign_conversation_speaker('u', 'c', is_user=True, segment_ids=['s0'])
                expected.update(read(world))
            yield snap

    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', MagicMock, raising=False)
    monkeypatch.setattr(
        StrictFirestoreCollection, 'select', lambda self, fields: SimpleNamespace(stream=lambda: []), raising=False
    )
    monkeypatch.setattr(db, 'db', store)
    db.migrate_conversations_level_batch('u', ['c'], target)
    saved = read(world)
    assert saved['transcript_segments'] == expected['transcript_segments']
    assert saved['manual_speaker_assignments'] == expected['manual_speaker_assignments']
    raw = store.rows[path]
    assert raw['data_protection_level'] == target
    assert isinstance(raw['transcript_segments'], str if target == 'enhanced' else bytes)
    if receipt_present:
        assert isinstance(raw['manual_speaker_assignments'], str if target == 'enhanced' else bytes)
    else:
        assert 'manual_speaker_assignments' not in raw
    assert {'manual_speaker_assignments', 'manual_speaker_assignments_compressed'} <= set(projection)
    before = deepcopy(raw)
    # Retry with no intervening edit: already migrated documents stay unchanged.
    monkeypatch.setattr(
        store,
        'get_all',
        lambda refs, field_paths: [SimpleNamespace(exists=True, id='c', reference=ref) for ref in refs],
    )
    db.migrate_conversations_level_batch('u', ['c'], target)
    assert store.rows[path] == before


def test_migration_skips_photo_query_when_has_photos_false(world, monkeypatch):
    store, path, _ = world
    legacy_path = ('users', 'u', 'conversations', 'c2')
    store.rows[path]['data_protection_level'] = 'standard'
    store.rows[path]['has_photos'] = False
    # Legacy doc without the flag; both conversations hold a photo doc.
    store.rows[legacy_path] = dict(
        id='c2', status='completed', transcript_segments=[], data_protection_level='standard'
    )
    for conv_id in ('c', 'c2'):
        store.rows[('users', 'u', 'conversations', conv_id, 'photos', 'p1')] = dict(
            data_protection_level='standard', base64='cGhvdG8='
        )

    projections = []

    def get_all(refs, field_paths):
        projections.append(list(field_paths))
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = ref.path[-1]
            yield snap

    selected = []

    def fake_select(self, fields):
        selected.append(self._path)
        return SimpleNamespace(stream=lambda: iter([]))

    batch = MagicMock()
    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', lambda: batch, raising=False)
    monkeypatch.setattr(StrictFirestoreCollection, 'select', fake_select, raising=False)
    monkeypatch.setattr(db, 'db', store)

    db.migrate_conversations_level_batch('u', ['c', 'c2'], 'enhanced')

    # The gate reads has_photos from the get_all projection.
    assert 'has_photos' in projections[0]
    # has_photos=False never queries photos; the legacy doc without the flag still does.
    assert selected == [('users', 'u', 'conversations', 'c2', 'photos')]
    assert batch.update.call_args_list == []
    assert store.rows[path]['data_protection_level'] == 'enhanced'
    assert store.rows[legacy_path]['data_protection_level'] == 'enhanced'


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
def test_migration_reencrypts_fetched_photos_to_target_level(world, monkeypatch, source, target):
    store, path, _ = world
    plain = 'cGhvdG8tcGF5bG9hZA=='
    stored = plain if source == 'standard' else encryption.encrypt(plain, 'u')
    store.rows[path]['data_protection_level'] = source
    store.rows[path]['has_photos'] = True
    photo_paths = {f'p{i}': ('users', 'u', 'conversations', 'c', 'photos', f'p{i}') for i in (1, 2)}
    for photo_path in photo_paths.values():
        store.rows[photo_path] = dict(data_protection_level=source, base64=stored)

    def get_all(refs, field_paths):
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = ref.path[-1]
            yield snap

    def fake_select(self, fields):
        def stream():
            for photo_path in sorted(photo_paths.values()):
                snap = StrictFirestoreSnapshot(store.rows[photo_path])
                snap.reference = StrictFirestoreDocument(store, photo_path)
                yield snap

        return SimpleNamespace(stream=stream)

    batch = MagicMock()
    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', lambda: batch, raising=False)
    monkeypatch.setattr(StrictFirestoreCollection, 'select', fake_select, raising=False)
    monkeypatch.setattr(db, 'db', store)

    db.migrate_conversations_level_batch('u', ['c'], target)

    updates = {call.args[0].path: call.args[1] for call in batch.update.call_args_list}
    assert set(updates) == set(photo_paths.values())
    for payload in updates.values():
        assert payload['data_protection_level'] == target
        if target == 'enhanced':
            assert encryption.decrypt(payload['base64'], 'u') == plain
        else:
            assert payload['base64'] == plain
    batch.commit.assert_called()
    assert store.rows[path]['data_protection_level'] == target


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_automatic_review_is_emitted_after_commit_and_not_on_retry(world, monkeypatch, level):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = level
    store.rows[path]['transcript_segments'][1]['speaker_match_source'] = 'sync_embedding'
    store.rows[path] = db._prepare_conversation_for_write(store.rows[path], 'u', level)
    observed = []

    def observe(uid, conversation_id, before, after):
        # The callback sees a durably committed manual label and cleared marker.
        saved = read(world)['transcript_segments'][1]
        assert saved['person_id'] == 'new' and saved['speaker_match_source'] is None
        observed.append(before[0].get('speaker_match_source'))

    monkeypatch.setattr(db, 'record_speaker_review', observe)
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert observed == ['sync_embedding', None]


@pytest.mark.parametrize('field,error', [('is_locked', PermissionError), ('deleted', LookupError)])
def test_blocked_manual_write_never_emits_review(world, monkeypatch, field, error):
    store, path, _ = world
    store.rows[path][field] = True
    observed = []
    monkeypatch.setattr(db, 'record_speaker_review', lambda *args: observed.append(args))
    with pytest.raises(error):
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert observed == []
