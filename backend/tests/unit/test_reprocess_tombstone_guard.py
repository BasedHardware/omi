"""Reprocess must reject a soft-deleted conversation.

`POST /v1/conversations/{id}/reprocess` fetches through `_get_valid_conversation_by_id`,
which does not filter soft-deleted tombstones (`get_conversation` returns them and the
helper only 404s on a missing doc). Reprocessing runs `process_conversation` with
`force_process=True`, regenerating structured data, action items, memories and
embeddings — so reprocessing a tombstone resurrects content the user deleted.

The guard rejects a *deleted* conversation while still allowing a *discarded* one,
which reprocess intentionally revives — the same tombstone-eligibility contract as
sync (#10119) and merge (#10262), via the shared `is_soft_deleted` predicate.
"""

from contextlib import nullcontext
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
        discarded = {
            'id': 'c1',
            'discarded': True,
            'status': 'completed',
            'finalization_incarnation_id': 'incarnation-1',
        }
        fake_conv = SimpleNamespace(language='en')

        def process_contract(*args, **kwargs):
            kwargs['persistence_observer'](True)
            return fake_conv

        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=discarded), patch.object(
            conv_router, 'deserialize_conversation', return_value=fake_conv
        ), patch.object(conv_router, 'process_conversation', side_effect=process_contract) as process, patch.object(
            conv_router.lifecycle_service, 'processing_admission_guard', return_value=nullcontext()
        ), patch.object(
            conv_router.finalization_identity_db,
            'ensure_conversation_finalization_identity',
            return_value=('incarnation-1', None, None),
        ):
            result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')
        process.assert_called_once()
        assert process.call_args.kwargs['expected_finalization_identity'] == ('incarnation-1', None, None)
        assert result is fake_conv

    def test_reprocess_stamps_and_rereads_a_legacy_conversation(self):
        legacy = {'id': 'c1', 'status': 'completed'}
        stamped = {**legacy, 'finalization_incarnation_id': 'incarnation-stamped'}
        fake_conv = SimpleNamespace(language='en')

        def process_contract(*args, **kwargs):
            kwargs['persistence_observer'](True)
            return fake_conv

        with patch.object(conv_router, '_get_valid_conversation_by_id', side_effect=(legacy, stamped)), patch.object(
            conv_router, 'deserialize_conversation', return_value=fake_conv
        ) as deserialize, patch.object(
            conv_router, 'process_conversation', side_effect=process_contract
        ) as process, patch.object(
            conv_router.lifecycle_service, 'processing_admission_guard', return_value=nullcontext()
        ), patch.object(
            conv_router.finalization_identity_db,
            'ensure_conversation_finalization_identity',
            return_value=('incarnation-stamped', None, None),
        ) as ensure_identity:
            result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')

        ensure_identity.assert_called_once_with('u1', 'c1')
        deserialize.assert_called_once_with(stamped)
        assert process.call_args.kwargs['expected_finalization_identity'] == ('incarnation-stamped', None, None)
        assert result is fake_conv

    def test_reprocess_rejects_an_unavailable_or_malformed_identity(self):
        conversation = {'id': 'c1', 'status': 'completed'}
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=conversation), patch.object(
            conv_router.finalization_identity_db, 'ensure_conversation_finalization_identity', return_value=None
        ), patch.object(conv_router, 'process_conversation') as process:
            with pytest.raises(HTTPException) as exc:
                conv_router.reprocess_conversation(conversation_id='c1', uid='u1')

        assert exc.value.status_code == 409
        process.assert_not_called()
