"""The learned-language user projection contains only bounded code counts."""

from types import SimpleNamespace

from database.live_language_profile import (
    FIELD,
    MAX_SESSIONS,
    _append_transaction,
    _clean_counts,
    get_live_language_sessions,
)


def test_counts_reject_text_and_unbounded_values():
    assert _clean_counts({'pt': 4, 'en': 2, 'text': 'private words', 'es': -1, 'fr': True}) == {
        'pt': 4,
        'en': 2,
    }
    assert len(_clean_counts({f'{first}{second}': 1 for first in 'abcd' for second in 'abcdef'})) == 16


def test_transaction_appends_one_session_and_drops_oldest():
    old = [{'en': 2}] * MAX_SESSIONS
    snapshot = SimpleNamespace(exists=True, to_dict=lambda: {FIELD: old})
    reference = SimpleNamespace(get=lambda **kwargs: snapshot)
    writes = []
    transaction = SimpleNamespace(update=lambda ref, data: writes.append((ref, data)))
    assert _append_transaction.to_wrap(transaction, reference, {'pt': 7, 'en': 3})
    assert len(writes) == 1
    assert writes[0][0] is reference
    sessions = writes[0][1][FIELD]
    assert len(sessions) == MAX_SESSIONS
    assert sessions[0] == {'en': 2}
    assert sessions[-1] == {'pt': 7, 'en': 3}
    assert all(set(session) <= {'pt', 'en'} for session in sessions)


def test_missing_user_cannot_be_recreated():
    reference = SimpleNamespace(get=lambda **kwargs: SimpleNamespace(exists=False))
    transaction = SimpleNamespace(update=lambda *_: (_ for _ in ()).throw(AssertionError('write')))
    assert not _append_transaction.to_wrap(transaction, reference, {'pt': 1})


def test_read_returns_only_valid_counts():
    snapshot = SimpleNamespace(to_dict=lambda: {FIELD: [{'pt': 7, 'text': 'private words'}, {'en': 3}]})
    reference = SimpleNamespace(get=lambda *_: snapshot)
    client = SimpleNamespace(collection=lambda *_: SimpleNamespace(document=lambda *_: reference))
    assert get_live_language_sessions('u', firestore_client=client) == [{'pt': 7}, {'en': 3}]
