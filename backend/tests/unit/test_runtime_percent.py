"""Contract (f): `_ramp` runtime percents, LKG fail-safe, CAS writes and behaviour-neutral wiring."""

import asyncio
import math
from pathlib import Path

import pytest

from config import batch_live_preview, summary_guarantee
from config import rollout_cohorts as policy
from database import rollout_cohorts as store
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.rollout import runtime_percent as rp


def ramp_doc(revision=3, env='prod', **entry):
    base = {'percents': {'batch-pipeline': 10.0, 'first-summary': 10.0}, 'legacy_sync': 'on', 'locked_by': None}
    base.update(entry)
    return {'schema_version': 1, 'revision': revision, 'envs': {env: base}}


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rp.time, 'monotonic', lambda: now[0])
    return now


@pytest.fixture
def reader(monkeypatch, clock):
    """A synchronous cache over a scripted reader; each call pops the next outcome (dict/None/Exception)."""
    outcomes = []
    calls = []

    def read():
        calls.append(1)
        value = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(value, Exception):
            raise value
        return None if value is None else store.normalize_ramp_document(value)

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setattr(rp, '_background_submitter', lambda fn: fn())
    monkeypatch.setattr(rp, '_cache', rp._RampCache(read))
    return outcomes, calls


def test_valid_uid_rejects_reserved_ramp_ids():
    assert not policy.valid_uid('_ramp')
    assert not policy.valid_uid('_ramp_staging')
    assert policy.valid_uid('ramp_user')
    assert policy.valid_uid('synthetic-owner')


def test_unbound_seam_returns_env_values(monkeypatch):
    monkeypatch.setattr(policy, '_percent_resolver', None)
    monkeypatch.setattr(policy, '_legacy_sync_resolver', None)
    assert policy.runtime_percent('batch-pipeline', env_default=7.0) == 7.0
    assert policy.legacy_sync_mode() == 'on'


def test_no_document_is_behaviour_neutral(reader):
    outcomes, calls = reader
    outcomes.append(None)
    assert rp.runtime_percent('batch-pipeline', env_default=5.0) == 5.0
    assert rp.legacy_sync_mode() == 'on'
    assert rp.ramp_snapshot().source == 'env_default'
    assert len(calls) == 1


def test_document_values_cached_for_thirty_seconds(reader, clock):
    outcomes, calls = reader
    outcomes.append(ramp_doc())
    for _ in range(100):
        assert rp.runtime_percent('batch-pipeline', env_default=5.0) == 10.0
    assert len(calls) == 1
    clock[0] += 29.9
    rp.runtime_percent('batch-pipeline', env_default=5.0)
    assert len(calls) == 1
    clock[0] += 0.2
    rp.runtime_percent('batch-pipeline', env_default=5.0)
    assert len(calls) == 2
    assert rp.ramp_snapshot().source == 'firestore'


def test_missing_name_uses_env_default(reader):
    outcomes, _ = reader
    outcomes.append(ramp_doc(percents={'batch-pipeline': 25.0}))
    assert rp.runtime_percent('first-summary', env_default=5.0) == 5.0
    assert rp.runtime_percent('unknown-name', env_default=3.0) == 3.0


def test_error_serves_last_known_good_indefinitely(reader, clock):
    outcomes, calls = reader
    outcomes.extend([ramp_doc(), RuntimeError('private path rollout_cohorts/_ramp')])
    assert rp.runtime_percent('batch-pipeline', env_default=0.0) == 10.0
    for _ in range(20):
        clock[0] += 31
        assert rp.runtime_percent('batch-pipeline', env_default=50.0) == 10.0
    snap = rp.ramp_snapshot()
    assert snap.source == 'lkg'
    assert snap.error_seconds >= 300
    assert rp.RUNTIME_PERCENT_SOURCE.labels(source='lkg')._value.get() == 1


def test_malformed_document_is_an_error_not_a_value(reader, clock):
    outcomes, _ = reader
    outcomes.extend([ramp_doc(), ramp_doc(percents={'batch-pipeline': 150.0})])
    assert rp.runtime_percent('batch-pipeline', env_default=0.0) == 10.0
    clock[0] += 31
    assert rp.runtime_percent('batch-pipeline', env_default=0.0) == 10.0
    assert rp.ramp_snapshot().source == 'lkg'


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1.0, 100.01, True, '5'])
def test_out_of_range_or_non_numeric_rejected(bad):
    with pytest.raises(store.RampDocumentError):
        store.normalize_ramp_document(ramp_doc(percents={'batch-pipeline': bad}))


def test_cold_start_error_returns_env_default(reader, caplog):
    outcomes, _ = reader
    outcomes.append(RuntimeError('rollout_cohorts/_ramp secret'))
    assert rp.runtime_percent('batch-pipeline', env_default=5.0) == 5.0
    assert rp.legacy_sync_mode() == 'on'
    assert rp.ramp_snapshot().source == 'env_default'
    assert 'secret' not in caplog.text


def test_nesting_clamped_at_read_time(reader):
    outcomes, _ = reader
    doc = ramp_doc(percents={'batch-pipeline': 10.0, 'batch-live-stt-retire': 25.0})
    outcomes.append(doc)
    assert rp.runtime_percent('batch-live-stt-retire', env_default=0.0) == 10.0


def test_legacy_sync_mode_and_staging_identity(reader, monkeypatch):
    outcomes, _ = reader
    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    outcomes.append(ramp_doc(env='staging', legacy_sync='draining'))
    assert rp.legacy_sync_mode() == 'draining'
    assert rp.ramp_snapshot().env == 'staging'


def test_unknown_deployment_identity_fails_safe(reader, monkeypatch):
    outcomes, _ = reader
    monkeypatch.setenv('OMI_DEPLOYMENT', 'canary')
    outcomes.append(ramp_doc())
    assert rp.runtime_percent('batch-pipeline', env_default=5.0) == 5.0


def test_event_loop_cold_path_never_blocks(monkeypatch, clock):
    submitted = []
    monkeypatch.setattr(rp, '_background_submitter', submitted.append)
    monkeypatch.setattr(rp, '_cache', rp._RampCache(lambda: store.normalize_ramp_document(ramp_doc())))
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')

    async def call():
        return rp.runtime_percent('batch-pipeline', env_default=5.0)

    assert asyncio.run(call()) == 5.0  # read scheduled, not awaited
    assert len(submitted) == 1
    submitted[0]()
    assert rp.runtime_percent('batch-pipeline', env_default=5.0) == 10.0


def test_bound_config_modules_read_runtime_percent(monkeypatch):
    monkeypatch.setattr(policy, '_percent_resolver', lambda name, default: {'first-summary': 100.0}.get(name, default))
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    assert summary_guarantee.enabled('synthetic-owner')
    monkeypatch.setattr(policy, '_percent_resolver', lambda name, default: default)
    assert not summary_guarantee.enabled('synthetic-owner')
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '7')
    assert batch_live_preview.rollout_percent() == 7.0
    monkeypatch.setattr(policy, '_percent_resolver', lambda name, default: math.nan)
    assert batch_live_preview.rollout_percent() == 0


def test_write_is_cas_with_history_row():
    db = StrictFirestore()
    revision = rp.write_ramp(
        'prod',
        {'percents': {'batch-pipeline': 5.0, 'first-summary': 5.0}},
        expected_revision=0,
        actor='lead',
        reason='seed',
        firestore_client=db,
    )
    assert revision == 1
    doc = store.normalize_ramp_document(db.rows[('rollout_cohorts', '_ramp')])
    assert doc['envs']['prod']['percents'] == {'batch-pipeline': 5.0, 'first-summary': 5.0}
    assert doc['envs']['prod']['updated_by'] == 'lead'
    history = db.rows[('rollout_cohorts', '_ramp', 'history', '0000000001')]
    assert history['before']['percents'] == {} and history['after']['percents']['batch-pipeline'] == 5.0
    assert history['actor'] == 'lead' and history['env'] == 'prod'
    with pytest.raises(store.RampRevisionConflict):
        rp.write_ramp(
            'prod', {'legacy_sync': 'draining'}, expected_revision=0, actor='lead', reason='x', firestore_client=db
        )


@pytest.mark.parametrize(
    'change',
    [
        {'percents': {'batch-live-stt-retire': 10.0}},  # nesting: retire > batch-pipeline
        {'percents': {'batch-pipeline': 101.0}},
        {'percents': {'other': 1.0}},
        {'legacy_sync': 'off'},
        {'allowlist': ['x']},
    ],
)
def test_writer_refuses_invalid_changes(change):
    db = StrictFirestore()
    rp.write_ramp(
        'prod',
        {'percents': {'batch-pipeline': 5.0}},
        expected_revision=0,
        actor='lead',
        reason='seed',
        firestore_client=db,
    )
    with pytest.raises(store.RampDocumentError):
        rp.write_ramp('prod', change, expected_revision=1, actor='lead', reason='bad', firestore_client=db)
    assert ('rollout_cohorts', '_ramp', 'history', '0000000002') not in db.rows


def test_composition_root_binds_runtime_percent():
    text = (Path(__file__).parents[2] / 'utils/rollout_cohorts.py').read_text()
    assert 'configure_runtime_percent()' in text
