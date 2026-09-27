"""Hermetic unit tests for input validation, boundary guards, and resilience in database/voice_profiles.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import database.voice_profiles as vp_db


def _make_mock_snapshot(data: dict | None = None, exists: bool = True):
    snap = MagicMock()
    snap.exists = exists
    snap.to_dict.return_value = data if data is not None else {}
    return snap


# ---------------------------------------------------------------------------
# Input validation: uid rejection across all functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_voice_profile_settings_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.get_voice_profile_settings(invalid_uid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_voice_profile_context_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.get_voice_profile_context(invalid_uid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_set_voice_profile_settings_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.set_voice_profile_settings(invalid_uid, {"speaker_tag_prompts_enabled": True})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_tag_prompt_state_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.get_tag_prompt_state(invalid_uid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_record_tag_prompts_shown_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.record_tag_prompts_shown(invalid_uid, datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_mark_tag_prompts_empty_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.mark_tag_prompts_empty(invalid_uid, datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_record_tag_prompts_dismissed_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.record_tag_prompts_dismissed(invalid_uid, datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_record_tag_prompt_answered_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.record_tag_prompt_answered(invalid_uid, "p1", datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_add_owner_voice_confirmation_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        vp_db.add_owner_voice_confirmation(
            invalid_uid, [0.1, 0.2], lambda vecs: vecs[0], conversation_id="c1"  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Specific argument validations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_prompt_id", [None, "", "   ", 123, []])
def test_record_tag_prompt_answered_rejects_invalid_prompt_id(invalid_prompt_id):
    with pytest.raises(ValueError, match="prompt_id must be a non-empty string"):
        vp_db.record_tag_prompt_answered("u1", invalid_prompt_id, datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_cid", [None, "", "   ", 123, []])
def test_add_owner_voice_confirmation_rejects_invalid_conversation_id(invalid_cid):
    with pytest.raises(ValueError, match="conversation_id must be a non-empty string"):
        vp_db.add_owner_voice_confirmation(
            "u1", [0.1, 0.2], lambda vecs: vecs[0], conversation_id=invalid_cid  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("invalid_embedding", [None, "", [], "not-a-list", 123])
def test_add_owner_voice_confirmation_rejects_invalid_embedding(invalid_embedding):
    with pytest.raises(ValueError, match="embedding must be a non-empty sequence of floats"):
        vp_db.add_owner_voice_confirmation(
            "u1", invalid_embedding, lambda vecs: vecs[0], conversation_id="c1"  # type: ignore[arg-type]
        )


def test_add_owner_voice_confirmation_rejects_non_numeric_embedding():
    with pytest.raises(ValueError, match="embedding elements must be floats"):
        vp_db.add_owner_voice_confirmation(
            "u1", [0.1, "not-a-float"], lambda vecs: vecs[0], conversation_id="c1"  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("invalid_pool", [None, 123, "not-callable", []])
def test_add_owner_voice_confirmation_rejects_invalid_pool(invalid_pool):
    with pytest.raises(ValueError, match="pool must be a callable"):
        vp_db.add_owner_voice_confirmation(
            "u1", [0.1, 0.2], invalid_pool, conversation_id="c1"  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("invalid_now", [None, 123, "invalid-date", []])
def test_recording_functions_reject_invalid_now(invalid_now):
    with pytest.raises(ValueError, match="now must be a valid datetime or ISO timestamp"):
        vp_db.record_tag_prompts_shown("u1", invalid_now)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="now must be a valid datetime or ISO timestamp"):
        vp_db.mark_tag_prompts_empty("u1", invalid_now)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="now must be a valid datetime or ISO timestamp"):
        vp_db.record_tag_prompts_dismissed("u1", invalid_now)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="now must be a valid datetime or ISO timestamp"):
        vp_db.record_tag_prompt_answered("u1", "p1", invalid_now)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Settings resolution and updates
# ---------------------------------------------------------------------------


def test_get_voice_profile_settings_resolves_defaults():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot({})
    fake_client.collection.return_value.document.return_value = doc_ref

    settings = vp_db.get_voice_profile_settings("  user-123  ", firestore_client=fake_client)
    assert settings == {
        "speaker_tag_prompts_enabled": True,
        "save_other_voice_profiles": True,
    }
    fake_client.collection.assert_called_with("users")
    fake_client.collection.return_value.document.assert_called_with("user-123")


def test_get_voice_profile_context_resolves_speaker_embedding():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot({
        "speaker_tag_prompts_enabled": False,
        "speaker_embedding": [0.1, 0.2, 0.3],
    })
    fake_client.collection.return_value.document.return_value = doc_ref

    settings, has_voiceprint = vp_db.get_voice_profile_context("u1", firestore_client=fake_client)
    assert settings["speaker_tag_prompts_enabled"] is False
    assert settings["save_other_voice_profiles"] is True
    assert has_voiceprint is True


def test_set_voice_profile_settings_rejects_non_dict():
    with pytest.raises(ValueError, match="updates must be a dictionary"):
        vp_db.set_voice_profile_settings("u1", "not-a-dict")  # type: ignore[arg-type]


def test_set_voice_profile_settings_rejects_unknown_setting():
    with pytest.raises(ValueError, match="Unknown voice profile setting.*unsupported_key"):
        vp_db.set_voice_profile_settings("u1", {"unsupported_key": True})


def test_set_voice_profile_settings_empty_updates_returns_early():
    fake_client = MagicMock()
    vp_db.set_voice_profile_settings("u1", {}, firestore_client=fake_client)
    fake_client.collection.assert_not_called()


def test_set_voice_profile_settings_merges_bools():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = doc_ref

    vp_db.set_voice_profile_settings(
        "  user-abc  ",
        {"speaker_tag_prompts_enabled": False},
        firestore_client=fake_client,
    )
    fake_client.collection.return_value.document.assert_called_with("user-abc")
    doc_ref.set.assert_called_once_with({"speaker_tag_prompts_enabled": False}, merge=True)


# ---------------------------------------------------------------------------
# State tracking and pacing
# ---------------------------------------------------------------------------


def test_get_tag_prompt_state_returns_dict():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot({"shown_sets": 3})
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    res = vp_db.get_tag_prompt_state("u1", firestore_client=fake_client)
    assert res == {"shown_sets": 3}


def test_record_tag_prompts_shown_first_stamp():
    fake_client = MagicMock()
    tx = MagicMock()
    fake_client.transaction.return_value = tx
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    doc_ref.get.return_value = _make_mock_snapshot({}, exists=False)

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    is_first = vp_db.record_tag_prompts_shown("u1", now, firestore_client=fake_client)

    assert is_first is True
    tx.create.assert_called_once()
    create_args = tx.create.call_args[0]
    assert create_args[1]["shown_sets"] == 1
    assert create_args[1]["first_shown_at"] == now
    assert create_args[1]["last_shown_at"] == now


def test_record_tag_prompts_shown_increment():
    fake_client = MagicMock()
    tx = MagicMock()
    fake_client.transaction.return_value = tx
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    doc_ref.get.return_value = _make_mock_snapshot(
        {"shown_sets": 2, "first_shown_at": "2026-09-20T10:00:00Z", "last_empty_check_at": "2026-09-26T10:00:00Z"},
        exists=True,
    )

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    is_first = vp_db.record_tag_prompts_shown("u1", now, firestore_client=fake_client)

    assert is_first is False
    tx.update.assert_called_once()
    update_args = tx.update.call_args[0]
    assert update_args[1]["shown_sets"] == 3
    assert update_args[1]["last_shown_at"] == now
    assert "first_shown_at" not in update_args[1]


def test_mark_tag_prompts_empty():
    fake_client = MagicMock()
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    vp_db.mark_tag_prompts_empty("u1", now, firestore_client=fake_client)
    doc_ref.set.assert_called_once_with({"last_empty_check_at": now}, merge=True)


def test_record_tag_prompts_dismissed_increments_streak():
    fake_client = MagicMock()
    tx = MagicMock()
    fake_client.transaction.return_value = tx
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    doc_ref.get.return_value = _make_mock_snapshot({"consecutive_dismissals": 2}, exists=True)

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    streak = vp_db.record_tag_prompts_dismissed("u1", now, firestore_client=fake_client)

    assert streak == 3
    tx.update.assert_called_once()
    assert tx.update.call_args[0][1]["consecutive_dismissals"] == 3


def test_record_tag_prompt_answered_prunes_and_resets_streak():
    fake_client = MagicMock()
    tx = MagicMock()
    fake_client.transaction.return_value = tx
    doc_ref = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(days=2)).isoformat()
    expired = (now - timedelta(days=10)).isoformat()

    doc_ref.get.return_value = _make_mock_snapshot(
        {
            "answered": {"p_recent": recent, "p_expired": expired},
            "consecutive_dismissals": 4,
        },
        exists=True,
    )

    vp_db.record_tag_prompt_answered("u1", "p_new", now, firestore_client=fake_client)

    tx.update.assert_called_once()
    update_data = tx.update.call_args[0][1]
    assert update_data["consecutive_dismissals"] == 0
    assert "p_new" in update_data["answered"]
    assert "p_recent" in update_data["answered"]
    assert "p_expired" not in update_data["answered"]


def test_answered_prompt_ids_handles_non_dict_and_filters_cutoff():
    assert vp_db.answered_prompt_ids("not-a-dict") == set()  # type: ignore[arg-type]

    now = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    state = {
        "answered": {
            "valid": (now - timedelta(days=1)).isoformat(),
            "expired": (now - timedelta(days=8)).isoformat(),
        }
    }
    assert vp_db.answered_prompt_ids(state, now) == {"valid"}


# ---------------------------------------------------------------------------
# Owner voice confirmations and pooling
# ---------------------------------------------------------------------------


def test_add_owner_voice_confirmation_pools_and_enforces_max():
    fake_client = MagicMock()
    tx = MagicMock()
    fake_client.transaction.return_value = tx
    user_ref = MagicMock()
    fake_client.collection.return_value.document.return_value = user_ref

    existing = [
        {"embedding": [0.1 * i], "conversation_id": f"conv_{i}", "at": datetime.now(timezone.utc)}
        for i in range(5)
    ]
    user_ref.get.return_value = _make_mock_snapshot(
        {
            "speaker_embedding": [0.99],
            "speaker_embedding_base": [0.5],
            "owner_voice_confirmations": existing,
        },
        exists=True,
    )

    def mock_pool(vectors):
        return [sum(v[0] for v in vectors) / len(vectors)]

    count = vp_db.add_owner_voice_confirmation(
        "  user-1  ",
        [0.8],
        mock_pool,
        conversation_id="conv_new",
        firestore_client=fake_client,
    )

    assert count == 5  # Sliding window keeps max 5
    tx.update.assert_called_once()
    payload = tx.update.call_args[0][1]
    assert len(payload["owner_voice_confirmations"]) == 5
    assert payload["owner_voice_confirmations"][-1]["conversation_id"] == "conv_new"
    assert "speaker_embedding" in payload
