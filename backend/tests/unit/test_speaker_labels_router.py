import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.speaker_labels import RejectSpeakerRequest, VoiceMatchesResponse
from routers import speaker_labels as router_module


def _client(monkeypatch, uid: str = "user-123") -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: uid
    return TestClient(app)


def _valid_reject_payload() -> dict:
    return {
        "kind": "not_me",
        "person_id": None,
        "segment_ids": ["seg-1", "seg-2"],
    }


def _dummy_conversation_dict() -> dict:
    return {
        "id": "conv-123",
        "created_at": "2026-10-01T12:00:00Z",
        "started_at": "2026-10-01T12:00:00Z",
        "finished_at": "2026-10-01T12:02:00Z",
        "structured": {
            "title": "Strategy Discussion",
            "overview": "Overview text",
            "emoji": "💡",
            "category": "work",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [
            {"id": "seg-1", "text": "Hello world", "speaker_id": 1, "is_user": False, "start": 0.0, "end": 2.0},
        ],
    }


def test_reject_speaker_label_success(monkeypatch):
    recorded_ignored = []
    removed_blobs = []

    def mock_assign(uid, conversation_id, **kwargs):
        assert uid == "user-123"
        assert conversation_id == "conv-123"
        assert kwargs["speaker_id"] == 1
        return _dummy_conversation_dict(), ["seg-1"], ["speech_profiles/old.wav"], {}

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)
    monkeypatch.setattr(
        router_module.voice_profiles_db, "record_ignored_voice", lambda *a, **k: recorded_ignored.append((a, k))
    )
    monkeypatch.setattr(router_module, "delete_speech_profile_blob", lambda p: removed_blobs.append(p))

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 200
    assert response.json()["id"] == "conv-123"
    assert "speech_profiles/old.wav" in removed_blobs


def test_reject_speaker_label_not_a_person_records_ignored_voice(monkeypatch):
    recorded_ignored = []

    def mock_assign(uid, conversation_id, **kwargs):
        return _dummy_conversation_dict(), ["seg-1"], [], {}

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)
    monkeypatch.setattr(
        router_module.voice_profiles_db, "record_ignored_voice", lambda *a, **k: recorded_ignored.append((a, k))
    )

    payload = {"kind": "not_a_person", "person_id": None, "segment_ids": ["seg-1"]}
    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=payload)
    assert response.status_code == 200
    assert len(recorded_ignored) == 1
    assert recorded_ignored[0][0][2] == 1  # speaker_id


@pytest.mark.parametrize("whitespace_id", ["   ", "%20"])
def test_reject_speaker_label_rejects_whitespace_conversation_id(monkeypatch, whitespace_id):
    client = _client(monkeypatch)
    response = client.post(f"/v1/conversations/{whitespace_id}/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 400
    assert response.json()["detail"] == "Valid conversation_id is required"


def test_reject_speaker_label_rejects_empty_conversation_id(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/v1/conversations//speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code in (404, 405)


def test_reject_speaker_label_rejects_negative_speaker_id(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/-1/reject", json=_valid_reject_payload())
    assert response.status_code == 400
    assert response.json()["detail"] == "Valid speaker_id must be non-negative"


def test_reject_speaker_label_not_found_bounded_404(monkeypatch):
    internal_leak = "INTERNAL_LEAK_TARGET_NOT_FOUND_COLLECTION_12345"

    def mock_assign(*args, **kwargs):
        raise LookupError(f"Target conversation doc missing internal leak: {internal_leak}")

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation or speaker not found"
    assert internal_leak not in response.text


def test_reject_speaker_label_plan_locked_402(monkeypatch):
    def mock_assign(*args, **kwargs):
        raise PermissionError("Plan locked conversation")

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 402
    assert response.json()["detail"] == "A paid plan is required to access this conversation."


def test_reject_speaker_label_conflict_bounded_409(monkeypatch):
    internal_leak = "INTERNAL_LEAK_SECRET_CONFLICT_TOKEN_67890"

    def mock_assign(*args, **kwargs):
        raise ValueError(f"State conflict on speaker assignment with token: {internal_leak}")

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid speaker rejection request"
    assert internal_leak not in response.text


def test_reject_speaker_label_unexpected_error_masks_500(monkeypatch):
    internal_secret = "FATAL_SECRET_FIRESTORE_CONNECTION_KEY_99999"

    def mock_assign(*args, **kwargs):
        raise RuntimeError(f"Database crash with credentials: {internal_secret}")

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)

    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=_valid_reject_payload())
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to process speaker label rejection"
    assert internal_secret not in response.text


def test_reject_speaker_label_post_processing_error_masks_500(monkeypatch):
    def mock_assign(*args, **kwargs):
        return _dummy_conversation_dict(), ["seg-1"], [], {}

    def mock_record_ignored(*args, **kwargs):
        raise RuntimeError("Ignored voice database write failure")

    monkeypatch.setattr(router_module.conversations_db, "assign_conversation_speaker", mock_assign)
    monkeypatch.setattr(router_module.voice_profiles_db, "record_ignored_voice", mock_record_ignored)

    payload = {"kind": "not_a_person", "person_id": None, "segment_ids": ["seg-1"]}
    client = _client(monkeypatch)
    response = client.post("/v1/conversations/conv-123/speakers/1/reject", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to process speaker label rejection"


def test_get_person_voice_matches_success(monkeypatch):
    async def mock_matches(uid, person_id):
        assert uid == "user-123"
        assert person_id == "person-456"
        return VoiceMatchesResponse(matches=[])

    monkeypatch.setattr(router_module, "find_person_voice_matches", mock_matches)

    client = _client(monkeypatch)
    response = client.get("/v1/users/people/person-456/voice-matches")
    assert response.status_code == 200
    assert response.json() == {"matches": []}


@pytest.mark.parametrize("whitespace_id", ["   ", "%20"])
def test_get_person_voice_matches_rejects_whitespace_person_id(monkeypatch, whitespace_id):
    client = _client(monkeypatch)
    response = client.get(f"/v1/users/people/{whitespace_id}/voice-matches")
    assert response.status_code == 400
    assert response.json()["detail"] == "Valid person_id is required"


def test_get_person_voice_matches_not_found_404(monkeypatch):
    internal_leak = "INTERNAL_LEAK_PERSON_NOT_FOUND_DOC_ID_44444"

    async def mock_matches(*args, **kwargs):
        raise LookupError(f"Person doc missing: {internal_leak}")

    monkeypatch.setattr(router_module, "find_person_voice_matches", mock_matches)

    client = _client(monkeypatch)
    response = client.get("/v1/users/people/person-missing/voice-matches")
    assert response.status_code == 404
    assert response.json()["detail"] == "Person not found"
    assert internal_leak not in response.text


def test_get_person_voice_matches_unexpected_error_masks_500(monkeypatch):
    internal_secret = "FATAL_SECRET_VOICE_MODEL_TOKEN_88888"

    async def mock_matches(*args, **kwargs):
        raise RuntimeError(f"Voice embedding model crash with token: {internal_secret}")

    monkeypatch.setattr(router_module, "find_person_voice_matches", mock_matches)

    client = _client(monkeypatch)
    response = client.get("/v1/users/people/person-456/voice-matches")
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to retrieve voice matches"
    assert internal_secret not in response.text
