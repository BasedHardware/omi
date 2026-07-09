from datetime import datetime, timezone

from google.protobuf.timestamp_pb2 import Timestamp

from database.conversation_projection import (
    CONVERSATION_LIST_FIELDS,
    apply_conversation_list_field_mask,
    conversation_snapshot_data,
)
from models.conversation import Conversation, conversation_mutation_data


class _Snapshot:
    exists = True
    id = 'conversation-1'
    update_time = datetime(2026, 7, 9, 12, 30, tzinfo=timezone.utc)

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
            'started_at': datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
            'finished_at': datetime(2026, 7, 9, 12, 5, tzinfo=timezone.utc),
            'structured': {},
            'transcript_segments': [],
        }


def test_firestore_update_time_is_exposed_as_opaque_conversation_revision():
    data = conversation_snapshot_data(_Snapshot())

    assert data['updated_at'] == _Snapshot.update_time
    assert data['revision'] == '2026-07-09T12:30:00+00:00'
    assert Conversation.model_validate(data).revision == data['revision']


def test_protobuf_update_time_is_normalized_with_subsecond_precision():
    update_time = Timestamp()
    expected = datetime(2026, 7, 9, 21, 52, 19, 342802, tzinfo=timezone.utc)
    update_time.FromDatetime(expected)
    snapshot = _Snapshot()
    snapshot.update_time = update_time

    data = conversation_snapshot_data(snapshot)

    assert data['updated_at'] == expected
    assert data['revision'] == '2026-07-09T21:52:19.342802+00:00'


def test_firestore_fake_timestamp_shape_is_normalized_with_subsecond_precision():
    update_time = type('FakeTimestamp', (), {'seconds': '1783633939', 'nanos': '342802'})()
    snapshot = _Snapshot()
    snapshot.update_time = update_time

    data = conversation_snapshot_data(snapshot)

    assert data['updated_at'] == datetime(2026, 7, 9, 21, 52, 19, 342802, tzinfo=timezone.utc)
    assert data['revision'] == '2026-07-09T21:52:19.342802+00:00'


def test_missing_snapshot_has_no_conversation_projection():
    snapshot = _Snapshot()
    snapshot.exists = False

    assert conversation_snapshot_data(snapshot) is None


def test_write_result_produces_lightweight_mutation_revision():
    result = type('WriteResult', (), {'update_time': _Snapshot.update_time})()

    data = conversation_mutation_data('conversation-1', result)

    assert data == {
        'id': 'conversation-1',
        'updated_at': _Snapshot.update_time,
        'revision': '2026-07-09T12:30:00+00:00',
    }


def test_list_projection_allowlist_never_hydrates_transcript_payload():
    assert 'transcript_segments' not in CONVERSATION_LIST_FIELDS
    assert {'id', 'created_at', 'structured', 'status', 'is_locked'} <= set(CONVERSATION_LIST_FIELDS)


def test_list_projection_applies_firestore_field_mask():
    class Query:
        selected = None

        def select(self, fields):
            self.selected = tuple(fields)
            return self

    query = Query()
    result = apply_conversation_list_field_mask(query)

    assert result is query
    assert query.selected == CONVERSATION_LIST_FIELDS
