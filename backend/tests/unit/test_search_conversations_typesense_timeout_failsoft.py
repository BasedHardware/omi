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


def test_search_conversations_non_transient_error_still_raises():
    with patch('utils.conversations.search.client') as mock_client:
        mock_client.collections['conversations'].documents.search.side_effect = ValueError('bad query shape')
        with pytest.raises(Exception, match='Failed to search conversations'):
            search_conversations(uid='uid-1', query='meeting notes')
