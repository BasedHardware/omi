"""Loading chat history must skip a malformed message instead of 500ing the send.

The chat send path built [Message(**msg) for msg in chat_db.get_messages(...)], and
Message has required fields (id, text, created_at, sender, type). One malformed or
legacy stored message raised a ValidationError that took down the whole send.
Message.deserialize_many_safe skips bad records, keeping the valid history.
"""

from datetime import datetime, timezone

from models.chat import Message


def _valid(mid):
    return {'id': mid, 'text': 'hi', 'created_at': datetime.now(timezone.utc), 'sender': 'human', 'type': 'text'}


def test_parses_valid_records():
    out = Message.deserialize_many_safe([_valid('m1'), _valid('m2')])
    assert [m.id for m in out] == ['m1', 'm2']


def test_skips_malformed_without_losing_valid():
    records = [_valid('good1'), {'id': 'bad', 'text': 'missing required fields'}, _valid('good2')]
    skipped = []
    out = Message.deserialize_many_safe(records, on_error=lambda record, exc: skipped.append(record))
    assert [m.id for m in out] == ['good1', 'good2']
    assert len(skipped) == 1


def test_tolerates_missing_callback():
    out = Message.deserialize_many_safe([{'id': 'bad'}, _valid('ok')])
    assert [m.id for m in out] == ['ok']


def test_empty():
    assert Message.deserialize_many_safe([]) == []
