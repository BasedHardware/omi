"""The finalizer runs the smart-merge step behind the fanout claim and before derived effects.

A donor (a committed absorb whose cleanup or refresh failed) is resumed before
the claim, because the production claim fences its discarded row. The fake claim
here applies that production admission rule; it must never answer ``claimed``
for a row production would fence, or the donor retry path is hidden again.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from utils import rollout_cohorts

from database import conversation_finalization_jobs as jobs_db
from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations import smart_merge
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.smart_merge import SmartMergeIncomplete

_JOB = {
    'finalization_revision': 1,
    'uid': 'u',
    'conversation_id': 'n',
    'status': 'leased',
    'dispatch_generation': 1,
    'lease_epoch': 1,
}
_BOUND = {'finalization_job_id': 'job', 'finalization_revision': 1}
_DONOR = {
    'deleted': True,
    'discarded': True,
    'sync_merged_into': 'p',
    'smart_merge': {'role': 'donor', 'survivor_id': 'p', 'survivor_revision': 1},
}


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
    row = {'id': 'n', 'status': 'completed', 'source': 'omi', 'discarded': False, **_BOUND}
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    # The live-episode hook runs after fanout completion; its own tests cover it.
    monkeypatch.setenv('EPISODES_ENABLED', 'off')
    monkeypatch.setenv('CALLS_RECAP_MODE', 'off')

    async def fake_run_blocking(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            calls.append(function)
            return row
        if function is finalizer.reserve_recording:
            # Exercise the real default-off gate; it must not claim a route or touch Firestore.
            return function(*args, **kwargs)
        if function is finalizer.apply_call_metadata:
            return function(*args, **kwargs)
        calls.append(function)
        if function is finalizer.finalization_jobs_db.get_finalization_job:
            return _JOB
        if function is finalizer.get_cached_user_geolocation:
            return None
        if function is finalizer.lifecycle_service.claim_finalization_fanout:
            # Production admission (discarded or unbound rows are fenced), not an always-claimed fake.
            admitted = jobs_db._conversation_admits_fanout(row, _JOB, 'job')  # pyright: ignore[reportPrivateUsage]
            return {'status': 'claimed' if admitted else 'fenced', 'fanout_key': 'key'}
        if function is finalizer.lifecycle_service.complete_finalization_fanout:
            return True
        if function is finalizer.link_duplicate_captures:
            raise RuntimeError('reached derived work')
        raise AssertionError(f'unexpected blocking call: {function!r}')

    monkeypatch.setattr(finalizer, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: _Conversation())
    return calls, row


@pytest.fixture
def resumes(monkeypatch):
    """Record the real smart_merge_step's donor resume; set ``error`` to make it fail."""
    seen = {'calls': [], 'error': None}

    async def direct(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    def finish_absorb(uid, donor_id, **kwargs):
        seen['calls'].append((uid, donor_id, kwargs))
        if seen['error']:
            raise seen['error']

    monkeypatch.setattr(smart_merge, 'run_blocking', direct)
    monkeypatch.setattr(smart_merge, 'finish_absorb', finish_absorb)
    return seen


async def _finalize(trigger=ProcessingTrigger.CAPTURE_END):
    return await finalizer.finalize_persisted_conversation(
        'u', 'n', finalization_job_id='job', dispatch_generation=1, lease_epoch=1, trigger=trigger
    )


@pytest.mark.asyncio
async def test_completed_minimum_reaches_processing_under_its_existing_job(harness, monkeypatch):
    calls, row = harness
    row.update(summary_title_provenance='server_minimum', summary_output_present=False)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    original = finalizer.run_blocking
    processed = []

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.process_with_episode_budget:
            processed.append(args)
            # A failed summary must fail this delivery before terminal fanout,
            # retaining the existing durable job's retry rather than skipping it.
            raise RuntimeError('synthetic provider unavailable')
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', run)
    with pytest.raises(finalizer.ConversationFinalizationError):
        await _finalize()
    assert len(processed) == 1
    assert processed[0][0] is finalizer.process_conversation
    assert finalizer.lifecycle_service.complete_finalization_fanout not in calls


def test_default_off_reservation_does_not_claim_record_owner(monkeypatch):
    from utils.batch_pipeline import live as batch_live

    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')

    def unexpected_claim(*_args, **_kwargs):
        raise AssertionError('dark-path reservation attempted a Firestore owner claim')

    monkeypatch.setattr(batch_live, 'claim_record_lane_owner', unexpected_claim)
    conversation = {
        'id': 'n',
        'status': 'processing',
        'private_cloud_sync_enabled': True,
        'language': 'en',
        'data_protection_level': 'standard',
    }

    assert finalizer.reserve_recording('u', conversation) is None
    assert 'record_lane_owner' not in conversation


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
@pytest.mark.parametrize('mode', ['off', 'shadow', 'merge'])
async def test_non_donor_stage_order_is_unchanged_in_every_mode(harness, resumes, monkeypatch, mode):
    calls, _ = harness
    monkeypatch.setenv('CONVERSATION_SMART_MERGE_MODE', mode)
    monkeypatch.setattr(smart_merge, 'decide_and_apply', lambda *args, **kwargs: False)
    with pytest.raises(finalizer.ConversationFinalizationError):
        await _finalize()
    assert calls == [
        finalizer.conversations_db.get_conversation,
        finalizer.get_cached_user_geolocation,
        finalizer.lifecycle_service.claim_finalization_fanout,
        finalizer.link_duplicate_captures,
    ]
    assert resumes['calls'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'trigger', [ProcessingTrigger.CAPTURE_END, ProcessingTrigger.CLIENT_FINALIZE, ProcessingTrigger.SERVER_RECOVERY]
)
@pytest.mark.parametrize('mode', ['off', 'shadow', 'merge'])
async def test_donor_retry_resumes_the_absorb_before_the_claim_fences_it(harness, resumes, monkeypatch, mode, trigger):
    calls, row = harness
    row.update(_DONOR)
    monkeypatch.setenv('CONVERSATION_SMART_MERGE_MODE', mode)
    assert await _finalize(trigger) is finalizer.ConversationFinalizationDisposition.fenced
    assert resumes['calls'] == [('u', 'n', {'owner': 'job', 'resumed': True})]
    # No geolocation, no derived work: resume, then the claim that closes the job.
    assert calls == [
        finalizer.conversations_db.get_conversation,
        finalizer.finalization_jobs_db.get_finalization_job,
        finalizer.lifecycle_service.claim_finalization_fanout,
    ]


@pytest.mark.asyncio
async def test_donor_resume_failure_stays_retryable_and_never_claims(harness, resumes, caplog):
    calls, row = harness
    row.update(_DONOR)
    resumes['error'] = SmartMergeIncomplete('RuntimeError')
    caplog.set_level('WARNING', logger=finalizer.logger.name)
    with pytest.raises(finalizer.ConversationFinalizationError) as raised:
        await _finalize()
    assert str(raised.value) == 'processing_failed'
    assert calls == [finalizer.conversations_db.get_conversation, finalizer.finalization_jobs_db.get_finalization_job]
    assert any('stage=smart_merge exception_type=SmartMergeIncomplete' in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_pusher_finalizer_refreshes_expired_shadow_cohort_before_admission(harness, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    conversation = _Conversation()
    conversation.status = ConversationStatus.processing
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _data: conversation)
    membership = [True]
    reads = []
    seen = []

    def read(uid):
        reads.append(uid)
        return {'prod': {'transcription-shadow': membership[0]}}

    def admit(uid, _conversation):
        seen.append(rollout_cohorts.in_rollout_cohort(uid, 'transcription-shadow'))
        raise RuntimeError('stop after real shadow admission boundary')

    monkeypatch.setattr(finalizer, '_maybe_start_shadow', admit)
    rollout_cohorts.configure_rollout_runtime()
    cache = rollout_cohorts._TTLReads(read)
    monkeypatch.setattr(rollout_cohorts, '_cache', cache)
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(rollout_cohorts, '_background_submitter', pool.submit)
        for value in (True, False):
            membership[0] = value
            if 'u' in cache.entries:
                cache.entries['u'].expires = 0
            with pytest.raises(finalizer.ConversationFinalizationError):
                await _finalize()
    assert seen == [True, False]
    assert reads == ['u', 'u']
