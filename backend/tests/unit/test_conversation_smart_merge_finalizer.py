"""The finalizer runs the smart-merge step behind the fanout claim and before derived effects."""

import pytest

from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.smart_merge import SmartMergeIncomplete


class _Conversation:
    def __init__(self):
        self.id = 'n'
        self.status = ConversationStatus.completed
        self.source = 'omi'
        self.discarded = False
        self.structured = None
        self.geolocation = None
        self.client_device_id = None


@pytest.fixture
def harness(monkeypatch):
    calls = []
    row = {'id': 'n', 'status': 'completed', 'source': 'omi'}

    async def fake_run_blocking(_executor, function, *args, **kwargs):
        calls.append(function)
        if function is finalizer.conversations_db.get_conversation:
            return row
        if function is finalizer.get_cached_user_geolocation:
            return None
        if function is finalizer.lifecycle_service.claim_finalization_fanout:
            return {'status': 'claimed', 'fanout_key': 'key'}
        if function is finalizer.lifecycle_service.complete_finalization_fanout:
            return True
        if function is finalizer.link_duplicate_captures:
            raise RuntimeError('reached derived work')
        raise AssertionError(f'unexpected blocking call: {function!r}')

    monkeypatch.setattr(finalizer, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: _Conversation())
    return calls, row


async def _finalize(trigger=ProcessingTrigger.CAPTURE_END):
    return await finalizer.finalize_persisted_conversation(
        'u', 'n', finalization_job_id='job', dispatch_generation=1, lease_epoch=1, trigger=trigger
    )


@pytest.mark.asyncio
async def test_absorbed_conversation_skips_every_derived_effect_and_completes_fanout(harness, monkeypatch):
    calls, row = harness
    seen = {}

    async def absorbed(uid, conversation_id, initial_row, *, trigger, owner):
        seen.update(uid=uid, conversation_id=conversation_id, row=initial_row, trigger=trigger, owner=owner)
        return True

    monkeypatch.setattr(finalizer, 'smart_merge_step', absorbed)
    assert await _finalize() is finalizer.ConversationFinalizationDisposition.completed
    assert seen == {
        'uid': 'u',
        'conversation_id': 'n',
        'row': row,
        'trigger': ProcessingTrigger.CAPTURE_END,
        'owner': 'job',
    }
    assert calls[-1] is finalizer.lifecycle_service.complete_finalization_fanout
    assert finalizer.link_duplicate_captures not in calls


@pytest.mark.asyncio
async def test_kept_conversation_continues_down_the_unchanged_path(harness, monkeypatch):
    calls, _ = harness

    async def kept(*args, **kwargs):
        return False

    monkeypatch.setattr(finalizer, 'smart_merge_step', kept)
    with pytest.raises(finalizer.ConversationFinalizationError):
        await _finalize()
    # It reached the first derived step (the harness stops there).
    assert calls[-1] is finalizer.link_duplicate_captures


@pytest.mark.asyncio
async def test_incomplete_merge_is_a_retryable_finalization_failure(harness, monkeypatch):
    async def incomplete(*args, **kwargs):
        raise SmartMergeIncomplete('refresh')

    monkeypatch.setattr(finalizer, 'smart_merge_step', incomplete)
    with pytest.raises(finalizer.ConversationFinalizationError) as raised:
        await _finalize()
    assert str(raised.value) == 'processing_failed'


@pytest.mark.asyncio
async def test_flag_off_step_leaves_the_finalizer_on_its_existing_path(harness, monkeypatch):
    calls, _ = harness
    monkeypatch.delenv('CONVERSATION_SMART_MERGE_MODE', raising=False)
    with pytest.raises(finalizer.ConversationFinalizationError):
        await _finalize()
    assert calls == [
        finalizer.conversations_db.get_conversation,
        finalizer.get_cached_user_geolocation,
        finalizer.lifecycle_service.claim_finalization_fanout,
        finalizer.link_duplicate_captures,
    ]
