"""Writer-side generation coverage at the strict transaction boundary."""

from datetime import datetime, timezone

import pytest

from database import chat_edits, people, person_aliases, speaker_learning, users
from database.people_generation import bump_people_generation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

PERSON = ('users', 'owner', 'people', 'p')
GENERATION = ('users', 'owner', 'people_meta', 'generation')
NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


@pytest.fixture
def store():
    return StrictFirestore(
        {
            ('users', 'owner'): {'save_other_voice_profiles': True},
            PERSON: {
                'id': 'p',
                'name': 'Alice',
                'updated_at': NOW,
                'speech_samples': ['one.wav'],
                'speech_sample_transcripts': ['one'],
            },
            GENERATION: {'generation': 7},
        }
    )


@pytest.mark.parametrize(
    'operation',
    [
        'rename',
        'dismiss',
        'pin',
        'sample_add',
        'sample_remove',
        'profile_replace',
        'profile_invalidate',
        'learning_state',
        'chat_apply',
        'chat_restore',
    ],
)
def test_each_transactional_writer_bumps_same_owner_generation(store, operation):
    ref = store.collection('users').document('owner').collection('people').document('p')
    owner = ref.parent.parent
    tx = store.transaction()
    if operation == 'rename':
        assert person_aliases.update_person_name_transaction(tx, ref, 'Alicia')
    elif operation == 'dismiss':
        assert person_aliases.dismiss_person_transaction(tx, ref)
    elif operation == 'pin':
        assert people.set_person_pinned('owner', 'p', True, firestore_client=store)
    elif operation == 'sample_add':
        assert users.add_sample_transaction(tx, ref, 'two.wav', 'two', 5)
    elif operation == 'sample_remove':
        assert users._remove_sample_transaction(tx, ref, 'one.wav')
    elif operation == 'profile_replace':
        users._replace_speech_profile_transaction(tx, ref, NOW, {'speaker_embedding': [1.0]}, user_ref=owner)
    elif operation == 'profile_invalidate':
        users._invalidate_speech_profile_transaction(tx, ref, 'c', ['s'])
    elif operation == 'learning_state':
        assert speaker_learning._update_voice_learning_transaction(tx, ref, owner, NOW, 'no_audio', 'unknown', 0, 10)
    else:
        before = chat_edits.snapshot('owner', 'person', 'p', firestore_client=store)
        if operation == 'chat_apply':
            chat_edits.apply_update('owner', 'person', 'p', before, {'name': 'New'}, firestore_client=store)
        else:
            previous = {**before, 'name': 'Previous'}
            chat_edits.restore('owner', 'person', 'p', before, previous, firestore_client=store)
    assert store.rows[GENERATION] == {'generation': 8}
    assert ('users', 'other', 'people_meta', 'generation') not in store.rows
    transaction = next(tx for tx in reversed(store.transactions) if tx.has_written)
    assert any(path == PERSON for path, _ in transaction.updates)
    assert [path for path, _ in transaction.sets] == [GENERATION]


def test_generation_bumps_are_unconditional_and_compose(store, monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"people_scan_dedupe":0}')
    ref = store.collection('users').document('owner').collection('people').document('p')
    for _ in range(3):
        bump_people_generation(store.transaction(), ref)
    assert store.rows[GENERATION]['generation'] == 10


def test_rejected_and_idempotent_writes_do_not_bump(store):
    ref = store.collection('users').document('owner').collection('people').document('p')
    assert not person_aliases.update_person_name_transaction(store.transaction(), ref, ' ')
    assert not users.add_sample_transaction(store.transaction(), ref, 'two.wav', 'two', 1)
    assert store.rows[GENERATION]['generation'] == 7


def test_account_purge_erases_generation_head_after_source_batches(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from database import user_data_deletion, batch_pipeline_purge

    owner = MagicMock()
    owner.get.return_value.exists = False
    owner.collections.return_value = [SimpleNamespace(id='people_meta'), SimpleNamespace(id='people')]
    client = MagicMock()
    client.collection.return_value.document.return_value = owner
    events = []
    meta = owner.collection.return_value.document.return_value
    meta.delete.side_effect = lambda: events.append('head_delete')
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: MagicMock())
    monkeypatch.setattr(user_data_deletion, 'stop_quiet_checks_for_account', lambda *args, **kwargs: None)
    # Test the erasure function independently of its unrelated staged-cache decorator.
    result = user_data_deletion.purge_user_subtree.__wrapped__(
        'owner', client, lambda sub, **kwargs: events.append(sub.id)
    )
    assert result['status'] == 'ok'
    assert events.index('people') < len(events) - 1
    assert events[-1] == 'head_delete'
    owner.collection.assert_any_call('people_meta')
