"""A repeatedly disagreeing pinned retained source holds once; a transient mismatch recovers."""

from copy import deepcopy
import json
from unittest.mock import Mock

from google.api_core.exceptions import ServiceUnavailable

from config.batch_pipeline import HELD_DEAD_LETTER_SECONDS, scheduler_control_key
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from tests.unit.test_batch_pipeline_invalid_manifest_hold import MAGIC, ref, serve
from utils.batch_pipeline.artifacts import ArtifactStore, ProtectionContext
from utils.batch_pipeline.source_audio import RetainedPcmDigestChanged
from utils.batch_pipeline.held_terminal import retained_digest_changed_held
from utils.batch_pipeline.scheduler import Scheduler
from utils.metrics import OMI_FALLBACK_TOTAL

SOURCE = b'\1\0' * 16000
WRONG = b'\2\0' * 16000


def metric():
    return OMI_FALLBACK_TOTAL.labels(
        component='stt_selection',
        from_mode='batch',
        to_mode='none',
        reason='retained_digest_changed',
        outcome='degraded',
    )._value.get()


def body():
    return (
        MAGIC
        + json.dumps(
            {
                'owner_id': 'synthetic-owner',
                'conversation_id': 'c',
                'capture_at': 1,
                'context': {},
                'references': [
                    {
                        **ref(0, 8000),
                        'bucket': 'omi-private-cloud-sync',
                        'path': 'chunks/synthetic-owner/c/x.bin',
                    }
                ],
            }
        ).encode()
    )


def retained_source(setup, downloads):
    """Real ArtifactStore -> materialize -> pinned fake source bytes, same generation."""
    client, _, _, artifacts, _, _ = setup
    row(client).update(unit_kind='capture_span', conversation_id='c')
    storage = Mock()
    blob = storage.bucket.return_value.blob.return_value
    blob.size = len(SOURCE)
    blob.metadata = {}
    blob.download_as_bytes.side_effect = list(downloads)
    source = ArtifactStore(
        storage,
        bucket='synthetic',
        namespace='batch_pipeline_prod',
        authorize=lambda _: ProtectionContext('standard', 0),
        key_for_owner=lambda _: b'0' * 32,
        register_artifact=lambda *args: None,
    )
    source._read = Mock(return_value=body())
    artifacts.fetch_audio.side_effect = source.fetch_audio
    return blob


def test_confirmed_digest_change_holds_once_and_keeps_custody(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    blob = retained_source(setup, [WRONG, WRONG])
    recovery.protocol.prepare('bad', binding.owner_id, 100)
    before = deepcopy(row(client))
    start = metric()
    http = serve(setup, monkeypatch)
    payload = {'stage': 'prod', 'segment_id': 'bad'}
    response = http.post('/v2/batch-pipeline/recover-quarantine', json=payload)
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': 'retained_digest_changed'}
    assert job['recovery']['settled_at'] == 100 and 'started_at' not in job['recovery']
    assert retained_digest_changed_held(job)
    assert {k: v for k, v in job.items() if k not in {'recovery', 'recovery_state', 'held_deadline_at'}} == {
        k: v for k, v in before.items() if k not in {'recovery', 'recovery_state', 'held_deadline_at'}
    }
    assert metric() == start + 1
    assert artifacts.fetch_audio.call_args.kwargs == {'confirm_retained_digest': True}
    # Exactly one confirmation re-read of the same pinned ref, then the hold.
    assert blob.download_as_bytes.call_count == 2
    assert blob.download_as_bytes.call_args.kwargs['if_generation_match'] == 1
    stt.assert_not_called()
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]
    # A retried delivery or sweep cannot prepare a new intent: no re-read, no second counter.
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'held'}
    assert metric() == start + 1
    assert blob.download_as_bytes.call_count == 2
    stt.assert_not_called()


def test_matching_second_read_passes_the_verified_audio_to_recovery(setup, monkeypatch):
    client, _, _, _, stt, _ = setup
    blob = retained_source(setup, [WRONG, SOURCE])
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'recovered'}
    assert blob.download_as_bytes.call_count == 2
    stt.assert_called_once()
    audio = stt.call_args.args[2]
    # The provider received the verified WAV with the confirmed PCM samples.
    assert audio[:4] == b'RIFF' and audio[8:12] == b'WAVE'
    assert SOURCE[:4096] in audio
    assert WRONG[:4096] not in audio
    job = row(client)
    assert job['recovery_state'] == 'recovered' and 'refusal' not in job['recovery']
    assert metric() == start


def test_confirmation_read_outage_stays_retryable(setup, monkeypatch):
    client, _, _, _, stt, _ = setup
    retained_source(setup, [WRONG, ServiceUnavailable('synthetic')])
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 500
    job = row(client)
    assert job['recovery_state'] == 'prepared' and 'refusal' not in job['recovery']
    assert metric() == start
    stt.assert_not_called()


def test_flag_off_keeps_the_legacy_single_read_and_500(setup, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_RETAINED_DIGEST_HOLD_ENABLED', 'false')
    client, _, _, artifacts, stt, _ = setup
    blob = retained_source(setup, [WRONG])
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 500
    assert artifacts.fetch_audio.call_args.kwargs == {}
    assert blob.download_as_bytes.call_count == 1
    job = row(client)
    assert job['recovery_state'] == 'prepared' and 'refusal' not in job['recovery']
    assert metric() == start
    stt.assert_not_called()


def test_lost_intent_token_blocks_the_terminal_cas(setup, monkeypatch):
    client, _, _, _, stt, _ = setup
    blob = retained_source(setup, [WRONG, WRONG])

    def lose_intent(*args, **kwargs):
        if blob.download_as_bytes.call_count == 2:
            row(client)['recovery']['token'] = 'new-token'
        return WRONG

    blob.download_as_bytes.side_effect = lose_intent
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'held'}
    job = row(client)
    assert job['recovery_state'] == 'prepared' and 'refusal' not in job['recovery']
    assert metric() == start
    stt.assert_not_called()


def test_privacy_revoked_after_mismatch_blocks_the_terminal_cas(setup, monkeypatch):
    client, _, binding, artifacts, stt, _ = setup
    retained_source(setup, [WRONG, WRONG])

    def revoke(*args, **kwargs):
        client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'pending'}
        raise RetainedPcmDigestChanged('retained PCM digest changed')

    artifacts.fetch_audio.side_effect = revoke
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'cancelled'}
    job = row(client)
    assert 'retained_digest_changed' != (job.get('recovery', {}).get('refusal') or {}).get('reason')
    assert metric() == start
    stt.assert_not_called()


def test_changed_audio_uri_blocks_the_terminal_cas(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert not recovery.protocol.hold_retained_digest_changed('bad', 'f' * 32, 100, audio_uri='gs://synthetic/audio')
    assert not recovery.protocol.hold_retained_digest_changed('bad', token, 100, audio_uri='gs://synthetic/other')
    assert recovery.protocol.start('bad', token, 100)
    assert not recovery.protocol.hold_retained_digest_changed('bad', token, 100, audio_uri='gs://synthetic/audio')
    assert row(client)['recovery_state'] == 'running'


def test_expired_tagged_row_skips_nightly_and_intake_auto_redrive(setup):
    client, store, _, _, _, _ = setup
    store_recovery = RecoveryStore(store)
    job = row(client)
    job.update(
        recovery_state='failed_held',
        recovery={
            'token': 't' * 32,
            'epoch': 1,
            'privacy_generation': 0,
            'prepared_at': 50,
            'settled_at': 90,
            'refusal': {'reason': 'retained_digest_changed'},
        },
    )
    client.rows['batch_pipeline_prod_control', scheduler_control_key(job['owner_key'])] = {'p0_active': True}
    # The real retained-expiry writer still stamps and expires the tagged row.
    assert store_recovery.expire_held('bad', 100) == 'stamped'
    assert store_recovery.expire_held('bad', 100 + HELD_DEAD_LETTER_SECONDS) == 'expired'
    job = row(client)
    assert job['state'] == 'dead' and job['dead_letter_reason'] == 'held_expired'
    assert retained_digest_changed_held(job)
    before = deepcopy(job)
    expired_at = job['held_expired_at']
    # Nightly maintenance (dead_before) refuses without a write or budget spend.
    assert not store_recovery.requeue_quarantined('bad', expired_at + 100, dead_before=expired_at + 1)
    # Intake-status automatic dead redrive (operator=False) refuses too.
    outcome = store.run(
        lambda tx: Scheduler.redrive_in_transaction(
            tx, tx.get('jobs', 'bad'), expired_at + 100, checked=store_recovery.checked
        )
    )
    assert outcome is None
    assert row(client) == before
    # The reviewed operator path still recovers the row.
    assert store_recovery.requeue_quarantined('bad', expired_at + 100)
    assert row(client)['state'] == 'ready'


def test_other_failed_held_reasons_keep_their_nightly_redrive(setup):
    client, store, _, _, _, _ = setup
    store_recovery = RecoveryStore(store)
    job = row(client)
    job.update(
        state='dead',
        dead_letter_reason='held_expired',
        held_expired_at=100.0,
        held_deadline_at=1.0,
        recovery_state='failed_held',
        recovery={
            'token': 't' * 32,
            'epoch': 1,
            'privacy_generation': 0,
            'prepared_at': 50,
            'settled_at': 90,
            'refusal': {'reason': 'input_missing'},
        },
        merge_pending=True,
        token='',
        lease_until=0,
    )
    client.rows['batch_pipeline_prod_control', scheduler_control_key(job['owner_key'])] = {'p0_active': True}
    assert store_recovery.requeue_quarantined('bad', 200, dead_before=150)
    assert row(client)['state'] == 'ready'
