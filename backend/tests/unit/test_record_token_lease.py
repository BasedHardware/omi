"""Producer custody lease: modes, stock seed, exact clocks and transactional renewal."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import Mock

import pytest

from config import record_seal_rules as lease, refactor_modes
from config.policy.batch import cohort_bucket
from database import record_audio
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
    return StrictFirestore({PATH: ROW})


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
    before = deepcopy(enabled.rows[PATH])
    assert record_audio.renew_record_token_lease('synthetic', 'record', source=source, firestore_client=enabled)
    row = enabled.rows[PATH]
    assert row['record_upload_revision'] == before['record_upload_revision'] + 1
    assert row['record_upload_sessions']['s'] == {
        **POD,
        'last_signal_at': NOW,
        'lease_expires_at': NOW + 3600,
        'signal_source': source,
    }
    assert not producer_tokens_dead(row['record_upload_sessions'], None, uid='synthetic', row=row)
    assert record_audio.renew_record_token_lease('synthetic', 'record', source=source, firestore_client=enabled)
    assert row['record_upload_revision'] == 8  # one bump, no repeated invalidation


def test_custody_renews_all_identified_tokens_but_frames_are_exact(enabled):
    enabled.rows[PATH]['record_upload_sessions']['other'] = {**TOKEN, 'pod': 'other'}
    enabled.rows[PATH]['record_upload_sessions']['legacy'] = True
    record_audio.renew_record_token_lease('synthetic', 'record', source='frames', session='s', firestore_client=enabled)
    assert enabled.rows[PATH]['record_upload_sessions']['other']['last_signal_at'] == TOKEN['last_signal_at']
    record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append', firestore_client=enabled)
    assert enabled.rows[PATH]['record_upload_sessions']['other']['last_signal_at'] == NOW
    assert enabled.rows[PATH]['record_upload_sessions']['legacy'] is True


def test_upload_survives_original_pusher_abandon_or_pod_death(enabled):
    enabled.rows[PATH]['record_upload_sessions']['s']['abandoned_at'] = NOW - 4000
    record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append', firestore_client=enabled)
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


def test_after_seal_append_counted_without_inventing_token_or_deleting_audio(enabled):
    enabled.rows[PATH].update(record_audio_closed=True, record_upload_sessions={}, raw_audio='retained')
    before = deepcopy(enabled.rows)
    counter = record_audio.lease_metrics.LATE_APPEND._value.get()
    record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append', firestore_client=enabled)
    assert enabled.rows == before
    assert record_audio.lease_metrics.LATE_APPEND._value.get() == counter + 1


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


def test_stock_seed_clamps_every_durable_anchor_and_never_uses_process_start(enabled, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - 100))
    assert not producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', str(NOW - 7200))
    assert producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW)
    for row, job, token in [
        ({**ROW, 'record_seal_refused_at': NOW - 10}, {}, POD),
        (ROW, {'available_at': NOW - 10}, POD),
        (ROW, {}, {**POD, 'abandoned_at': NOW - 10}),
    ]:
        assert not producer_tokens_dead({'s': token}, None, uid='synthetic', row=row, job=job)
    monkeypatch.delenv('RECORD_TOKEN_LEASE_DEPLOYED_AT')
    assert not producer_tokens_dead({'s': POD}, None, uid='synthetic', row=ROW)


def test_partial_late_custody_bytes_invalidate_barrier_even_after_map_was_cleared(enabled):
    enabled.rows[PATH].update(record_upload_sessions={}, record_audio_partial={'upload_revision': 7})
    record_audio.renew_record_token_lease('synthetic', 'record', source='custody_append', firestore_client=enabled)
    assert enabled.rows[PATH]['record_upload_revision'] == 8
    assert enabled.rows[PATH]['record_audio_partial']['upload_revision'] == 7
    assert not enabled.rows[PATH].get('record_audio_closed')


def test_generic_mode_reader_uses_dark_default(monkeypatch):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    assert refactor_modes.mode('RECORD_TOKEN_LEASE_MODE') == 'off'
    assert not refactor_modes.serving_for('RECORD_TOKEN_LEASE_MODE', 'synthetic')
