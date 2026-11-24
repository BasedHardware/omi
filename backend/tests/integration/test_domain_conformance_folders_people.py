"""Domain semantics, exercised exclusively through ports and the synthetic harness.

OMI_REQUIRE_STORE_BACKENDS=sim,emulator requires both implementations; a skip
never counts as an emulator proof. All data is synthetic and loopback-only.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from database.ports.base import MutationConflict, RevisionConflict
from database.ports.folders import FolderCreate, FolderEntity, FolderUpdate, resolve_category_folder_id
from database.ports.people import PersonDraft, PersonEntity
from testing.domain_fixtures import domain_backend

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_crud_types_and_unknown_fields(domain_backend):
    h = domain_backend
    sid = h.space('crud')
    repo = h.folders(sid)
    row = repo.create(FolderCreate(name='Test', description='description'))
    assert isinstance(row, FolderEntity) and type(row.order) is int
    assert row.created_at.tzinfo is not None and row.revision == 1
    h.seed(sid, 'folders', 'legacy', {'name': 'legacy', 'order': 4, 'created_at': NOW, 'unknown': {'x': 1}})
    legacy = repo.get('legacy')
    assert legacy.created_at == NOW and legacy.model_extra['unknown'] == {'x': 1}
    updated = repo.update(row.id, FolderUpdate(description=None))
    assert updated.name == 'Test' and updated.description is None
    assert updated.revision > row.revision
    assert repo.update(row.id, FolderUpdate()).revision == updated.revision
    assert repo.get_by_category_mapping('none') is None


def test_malformed_storage_is_not_wire_validation(domain_backend):
    h = domain_backend
    sid = h.space('malformed')
    h.seed(sid, 'folders', 'legacy', {'name': None, 'order': 0, 'color': 42, 'unknown': 'keep'})
    row = h.folders(sid).get('legacy')
    assert row.name is None and row.color == 42 and row.model_extra['unknown'] == 'keep'


def test_keyset_byte_order_and_deleted_cursor(domain_backend):
    h = domain_backend
    sid = h.space('pages')
    repo = h.folders(sid)
    for fid in ['ä', 'a', 'z', 'B']:
        h.seed(sid, 'folders', fid, {'name': fid, 'order': 0})
    first = repo.list(limit=2)
    assert [row.id for row in first.items] == ['B', 'a']
    repo.delete('a')
    h.seed(sid, 'folders', 'A', {'name': 'insert before cursor', 'order': 0})
    h.seed(sid, 'folders', 'b', {'name': 'insert after cursor', 'order': 0})
    second = repo.list(limit=2, cursor=first.next_cursor)
    assert [row.id for row in second.items] == ['b', 'z']
    last = repo.list(limit=2, cursor=second.next_cursor)
    assert [row.id for row in last.items] == ['ä'] and last.next_cursor is None
    assert repo.list(limit=10).next_cursor is None
    with pytest.raises(ValueError):
        repo.list(limit=0)


def test_folder_cas(domain_backend):
    h = domain_backend
    sid = h.space('cas')
    repo = h.folders(sid)
    row = repo.create(FolderCreate(name='Before'))
    next_row = repo.update(row.id, FolderUpdate(name='After'), expected_revision=row.revision)
    with pytest.raises(RevisionConflict) as error:
        repo.update(row.id, FolderUpdate(name='Stale'), expected_revision=row.revision)
    assert error.value.space_id == sid and error.value.entity == 'folders'
    assert error.value.entity_id == row.id and error.value.current_revision == next_row.revision
    with pytest.raises(RevisionConflict):
        repo.delete(row.id, expected_revision=row.revision)
    assert repo.get(row.id).name == 'After'
    assert repo.delete(row.id, expected_revision=next_row.revision)
    assert repo.get(row.id) is None


def test_folder_receipts(domain_backend):
    h = domain_backend
    repo = h.folders(h.space('receipts'))
    row = repo.create(FolderCreate(name='One'), mutation_id='create')
    assert repo.create(FolderCreate(name='One'), mutation_id='create').id == row.id
    assert len(repo.list().items) == 1
    with pytest.raises(MutationConflict):
        repo.create(FolderCreate(name='Different'), mutation_id='create')
    changed = repo.update(row.id, FolderUpdate(name='Two'), mutation_id='update')
    assert repo.update(row.id, FolderUpdate(name='Two'), mutation_id='update').revision == changed.revision
    with pytest.raises(MutationConflict):
        repo.update(row.id, FolderUpdate(name='Three'), mutation_id='update')
    assert repo.delete(row.id, mutation_id='delete')
    assert repo.delete(row.id, mutation_id='delete')
    with pytest.raises(MutationConflict):
        repo.create(FolderCreate(name='One'), mutation_id='create')


def test_people_generation_fences_and_replay(domain_backend):
    h = domain_backend
    sid = h.space('generation')
    repo = h.people(sid)
    assert repo.read_generation() is None
    draft = PersonDraft(id='p', name='Synthetic', embedding=[1, 2], updated_at=NOW)
    created = repo.get_or_create_by_name(draft, mutation_id='create')
    assert isinstance(created, PersonEntity) and created.model_extra['embedding'] == [1, 2]
    # Create returns the unprojected draft, not is_user_created added in storage.
    assert 'is_user_created' not in created.model_fields_set
    first = repo.read_generation()
    assert first.value == 1
    assert repo.get_or_create_by_name(draft, mutation_id='create').id == 'p'
    assert repo.read_generation() == first
    existing = repo.get_or_create_by_name(PersonDraft(id='other', name='Synthetic'))
    assert existing.id == 'p' and existing.model_extra['voice_learning_state'] == 'unknown'
    assert repo.read_generation() == first
    with pytest.raises(MutationConflict):
        repo.get_or_create_by_name(PersonDraft(id='other', name='Different'), mutation_id='create')
    pinned = repo.set_pinned('p', True, now=NOW, mutation_id='pin')
    second = repo.read_generation()
    assert second.value == first.value + 1 and second.token != first.token
    assert repo.set_pinned('p', True, now=NOW + timedelta(days=1)).pinned_at == NOW
    assert repo.read_generation() == second
    assert repo.set_pinned('p', True, mutation_id='pin').revision == pinned.revision
    assert repo.read_generation() == second
    with pytest.raises(MutationConflict):
        repo.set_pinned('p', False, mutation_id='pin')
    with pytest.raises(RevisionConflict) as error:
        repo.set_pinned('p', False, expected_revision=pinned.revision - 1)
    assert error.value.current_revision == pinned.revision
    repo.set_pinned('p', False, expected_revision=pinned.revision)
    assert repo.read_generation().value == second.value + 1


def test_legacy_person_revision_advances(domain_backend):
    h = domain_backend
    sid = h.space('legacy-person')
    h.seed(sid, 'people', 'p', {'name': 'Legacy', 'private_extension': 'keep'})
    repo = h.people(sid)
    row = repo.set_pinned('p', True, expected_revision=1)
    assert row.revision == 2 and row.model_extra['private_extension'] == 'keep'
    assert repo.set_pinned('p', True).revision == 2


def test_concurrent_pins_lose_no_generation_bumps(domain_backend):
    h = domain_backend
    sid = h.space('concurrent')
    repo = h.people(sid)
    for fid in ('one', 'two'):
        repo.get_or_create_by_name(PersonDraft(id=fid, name=fid))
    before = repo.read_generation()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda fid: repo.set_pinned(fid, True), ['one', 'two']))
    assert all(row.pinned for row in results)
    after = repo.read_generation()
    assert after.value == before.value + 2 and after.token != before.token


def test_uow_atomicity_and_cross_domain_composition(domain_backend):
    h = domain_backend
    sid = h.space('atomic')
    folders, people, store = h.folders(sid), h.people(sid), h.store(sid)
    folder = folders.create(FolderCreate(name='Folder'))
    people.get_or_create_by_name(PersonDraft(id='p', name='Person'))
    before = people.read_generation()

    def fail(tx):
        # Pin reads first. Reorder is write-only: valid without write buffering.
        tx.people.set_pinned('p', True)
        tx.folders.reorder([folder.id])
        raise RuntimeError('rollback')

    with pytest.raises(RuntimeError, match='rollback'):
        store.run(fail)
    assert folders.get(folder.id).revision == folder.revision
    assert people.read_generation() == before
    assert people.set_pinned('p', False).pinned is not True

    def compose(tx):
        assert tx.space_id == sid
        fence = tx.people.read_generation()
        row = tx.folders.create(FolderCreate(name='After read'))
        return fence, row

    fence, row = store.run_with_contention_retry(compose, operation_name='domain_conformance')
    assert fence == before and folders.get(row.id).name == 'After read'
    store.run(lambda tx: (tx.people.set_pinned('p', True), tx.folders.reorder([folder.id])))
    assert people.read_generation().value == before.value + 1
    assert folders.get(folder.id).revision > folder.revision


@pytest.mark.parametrize('default', [True, False])
@pytest.mark.parametrize('in_uow', [True, False])
@pytest.mark.parametrize('user_set', [None, False, True], ids=['unset', 'false', 'true'])
def test_delete_rehomes_and_refreshes_count(domain_backend, default, in_uow, user_set):
    h = domain_backend
    sid = h.space('delete')
    repo = h.folders(sid)
    source = repo.create(FolderCreate(name='Source'))
    if default:
        h.seed(sid, 'folders', 'default', {'name': 'Default', 'is_default': True, 'order': 0})
    h.seed(
        sid,
        'conversations',
        'c',
        {
            'folder_id': source.id,
            'discarded': False,
            'created_at': NOW,
            **({'folder_user_set': user_set} if user_set is not None else {}),
        },
    )
    if in_uow:
        assert h.store(sid).run(lambda tx: tx.folders.delete(source.id))
    else:
        assert repo.delete(source.id)
    assert repo.get(source.id) is None
    target = 'default' if default else None
    rehomed = h.read(sid, 'conversations', 'c')
    assert rehomed['folder_id'] == target
    assert rehomed.get('folder_user_set') is user_set
    assert ('folder_user_set' in rehomed) is (user_set is not None)
    if default:
        assert repo.get(target).conversation_count == 1
        assert repo.conversations_in_folder(target)[0].get('folder_user_set') is user_set
    # Moving from either target/unfiled proves the old pointer is safe.
    dest = repo.create(FolderCreate(name='Destination'))
    assert repo.move_conversation('c', dest.id)
    assert repo.get(dest.id).conversation_count == 1


def test_assignment_count_and_offset_quirk(domain_backend):
    h = domain_backend
    sid = h.space('assign')
    repo = h.folders(sid)
    first, second = repo.create(FolderCreate(name='First')), repo.create(FolderCreate(name='Second'))
    for i in range(3):
        h.seed(
            sid,
            'conversations',
            str(i),
            {'folder_id': first.id, 'discarded': False, 'deleted': i == 2, 'created_at': NOW + timedelta(seconds=i)},
        )
    assert repo.conversations_in_folder(first.id, limit=1) == []
    assert repo.conversations_in_folder(first.id, limit=1, offset=1)[0]['id'] == '1'
    assert 'id' not in h.read(sid, 'conversations', '1')
    assert repo.refresh_conversation_count(first.id) == 3  # includes deleted: established count query
    assert repo.bulk_move_conversations(['0', '1', 'missing'], second.id) == 2
    assert repo.get(first.id).conversation_count == 1 and repo.get(second.id).conversation_count == 2
    assert all(row['folder_user_set'] for row in repo.conversations_in_folder(second.id))
    assert not repo.move_conversation('missing', second.id)
    assert repo.bulk_move_conversations([], second.id) == 0


def test_system_initialization_missing_entities_and_order(domain_backend):
    h = domain_backend
    sid = h.space('system')
    repo = h.folders(sid)
    first = repo.initialize_system()
    second = repo.initialize_system()
    assert [row.id for row in first] == [row.id for row in second]
    assert [row.revision for row in first] == [row.revision for row in second]
    assert len(first) == 3
    assert resolve_category_folder_id('finance', first) == repo.get_by_category_mapping('work').id
    assert resolve_category_folder_id('other', first) is None
    assert repo.create(FolderCreate(name='Next')).order == max(row.order for row in first) + 1
    assert repo.get('missing') is None
    assert repo.update('missing', FolderUpdate(name='No')) is None
    assert h.people(sid).set_pinned('missing', True) is None


def test_legacy_folder_blind_writes_advance_revision(domain_backend):
    h = domain_backend
    sid = h.space('legacy-folder-revisions')
    repo = h.folders(sid)
    h.seed(sid, 'folders', 'reorder', {'name': 'Reorder', 'order': 0})
    h.seed(sid, 'folders', 'count', {'name': 'Count', 'order': 1})
    before = repo.get('reorder').revision
    repo.reorder(['reorder'])
    assert repo.get('reorder').revision > before
    before = repo.get('count').revision
    repo.refresh_conversation_count('count')
    assert repo.get('count').revision > before


def test_named_folder_mutations_replay_without_second_writes(domain_backend):
    h = domain_backend
    sid = h.space('named-folder-mutations')
    repo = h.folders(sid)
    source = repo.create(FolderCreate(name='Source'))
    target = repo.create(FolderCreate(name='Target'))
    h.seed(sid, 'conversations', 'c', {'folder_id': source.id, 'discarded': False, 'created_at': NOW})
    assert repo.refresh_conversation_count(source.id, mutation_id='count') == 1
    revision = repo.get(source.id).revision
    assert repo.refresh_conversation_count(source.id, mutation_id='count') == 1
    assert repo.get(source.id).revision == revision
    repo.reorder([source.id, target.id], mutation_id='order')
    revision = repo.get(source.id).revision
    repo.reorder([source.id, target.id], mutation_id='order')
    assert repo.get(source.id).revision == revision
    assert repo.move_conversation('c', target.id, mutation_id='move')
    revision = repo.get(target.id).revision
    assert repo.move_conversation('c', target.id, mutation_id='move')
    assert repo.get(target.id).revision == revision
    assert repo.bulk_move_conversations(['c', 'missing'], source.id, mutation_id='bulk') == 1
    revision = repo.get(source.id).revision
    assert repo.bulk_move_conversations(['c', 'missing'], source.id, mutation_id='bulk') == 1
    assert repo.get(source.id).revision == revision
    assert repo.bulk_move_conversations([], source.id) == 0
    assert repo.get(source.id).revision == revision


def test_noop_initialization_reserves_mutation_id_across_domains(domain_backend):
    h = domain_backend
    sid = h.space('shared-receipts')
    repo = h.folders(sid)
    first = repo.initialize_system()
    assert [f.id for f in repo.initialize_system(mutation_id='shared')] == [f.id for f in first]
    with pytest.raises(MutationConflict):
        h.people(sid).get_or_create_by_name(PersonDraft(id='p', name='Different operation'), mutation_id='shared')


def test_legacy_folder_and_person_ids_come_from_document_keys(domain_backend):
    h = domain_backend
    sid = h.space('legacy-ids')
    h.seed(sid, 'folders', 'folder-key', {'name': 'Legacy', 'order': 0})
    folders = h.folders(sid)
    assert 'id' not in h.read(sid, 'folders', 'folder-key')
    assert folders.get('folder-key').id == 'folder-key'
    assert folders.list().items[0].id == 'folder-key'
    assert folders.update('folder-key', FolderUpdate(name='Changed')).id == 'folder-key'
    assert 'id' not in h.read(sid, 'folders', 'folder-key')

    h.seed(sid, 'people', 'person-key', {'name': 'Legacy person'})
    people = h.people(sid)
    draft = PersonDraft(id='unused', name='Legacy person')
    assert 'id' not in h.read(sid, 'people', 'person-key')
    assert people.get_or_create_by_name(draft, mutation_id='legacy-person').id == 'person-key'
    assert people.get_or_create_by_name(draft, mutation_id='legacy-person').id == 'person-key'
    assert people.set_pinned('person-key', True, mutation_id='pin').id == 'person-key'
    assert people.set_pinned('person-key', True, mutation_id='pin').id == 'person-key'
    assert 'id' not in h.read(sid, 'people', 'person-key')


@pytest.mark.parametrize('include_discarded', [False, True])
def test_folder_listing_requires_explicit_false_before_paging(domain_backend, include_discarded):
    h = domain_backend
    sid = h.space('missing-discarded')
    repo = h.folders(sid)
    folder = repo.create(FolderCreate(name='Legacy'))
    for i, fields in enumerate([{'discarded': True}, {}, {'discarded': False}, {'discarded': None}]):
        h.seed(
            sid, 'conversations', str(i), {'folder_id': folder.id, 'created_at': NOW - timedelta(seconds=i), **fields}
        )
    expected = ['0', '1', '2', '3'] if include_discarded else ['2']
    assert [r['id'] for r in repo.conversations_in_folder(folder.id)] == ['2']
    assert [r['id'] for r in repo.conversations_in_folder(folder.id, include_discarded=include_discarded)] == expected
    assert [
        r['id'] for r in repo.conversations_in_folder(folder.id, limit=1, offset=1, include_discarded=include_discarded)
    ] == expected[1:2]


@pytest.mark.parametrize(
    'legacy_name,draft_name', [(42, '42'), (True, 'true'), ({'x': 1}, '{"x": 1}'), (['x'], '["x"]')]
)
def test_people_name_match_requires_string(domain_backend, legacy_name, draft_name):
    h = domain_backend
    sid = h.space('typed-name')
    h.seed(sid, 'people', 'legacy', {'name': legacy_name})
    repo = h.people(sid)
    draft = PersonDraft(id='fresh', name=draft_name)
    assert repo.get_or_create_by_name(draft).id == 'fresh'
    assert repo.get_or_create_by_name(PersonDraft(id='unused', name=draft_name)).id == 'fresh'
    assert h.read(sid, 'people', 'legacy')['name'] == legacy_name
