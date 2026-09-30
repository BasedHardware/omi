import math
from datetime import datetime, timezone
import pytest

from database import voice_profiles
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

USER = ('users', 'u')


def _pool(vectors):
    size = len(vectors[0])
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]


def test_invalid_uid_raises_value_error():
    store = StrictFirestore()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles.get_voice_profile_settings("", firestore_client=store)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles.get_voice_profile_context("   ", firestore_client=store)

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        voice_profiles.set_voice_profile_settings(None, {'save_other_voice_profiles': False}, firestore_client=store)


def test_invalid_prompt_id_raises_value_error():
    store = StrictFirestore()
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="prompt_id must be a non-empty string"):
        voice_profiles.record_tag_prompt_answered("u", "", now, firestore_client=store)

    with pytest.raises(ValueError, match="prompt_id must be a non-empty string"):
        voice_profiles.record_tag_prompt_answered("u", "   ", now, firestore_client=store)


def test_invalid_conversation_id_raises_value_error():
    store = StrictFirestore()
    with pytest.raises(ValueError, match="conversation_id must be a non-empty string"):
        voice_profiles.add_owner_voice_confirmation(
            "u", [0.1, 0.2], _pool, conversation_id="", firestore_client=store
        )


def test_non_finite_embedding_raises_value_error():
    store = StrictFirestore()
    with pytest.raises(ValueError, match="embedding contains invalid or non-finite coordinate"):
        voice_profiles.add_owner_voice_confirmation(
            "u", [0.1, float('nan')], _pool, conversation_id="c1", firestore_client=store
        )

    with pytest.raises(ValueError, match="embedding contains invalid or non-finite coordinate"):
        voice_profiles.add_owner_voice_confirmation(
            "u", [float('inf'), 0.2], _pool, conversation_id="c1", firestore_client=store
        )


def test_empty_embedding_raises_value_error():
    store = StrictFirestore()
    with pytest.raises(ValueError, match="embedding must be a non-empty sequence"):
        voice_profiles.add_owner_voice_confirmation(
            "u", [], _pool, conversation_id="c1", firestore_client=store
        )


def test_non_finite_pooled_result_raises_value_error():
    store = StrictFirestore()
    def _bad_pool(vectors):
        return [float('nan'), 1.0]

    with pytest.raises(ValueError, match="pooled vector contains invalid or non-finite coordinate"):
        voice_profiles.add_owner_voice_confirmation(
            "u", [0.1, 0.2], _bad_pool, conversation_id="c1", firestore_client=store
        )
