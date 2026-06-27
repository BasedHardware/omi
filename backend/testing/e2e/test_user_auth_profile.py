"""
User/auth/profile/account e2e coverage.

These tests exercise real user/account routes through the FastAPI app while
using fake Firestore/Redis and local-development auth.
"""

from fakes.firestore import get_mock_firestore


def _seed_user(uid="123", **fields):
    data = {"id": uid, "uid": uid, "name": "E2E User", "email": "e2e@example.com"}
    data.update(fields)
    get_mock_firestore().collection("users").document(uid).set(data)
    return data


def test_auth_guard_and_onboarding_roundtrip(client, auth_headers):
    unauth = client.get("/v1/users/onboarding")
    assert unauth.status_code == 401

    malformed = client.get("/v1/users/onboarding", headers={"Authorization": "dev-token"})
    assert malformed.status_code == 401

    default = client.get("/v1/users/onboarding", headers=auth_headers)
    assert default.status_code == 200, default.text
    assert default.json() == {"completed": False, "acquisition_source": ""}

    patch = client.patch(
        "/v1/users/onboarding",
        json={"completed": True, "acquisition_source": "friend"},
        headers=auth_headers,
    )
    assert patch.status_code == 200, patch.text

    persisted = client.get("/v1/users/onboarding", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    assert persisted.json() == {"completed": True, "acquisition_source": "friend"}


def test_profile_410_then_seeded_profile(client, auth_headers):
    missing = client.get("/v1/users/profile", headers=auth_headers)
    assert missing.status_code == 410

    seeded = _seed_user(data_protection_level="standard")
    resp = client.get("/v1/users/profile", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == seeded["name"]
    assert body["email"] == seeded["email"]
    assert body["data_protection_level"] == "standard"


def test_language_and_transcription_preferences_roundtrip(client, auth_headers):
    language = client.get("/v1/users/language", headers=auth_headers)
    assert language.status_code == 200, language.text
    assert language.json() == {"language": None}

    set_language = client.patch("/v1/users/language", json={"language": "en"}, headers=auth_headers)
    assert set_language.status_code == 200, set_language.text
    assert set_language.json()["status"] == "ok"

    language = client.get("/v1/users/language", headers=auth_headers)
    assert language.status_code == 200, language.text
    assert language.json() == {"language": "en"}

    prefs_update = client.patch(
        "/v1/users/transcription-preferences",
        json={"single_language_mode": True, "vocabulary": ["Omi", "Hermes"]},
        headers=auth_headers,
    )
    assert prefs_update.status_code == 200, prefs_update.text

    prefs = client.get("/v1/users/transcription-preferences", headers=auth_headers)
    assert prefs.status_code == 200, prefs.text
    body = prefs.json()
    assert body["language"] == "en"
    assert body["single_language_mode"] is True
    assert body["vocabulary"] == ["Omi", "Hermes"]


def test_people_crud_without_speech_sample_signing(client, auth_headers):
    create = client.post("/v1/users/people", json={"name": "Alice E2E"}, headers=auth_headers)
    assert create.status_code == 200, create.text
    person = create.json()
    person_id = person["id"]
    assert person["name"] == "Alice E2E"

    duplicate = client.post("/v1/users/people", json={"name": "Alice E2E"}, headers=auth_headers)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["id"] == person_id

    listed = client.get("/v1/users/people?include_speech_samples=false", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert any(p["id"] == person_id for p in listed.json())

    single = client.get(f"/v1/users/people/{person_id}?include_speech_samples=false", headers=auth_headers)
    assert single.status_code == 200, single.text
    assert single.json()["name"] == "Alice E2E"

    rename = client.patch(f"/v1/users/people/{person_id}/name?value=Alice Renamed", headers=auth_headers)
    assert rename.status_code == 200, rename.text

    renamed = client.get(f"/v1/users/people/{person_id}?include_speech_samples=false", headers=auth_headers)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Alice Renamed"

    delete = client.delete(f"/v1/users/people/{person_id}", headers=auth_headers)
    assert delete.status_code == 204, delete.text

    missing = client.get(f"/v1/users/people/{person_id}?include_speech_samples=false", headers=auth_headers)
    assert missing.status_code == 404


def test_notification_assistant_ai_profile_and_byok_state(client, auth_headers):
    _seed_user()

    notif = client.get("/v1/users/notification-settings", headers=auth_headers)
    assert notif.status_code == 200, notif.text
    assert notif.json() == {"enabled": True, "frequency": 0}

    notif_patch = client.patch(
        "/v1/users/notification-settings",
        json={"enabled": False, "frequency": 3},
        headers=auth_headers,
    )
    assert notif_patch.status_code == 200, notif_patch.text
    assert notif_patch.json() == {"enabled": False, "frequency": 3}

    invalid_notif = client.patch(
        "/v1/users/notification-settings",
        json={"frequency": 6},
        headers=auth_headers,
    )
    assert invalid_notif.status_code == 422

    assistant = client.patch(
        "/v1/users/assistant-settings",
        json={"focus": {"enabled": True, "cooldown_interval": 60}, "update_channel": "beta"},
        headers=auth_headers,
    )
    assert assistant.status_code == 200, assistant.text

    assistant_merge = client.patch(
        "/v1/users/assistant-settings",
        json={"focus": {"notifications_enabled": False}},
        headers=auth_headers,
    )
    assert assistant_merge.status_code == 200, assistant_merge.text
    merged = assistant_merge.json()
    fetched_settings = client.get("/v1/users/assistant-settings", headers=auth_headers)
    assert fetched_settings.status_code == 200, fetched_settings.text
    fetched = fetched_settings.json()
    assert fetched["focus"]["enabled"] is True
    assert fetched["focus"]["cooldown_interval"] == 60
    assert fetched["focus"]["notifications_enabled"] is False
    assert fetched["update_channel"] == "beta"

    ai_initial = client.get("/v1/users/ai-profile", headers=auth_headers)
    assert ai_initial.status_code == 200, ai_initial.text
    assert ai_initial.json() is None

    ai_patch = client.patch(
        "/v1/users/ai-profile",
        json={"profile_text": "E2E profile", "generated_at": "2026-01-01T00:00:00Z", "data_sources_used": 2},
        headers=auth_headers,
    )
    assert ai_patch.status_code == 200, ai_patch.text
    assert ai_patch.json()["profile_text"] == "E2E profile"

    ai_merge = client.patch("/v1/users/ai-profile", json={"data_sources_used": 3}, headers=auth_headers)
    assert ai_merge.status_code == 200, ai_merge.text
    assert ai_merge.json()["profile_text"] == "E2E profile"
    assert ai_merge.json()["data_sources_used"] == 3

    bad_byok = client.post(
        "/v1/users/me/byok-active",
        json={"fingerprints": {"openai": "a" * 64}},
        headers=auth_headers,
    )
    assert bad_byok.status_code == 400

    good_fingerprints = {provider: "a" * 64 for provider in ["openai", "anthropic", "gemini", "deepgram"]}
    byok = client.post("/v1/users/me/byok-active", json={"fingerprints": good_fingerprints}, headers=auth_headers)
    assert byok.status_code == 200, byok.text
    assert byok.json() == {"active": True}

    deactivate = client.delete("/v1/users/me/byok-active", headers=auth_headers)
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json() == {"active": False}
