"""Actual Dream coordinator, storage admission, verified journal apply and Undo."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import AsyncMock

import pytest

from config.dream_session import SessionLimits
from database import dream_store, dream_turns, legal_holds, review_store, review_changes
from database.legal_holds import DestructiveOperationInProgress, LegalHoldActive
from models.agent_edit import HarnessEdit
from models.agent_tools import VerificationBatch, Verification
from tests.unit.test_dream_cleanup_edits import store, records, UID  # pyright: ignore[reportUnusedImport]
from tests.unit.test_dream_session import call, turn
from utils.agent_capabilities import tools as dream_tools
from utils import dream_agent, dream_seed, dream_capacity
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE
from utils.llm.shaped_agent import Turn


@pytest.fixture
def runtime(store, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(
        legal_holds, 'account_deletion_firestore_client', lambda **kwargs: kwargs.get('firestore_client') or store
    )
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *args: set())
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_turns.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=('synthetic-slot', 'synthetic-token')))
    monkeypatch.setattr(dream_capacity, 'release', AsyncMock())
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records(store).get(ref))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: (
            {'targets': list(records(store)), 'vocabulary': []},
            EvidenceRecords(records(store)),
            [],
            SessionLimits(),
        ),
    )
    return store


def scripted(votes, *, on_plan=None):
    verified = 0

    async def model(uid, lane, mount, messages):
        nonlocal verified
        if lane == MAIN_LANE:
            if on_plan:
                on_plan()
            return turn(
                [
                    call(
                        'propose_edit',
                        {
                            'edit': {
                                'kind': 'dismiss_person',
                                'target': 'people/junk',
                                'evidence': ['conversations/one'],
                                'reason': 'Synthetic junk profile',
                                'value': 4,
                            }
                        },
                    ),
                    call(
                        'finish',
                        {'summary': 'Checked synthetic records', 'notes': 'Look for repeated junk profiles'},
                        2,
                    ),
                ],
                tokens=10,
            )
        assert lane == VERIFY_LANE
        import json

        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        assert 'UNTRUSTED SEED' not in messages[-1]['content']
        vote = votes[verified]
        verified += 1
        return Turn(
            tokens=20,
            prompt_tokens=15,
            cached_tokens=5,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=vote, reason='Synthetic independent evidence check')
                    for row in batch
                ]
            ),
        )

    return model


@pytest.mark.parametrize(
    'votes,status', [([True, True], 'applied'), ([True, False], 'suggested'), ([False, False], 'verifier_disagree')]
)
def test_two_verifiers_select_apply_review_or_drop_and_report_counts(runtime, votes, status):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted(votes)))
    assert report['status'] == 'complete', str(report)
    assert report['tokens'] == 50 and report['cached_tokens'] == 10
    assert report['verifier_calls'] == 2 and report['turns'] == 1
    assert report['outcomes'][0]['status'] == status
    assert runtime.rows[('dream_users', UID)]['lease'] is None
    day = next(key[3] for key in runtime.rows if key[:3] == ('dream_users', UID, 'spend'))
    # Scripted turns report no priced receipt, so the conservative 3.8 hold stays.
    assert runtime.rows[('dream_users', UID, 'spend', day)]['reserved_usd'] > 0
    assert not any(key[0] == 'dream_global_spend' for key in runtime.rows)
    assert runtime.rows[('dream_users', UID, 'spend', day)].get('observed_usd', 0) == pytest.approx(0)
    if status == 'applied':
        changes = []
        for key, value in runtime.rows.items():
            if key[2:3] != ('review_changes',):
                continue
            journal = review_store.decode_doc(UID, value)
            if journal is not None:
                changes.append(journal['change'])
        review_changes.set_undone(UID, changes[0]['change_id'], True)
        assert runtime.rows[('users', UID, 'people', 'junk')] == before
    else:
        assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_dry_run_runs_real_guards_and_verifiers_without_any_storage_writes(runtime):
    before = deepcopy(runtime.rows)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True]), dry_run=True))
    assert report['status'] == 'complete', report and report['outcomes'][0]['status'] == 'dry_run'
    assert runtime.rows == before and not runtime.transactions


def test_kill_switch_prevents_reads_model_calls_and_all_effects(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    monkeypatch.setattr(dream_seed, 'load', lambda *args: pytest.fail('Disabled seed read'))
    model = AsyncMock()
    assert asyncio.run(dream_agent.run_pass(UID, turn=model)) == {'status': 'not_admitted', 'reason': 'disabled'}
    model.assert_not_called()


def _proposals(runtime):
    proposals = []
    for key, value in runtime.rows.items():
        if key[:3] != ('users', UID, 'review_proposals'):
            continue
        proposal = review_store.decode_doc(UID, value)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def _plan(*, value=4):
    return turn(
        [
            call(
                'propose_edit',
                {
                    'edit': {
                        'kind': 'dismiss_person',
                        'target': 'people/junk',
                        'evidence': ['conversations/one'],
                        'reason': 'Synthetic junk profile',
                        'value': value,
                    }
                },
            ),
            call('finish', {'summary': 'Checked synthetic records', 'notes': 'Look for repeated junk profiles'}, 2),
        ],
        tokens=10,
    )


def _verdict(messages, agree):
    batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
    return Turn(
        tokens=20,
        value=VerificationBatch(
            decisions=[
                Verification(id=row['id'], agree=agree, reason='Synthetic independent evidence check') for row in batch
            ]
        ),
    )


def test_transient_gate_contention_retries_committed_effect_idempotently(runtime, monkeypatch):
    apply = dream_tools.apply_verified_edit
    attempts = []
    waits = []

    def commit_then_contend_once(*args, **kwargs):
        status = apply(*args, **kwargs)
        attempts.append(status)
        if len(attempts) == 1:
            try:
                raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')
            except DestructiveOperationInProgress as cause:
                raise review_store.ReviewConflict('Memory lifecycle authority changed or is unavailable') from cause
        return status

    async def no_wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', commit_then_contend_once)
    monkeypatch.setattr(dream_agent, '_sleep_gate_retry', no_wait)
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])

    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'complete', report
    assert report['outcomes'][0]['status'] == 'applied'
    assert attempts == ['applied', 'applied']
    assert waits == [5]
    changes = [value for key, value in runtime.rows.items() if key[2:3] == ('review_changes',)]
    assert len(changes) == 1
    assert runtime.rows[('users', UID, 'people', 'junk')] != before


def test_earlier_pass_journal_does_not_skip_first_attempt_validation(runtime, monkeypatch):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    edit = HarnessEdit(
        kind='dismiss_person',
        target='people/junk',
        evidence=['conversations/one'],
        reason='Synthetic junk profile',
        value=4,
    )
    key = dream_tools.edit_key(edit, records(runtime))
    change_id = dream_tools.dream_change_view.change_id_for_key(UID, key)
    journal_ref = review_store.user(UID).collection('review_changes').document(review_store.safe_id(change_id))
    journal_ref.set(
        review_store.encode_doc(
            UID,
            {
                'edit_key': key,
                'created_at': datetime.now(timezone.utc) - timedelta(days=1),
                'change': {'change_id': change_id, 'undone': False},
            },
        )
    )
    revalidations = []
    revalidate = dream_tools.revalidate_proposal

    def stale_on_effect(uid, proposal):
        revalidations.append(None)
        if len(revalidations) == 2:
            raise review_store.ReviewConflict('Dream proposal evidence changed')
        return revalidate(uid, proposal)

    monkeypatch.setattr(dream_tools, 'revalidate_proposal', stale_on_effect)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'complete', report
    assert report['outcomes'][0]['status'] == 'invalid_evidence'
    assert len(revalidations) == 2
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_each_effect_gets_a_fresh_gate_backoff_index(runtime, monkeypatch):
    apply = dream_tools.apply_verified_edit
    target_ids = [f'junk-{index}' for index in range(6)]
    for index, target_id in enumerate(target_ids):
        runtime.rows[('users', UID, 'people', target_id)] = {
            'id': target_id,
            'name': f'Synthetic {index}',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        }
    attempts = {target_id: 0 for target_id in target_ids}
    waits = []

    def contend_once_per_effect(uid, edit, *args, **kwargs):
        target_id = edit.target.split('/', 1)[1]
        attempts[target_id] += 1
        if attempts[target_id] == 1:
            raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')
        return apply(uid, edit, *args, **kwargs)

    async def no_wait(seconds):
        waits.append(seconds)

    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            calls = [
                call(
                    'propose_edit',
                    {
                        'edit': {
                            'kind': 'dismiss_person',
                            'target': f'people/{target_id}',
                            'evidence': ['conversations/one'],
                            'reason': 'Synthetic junk profile',
                            'value': 4,
                        }
                    },
                    index,
                )
                for index, target_id in enumerate(target_ids, start=1)
            ]
            calls.append(call('finish', {'summary': 'Checked synthetic records', 'notes': 'Apply six edits'}, 7))
            return turn(calls, tokens=10)
        assert lane == VERIFY_LANE
        batch = json.loads(messages[-1]['content'].split('\n', 1)[1])
        return Turn(
            tokens=20,
            value=VerificationBatch(
                decisions=[
                    Verification(id=row['id'], agree=True, reason='Synthetic independent evidence check')
                    for row in batch
                ]
            ),
        )

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', contend_once_per_effect)
    monkeypatch.setattr(dream_agent, '_sleep_gate_retry', no_wait)
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))

    assert report['status'] == 'complete', report
    assert len(report['outcomes']) == len(target_ids)
    assert {item['status'] for item in report['outcomes']} == {'applied'}
    assert attempts == {target_id: 2 for target_id in target_ids}
    assert waits == [5] * len(target_ids)


def test_retry_timeout_is_reported_as_gate_contention_and_releases_lease(runtime, monkeypatch):
    def contend(*args, **kwargs):
        raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')

    async def timed_out_sleep(_seconds):
        raise TimeoutError()

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', contend)
    monkeypatch.setattr(dream_agent, '_sleep_gate_retry', timed_out_sleep)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'failed'
    assert report['error_code'] == 'dream_gate_contention'
    assert report['stop_reason'] == 'dream_gate_contention'
    assert runtime.rows[('dream_users', UID)]['lease'] is None
    release = dream_capacity.release
    assert isinstance(release, AsyncMock)
    release.assert_awaited_once()


def test_timeout_during_retried_executor_apply_keeps_lease_and_capacity(runtime, monkeypatch):
    real_timeout = asyncio.timeout
    deadlines = []
    attempts = []
    release_worker = Event()
    worker_finished = Event()

    def controlled_timeout(seconds):
        if seconds != 333:
            return real_timeout(seconds)
        deadline = real_timeout(None)
        deadlines.append(deadline)
        return deadline

    async def no_wait(_seconds):
        pass

    async def scenario():
        loop = asyncio.get_running_loop()

        def apply(*args, **kwargs):
            attempts.append(kwargs.get('gate_retry', False))
            if len(attempts) == 1:
                raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')
            loop.call_soon_threadsafe(deadlines[0].reschedule, loop.time())
            try:
                release_worker.wait()
            finally:
                worker_finished.set()
            return 'applied'

        monkeypatch.setattr(dream_tools, 'apply_verified_edit', apply)
        try:
            report = await dream_agent.run_pass(UID, turn=scripted([True, True]), timeout_seconds=333)
            assert not worker_finished.is_set()
            assert report['status'] == 'failed' and report['error_type'] == 'TimeoutError', report
            assert runtime.rows[('dream_users', UID)]['lease'] is not None
            dream_capacity.release.assert_not_awaited()
            assert attempts == [False, True]
        finally:
            release_worker.set()
            if len(attempts) == 2:
                await dream_agent.run_blocking(dream_agent.db_executor, worker_finished.wait)

    monkeypatch.setattr(dream_agent.asyncio, 'timeout', controlled_timeout)
    monkeypatch.setattr(dream_agent, '_sleep_gate_retry', no_wait)
    asyncio.run(scenario())


def test_persistent_gate_contention_has_bounded_failure_code(runtime, monkeypatch, caplog):
    attempts = []
    waits = []
    caplog.set_level('INFO', logger='utils.dream_metrics')

    def keep_contending(*args, **kwargs):
        attempts.append(None)
        raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')

    async def no_wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', keep_contending)
    monkeypatch.setattr(dream_agent, '_sleep_gate_retry', no_wait)

    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'failed'
    assert report['error_type'] == 'ValueError'
    assert report['error_code'] == 'dream_gate_contention'
    assert report['stop_reason'] == 'dream_gate_contention'
    assert len(attempts) == 5
    assert waits == [5, 15, 30, 60]
    assert 'error_code=dream_gate_contention stop_reason=dream_gate_contention' in caplog.text
    assert not [value for key, value in runtime.rows.items() if key[2:3] == ('review_changes',)]


@pytest.mark.parametrize(
    'failure',
    [
        LegalHoldActive('destructive deletion is blocked by an active legal hold'),
        DestructiveOperationInProgress('external data write blocked by account deletion'),
    ],
)
def test_legal_hold_and_account_deletion_blocks_are_not_retried(runtime, monkeypatch, failure):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(None)
        raise failure

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', blocked)
    monkeypatch.setattr(
        dream_agent,
        '_sleep_gate_retry',
        lambda *_: pytest.fail('legal hold and account deletion blocks must not be retried'),
    )

    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'failed'
    assert len(attempts) == 1


def test_canonical_account_deletion_gate_is_not_retried(runtime, monkeypatch):
    runtime.rows[('account_deletions', UID)] = {'wipe_status': 'cancelled'}
    runtime.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': legal_holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': 'account_deletion',
        'token': 'synthetic-account-deletion-token',
        'state': 'running',
        'started_at': datetime.now(timezone.utc),
        'finished_at': None,
    }
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(None)
        raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')

    monkeypatch.setattr(dream_tools, 'apply_verified_edit', blocked)
    monkeypatch.setattr(
        dream_agent,
        '_sleep_gate_retry',
        lambda *_: pytest.fail('account deletion gate must not be retried'),
    )

    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))

    assert report['status'] == 'failed'
    assert report['error_type'] == 'DestructiveOperationInProgress'
    assert len(attempts) == 1


def test_live_kill_after_planning_cannot_apply_staged_work(runtime, monkeypatch):
    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(
        dream_agent.run_pass(
            UID, turn=scripted([True, True], on_plan=lambda: monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false'))
        )
    )
    assert not report['outcomes']
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_default_unverified_is_recorded_and_not_offered(runtime):
    async def model(uid, lane, mount, messages):
        if lane == MAIN_LANE:
            return _plan()
        raise RuntimeError('synthetic verifier failure')

    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert report['outcomes'][0]['status'] == 'verifier_unverified'
    assert _proposals(runtime) == []
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_non_default_unverified_is_offered_with_a_kind_title(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps({'dismiss_person': [{'strategy': 'cheap_model'}]}))
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        assert lane == MAIN_LANE
        return _plan()

    before = deepcopy(runtime.rows[('users', UID, 'people', 'junk')])
    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert report['outcomes'][0]['status'] == 'suggested'
    assert lanes == [MAIN_LANE]
    proposals = _proposals(runtime)
    assert len(proposals) == 1
    item = proposals[0]['item']
    assert item['title'] == 'Dismiss person'
    assert item['agent_proposal']['edit']['reason'] == 'Synthetic junk profile'
    assert runtime.rows[('users', UID, 'people', 'junk')] == before


def test_non_default_unverified_below_the_offer_threshold_stays_recorded(runtime, monkeypatch):
    monkeypatch.setenv('DREAM_VERIFIER_POLICY', json.dumps({'dismiss_person': [{'strategy': 'cheap_model'}]}))

    async def model(uid, lane, mount, messages):
        return _plan(value=2)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'verifier_unverified'
    assert _proposals(runtime) == []


def test_cheap_turn_uses_the_named_lane_and_disagree_is_not_offered(runtime, monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'dismiss_person': [{'strategy': 'cheap_model', 'lane': 'synthetic-cheap'}]}),
    )
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        if lane == MAIN_LANE:
            return _plan()
        assert lane == 'synthetic-cheap'
        return _verdict(messages, False)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['status'] == 'complete', str(report)
    assert lanes == [MAIN_LANE, 'synthetic-cheap']
    assert report['outcomes'][0]['status'] == 'verifier_disagree'
    assert _proposals(runtime) == []


def test_verify_lane_is_not_used_as_the_cheap_turn(runtime, monkeypatch):
    monkeypatch.setenv(
        'DREAM_VERIFIER_POLICY',
        json.dumps({'dismiss_person': [{'strategy': 'cheap_model', 'lane': VERIFY_LANE}]}),
    )
    lanes = []

    async def model(uid, lane, mount, messages):
        lanes.append(lane)
        assert lane == MAIN_LANE
        return _plan()

    report = asyncio.run(dream_agent.run_pass(UID, turn=model))
    assert report['outcomes'][0]['status'] == 'suggested'
    assert lanes == [MAIN_LANE]
    assert _proposals(runtime)[0]['item']['title'] == 'Dismiss person'


def test_price_weighted_cache_usage_allows_more_main_turns_than_raw_tokens(runtime, monkeypatch):
    limits = SessionLimits(bucket='light', turns=8, tools=8, read_bytes=64000, read_call_bytes=64000, tokens=10000)
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )
    main_calls = []

    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        main_calls.append(messages)
        if len(main_calls) <= 5:
            tool_call = call('read', {'refs': ['conversations/one']}, index=len(main_calls))
            return Turn(
                tokens=4000,
                prompt_tokens=4000,
                completion_tokens=0,
                cached_tokens=3500,
                tool_calls=(tool_call,),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
            )
        return turn([call('finish', {'summary': 'Checked cached records', 'notes': ''}, index=99)], tokens=4000)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert report['turns'] == 6
    assert report['tokens'] == 24000 and report['cached_tokens'] == 17500
    assert report['price_weighted_tokens'] == 8250 < limits.tokens
    assert report['accounted_tokens'] == report['tokens']


def test_unreported_cache_is_full_price_in_real_run_pass(runtime, monkeypatch):
    limits = SessionLimits(bucket='light', turns=3, tools=2, read_bytes=64000, read_call_bytes=64000, tokens=10000)
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )
    main_calls = 0

    async def model(uid, lane, mount, messages):
        nonlocal main_calls
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        main_calls += 1
        if main_calls == 1:
            tool_call = call('read', {'refs': ['conversations/one']})
            return Turn(
                tokens=4000,
                prompt_tokens=4000,
                completion_tokens=0,
                cached_tokens=None,
                tool_calls=(tool_call,),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
            )
        return Turn(tokens=4000, prompt_tokens=4000, completion_tokens=0, cached_tokens=None)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert main_calls == 2
    assert report['tokens'] == report['price_weighted_tokens'] == 8000
