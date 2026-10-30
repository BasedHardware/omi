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
        """Any successful explicit reprocess of a hidden row is the user's keep, not only sync review rows."""
        discarded = {'id': 'c1', 'discarded': True, 'status': 'completed'}
        fake_conv = SimpleNamespace(language='en', discarded=False, sync_relevance=None)
        with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=discarded), patch.object(
            conv_router, 'deserialize_conversation', return_value=fake_conv
        ), patch.object(conv_router, 'process_conversation', return_value=fake_conv) as process, patch.object(
            conv_router.lifecycle_service, 'restore_discarded', return_value=True
        ) as restore:
            result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')
        process.assert_called_once()
        restore.assert_called_once_with('u1', 'c1')
        assert result is fake_conv
        assert result.sync_relevance is None


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


@pytest.mark.parametrize('app_ids', [(None, None), ('first-app', 'second-app')])
def test_concurrent_reprocess_calls_share_the_active_summary_writer(monkeypatch, app_ids):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    row = {'id': 'c1', 'status': 'completed', 'structured': {'overview': 'Existing summary'}}
    model = SimpleNamespace(language='en', discarded=False, structured=SimpleNamespace(overview='New summary'))
    started, release = Event(), Event()

    def paid(*args, **kwargs):
        started.set()
        assert release.wait(5), 'test did not release the active processor'
        return model

    with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=row), patch.object(
        conv_router, 'deserialize_conversation', return_value=model
    ), patch.object(
        conv_router, '_validate_reprocess_app_selection', side_effect=lambda uid, app_id: SimpleNamespace(id=app_id)
    ), patch.object(
        conv_router, 'process_conversation', side_effect=paid
    ) as process, patch.object(
        conv_router, 'schedule_reprocessed_learning', return_value=model
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(conv_router.reprocess_conversation, 'c1', uid='u1', app_id=app_ids[0])
            try:
                assert started.wait(5), 'processor did not start'
                concurrent = pool.submit(conv_router.reprocess_conversation, 'c1', uid='u1', app_id=app_ids[1])
                # The second caller never echoes the stale row as success (summary-v2 F1).
                with pytest.raises(HTTPException) as busy:
                    concurrent.result(timeout=5)
                assert busy.value.status_code == 409
                assert busy.value.detail['code'] == 'conversation_processing_in_progress'
                process.assert_called_once()
                assert process.call_args.kwargs['app_id'] == app_ids[0]
            finally:
                release.set()
            assert first.result(timeout=5) is model
    process.assert_called_once()


@pytest.mark.parametrize('app_ids', [(None, None), ('first-app', 'second-app')])
def test_sequential_reprocess_calls_both_run_after_success(monkeypatch, app_ids):
    from database import processing_attention as attention

    row = {'id': 'c1', 'status': 'completed', 'structured': {'overview': 'Existing summary'}}
    # An explicit selection only returns after its app produced a result; the
    # attention outcome is judged on that result, not on the notes overview.
    model = SimpleNamespace(
        language='en',
        discarded=False,
        structured=SimpleNamespace(overview='New summary'),
        apps_results=[SimpleNamespace(app_id=app_id, content='App summary') for app_id in app_ids if app_id],
    )
    with patch.object(conv_router, '_get_valid_conversation_by_id', return_value=row), patch.object(
        conv_router, 'deserialize_conversation', return_value=model
    ), patch.object(
        conv_router, '_validate_reprocess_app_selection', side_effect=lambda uid, app_id: SimpleNamespace(id=app_id)
    ), patch.object(
        conv_router, 'process_conversation', return_value=model
    ) as process, patch.object(
        conv_router, 'schedule_reprocessed_learning', return_value=model
    ):
        assert conv_router.reprocess_conversation('c1', uid='u1', app_id=app_ids[0]) is model
        assert conv_router.reprocess_conversation('c1', uid='u1', app_id=app_ids[1]) is model
    assert process.call_count == 2
    assert [call.kwargs['app_id'] for call in process.call_args_list] == list(app_ids)
    claim_id = attention.claim_id('c1', attention.generation(row))
    current = attention.db.rows[('users', 'u1', 'conversations', 'c1', 'processing_retry_claims', claim_id)]
    assert current['attempt'] == 2
    assert current['state'] == 'succeeded'


@pytest.fixture(autouse=True)
def retry_ledger(monkeypatch):
    from database import processing_attention as attention
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    client = StrictFirestore({('users', 'u1', 'conversations', 'c1'): {'id': 'c1', 'status': 'completed'}})
    monkeypatch.setattr(attention, 'db', client)
    monkeypatch.setattr(attention.firestore, 'transactional', lambda fn: fn)

    def run(client, fn, *args, **kwargs):
        with client.lock:
            return fn(client.transaction(), *args, **kwargs)

    monkeypatch.setattr(attention, 'run_transactional', run)
