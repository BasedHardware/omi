# LIFECYCLE: permanent
"""PL-583/584/585: provider delivery on old Firestore, replacement Postgres and sim.

Admission, settlement, ordered merge, privacy and transactions are production code.
Only vendor/audio IO and the outbox enqueue boundary are synthetic. This qualifies
the stage/Store interface, not the unresolved PL-581 carrier-to-unit binding or
background owner discovery. Require OMI_REQUIRE_STORE_BACKENDS=all for full proof.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from config.batch_pipeline import FRESH_CAPTURE_LAG_SECONDS
from config.policy import BatchUnitPolicy
from database import batch_pipeline_intake
from database.outbox import EnqueueResult
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import provider_stt_admission
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_stt import ProviderSttStage
from utils.batch_pipeline.projection_hold_policy import quarantines_assignment_conflict
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason
from database.batch_pipeline_privacy import BatchPrivacyBlocked

pytestmark = pytest.mark.integration
POLICY = BatchUnitPolicy(batch_enabled=True, batch_percent=100)
ROUTE = provider_stt_admission.SttRoute('provider', 'unsupported_language', 'modulate', 'ja')
MEMBERSHIP = 'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED'
RELEASE = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'
LAG = 'BATCH_PIPELINE_PROVIDER_FRESH_CAPTURE_LAG_SECONDS'
CAPTURE = 1_000_000.0
SETTLED = CAPTURE + 100_000.0


class EnqueueBoundary:
    """No task transport: admission must still supply its owning transaction."""

    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, tx=None, now):
        assert tx is not None
        assert payload == {'segment_id': dedupe_key}
        return EnqueueResult(dedupe_key, False, f'wake-{dedupe_key}')


class Artifacts:
    def fetch_audio(self, item):
        return b'synthetic-only'

    def persist_recovery_result(self, item, payload, token):
        return f'gs://synthetic/results/{item.segment_id}/{token}.enc'

    def find_recovery_result(self, item, token):
        return None


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    for name in (MEMBERSHIP, RELEASE, LAG):
        monkeypatch.delenv(name, raising=False)
    store_backend.seed_user('owner')
    return store_backend


def row(h, segment):
    return h.store.run(lambda tx: tx.get('jobs', segment))


def admit(h, segment, *, capture=CAPTURE, lag=60.0):
    uid = h.uid('owner')
    conversation = f'conv-{segment}'
    h.customer.add_conversation(uid, conversation)
    item = WorkItem(
        segment,
        uid,
        capture,
        f'gs://synthetic/audio/{segment}',
        5.0,
        Priority.FRESH,
        conversation_id=conversation,
        privacy_generation=0,
    )
    binding = ProjectionBinding(uid, conversation, f'content-{segment}', (segment,), language='ja')
    outcome = batch_pipeline_intake.admit(
        h.store,
        [item],
        binding,
        capture + 5.0 + lag,
        namespace=h.namespace,
        enqueue=provider_stt_admission.provider_enqueue(ROUTE, EnqueueBoundary(), {}),
        policy=POLICY,
    )
    assert outcome['outcome'] == 'batch'
    return row(h, segment)


def settle(h, segment, now=SETTLED):
    calls = []

    def vendor(item, language, inspected, *, service):
        calls.append(item.segment_id)
        return {
            'audio_seconds': 5.0,
            'speech_seconds': 2.5,
            'speech_spans': [{'start': 0.5, 'end': 3.0}],
            'words': [{'word': 'synthetic', 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': service,
            'language': language,
            'recovery_version': 1,
        }

    stage = ProviderSttStage(
        h.store,
        Artifacts(),
        stt=vendor,
        allowed=lambda *_: True,
        # Keep merge conformance on the paid path, above the short-speech threshold.
        inspect=lambda *_: (b'\0\0' * 80_000, 5.0, [{'start': 0.5, 'end': 3.0}]),
        clock=lambda: now,
    )
    result = stage.run(segment)
    assert (result.outcome, result.reason) == ('done', 'processed')
    assert calls == [segment]
    return row(h, segment)


@pytest.mark.parametrize(
    'lag,fresh,late', [(600.0, True, False), (7200.0, True, True), (86400.0, True, True), (86401.0, False, False)]
)
def test_pl583_admission_keeps_provider_freshness_distinct_from_conflict_lane(h, lag, fresh, late):
    original = admit(h, 'unit', lag=lag)
    assert original['fresh_capture'] is fresh
    assert original.get('late_upload', False) is late
    assert original['policy'] == POLICY.to_dict() and original['audio_uri'] == 'gs://synthetic/audio/unit'
    # Restart/idempotent admission never reclassifies accepted work under a new clock.
    assert admit(h, 'unit', lag=lag + 100_000.0) == original
    error = SyncAssignmentConflict('synthetic', subtype=SyncAssignmentConflictReason.RECORD_FINALIZE_PENDING)
    assert quarantines_assignment_conflict(error, original, now=CAPTURE + 2 * 86400.0) is (late or not fresh)


def test_pl583_rollback_changes_only_future_admissions(h, monkeypatch):
    original = admit(h, 'accepted', lag=7200.0)
    monkeypatch.setenv(LAG, '600')
    assert admit(h, 'after-rollback', capture=CAPTURE + 10.0, lag=7200.0)['fresh_capture'] is False
    assert row(h, 'accepted') == original
    assert FRESH_CAPTURE_LAG_SECONDS == 600.0


@pytest.mark.parametrize('depth', [0, 2])
@pytest.mark.parametrize('recovered', [False, True], ids=['ordinary', 'recovery-release'])
@pytest.mark.parametrize('rollback', [False, True], ids=['membership-on', 'membership-rollback'])
def test_pl585_fresh_provider_passes_held_backlog_without_releasing_it(h, monkeypatch, depth, recovered, rollback):
    monkeypatch.setenv(MEMBERSHIP, 'false')
    admit(h, 'backlog', capture=CAPTURE - 100.0, lag=90_000.0)
    settle(h, 'backlog')
    if recovered:
        h.store.run(lambda tx: tx.put('jobs', 'backlog', {**tx.get('jobs', 'backlog'), 'recovery_state': 'recovered'}))
    retained = row(h, 'backlog')
    monkeypatch.delenv(MEMBERSHIP)
    admit(h, 'fresh', lag=7200.0)
    settled = settle(h, 'fresh')
    assert settled['ready_at'] == SETTLED
    if rollback:
        monkeypatch.setenv(MEMBERSHIP, 'false')
    merge = OrderedMerge(h.store, head_wait_seconds=60, catch_up_depth=depth)
    entry = merge.commit_next(h.uid('owner'), SETTLED + 1)
    assert entry is not None, 'a ready fresh result must pass the held backlog'
    assert entry['segment_id'] == 'fresh' and entry['fresh_first'] is True
    assert entry['fresh_capture'] is True and entry['projection_state'] == 'pending'
    assert merge.commit_next(h.uid('owner'), SETTLED + 1000) is None
    assert merge.commit_next(h.uid('owner'), SETTLED + 1000, release=['backlog']) is None
    assert row(h, 'backlog') == retained
    assert merge.held_owners == set()
    assert not h.store.run(lambda tx: tx.get('merge_holds', owner_key(h.uid('owner')))).get('held')
    # Explicit release resumes the retained result, after the fresh log entry.
    monkeypatch.setenv('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', 'false')
    monkeypatch.setenv(RELEASE, 'true')
    released = OrderedMerge(h.store, head_wait_seconds=60, catch_up_depth=depth).commit_next(
        h.uid('owner'), SETTLED + 1001
    )
    assert released['segment_id'] == 'backlog' and released['late_capture'] is True
    assert released['previous_segment_id'] == 'fresh' and released['log_sequence'] == 2


def test_pl584_legacy_settle_clock_obeys_exact_head_wait_and_late_chain(h, monkeypatch):
    monkeypatch.setenv(MEMBERSHIP, 'false')
    admit(h, 'backlog', capture=CAPTURE - 100, lag=90_000)
    settle(h, 'backlog')
    monkeypatch.delenv(MEMBERSHIP)
    admit(h, 'waiting', capture=CAPTURE + 10)
    admit(h, 'ready', capture=CAPTURE + 20)
    monkeypatch.setenv(MEMBERSHIP, 'false')
    ready = settle(h, 'ready')
    assert 'ready_at' not in ready and ready['provider_intent']['settled_at'] == SETTLED
    monkeypatch.delenv(MEMBERSHIP)
    merge = OrderedMerge(h.store, head_wait_seconds=60, catch_up_depth=2)
    uid = h.uid('owner')
    assert merge.commit_next(uid, SETTLED + 59.999) is None
    entry = merge.commit_next(uid, SETTLED + 60)
    assert entry is not None, 'the durable settlement clock must release the ready result at the head-wait boundary'
    assert entry['segment_id'] == 'ready' and entry['fresh_first'] is True
    assert entry['head_wait_bypass'] is True and entry['log_sequence'] == 1
    assert row(h, 'waiting')['merge_pending'] is True
    assert row(h, 'backlog')['state'] == 'result_ready'
    settle(h, 'waiting', now=SETTLED + 100)
    late = OrderedMerge(h.store, head_wait_seconds=60, catch_up_depth=2).commit_next(uid, SETTLED + 101)
    assert late['segment_id'] == 'waiting' and late['late_capture'] is True
    assert late['previous_segment_id'] == 'ready' and late['log_sequence'] == 2
    assert OrderedMerge(h.store).commit_next(uid, SETTLED + 102) is None


def race_before_fresh_commit(h, monkeypatch, action, *, transactional):
    """Interleave at the boundary the selected merge mode actually uses."""
    raced = []

    def change_once():
        if not raced:
            raced.append(True)
            action()

    if transactional:
        run = h.store.run

        def after_strict_transaction(body):
            result = run(body)
            change_once()
            return result

        monkeypatch.setattr(h.store, 'run', after_strict_transaction)
    else:
        probe = h.store.fresh_pending

        def after_probe(*args):
            rows = probe(*args)
            change_once()
            return rows

        monkeypatch.setattr(h.store, 'fresh_pending', after_probe)
    return raced


@pytest.mark.parametrize('transactional', [False, True], ids=['probe', 'transactional'])
def test_pl585_privacy_revoke_before_fresh_commit_preserves_custody(h, monkeypatch, transactional):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', str(transactional).lower())
    admit(h, 'backlog', capture=CAPTURE - 100, lag=90_000)
    settle(h, 'backlog')
    admit(h, 'fresh')
    settle(h, 'fresh')
    original = row(h, 'fresh')
    raced = race_before_fresh_commit(
        h, monkeypatch, lambda: h.customer.block_privacy(h.uid('owner')), transactional=transactional
    )
    assert OrderedMerge(h.store).commit_next(h.uid('owner'), SETTLED + 100) is None
    assert raced == [True], 'the selected merge mode must execute the privacy race'
    assert row(h, 'fresh') == original
    assert not h.store.run(lambda tx: tx.get('results', 'fresh'))


@pytest.mark.parametrize('transactional', [False, True], ids=['probe', 'transactional'])
def test_pl584_a_predecessor_settled_before_fresh_commit_cannot_be_skipped(h, monkeypatch, transactional):
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', str(transactional).lower())
    admit(h, 'backlog', capture=CAPTURE - 100, lag=90_000)
    settle(h, 'backlog')
    admit(h, 'earlier', capture=CAPTURE + 10)
    admit(h, 'later', capture=CAPTURE + 20)
    settle(h, 'later')
    raced = race_before_fresh_commit(
        h, monkeypatch, lambda: settle(h, 'earlier', now=SETTLED + 30), transactional=transactional
    )
    uid = h.uid('owner')
    first = OrderedMerge(h.store, head_wait_seconds=60).commit_next(uid, SETTLED + 60)
    assert raced == [True], 'the selected merge mode must execute the predecessor race'
    if transactional:
        # Selection and commit share a snapshot, which now includes the predecessor.
        assert first is not None and first['segment_id'] == 'earlier'
    else:
        # The stale outside probe cannot pass a predecessor that became ready.
        assert first is None
    assert not h.store.run(lambda tx: tx.get('results', 'later'))
    merge = OrderedMerge(h.store, head_wait_seconds=60)
    first = first or merge.commit_next(uid, SETTLED + 61)
    second = merge.commit_next(uid, SETTLED + 61)
    assert [first['segment_id'], second['segment_id']] == ['earlier', 'later']
    assert second['previous_segment_id'] == 'earlier' and second['log_sequence'] == 2


def test_meter_spends_one_token_with_the_result_and_preserves_fresh_chain(h, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', 'true')
    for n in range(2):
        admit(h, f'old-{n}', capture=CAPTURE + n, lag=90_000)
        settle(h, f'old-{n}')
    heartbeat = SETTLED + 100
    control = dict(
        state='open',
        rate_per_hour=1,
        reach_seconds=0,
        window=int(heartbeat // 3600),
        tokens_used=0,
        updated_at=heartbeat,
    )
    h.store.run(lambda tx: tx.put('backlog_release', 'gate', control))
    merge = OrderedMerge(h.store, catch_up_depth=0)
    first = merge.commit_next(h.uid('owner'), heartbeat)
    assert first['segment_id'] == 'old-0' and first['backlog_release'] is True
    spent = h.store.run(lambda tx: tx.get('backlog_release', 'gate'))
    assert spent == {**control, 'tokens_used': 1}
    assert merge.commit_next(h.uid('owner'), heartbeat) is None
    admit(h, 'fresh', capture=CAPTURE + 10)
    settle(h, 'fresh')
    fresh = merge.commit_next(h.uid('owner'), heartbeat)
    assert fresh['segment_id'] == 'fresh' and 'backlog_release' not in fresh
    assert fresh['previous_segment_id'] == 'old-0'
    assert h.store.run(lambda tx: tx.get('backlog_release', 'gate')) == spent
    assert row(h, 'old-1')['state'] == 'result_ready'


def test_meter_privacy_refusal_spends_no_token_or_result(h, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', 'true')
    admit(h, 'old', lag=90_000)
    settle(h, 'old')
    heartbeat = SETTLED + 100
    control = dict(
        state='open',
        rate_per_hour=1,
        reach_seconds=0,
        window=int(heartbeat // 3600),
        tokens_used=0,
        updated_at=heartbeat,
    )
    h.store.run(lambda tx: tx.put('backlog_release', 'gate', control))
    h.customer.block_privacy(h.uid('owner'))
    # Privacy may fence the strict transaction before it reaches the metered lane.
    try:
        assert OrderedMerge(h.store, catch_up_depth=0).commit_next(h.uid('owner'), heartbeat) is None
    except BatchPrivacyBlocked:
        pass
    assert h.store.run(lambda tx: tx.get('backlog_release', 'gate')) == control
    assert not h.store.run(lambda tx: tx.get('results', 'old'))
    assert row(h, 'old')['state'] == 'result_ready'
