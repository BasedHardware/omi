from datetime import datetime, timezone

from database import entity_timeline_sources

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, document_id, payload):
        self.id = document_id
        self._payload = payload
        self.update_time = None

    def to_dict(self):
        return dict(self._payload)


class _Query:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, document_id):
        return _Document(self._store, (*self._path, document_id))

    def where(self, *args, filter=None):
        self._store.filters.append(filter if filter is not None else args)
        return self

    def order_by(self, field_path, direction=None):
        self._store.orderings.append((field_path, direction))
        return self

    def limit(self, value):
        self._store.limit_value = value
        return self

    def stream(self):
        self._store.streamed_path = self._path
        return iter(self._store.rows[: self._store.limit_value])


class _Document:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def collection(self, name):
        return _Query(self._store, (*self._path, name))


class _Store:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.orderings = []
        self.limit_value = None
        self.streamed_path = None

    def collection(self, name):
        return _Query(self, (name,))


def _filter_triples(filters):
    triples = []
    for value in filters:
        if isinstance(value, tuple):
            triples.append(value)
        else:
            triples.append((value.field_path, value.op_string, value.value))
    return triples


def test_conversation_reader_is_owner_scoped_completed_and_deterministically_bounded():
    store = _Store(
        [
            _Snapshot(
                "conversation-1",
                {
                    "created_at": NOW,
                    "status": "completed",
                    "discarded": False,
                    "transcript_segments": [{"person_id": "person-1", "text": "private"}],
                },
            )
        ]
    )

    rows = entity_timeline_sources.list_entity_timeline_conversations(
        "u1",
        db_client=store,
        limit=2,
        start_date=NOW,
        end_date=NOW,
    )

    assert rows[0]["id"] == "conversation-1"
    assert rows[0]["transcript_segments"][0]["person_id"] == "person-1"
    assert "text" not in rows[0]["transcript_segments"][0]
    assert store.streamed_path == ("users", "u1", "conversations")
    assert ("discarded", "==", False) in _filter_triples(store.filters)
    assert ("status", "==", "completed") in _filter_triples(store.filters)
    assert ("created_at", ">=", NOW) in _filter_triples(store.filters)
    assert ("created_at", "<=", NOW) in _filter_triples(store.filters)
    assert [field for field, _ in store.orderings] == ["created_at", "__name__"]
    assert store.limit_value == 2


def test_conversation_reader_bounds_compressed_decode_and_projects_identity_only():
    from database.conversations import encode_conversation_for_write

    encoded = encode_conversation_for_write(
        "u1",
        {"transcript_segments": [{"person_id": "person-1", "is_user": False, "text": "PRIVATE TRANSCRIPT"}]},
    )
    store = _Store(
        [
            _Snapshot(
                "conversation-1",
                {
                    "created_at": NOW,
                    "status": "completed",
                    "discarded": False,
                    **encoded,
                },
            )
        ]
    )

    rows = entity_timeline_sources.list_entity_timeline_conversations("u1", db_client=store, limit=1)

    assert rows[0]["transcript_segments"] == [{"is_user": False, "person_id": "person-1"}]
    assert "PRIVATE TRANSCRIPT" not in repr(rows[0])


def test_conversation_reader_fails_oversized_decoded_transcript_closed():
    from database.conversations import encode_conversation_for_write

    encoded = encode_conversation_for_write(
        "u1",
        {"transcript_segments": [{"person_id": "person-1", "text": "x" * (513 * 1024)}]},
    )
    store = _Store(
        [
            _Snapshot(
                "conversation-1",
                {
                    "created_at": NOW,
                    "status": "completed",
                    "discarded": False,
                    **encoded,
                },
            )
        ]
    )

    rows = entity_timeline_sources.list_entity_timeline_conversations("u1", db_client=store, limit=1)

    assert rows[0]["transcript_segments"] == []


def test_calendar_and_screen_readers_use_owner_path_range_tiebreaker_and_limit():
    meeting_store = _Store([_Snapshot("meeting-1", {"start_time": NOW, "title": "Review"})])
    screen_store = _Store(
        [
            _Snapshot(
                "screen-1",
                {
                    "timestamp": "2026-08-24 12:00:00.000",
                    "appName": "Slack",
                    "windowTitle": "Review",
                    "ocrText": "Alice",
                },
            )
        ]
    )

    meetings = entity_timeline_sources.list_entity_timeline_meetings(
        "u1",
        db_client=meeting_store,
        limit=3,
        start_date=NOW,
        end_date=NOW,
    )
    screens = entity_timeline_sources.list_entity_timeline_screen_activity(
        "u1",
        db_client=screen_store,
        limit=4,
        start_date=NOW,
        end_date=NOW,
    )

    assert meetings[0]["id"] == "meeting-1"
    assert screens[0]["id"] == "screen-1"
    assert meeting_store.streamed_path == ("users", "u1", "meetings")
    assert screen_store.streamed_path == ("users", "u1", "screen_activity")
    assert [field for field, _ in meeting_store.orderings] == ["start_time", "__name__"]
    assert [field for field, _ in screen_store.orderings] == ["timestamp", "__name__"]
    assert meeting_store.limit_value == 3
    assert screen_store.limit_value == 4
