"""Hermetic route coverage for the universal GET ``/v3/memories`` path."""

from fakes.firestore import seed_memory


def _memory_doc(memory_id: str, content: str) -> dict:
    return {
        "id": memory_id,
        "content": content,
        "category": "manual",
        "visibility": "public",
        "manually_added": True,
        "reviewed": False,
        "edited": False,
        "is_locked": False,
        "user_review": True,
    }


def test_universal_get_adapts_historical_rows_and_exposes_one_capability_contract(client, auth_headers):
    seed_memory("123", _memory_doc("historical-1", "historical memory"))

    response = client.get("/v3/memories?limit=10&offset=0", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == ["historical-1"]
    assert response.json()[0]["memory_tier"] == "long_term"
    assert response.headers["x-omi-memory-canonical-lifecycle-exposed"] == "true"
    assert response.headers["x-omi-memory-device-scope-supported"] == "true"
    assert response.headers["x-omi-memory-default-delete-supported"] == "true"
    assert response.headers["cache-control"] == "no-store"


def test_cursor_cannot_select_the_retired_cutover_projection(client, auth_headers):
    seed_memory("123", _memory_doc("must-not-leak", "historical memory"))

    response = client.get("/v3/memories?cursor=retired-token", headers=auth_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_or_stale_cursor:malformed_cursor"}


def test_device_scoped_request_without_identity_fails_closed(client, auth_headers):
    response = client.get("/v3/memories?device_scope=current", headers=auth_headers)

    assert response.status_code == 400
