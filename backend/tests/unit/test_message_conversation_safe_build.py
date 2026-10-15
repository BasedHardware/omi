"""Regression tests for ``MessageConversation.safe_build_many`` (issue #20018).

Chat callers attach memory conversations to an AI message AFTER the message is
persisted; a throwing comprehension there orphaned the stored id while the
client kept a fresh in-memory one. The safe builder must skip malformed
members instead of raising.
"""

from datetime import datetime, timezone

from models.chat import MessageConversation

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _valid_dict(**over):
    m = {'id': 'c1', 'structured': {'title': 'T', 'emoji': 'e'}, 'created_at': NOW}
    m.update(over)
    return m


def test_dict_members_build():
    out = MessageConversation.safe_build_many([_valid_dict()])
    assert len(out) == 1
    assert out[0].id == 'c1'


def test_live_model_members_pass_through():
    member = MessageConversation.model_validate(_valid_dict(id='c2'))
    out = MessageConversation.safe_build_many([member])
    assert out == [member]


def test_object_with_model_dump_builds():
    class LiveDoc:
        def model_dump(self):
            return _valid_dict(id='c3')

    out = MessageConversation.safe_build_many([LiveDoc()])
    assert len(out) == 1 and out[0].id == 'c3'


def test_malformed_members_are_skipped_without_raising():
    members = [
        _valid_dict(id='ok1'),
        {'id': 'no-structured'},  # missing structured
        'not-a-mapping',
        _valid_dict(id='ok2', created_at='garbage'),  # bad datetime
        None,
        {'structured': {'title': 'T', 'emoji': 'e'}, 'created_at': NOW},  # missing id
    ]
    skipped = []
    out = MessageConversation.safe_build_many(members, on_error=lambda m, e: skipped.append((m, type(e).__name__)))
    # bad created_at is malformed too — only ok1 survives; five members report.
    assert [m.id for m in out] == ['ok1']
    assert len(skipped) == 5


def test_no_on_error_callback_still_skips():
    out = MessageConversation.safe_build_many([{'bad': True}, _valid_dict(id='fine')])
    assert [m.id for m in out] == ['fine']
