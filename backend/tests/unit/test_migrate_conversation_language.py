from argparse import ArgumentTypeError
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from models.conversation import CreateConversation
from models.conversation_enums import ConversationSource
from scripts import migrate_conversation_language


def test_migration_updates_only_blank_friend_languages(monkeypatch):
    conversations = []
    updated = []
    for conversation_id, data in (
        ('missing', {'source': 'friend'}),
        ('blank', {'source': 'friend', 'language': '  '}),
        ('french', {'source': 'friend', 'language': 'fr'}),
        ('friend_com_missing', {'source': 'friend_com'}),
    ):
        conversation = MagicMock(id=conversation_id)
        conversation.to_dict.return_value = data
        conversation.reference.update.side_effect = lambda updates, conversation_id=conversation_id: updated.append(
            (conversation_id, updates)
        )
        conversations.append(conversation)

    firestore_client = MagicMock()
    conversations_ref = firestore_client.collection.return_value.document.return_value.collection.return_value
    conversations_ref.where.return_value.stream.return_value = conversations

    result = migrate_conversation_language.process_user('uid', dry_run=False, firestore_client=firestore_client)

    assert result == {'uid': 'uid', 'fixed': 3, 'status': 'ok'}
    assert updated == [
        ('missing', {'language': 'en'}),
        ('blank', {'language': 'en'}),
        ('friend_com_missing', {'language': 'en'}),
    ]
    conversations_ref.where.assert_called_once()


def test_conversation_language_default_is_scoped_to_friend_source():
    values = {
        'started_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        'transcript_segments': [],
    }

    assert CreateConversation(**values).language is None
    assert CreateConversation(**values, source=ConversationSource.friend).language == 'en'
    assert CreateConversation(**values, source=ConversationSource.friend, language='  ').language == 'en'
    assert CreateConversation(**values, source=ConversationSource.friend, language='fr').language == 'fr'


def test_worker_count_must_be_positive():
    with pytest.raises(ArgumentTypeError):
        migrate_conversation_language._positive_int('0')
    with pytest.raises(SystemExit):
        migrate_conversation_language._build_parser().parse_args(['--workers', '0'])


def test_user_limit_must_be_nonnegative():
    with pytest.raises(ArgumentTypeError):
        migrate_conversation_language._nonnegative_int('-1')
    with pytest.raises(SystemExit):
        migrate_conversation_language._build_parser().parse_args(['--limit', '-1'])


def test_user_pages_are_bounded_and_resume_after_last_document():
    first_page = [MagicMock(id='a'), MagicMock(id='b')]
    second_page = [MagicMock(id='c')]
    firestore_client = MagicMock()
    users_query = firestore_client.collection.return_value.order_by.return_value
    first_query = users_query
    second_query = users_query.start_after.return_value
    first_query.limit.return_value.stream.return_value = first_page
    second_query.limit.return_value.stream.return_value = second_page

    assert list(migrate_conversation_language._iter_user_pages(firestore_client, page_size=2)) == [['a', 'b'], ['c']]
    users_query.start_after.assert_called_once_with(first_page[-1])
    first_query.limit.assert_called_once_with(2)
    second_query.limit.assert_called_once_with(2)


def test_empty_uid_is_rejected_before_user_enumeration(monkeypatch):
    monkeypatch.setattr('sys.argv', ['migrate_conversation_language', '--uid', '  '])

    with pytest.raises(SystemExit):
        migrate_conversation_language.main()


def test_migration_worker_reports_client_errors():
    firestore_client = MagicMock()
    firestore_client.collection.side_effect = RuntimeError('test client failure')

    result = migrate_conversation_language.process_user('uid', dry_run=True, firestore_client=firestore_client)

    assert result['uid'] == 'uid'
    assert result['fixed'] == 0
    assert result['status'] == 'error: test client failure'
