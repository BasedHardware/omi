"""
Scenario: iMessage connector end-to-end.

Drives the REAL /v1/imessage/* routes through the hermetic backend (fake
Firestore/Redis/Storage, dev-token auth → uid 123). Proves the synchronous
postconditions of "connect iMessage": threads are accepted, each contact handle
is upserted into the People graph, connection state is recorded, and re-sending
the same messages is deduped.

(Heavy per-conversation post-processing — summary/memory/profile — runs in a
background task and needs an LLM, so it is out of scope for this deterministic
scenario; the people/consent/dedup path below is fully synchronous.)
"""


def _thread(chat_guid="iMessage;-;+15551234567", name="Alice", handle="+15551234567"):
    return {
        "chat_guid": chat_guid,
        "chat_identifier": handle,
        "display_name": name,
        "is_group": False,
        "messages": [
            {
                "guid": "m1",
                "text": "hey are we still on for dinner?",
                "is_from_me": False,
                "handle": handle,
                "timestamp": "2026-01-01T18:00:00+00:00",
            },
            {"guid": "m2", "text": "yes! 7pm works", "is_from_me": True, "timestamp": "2026-01-01T18:01:00+00:00"},
            {
                "guid": "m3",
                "text": "perfect, see you then",
                "is_from_me": False,
                "handle": handle,
                "timestamp": "2026-01-01T18:02:00+00:00",
            },
        ],
    }


class TestIMessageConnector:
    def test_ingest_populates_people_and_dedupes(self, client, auth_headers):
        # 1. Ingest a thread.
        resp = client.post(
            "/v1/imessage/threads",
            headers=auth_headers,
            json={"threads": [_thread()], "language": "en", "last_rowid": 100},
        )
        assert resp.status_code == 200, f"ingest failed: {resp.text}"
        body = resp.json()
        assert body["success"] is True
        assert body["people_upserted"] == 1
        assert body["messages_ingested"] == 3
        assert body["conversations_created"] == 1
        assert body["skipped_duplicates"] == 0

        # 2. The contact is now in the People graph (was empty before).
        people = client.get("/v1/users/people", headers=auth_headers)
        assert people.status_code == 200, people.text
        names = [p.get("name") for p in people.json()]
        assert "Alice" in names, f"Alice not found in people: {names}"

        # 3. Connection status reflects the consent + cursor.
        status = client.get("/v1/imessage/connection-status", headers=auth_headers)
        assert status.status_code == 200, status.text
        s = status.json()
        assert s["connected"] is True
        assert s["enabled"] is True
        assert s["last_rowid"] == 100

        # 4. Re-sending the same messages is deduped (idempotent sync).
        resp2 = client.post(
            "/v1/imessage/threads",
            headers=auth_headers,
            json={"threads": [_thread()], "language": "en", "last_rowid": 100},
        )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        assert body2["skipped_duplicates"] == 3
        assert body2["messages_ingested"] == 0
        assert body2["conversations_created"] == 0

        # 5. Settings round-trip: opt a handle out.
        put = client.put(
            "/v1/imessage/settings",
            headers=auth_headers,
            json={"enabled": True, "opted_out_handles": ["+15550000000"], "backfill_days": 30},
        )
        assert put.status_code == 200, put.text
        assert put.json()["opted_out_handles"] == ["+15550000000"]
        assert put.json()["backfill_days"] == 30

        got = client.get("/v1/imessage/settings", headers=auth_headers)
        assert got.status_code == 200
        assert got.json()["opted_out_handles"] == ["+15550000000"]

        # 6. Disconnect succeeds.
        disc = client.post("/v1/imessage/disconnect", headers=auth_headers)
        assert disc.status_code == 200
        assert disc.json()["success"] is True
