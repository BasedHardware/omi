import os

os.environ.setdefault('TYPESENSE_API_KEY', 'test-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')

from unittest.mock import patch

import pytest

from utils.conversations.search import ConversationSearchUnavailableError, search_conversations


def test_search_conversations_typesense_timeout_failsoft():
    with patch('utils.conversations.search.client') as mock_client:
        mock_client.collections['conversations'].documents.search.side_effect = TimeoutError(
            'HTTPSConnectionPool(host="typesense"): Read timed out (read timeout=2)'
        )
        with pytest.raises(ConversationSearchUnavailableError):
            search_conversations(uid='uid-1', query='meeting notes')


def test_search_conversations_typesense_service_unavailable_failsoft():
    class ServiceUnavailable(Exception):
        pass

    ServiceUnavailable.__module__ = 'typesense.exceptions'
    with patch('utils.conversations.search.client') as mock_client:
        mock_client.collections['conversations'].documents.search.side_effect = ServiceUnavailable(
            '{"message":"not ready"}'
        )
        with pytest.raises(ConversationSearchUnavailableError):
            search_conversations(uid='uid-1', query='meeting notes')


def test_search_conversations_non_transient_error_still_raises():
    with patch('utils.conversations.search.client') as mock_client:
        mock_client.collections['conversations'].documents.search.side_effect = ValueError('bad query shape')
        with pytest.raises(Exception, match='^Failed to search conversations$') as exc_info:
            search_conversations(uid='uid-1', query='meeting notes')
        assert str(exc_info.value) == 'Failed to search conversations'
        assert 'bad query shape' not in str(exc_info.value)


@pytest.mark.parametrize(
    'value, expected', [(None, 5), ('9', 9), ('1', 1), ('30', 30), ('0', 5), ('31', 5), ('oops', 5), ('2.5', 5)]
)
def test_typesense_timeout_is_lazily_bounded(monkeypatch, value, expected):
    import utils.conversations.search as search
    from unittest.mock import MagicMock

    monkeypatch.delenv('TYPESENSE_CONNECTION_TIMEOUT_SECONDS', raising=False)
    if value is not None:
        monkeypatch.setenv('TYPESENSE_CONNECTION_TIMEOUT_SECONDS', value)
    monkeypatch.setattr(search, '_typesense_client', None)
    constructor = MagicMock()
    monkeypatch.setattr(search.typesense, 'Client', constructor)
    search._get_typesense_client()
    assert constructor.call_args.args[0]['connection_timeout_seconds'] == expected


def test_keyword_helper_can_surface_degradation(monkeypatch):
    import utils.conversations.search as search

    def unavailable(**kwargs):
        raise TimeoutError('keyword index offline')

    monkeypatch.setattr(search, 'search_conversations', unavailable)
    assert search.keyword_search_conversation_ids('uid', 'topic') == []
    with pytest.raises(ConversationSearchUnavailableError):
        search.keyword_search_conversation_ids('uid', 'topic', raise_on_error=True)
