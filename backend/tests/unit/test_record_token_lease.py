"""Producer custody lease: modes, stock seed, exact clocks and transactional renewal."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import Mock

from prometheus_client import Counter
import pytest

from config import record_seal_rules as lease, refactor_modes
from config.policy.batch import cohort_bucket
from database import record_audio, record_custody_append
from utils.observability import firestore_probe_export
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead

NOW = 2_000_000_000.0
PATH = ('users', 'synthetic', 'conversations', 'record')
POD = {'pod': 'live', 'process_started_at': NOW - 86400}
TOKEN = {**POD, 'last_signal_at': NOW - 7200, 'lease_expires_at': NOW - 3600, 'signal_source': 'frames'}
ROW = {
    'status': 'completed',
    'finished_at': datetime.fromtimestamp(NOW - 86400, timezone.utc),
    'record_lane_owner': 'batch_live_v1',
    'private_cloud_sync_enabled': True,
    'record_upload_revision': 7,
    'record_upload_sessions': {'s': TOKEN},
}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setattr(record_audio.time, 'time', lambda: NOW)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(record_custody_append.time, 'time', lambda: NOW)
    return StrictFirestore({PATH: ROW, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})


@pytest.mark.parametrize(
    'raw,expected',
    [
        (None, 3600.0),
        ('0', 3600.0),
        ('1800', 1800.0),
        ('7200', 7200.0),
        ('bad', 3600.0),
        ('-5', 3600.0),
        ('nan', 3600.0),
        ('inf', 3600.0),
        ('7201', 3600.0),
    ],
)
def test_lease_setting_is_bounded(monkeypatch, raw, expected):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_SECONDS', raising=False)
    if raw is not None:
        monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', raw)
    assert lease.token_lease_seconds() == expected


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve', '', 'invalid'])
@pytest.mark.parametrize('percent', [0, 1, 10, 50, 100])
def test_mode_cohort_and_kill_switch(monkeypatch, mode, percent):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', str(percent))
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE_SERVE_UID_SHA256S', raising=False)
    assert lease.token_lease_serving('synthetic') is (
        mode == 'serve' and cohort_bucket('synthetic', 'record-token-lease') < percent
    )


def test_digest_cohort_never_bypasses_off_or_shadow(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_UID_SHA256S', refactor_modes.uid_digest('synthetic'))
    for mode in ('serve', 'shadow', 'off'):
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
        assert lease.token_lease_serving('synthetic') is (mode == 'serve')


def test_default_and_malformed_mode_are_dark(monkeypatch):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    assert lease.token_lease_mode() == 'off'
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'bad')
    assert lease.token_lease_mode() == 'off'


@pytest.mark.parametrize('mode', ['off', None])
def test_off_is_bit_exact_old_write_payload_and_performs_no_renewal_io(monkeypatch, mode):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    if mode:
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    client = StrictFirestore({PATH: {**ROW, 'record_upload_sessions': {}}})
    assert record_audio.set_record_upload_pending(
        'synthetic', 'record', 's', True, producer=POD, firestore_client=client
    )
    assert client.transactions[-1].updates == [
        (
            PATH,
            {
                'record_upload_sessions': {'s': POD},
                'record_audio_closed': False,
                'record_upload_revision': 8,
            },
        )
    ]
    before = json.dumps(client.rows[PATH], sort_keys=True, default=str)
    no_client = Mock(side_effect=AssertionError('off must not construct a client'))
    monkeypatch.setattr(record_audio, 'get_firestore_client', no_client)
    assert not record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append')
    assert json.dumps(client.rows[PATH], sort_keys=True, default=str) == before
    # Inert expired fields never change the original live-pod decision.
    assert not producer_tokens_dead({'s': TOKEN}, None, uid='synthetic', row=ROW)
    assert producer_tokens_dead({'s': {**TOKEN, 'abandoned_at': NOW - 50}}, None, uid='synthetic', row=ROW)
    assert record_audio.set_record_upload_pending('synthetic', 'record', 's', False, firestore_client=client)
    assert client.transactions[-1].updates == [(PATH, {'record_upload_sessions': {}})]
    assert record_audio.seal_record_audio('synthetic', 'record', firestore_client=client) is None
    assert client.transactions[-1].updates == [(PATH, {'record_audio_closed': True})]


@pytest.mark.parametrize('source', ['frames', 'custody_append'])
def test_late_signal_reactivates_token_and_invalidates_partial_revision(enabled, source):
    producer = {**POD, 'pod': ''} if source == 'custody_append' else POD
    enabled.rows[PATH]['record_upload_sessions']['s'].update(producer, signal_source=source)
    before = deepcopy(enabled.rows[PATH])
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source=source, session='s', firestore_client=enabled
    )
    row = enabled.rows[PATH]
    assert row['record_upload_revision'] == before['record_upload_revision'] + (source == 'frames')
    assert row['record_upload_sessions']['s'] == {
        **producer,
        'last_signal_at': NOW,
        'lease_expires_at': NOW + lease.producer_token_lease_seconds({**producer, 'signal_source': source}),
        'signal_source': source,
    }
    assert not producer_tokens_dead(row['record_upload_sessions'], None, uid='synthetic', row=row)
    assert bool(
        record_audio.renew_record_token_lease(
            'synthetic', 'record', source=source, session='s', firestore_client=enabled
        )
    ) is (source == 'frames')
    assert row['record_upload_revision'] == (8 if source == 'frames' else 7)


def test_custody_renews_only_custody_tokens_and_frames_are_exact(enabled):
    enabled.rows[PATH]['record_upload_sessions']['other'] = {**TOKEN, 'pod': '', 'signal_source': 'custody_append'}
    enabled.rows[PATH]['record_upload_sessions']['legacy'] = True
    record_audio.renew_record_token_lease('synthetic', 'record', source='frames', session='s', firestore_client=enabled)
    assert enabled.rows[PATH]['record_upload_sessions']['other']['last_signal_at'] == TOKEN['last_signal_at']
    record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='other', firestore_client=enabled
    )
    assert enabled.rows[PATH]['record_upload_sessions']['other']['last_signal_at'] == NOW
    assert enabled.rows[PATH]['record_upload_sessions']['legacy'] is True
    assert enabled.rows[PATH]['record_upload_sessions']['s']['signal_source'] == 'frames'


def test_custody_upload_survives_abandon_or_pod_death(enabled):
    enabled.rows[PATH]['record_upload_sessions']['s'].update(pod='', signal_source='custody_append')
    enabled.rows[PATH]['record_upload_sessions']['s']['abandoned_at'] = NOW - 4000
    record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='s', firestore_client=enabled
    )
    tokens = enabled.rows[PATH]['record_upload_sessions']
    assert 'abandoned_at' not in tokens['s']
    proof = {'namespace': 'prod-omi-backend', 'captured_at': NOW, 'pods': {}}
    assert not producer_tokens_dead(tokens, proof, uid='synthetic', row=enabled.rows[PATH])


@pytest.mark.parametrize('change', [{'deleted': True}, {'record_lane_owner': 'legacy_final_pass_v1'}])
def test_never_recreates_or_mutates_ineligible_rows(enabled, change):
    enabled.rows[PATH].update(change)
    before = deepcopy(enabled.rows)
    assert not record_audio.renew_record_token_lease('synthetic', 'record', source='frames', firestore_client=enabled)
    assert enabled.rows == before
    enabled.rows.clear()
    assert not record_audio.renew_record_token_lease('synthetic', 'record', source='frames', firestore_client=enabled)
    assert not enabled.rows


def test_manifest_heartbeat_never_counts_a_late_append_or_deletes_audio(enabled):
    enabled.rows[PATH].update(record_audio_closed=True, record_upload_sessions={}, raw_audio='retained')
    before = deepcopy(enabled.rows)
    counter = record_audio.lease_metrics.LATE_APPEND._value.get()
    record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append', firestore_client=enabled)
    assert enabled.rows == before
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == counter


@pytest.mark.parametrize(
    'age,tokens,status,expired',
    [
        (3599, {'s': POD}, 'completed', False),
        (3600, {'s': POD}, 'completed', False),
        (3601, {'s': POD, 't': POD}, 'completed', True),
        (86400, {'s': True}, 'completed', False),
        (86400, {'s': POD, 't': True}, 'completed', False),
        (86400, {'s': {'pod': ''}}, 'completed', False),
        (86400, {'s': POD}, 'in_progress', False),
        (86400, {}, 'completed', True),
    ],
)
def test_stock_seed_replaces_24832_age_grace(enabled, monkeypatch, age, tokens, status, expired):
    # Salvaged #24832 identity/status/boundary cases now require a deployment
    # clamp and three quiet clocks, rather than merely an old finished_at.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - age))
    row = {**ROW, 'status': status}
    assert producer_tokens_dead(tokens, None, uid='synthetic', row=row) is expired


def test_stock_seed_is_bounded_by_serve_enable_and_never_uses_process_start(enabled, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - 100))
    assert not producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW)
    enabled_at = NOW - 7200
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(enabled_at))
    for row, job, token in [
        (ROW, {}, POD),
        ({**ROW, 'finished_at': NOW - 10}, {}, POD),
        ({**ROW, 'record_seal_refused_at': NOW - 10}, {}, POD),
        (ROW, {'available_at': NOW - 10}, POD),
        (ROW, {}, {**POD, 'abandoned_at': NOW - 10}),
    ]:
        assert lease.token_lease_clocks(token, row=row, job=job) == (enabled_at, enabled_at + 3600)
        assert producer_tokens_dead({'s': token}, None, uid='synthetic', row=row, job=job)
    monkeypatch.delenv('RECORD_TOKEN_LEASE_DEPLOYED_AT')
    assert not producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW)


def test_moving_retry_wake_cannot_extend_legacy_lease(enabled, monkeypatch):
    enabled_at = NOW - 3601
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(enabled_at))
    for wake in (enabled_at, NOW - 60, NOW, NOW + 86400):
        job = {'available_at': wake, 'updated_at': wake}
        assert lease.token_lease_clocks(POD, row=ROW, job=job)[1] == enabled_at + 3600
        assert producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW, job=job)


@pytest.mark.parametrize('authority', ['pod', 'abandon'])
def test_server_signal_newer_than_stoppage_proof_keeps_token_alive(enabled, authority):
    # The pod list predates an observed append; uploader custody outlives pusher.
    proof = {'namespace': 'prod-omi-backend', 'captured_at': NOW - 120, 'pods': {}}
    token = {**TOKEN, 'last_signal_at': NOW - 60, 'lease_expires_at': NOW + 3540}
    if authority == 'abandon':
        # Also exercise an expired signal: an older abandonment cannot regain
        # authority merely because a newer server signal has aged out.
        token = {**TOKEN, 'abandoned_at': TOKEN['last_signal_at'] - 60}
        proof = None
    assert not producer_tokens_dead({'s': token}, proof, uid='synthetic', row=ROW)


@pytest.mark.parametrize('proof_offset', [-60, 0, 60])
def test_only_strictly_newer_signal_supersedes_abandon_proof(enabled, proof_offset):
    token = {**TOKEN, 'abandoned_at': TOKEN['last_signal_at'] + proof_offset}
    assert producer_tokens_dead({'s': token}, None, uid='synthetic', row=ROW) is (proof_offset >= 0)


def test_partial_custody_fences_before_and_bumps_only_after_durable_acceptance(enabled):
    enabled.rows[PATH].update(record_upload_sessions={}, record_audio_partial={'upload_revision': 7})
    assert record_custody_append.begin('synthetic', 'record', 'custody:upload', firestore_client=enabled)
    row = enabled.rows[PATH]
    assert row['record_upload_revision'] == 7
    assert row['record_upload_sessions']['custody:upload']['signal_source'] == 'custody_append'
    assert not producer_tokens_dead(row['record_upload_sessions'], None, uid='synthetic', row=row)
    assert record_custody_append.finish(
        'synthetic', 'record', 'custody:upload', accepted=True, firestore_client=enabled
    )
    row = enabled.rows[PATH]
    assert row['record_upload_revision'] == row['record_audio_partial']['upload_revision'] == 8
    assert not row['record_upload_sessions']
    assert not row['record_audio_closed']


def test_generic_mode_reader_uses_dark_default(monkeypatch):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    assert refactor_modes.mode('RECORD_TOKEN_LEASE_MODE') == 'off'
    assert not refactor_modes.serving_for('RECORD_TOKEN_LEASE_MODE', 'synthetic')


def test_stock_seed_preserves_original_pod_and_abandon_authorities(enabled, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - 10))
    proof = {'namespace': 'prod-omi-backend', 'captured_at': NOW, 'pods': {}}
    assert producer_tokens_dead({'s': POD}, proof, uid='synthetic', row=ROW)
    assert producer_tokens_dead({'s': {**POD, 'abandoned_at': NOW - 10}}, None, uid='synthetic', row=ROW)


def test_manifest_cannot_resurrect_a_legacy_frame_token(enabled, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - 7200))
    enabled.rows[PATH]['record_upload_sessions'] = {'s': POD}
    assert producer_tokens_dead({'s': POD}, None, uid='synthetic', row=enabled.rows[PATH])
    assert not record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', firestore_client=enabled
    )
    assert enabled.rows[PATH]['record_upload_revision'] == 7  # heartbeat is not a stored append
    assert producer_tokens_dead(
        enabled.rows[PATH]['record_upload_sessions'], None, uid='synthetic', row=enabled.rows[PATH]
    )

    assert record_custody_append.begin('synthetic', 'record', 'custody:real-upload', firestore_client=enabled)
    assert not producer_tokens_dead(
        enabled.rows[PATH]['record_upload_sessions'], None, uid='synthetic', row=enabled.rows[PATH]
    )


def test_unclaimed_owner_keeps_its_token_live_until_batch_owner_resolution(enabled):
    enabled.rows[PATH]['record_lane_owner'] = None
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='frames', session='s', firestore_client=enabled
    )
    assert enabled.rows[PATH]['record_upload_sessions']['s']['last_signal_at'] == NOW
    enabled.rows[PATH]['record_lane_owner'] = 'batch_live_v1'
    assert not producer_tokens_dead(enabled.rows[PATH]['record_upload_sessions'], None, uid='synthetic')


def test_partial_and_complete_seals_restore_exact_frame_token_in_serve(enabled):
    enabled.rows[PATH].update(record_upload_sessions={}, record_audio_partial={'upload_revision': 7})
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='frames', session='s', producer=POD, firestore_client=enabled
    )
    assert enabled.rows[PATH]['record_upload_revision'] == 8
    assert enabled.rows[PATH]['record_upload_sessions']['s']['pod'] == POD['pod']
    enabled.rows[PATH].update(record_audio_closed=True, record_audio_partial=None, record_upload_sessions={})
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='frames', session='s', producer=POD, firestore_client=enabled
    )
    assert not enabled.rows[PATH]['record_audio_closed']
    assert set(enabled.rows[PATH]['record_upload_sessions']) == {'s'}
    assert enabled.rows[PATH]['record_upload_revision'] == 9


def test_off_terminal_metrics_keep_old_wire_output_even_after_rollback(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    before = firestore_probe_export.terminal_totals()
    counter = Counter('omi_record_token_lease_expired_would_total', 'Synthetic lease expiry', registry=None)
    counter.inc()
    monkeypatch.setattr(firestore_probe_export, 'COLLECTORS', (*firestore_probe_export.COLLECTORS[:2], counter))
    assert firestore_probe_export.terminal_totals() == before
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    assert any(
        row[0] == 'omi_record_token_lease_expired_would_total' for row in firestore_probe_export.terminal_totals()
    )


@pytest.mark.parametrize('accepted', [False, True])
def test_custody_exact_clear_and_late_counter_follow_acceptance(enabled, accepted):
    before = record_audio.lease_metrics.LATE_APPEND._value.get()
    assert record_custody_append.begin('synthetic', 'record', 'custody:first', firestore_client=enabled)
    assert record_custody_append.begin('synthetic', 'record', 'custody:other', firestore_client=enabled)
    assert enabled.rows[PATH]['record_upload_revision'] == 7
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == before
    record_custody_append.finish('synthetic', 'record', 'custody:first', accepted=accepted, firestore_client=enabled)
    assert 'custody:first' not in enabled.rows[PATH]['record_upload_sessions']
    assert 'custody:other' in enabled.rows[PATH]['record_upload_sessions']
    assert enabled.rows[PATH]['record_upload_revision'] == 7 + accepted
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == before + accepted
    # A repeated/lost completion response cannot double-count or bump again.
    snapshot = deepcopy(enabled.rows)
    assert (
        record_custody_append.finish(
            'synthetic', 'record', 'custody:first', accepted=accepted, firestore_client=enabled
        )
        is accepted
    )
    assert enabled.rows == snapshot
    assert not enabled.transactions[-1].has_written
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == before + accepted


def test_custody_heartbeat_writes_at_most_once_per_half_lease(enabled, monkeypatch):
    enabled.rows[PATH]['record_upload_sessions'] = {'custody': {**TOKEN, 'pod': '', 'signal_source': 'custody_append'}}
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='custody', firestore_client=enabled
    )
    for seconds in (0, 1, 60, 1949):
        monkeypatch.setattr(record_audio.time, 'time', lambda: NOW + seconds)
        assert not record_audio.renew_record_token_lease(
            'synthetic', 'record', source='custody_append', session='custody', firestore_client=enabled
        )
        assert not enabled.transactions[-1].updates
    monkeypatch.setattr(record_audio.time, 'time', lambda: NOW + 1950)
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='custody', firestore_client=enabled
    )
    assert len(enabled.transactions[-1].updates) == 1


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('sessions', [{}, {'s': TOKEN}])
def test_complete_frame_reopen_is_serve_only_and_shadow_only_counts(enabled, monkeypatch, mode, sessions):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    enabled.rows[PATH].update(record_audio_closed=True, record_upload_sessions=deepcopy(sessions), raw_audio='retained')
    before = deepcopy(enabled.rows)
    counter = record_audio.lease_metrics.LATE_APPEND._value.get()
    observed = {}
    record_audio.renew_record_token_lease(
        'synthetic',
        'record',
        source='frames',
        session='s',
        producer=POD,
        firestore_client=enabled,
        late_observation=observed,
    )
    if mode == 'serve':
        assert not enabled.rows[PATH]['record_audio_closed']
        assert enabled.rows[PATH]['raw_audio'] == 'retained'
        assert enabled.rows[PATH]['record_upload_revision'] == 8
        assert any(row.get('partial_coordinator') for row in enabled.rows.values())
    else:
        assert enabled.rows == before
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == counter
    assert bool(observed.get('late')) is (mode != 'off')


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_crashed_custody_token_keeps_own_lease_exit_after_rollback(enabled, monkeypatch, mode):
    enabled.rows[PATH]['record_upload_sessions'] = {}
    assert record_custody_append.begin('synthetic', 'record', 'custody:crashed', firestore_client=enabled)
    row = enabled.rows[PATH]
    token = row['record_upload_sessions']['custody:crashed']
    assert token['pod'] == ''
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    duration = lease.custody_token_lease_seconds()
    for elapsed in (0, duration - 1, duration):
        monkeypatch.setattr(record_audio.time, 'time', lambda: NOW + elapsed)
        assert not producer_tokens_dead(row['record_upload_sessions'], None, uid='synthetic', row=row)
    monkeypatch.setattr(record_audio.time, 'time', lambda: NOW + duration + 1)
    assert producer_tokens_dead(row['record_upload_sessions'], None, uid='synthetic', row=row)
    if mode == 'off':
        assert not producer_tokens_dead({'frame': TOKEN}, None, uid='synthetic', row=row)


def test_off_custody_begin_has_no_io(enabled, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    monkeypatch.setattr(record_custody_append, 'get_firestore_client', Mock(side_effect=AssertionError('off IO')))
    before = deepcopy(enabled.rows)
    assert not record_custody_append.begin('synthetic', 'record', 'custody:upload')
    assert enabled.rows == before


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('expired', [False, True])
def test_new_frame_token_observes_older_lease_before_replacing_custody(enabled, monkeypatch, mode, expired):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    old = {**TOKEN, 'lease_expires_at': NOW - 1 if expired else NOW + 3600}
    enabled.rows[PATH].update(record_upload_sessions={'old': old}, record_audio_closed=False)
    observed = {}
    counter = record_audio.lease_metrics.LATE_APPEND._value.get()
    assert record_audio.set_record_upload_pending(
        'synthetic', 'record', 'new', True, producer=POD, firestore_client=enabled, late_observation=observed
    )
    assert observed['late'] is (expired and mode != 'off')
    assert enabled.rows[PATH]['record_upload_sessions']['old'] == old
    assert enabled.rows[PATH]['record_upload_revision'] == 8
    assert not enabled.rows[PATH].get('record_audio_partial')
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == counter  # no durable frame yet


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize('state', ['closed', 'partial'])
def test_throttled_custody_renewal_still_observes_late_state(enabled, monkeypatch, mode, state):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    row = enabled.rows[PATH]
    row['record_upload_sessions']['s'].update(last_signal_at=NOW - 1, lease_expires_at=NOW + 3599)
    row['record_audio_closed' if state == 'closed' else 'record_audio_partial'] = True
    before = deepcopy(enabled.rows)
    observed = {}
    assert not record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', firestore_client=enabled, late_observation=observed
    )
    assert observed == {'late': True}
    assert enabled.rows == before
    assert not enabled.transactions[-1].has_written
