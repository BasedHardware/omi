"""Source-document deletion must finish before a manual merge reports success."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules


@pytest.fixture
def merge(monkeypatch):
    # The worker and cleanup helper are real. Only their I/O dependencies and
    # conversation model are isolated; no cloud clients are constructed.
    names = [
        'database',
        'database._client',
        'database.conversations',
        'database.action_items',
        'database.vector_db',
        'models',
        'models.audio_file',
        'models.conversation',
        'models.conversation_enums',
        'models.structured',
        'utils.cloud_tasks',
        'utils.conversations.lifecycle',
        'utils.conversations.process_conversation',
        'utils.conversations.smart_merge_audit',
        'utils.conversations.capture_shadow_outcomes',
        'utils.memory.memory_service',
        'utils.memory.retraction_scope',
        'utils.notifications',
        'utils.other.storage',
    ]
    fakes = {name: AutoMockModule(name) for name in names}
    fakes['database'].__path__ = []
    fakes['models'].__path__ = []
    fakes['models.conversation'].Conversation.side_effect = lambda **fields: SimpleNamespace(
        **fields, model_dump=lambda: dict(fields)
    )
    fakes['database.action_items'].get_action_items_by_conversation.return_value = []
    fakes['database.conversations'].get_conversation.return_value = {}
    fakes['utils.memory.retraction_scope'].canonical_intake_is_fenced.return_value = False
    fakes['utils.memory.retraction_scope'].retraction_can_be_skipped.return_value = True

    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.conversations.merge_conversations',
            str(Path(__file__).resolve().parents[2] / 'utils/conversations/merge_conversations.py'),
        )
        monkeypatch.setattr(module, '_collect_all_photos', lambda *_args: [])
        monkeypatch.setattr(module, '_copy_audio_chunks_for_merge', lambda *_args: [])
        monkeypatch.setattr(module, '_cleanup_merged_target_after_failure', MagicMock(return_value=True))
        # Keep the real notification import inside perform_merge_async, and
        # expose its stub for assertions about the external success signal.
        module_test_context = SimpleNamespace(
            module=module, notifications=fakes['utils.notifications'], action_items=fakes['database.action_items']
        )
        yield module_test_context


@pytest.mark.parametrize('purge_sync_sources', [True, False])
def test_source_document_deletion_failure_propagates(merge, purge_sync_sources):
    module = merge.module
    delete = module.conversations_db.delete_conversation
    failure = RuntimeError('source document unavailable')
    delete.side_effect = failure

    with pytest.raises(RuntimeError) as caught:
        module._delete_conversation_and_related_data('test-user', 'source-a', purge_sync_sources=purge_sync_sources)

    assert caught.value is failure
    delete.assert_called_once_with('test-user', 'source-a')


def _install_sources(module):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    sources = {
        cid: {
            'id': cid,
            'created_at': now + timedelta(minutes=index),
            'started_at': now + timedelta(minutes=index),
            'finished_at': now + timedelta(minutes=index + 1),
            'language': 'en',
            'source': 'omi',
            'transcript_segments': [],
        }
        for index, cid in enumerate(['source-a', 'source-b'])
    }
    module.conversations_db.get_conversation.side_effect = lambda _uid, cid: sources[cid]


@pytest.mark.parametrize('failed_source', ['source-a', 'source-b'])
def test_merge_delete_failure_preserves_target_and_withholds_success(merge, failed_source):
    module = merge.module
    _install_sources(module)

    def delete_source(_uid, cid):
        if cid == failed_source:
            raise RuntimeError('source document unavailable')

    module.conversations_db.delete_conversation.side_effect = delete_source

    module.perform_merge_async('test-user', ['source-a', 'source-b'], reprocess=False)

    attempted = ['source-a'] if failed_source == 'source-a' else ['source-a', 'source-b']
    assert module.conversations_db.delete_conversation.call_args_list == [call('test-user', cid) for cid in attempted]
    module._cleanup_merged_target_after_failure.assert_not_called()
    module.record_capture_outcome.assert_not_called()
    merge.notifications.send_merge_completed_message.assert_not_called()
    merged_id = module.lifecycle_service.create_processing_conversation.call_args.args[1]['id']
    assert module.lifecycle_service.complete.call_args_list == [
        call('test-user', merged_id),
        call('test-user', 'source-a'),
        call('test-user', 'source-b'),
    ]


def test_merge_reports_success_only_after_both_sources_are_deleted(merge):
    module = merge.module
    _install_sources(module)
    events = []
    module.conversations_db.delete_conversation.side_effect = lambda _uid, cid: events.append(cid)
    module.record_capture_outcome.side_effect = lambda *_args: events.append('outcome')
    merge.notifications.send_merge_completed_message.side_effect = lambda *_args: events.append('notification')

    module.perform_merge_async('test-user', ['source-a', 'source-b'], reprocess=False)

    assert events == ['source-a', 'source-b', 'outcome', 'notification']
    module._cleanup_merged_target_after_failure.assert_not_called()


@pytest.mark.parametrize('artifact', ['action_items', 'photos', 'audio', 'vector'])
def test_artifact_cleanup_remains_best_effort(merge, artifact):
    module = merge.module
    cleanup = {
        'action_items': merge.action_items.delete_action_items_for_conversation,
        'photos': module.conversations_db.delete_conversation_photos,
        'audio': module.delete_conversation_audio_files,
        'vector': module.delete_vector,
    }[artifact]
    cleanup.side_effect = RuntimeError('artifact unavailable')

    module._delete_conversation_and_related_data('test-user', 'source-a')

    cleanup.assert_called_once_with('test-user', 'source-a')
    module.conversations_db.delete_conversation.assert_called_once_with('test-user', 'source-a')
