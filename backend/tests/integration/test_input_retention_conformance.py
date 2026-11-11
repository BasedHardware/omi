"""PL-528/529/530: retained-input expiry on old Firestore, Postgres and sim.

This exercises the real recovery transactions with synthetic custody receipts.
It does not read a bucket, run an operator, or prove the maintenance scan SLA.
Require OMI_REQUIRE_STORE_BACKENDS=all for complete local qualification.
"""

from copy import deepcopy

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.input_retention import STAGING_BUCKET, TERMINAL_SECONDS
from utils.batch_pipeline.scheduler import owner_key

pytestmark = pytest.mark.integration

T0 = 1_800_000_000.0
DUE = T0 + TERMINAL_SECONDS
SID = 'retained'
AUDIO = f'gs://{STAGING_BUCKET}/synthetic/retained#7'


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', 'true')


def read(h, table='jobs', key=SID):
    return h.store.run(lambda tx: tx.get(table, key))


def patch(h, fields, table='jobs', key=SID):
    def update(tx):
        row = tx.get(table, key)
        tx.put(table, key, {**row, **fields})

    h.store.run(update)


def seed(h, leg):
    owner = h.seed_user('retention')
    binding = ProjectionBinding(owner, 'bp_upload', 'synthetic-content', (SID,))
    item = WorkItem(SID, owner, T0, AUDIO, 20.0, Priority.FRESH, privacy_generation=0)
    assert (
        admit(
            h.store,
            [item],
            binding,
            T0,
            namespace=h.namespace,
            intake={'owner_id': owner, 'content_id': binding.content_id, 'segment_ids': [SID], 'total_files': 1},
            policy=BatchUnitPolicy(batch_enabled=True, batch_percent=100),
        )['outcome']
        == 'batch'
    )
    fields = {
        'state': 'quarantined',
        'quarantine_reason': 'worker_failed',
        'recovery_state': 'held',
        'merge_pending': False,
        'token': '',
        'lease_until': 0,
        'held_deadline_at': DUE + 10 * 86400,
        'attempt': 3,
        'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'},
    }
    if leg == 'assignment':
        fields.update(state='committed', result={'result_uri': 'gs://synthetic/result#3'})
        patch(
            h,
            {
                'segment_id': SID,
                'owner_key': owner_key(owner),
                'projection_state': 'quarantine_held',
                'projection': {'state': 'quarantined', 'disposition': 'ambiguous_generation'},
            },
            'results',
        )
    patch(h, fields)
    return owner, f'{owner}/{binding.content_id}'


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_pl528_day29_is_a_retained_reasoned_terminal_not_a_custody_release(store_backend, leg):
    h = store_backend
    _, ledger_key = seed(h, leg)
    before = read(h)
    result = read(h, 'results')
    ledger = read(h, 'content', ledger_key)
    recovery = RecoveryStore(h.store)
    assert recovery.expire_held(SID, DUE - 1) == 'held'
    assert read(h) == before
    assert recovery.expire_held(SID, DUE) == 'expired'
    assert read(h) == {
        **before,
        'state': 'dead',
        'merge_pending': leg == 'gpu',
        'dead_letter_reason': 'input_expiring',
        'input_expiring_at': DUE,
        'input_expiring_leg': leg,
    }
    assert read(h, 'results') == result
    expected_ledger = {**ledger, 'artifact_missing_units': [SID]} if leg == 'gpu' else ledger
    assert read(h, 'content', ledger_key) == expected_ledger
    assert 'expires_at' not in read(h)
    terminal = deepcopy(read(h))
    assert recovery.expire_held(SID, DUE + 1) == 'held'
    # A nightly held-expired requeue cannot turn input_expiring into a paid retry.
    assert not recovery.requeue_quarantined(SID, DUE + 86400, dead_before=DUE + 1)
    assert read(h) == terminal
    assert read(h, 'results') == result
    assert read(h, 'content', ledger_key) == expected_ledger


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
@pytest.mark.parametrize('staged', [None, False, 0, -1, '123', {}])
def test_pl529_malformed_staged_clock_falls_back_without_hiding_due_input(store_backend, leg, staged):
    h = store_backend
    seed(h, leg)
    patch(h, {'audio_staged_at': staged})
    assert RecoveryStore(h.store).expire_held(SID, DUE - 1) == 'held'
    assert RecoveryStore(h.store).expire_held(SID, DUE) == 'expired'
    assert read(h)['dead_letter_reason'] == 'input_expiring'
    assert read(h)['audio_uri'] == AUDIO
    assert read(h)['attempt'] == 3


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_pl529_reuploaded_input_uses_its_current_staging_clock(store_backend, leg):
    h = store_backend
    seed(h, leg)
    replacement = f'gs://{STAGING_BUCKET}/synthetic/reuploaded#8'
    patch(h, {'audio_staged_at': T0 + 86400, 'audio_uri': replacement})
    before = read(h)
    assert RecoveryStore(h.store).expire_held(SID, DUE) == 'held'
    assert read(h) == before
    assert RecoveryStore(h.store).expire_held(SID, DUE + 86400) == 'expired'
    assert read(h)['audio_uri'] == replacement
    assert read(h)['enqueued_at'] == before['enqueued_at']


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
@pytest.mark.parametrize('fence', ['privacy', 'ledger'])
def test_pl530_terminalization_rechecks_current_privacy_and_content_owner(store_backend, leg, fence):
    h = store_backend
    owner, ledger_key = seed(h, leg)
    error = ProjectionBlocked
    if fence == 'privacy':
        h.customer.block_privacy(owner)
        error = BatchPrivacyBlocked
    else:
        patch(h, {'job_id': 'foreign-owner-job'}, 'content', ledger_key)
    before = read(h)
    ledger = read(h, 'content', ledger_key)
    result = read(h, 'results')
    with pytest.raises(error):
        RecoveryStore(h.store).expire_held(SID, DUE)
    assert read(h) == before
    assert read(h, 'content', ledger_key) == ledger
    assert read(h, 'results') == result


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
@pytest.mark.parametrize('fence', ['kill', 'lease', 'intent'])
def test_pl530_age_cannot_override_kill_live_lease_or_operator_intent(store_backend, monkeypatch, leg, fence):
    h = store_backend
    seed(h, leg)
    if fence == 'kill':
        monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', 'false')
    elif fence == 'lease':
        patch(h, {'token': 'current-worker', 'lease_until': DUE + 120})
    else:
        patch(h, {'speech_redrive': {'state': 'prepared'}})
    before = read(h)
    result = read(h, 'results')
    assert RecoveryStore(h.store).expire_held(SID, DUE) == 'held'
    assert read(h) == before
    assert read(h, 'results') == result
