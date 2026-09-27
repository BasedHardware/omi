from datetime import datetime, timedelta, timezone

import pytest

from database import voice_profiles
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

USER = ('users', 'u')
STATE = ('users', 'u', 'speaker_tag_prompts', 'state')


def _pool(vectors):
    size = len(vectors[0])
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]


def test_first_confirmation_preserves_enrollment_as_base():
    earlier = datetime(2026, 9, 1, tzinfo=timezone.utc)
    store = StrictFirestore({USER: {'speaker_embedding': [1.0, 0.0], 'speaker_embedding_updated_at': earlier}})
    count = voice_profiles.add_owner_voice_confirmation(
        'u', [0.0, 1.0], _pool, conversation_id='c1', firestore_client=store
    )
    row = store.rows[USER]
    assert count == 1
    assert row['speaker_embedding_base'] == [1.0, 0.0]
    assert row['speaker_embedding'] == [0.5, 0.5]
    assert row['owner_voice_pooled_at'] == row['speaker_embedding_updated_at']


def test_confirmations_are_capped_and_base_survives():
    store = StrictFirestore({USER: {'speaker_embedding': [1.0, 0.0]}})
    for index in range(voice_profiles.OWNER_VOICE_CONFIRMATIONS_MAX + 2):
        voice_profiles.add_owner_voice_confirmation(
            'u', [0.0, float(index)], _pool, conversation_id=f'c{index}', firestore_client=store
        )
    row = store.rows[USER]
    assert len(row['owner_voice_confirmations']) == voice_profiles.OWNER_VOICE_CONFIRMATIONS_MAX
    assert row['owner_voice_confirmations'][0]['conversation_id'] == 'c2'
    assert row['speaker_embedding_base'] == [1.0, 0.0]


def test_a_newer_enrollment_replaces_the_base():
    store = StrictFirestore({USER: {'speaker_embedding': [1.0, 0.0]}})
    voice_profiles.add_owner_voice_confirmation('u', [0.0, 1.0], _pool, conversation_id='c1', firestore_client=store)
    row = store.rows[USER]
    row['speaker_embedding'] = [0.2, 0.2]
    row['speaker_embedding_updated_at'] = row['owner_voice_pooled_at'] + timedelta(seconds=5)
    voice_profiles.add_owner_voice_confirmation('u', [0.0, 1.0], _pool, conversation_id='c2', firestore_client=store)
    assert store.rows[USER]['speaker_embedding_base'] == [0.2, 0.2]


def test_no_enrollment_pools_confirmations_only():
    store = StrictFirestore({USER: {}})
    voice_profiles.add_owner_voice_confirmation('u', [0.0, 1.0], _pool, conversation_id='c1', firestore_client=store)
    voice_profiles.add_owner_voice_confirmation('u', [1.0, 1.0], _pool, conversation_id='c2', firestore_client=store)
    row = store.rows[USER]
    assert 'speaker_embedding_base' not in row
    assert row['speaker_embedding'] == [0.5, 1.0]


def test_a_missing_user_document_is_created_not_updated():
    store = StrictFirestore()
    count = voice_profiles.add_owner_voice_confirmation(
        'u', [0.0, 1.0], _pool, conversation_id='c1', firestore_client=store
    )
    row = store.rows[USER]
    assert count == 1
    assert row['speaker_embedding'] == [0.0, 1.0]
    assert row['owner_voice_confirmations'][0]['conversation_id'] == 'c1'
    assert 'speaker_embedding_base' not in row
    transaction = store.transactions[-1]
    assert transaction.creates and not transaction.updates


def test_an_existing_empty_document_is_updated_not_created():
    store = StrictFirestore({USER: {}})
    voice_profiles.add_owner_voice_confirmation('u', [0.0, 1.0], _pool, conversation_id='c1', firestore_client=store)
    transaction = store.transactions[-1]
    assert transaction.updates and not transaction.creates
    assert store.rows[USER]['speaker_embedding'] == [0.0, 1.0]


class _Doc:
    def __init__(self, rows, path):
        self.rows, self.path = rows, path

    def collection(self, name):
        return _Collection(self.rows, self.path + (name,))

    def get(self):
        data = self.rows.get(self.path)

        class Snapshot:
            def to_dict(self_inner):
                return dict(data) if data is not None else None

        return Snapshot()

    def set(self, data, merge=False):
        current = dict(self.rows.get(self.path) or {}) if merge else {}
        for key, value in data.items():
            if value is voice_profiles.firestore.DELETE_FIELD:
                current.pop(key, None)
            else:
                current[key] = value
        self.rows[self.path] = current


class _Collection:
    def __init__(self, rows, path):
        self.rows, self.path = rows, path

    def document(self, name):
        return _Doc(self.rows, self.path + (name,))


class _Client:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return _Collection(self.rows, (name,))


def test_settings_default_on_and_reject_unknown_keys():
    client = _Client()
    assert voice_profiles.get_voice_profile_settings('u', firestore_client=client) == {
        'speaker_tag_prompts_enabled': True,
        'save_other_voice_profiles': True,
    }
    voice_profiles.set_voice_profile_settings('u', {'save_other_voice_profiles': False}, firestore_client=client)
    settings, has_voice = voice_profiles.get_voice_profile_context('u', firestore_client=client)
    assert settings['save_other_voice_profiles'] is False and settings['speaker_tag_prompts_enabled'] is True
    assert has_voice is False
    with pytest.raises(ValueError):
        voice_profiles.set_voice_profile_settings('u', {'is_admin': True}, firestore_client=client)


def test_pacing_writes_run_in_transactions_and_track_first_set_streak_and_answers():
    store = StrictFirestore()
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)

    assert voice_profiles.record_tag_prompts_shown('u', now, firestore_client=store) is True
    transaction = store.transactions[-1]
    assert transaction.creates and not transaction.updates
    assert store.rows[STATE]['first_shown_at'] == now

    store.rows[STATE]['last_empty_check_at'] = now
    assert voice_profiles.record_tag_prompts_shown('u', now, firestore_client=store) is False
    transaction = store.transactions[-1]
    assert transaction.updates and not transaction.creates
    # StrictFirestore keeps the DELETE_FIELD sentinel in the row rather than applying it.
    assert (
        store.rows[STATE].get('last_empty_check_at', voice_profiles.firestore.DELETE_FIELD)
        is voice_profiles.firestore.DELETE_FIELD
    )
    assert store.rows[STATE]['shown_sets'] == 2

    assert voice_profiles.record_tag_prompts_dismissed('u', now, firestore_client=store) == 1
    assert voice_profiles.record_tag_prompts_dismissed('u', now, firestore_client=store) == 2
    voice_profiles.record_tag_prompt_answered('u', 'old', now - timedelta(days=8), firestore_client=store)
    voice_profiles.record_tag_prompt_answered('u', 'new', now, firestore_client=store)
    state = store.rows[STATE]
    assert state['consecutive_dismissals'] == 0
    assert state['shown_sets'] == 2
    assert voice_profiles.answered_prompt_ids(state, now) == {'new'}
    assert len(store.transactions) == 6
    assert all(transaction.has_written for transaction in store.transactions)
