"""Reprocess and GET-by-id must reject a soft-deleted conversation.

`_get_valid_conversation_by_id` 404s a `deleted` tombstone so user-facing routes
cannot fetch a merged-away donor. Reprocess keeps a second `is_soft_deleted`
check because it force-processes discarded rows: a tombstone must not enter
`process_conversation` even if a caller patches the helper.

The guard rejects a *deleted* conversation while still allowing a *discarded* one,
which reprocess intentionally revives — the same tombstone-eligibility contract as
sync (#10119) and merge (#10262), via the shared `is_soft_deleted` predicate.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from database.conversations import eligible_merge_target, is_soft_deleted


class TestIsSoftDeleted:
    def test_deleted_is_tombstoned(self):
        assert is_soft_deleted({'id': 'c1', 'deleted': True}) is True

    def test_discarded_is_not_tombstoned(self):
        # Discarded stays revivable — reprocess/merge intentionally revive it.
        assert is_soft_deleted({'id': 'c1', 'discarded': True}) is False

    def test_plain_conversation_is_not_tombstoned(self):
        assert is_soft_deleted({'id': 'c1'}) is False

    def test_none_is_not_tombstoned(self):
        assert is_soft_deleted(None) is False

    def test_eligible_merge_target_still_excludes_only_deleted(self):
        # The refactor onto is_soft_deleted must be behaviour-preserving.
        assert eligible_merge_target({'id': 'c1', 'deleted': True}) is False
        assert eligible_merge_target({'id': 'c1', 'discarded': True}) is True
        assert eligible_merge_target(None) is False


class TestGetValidConversationByIdTombstone:
    def test_helper_404s_a_soft_deleted_conversation(self):
        deleted = {'id': 'c1', 'deleted': True, 'sync_merged_into': 'survivor'}
        with patch.object(conv_router.conversations_db, 'get_conversation', return_value=deleted):
            with pytest.raises(HTTPException) as exc:
                conv_router._get_valid_conversation_by_id('u1', 'c1')
        assert exc.value.status_code == 404

    def test_helper_returns_a_live_conversation(self):
        live = {'id': 'c1', 'status': 'completed'}
        with patch.object(conv_router.conversations_db, 'get_conversation', return_value=live):
            assert conv_router._get_valid_conversation_by_id('u1', 'c1') == live


class TestReprocessTombstoneGuard:
    def test_reprocess_rejects_soft_deleted_conversation(self):
        deleted = {'id': 'c1', 'deleted': True, 'status': 'completed'}
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=deleted), patch.object(
            conv_router, 'process_conversation'
        ) as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation(conversation_id='c1', uid='u1')
        assert exc.value.status_code == 404
        process.assert_not_called()  # deleted content never re-enters the pipeline

    def test_reprocess_still_allows_a_discarded_conversation(self):
        discarded = {'id': 'c1', 'discarded': True, 'status': 'completed'}
        fake_conv = SimpleNamespace(language='en')
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=discarded), patch.object(
            conv_router, 'deserialize_conversation', return_value=fake_conv
        ), patch.object(conv_router, 'process_conversation', return_value=fake_conv) as process:
            result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')
        process.assert_called_once()
        assert result is fake_conv


@pytest.mark.parametrize('discarded,restored', [(False, True), (False, False), (True, False)])
def test_explicit_reprocess_promotes_review_only_after_success(discarded, restored):
    row = {'id': 'c1', 'discarded': True, 'status': 'completed', 'sync_relevance': 'review'}
    model = SimpleNamespace(language='en', discarded=discarded, sync_relevance='review')
    with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=row), patch.object(
        conv_router, 'deserialize_conversation', return_value=model
    ), patch.object(conv_router, 'process_conversation', return_value=model), patch.object(
        conv_router.lifecycle_service, 'restore_discarded', return_value=restored
    ) as restore:
        result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')
    if discarded:
        restore.assert_not_called()
    else:
        restore.assert_called_once_with('u1', 'c1')
    assert result.sync_relevance == ('keep' if restored else 'review')
