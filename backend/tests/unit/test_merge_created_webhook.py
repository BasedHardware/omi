"""A merge must not announce a merged conversation that its own rollback deletes.

perform_merge_async processes the new merged conversation, which produces the
developer ``conversation_created`` webhook, before ``review_overlay_merge.transfer``
moves the correction anchors and the sources are deleted. A transfer conflict (a
source deleted, locked or edited while the merge was processing) rolls the merge
back and deletes the merged conversation, so the webhook must wait until that
rollback is no longer possible.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import sys
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

import utils.conversations.merge_conversations as merge


@pytest.fixture(scope='module', autouse=True)
def _warm_merge_imports():
    """perform_merge_async does heavy local imports at call time. Charge them to
    module setup so the fast-unit CPU-time guard measures only the call phase."""
    import database.review_overlay_merge  # noqa: F401
    import utils.conversations.process_conversation  # noqa: F401
    import utils.notifications  # noqa: F401


def _install(monkeypatch, transfer_result):
    """Stub the merge's storage edges; record transfer, webhook, deletes and completion in order."""
    from database import review_overlay_merge
    import utils.notifications as notifications

    events = []
    sources = {
        'c1': {'id': 'c1', 'status': 'completed', 'started_at': None},
        'c2': {'id': 'c2', 'status': 'completed', 'started_at': None},
    }
    monkeypatch.setattr(merge.conversations_db, "get_conversation", lambda uid, cid: sources.get(cid))
    monkeypatch.setattr(merge, "_collect_all_photos", lambda uid, convs: [])
    monkeypatch.setattr(merge, "_copy_audio_chunks_for_merge", lambda uid, convs, new_id: [])
    monkeypatch.setattr(merge, "_determine_visibility", lambda convs: 'private')
    monkeypatch.setattr(merge, "_shared_client_device_provenance", lambda convs: (None, None))
    monkeypatch.setattr(
        merge,
        "Conversation",
        lambda **kw: MagicMock(
            **{'model_dump.return_value': {'id': kw['id'], 'language': 'en'}, 'id': kw['id'], 'language': 'en'}
        ),
    )
    monkeypatch.setattr(merge.lifecycle_service, "create_processing_conversation", MagicMock(return_value=True))
    monkeypatch.setattr(merge.lifecycle_service, "processing_admission_guard", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(merge.lifecycle_service, "complete", MagicMock())
    monkeypatch.setattr(merge, "is_audio_merge_dispatch_enabled", lambda: False)
    monkeypatch.setattr(merge, "canonical_intake_is_fenced", lambda: False)
    monkeypatch.setattr(
        merge, "_delete_conversation_and_related_data", lambda uid, cid, **kwargs: events.append(('delete', cid))
    )
    fail = MagicMock()
    monkeypatch.setattr(merge, "_handle_merge_failure", fail)

    def transfer(uid, source_ids, destination_id, **kwargs):
        events.append(('transfer', destination_id))
        return transfer_result()

    monkeypatch.setattr(review_overlay_merge, 'transfer', transfer)
    monkeypatch.setattr(
        notifications,
        'send_merge_completed_message',
        lambda uid, new_id, conversation_ids: events.append(('merge_completed', new_id)),
    )

    def process(uid, language, conversation, *, created_webhook_observer=None, **kwargs):
        # process_conversation's MERGE contract (not a reprocess): send the created
        # webhook during processing, or hand that send to the observer.
        def send():
            events.append(('created_webhook', conversation.id))

        if created_webhook_observer is None:
            send()
        else:
            created_webhook_observer(send)
        return conversation

    monkeypatch.setattr(sys.modules['utils.conversations.process_conversation'], 'process_conversation', process)
    return events, fail


def test_transfer_rollback_never_announces_the_merged_conversation_it_deletes(monkeypatch):
    from database.review_store import ReviewConflict

    def conflict():
        # A source was deleted, locked or edited while the merge was processing.
        raise ReviewConflict('Merge source unavailable')

    events, fail = _install(monkeypatch, conflict)

    merge.perform_merge_async('u1', ['c1', 'c2'])

    merged_id = next(conversation_id for event, conversation_id in events if event == 'transfer')
    assert events == [('transfer', merged_id)]
    # The rollback deletes this merged record, so no webhook may have announced it.
    fail.assert_called_once_with(
        'u1',
        ['c1', 'c2'],
        merged_conversation_id=merged_id,
        failure_phase=merge.MergeFailurePhase.BEFORE_SOURCE_DELETION,
    )


def test_committed_merge_announces_the_merged_conversation_once_transfer_succeeds(monkeypatch):
    events, fail = _install(monkeypatch, lambda: True)

    merge.perform_merge_async('u1', ['c1', 'c2'])

    merged_id = next(conversation_id for event, conversation_id in events if event == 'transfer')
    assert events == [
        ('transfer', merged_id),
        ('created_webhook', merged_id),
        ('delete', 'c1'),
        ('delete', 'c2'),
        ('merge_completed', merged_id),
    ]
    fail.assert_not_called()
