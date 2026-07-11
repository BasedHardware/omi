from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from unittest.mock import MagicMock

from database import sync_ledger, user_usage
from scripts.render_cloud_run_clone_env import clone_environment
from utils.sync import backfill, capture_manifest, content_id, lanes


def test_lane_classification_fresh_backfill_and_untrusted(monkeypatch):
    now = 2_000_000_000
    monkeypatch.setenv('SYNC_FRESH_MAX_AGE_SECONDS', '21600')
    monkeypatch.setenv('SYNC_BACKFILL_MAX_AGE_SECONDS', '2592000')
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda name: int(name.split('.')[0]))

    fresh = lanes.classify_sync_lane([f'{now - 60}.opus'], client_device_id='device-1', now=now)
    historical = lanes.classify_sync_lane([f'{now - 8 * 86400}.opus'], client_device_id='device-1', now=now)
    future = lanes.classify_sync_lane([f'{now + 301}.opus'], client_device_id='device-1', now=now)
    invalid = lanes.classify_sync_lane(['invalid.opus'], client_device_id='device-1', now=now)
    legacy = lanes.classify_sync_lane([f'{now - 60}.opus'], client_device_id=None, now=now)

    assert fresh.lane == lanes.SyncLane.FRESH
    assert fresh.trust == lanes.CaptureTimeTrust.DEVICE_BOUND
    assert historical.lane == lanes.SyncLane.BACKFILL
    assert historical.reason == 'historical_capture'
    assert future.lane == lanes.SyncLane.BACKFILL
    assert future.trust == lanes.CaptureTimeTrust.UNTRUSTED
    assert invalid.lane == lanes.SyncLane.BACKFILL
    assert invalid.trust == lanes.CaptureTimeTrust.UNTRUSTED
    assert legacy.lane == lanes.SyncLane.BACKFILL
    assert legacy.reason == 'unbound_capture_time'


def test_lane_classification_rejects_lookback_beyond_30_days(monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _name: now - 31 * 86400)

    decision = lanes.classify_sync_lane(['old.opus'], client_device_id='device-1', now=now)

    assert decision.lane == lanes.SyncLane.BACKFILL
    assert decision.automatic_recovery_allowed is False
    assert decision.reason == 'lookback_exceeded'


def test_fresh_capture_proof_requires_server_conversation_window(monkeypatch):
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _filename: 1000)

    assert lanes.capture_times_within_window(['audio.bin'], 900, 1100) is True
    assert lanes.capture_times_within_window(['audio.bin'], 1101, 1200) is False


def test_content_identity_is_stable_across_paths_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    first_dir = tmp_path / 'first'
    second_dir = tmp_path / 'second'
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / '100.opus').write_bytes(b'audio-a')
    (first_dir / '200.opus').write_bytes(b'audio-b')
    (second_dir / '100.opus').write_bytes(b'audio-a')
    (second_dir / '200.opus').write_bytes(b'audio-b')

    one = content_id.compute_sync_content_id('uid-1', [str(first_dir / '200.opus'), str(first_dir / '100.opus')])
    two = content_id.compute_sync_content_id('uid-1', [str(second_dir / '100.opus'), str(second_dir / '200.opus')])
    other_user = content_id.compute_sync_content_id(
        'uid-2', [str(second_dir / '100.opus'), str(second_dir / '200.opus')]
    )

    assert one == two
    assert one != other_user
    assert 'audio' not in one


def test_content_identity_distinguishes_identical_audio_at_different_capture_times(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    first = tmp_path / '100.opus'
    second = tmp_path / '200.opus'
    first.write_bytes(b'silence')
    second.write_bytes(b'silence')

    assert content_id.compute_sync_content_id('uid', [str(first)]) != content_id.compute_sync_content_id(
        'uid', [str(second)]
    )


def test_cloud_run_clone_preserves_live_contract_and_overlays_lane_settings():
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'env': [
                                {'name': 'REDIS_DB_HOST', 'value': '10.0.0.1'},
                                {
                                    'name': 'DEEPGRAM_API_KEY',
                                    'valueFrom': {'secretKeyRef': {'name': 'DEEPGRAM_API_KEY', 'key': '7'}},
                                },
                                {
                                    'name': 'GOOGLE_APPLICATION_CREDENTIALS',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'GOOGLE_APPLICATION_CREDENTIALS', 'key': 'latest'}
                                    },
                                },
                            ]
                        }
                    ]
                }
            }
        }
    }

    env_vars, secrets = clone_environment(
        service,
        'REDIS_DB_HOST=10.0.0.2\nSYNC_TASKS_QUEUE=sync-backfill',
        'ENCRYPTION_SECRET=ENCRYPTION_SECRET:latest',
        drop_names='GOOGLE_APPLICATION_CREDENTIALS',
    )

    assert 'REDIS_DB_HOST=10.0.0.2' in env_vars
    assert 'SYNC_TASKS_QUEUE=sync-backfill' in env_vars
    assert 'DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:7' in secrets
    assert 'ENCRYPTION_SECRET=ENCRYPTION_SECRET:latest' in secrets
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in env_vars
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in secrets


def test_cloud_run_clone_allows_explicit_manifest_secret_to_restore_dropped_live_name():
    service = {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'env': [
                                {
                                    'name': 'GOOGLE_APPLICATION_CREDENTIALS',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'GOOGLE_APPLICATION_CREDENTIALS', 'key': '7'}
                                    },
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    _, secrets = clone_environment(
        service,
        '',
        'GOOGLE_APPLICATION_CREDENTIALS=GOOGLE_APPLICATION_CREDENTIALS:1',
        drop_names='GOOGLE_APPLICATION_CREDENTIALS',
    )

    assert secrets == 'GOOGLE_APPLICATION_CREDENTIALS=GOOGLE_APPLICATION_CREDENTIALS:1'


def test_deploy_contract_routes_both_backfill_budget_alerts():
    action = (Path(__file__).resolve().parents[3] / '.github/actions/sync-backfill-lifecycle/action.yml').read_text()
    manual = (Path(__file__).resolve().parents[3] / '.github/workflows/gcp_backend.yml').read_text()

    assert 'SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS' in manual
    assert "provision_budget_alerts: ${{ github.event.inputs.environment == 'prod' && 'true' || 'false' }}" in manual
    assert 'for THRESHOLD in 70 90' in action
    assert 'gcloud monitoring policies create' in action
    assert 'Cannot find metric(s)' in action
    assert 'Waiting for log-based metric' in action
    assert '--notification-channels="$ALERT_CHANNELS"' in action


def test_sync_backfill_lifecycle_is_shared_by_manual_and_auto_dev():
    root = Path(__file__).resolve().parents[3]
    action = (root / '.github/actions/sync-backfill-lifecycle/action.yml').read_text()
    manual = (root / '.github/workflows/gcp_backend.yml').read_text()
    auto_dev = (root / '.github/workflows/gcp_backend_auto_dev.yml').read_text()

    for workflow in (manual, auto_dev):
        assert 'uses: ./.github/actions/sync-backfill-lifecycle' in workflow
        assert 'concurrency:' in workflow
        assert 'cancel-in-progress: false' in workflow
        assert 'id: sync-backfill' in workflow
        assert 'mode: worker' in workflow
        assert 'mode: platform' in workflow
        assert '${{ steps.sync-backfill.outputs.sync_backfill_env_vars }}' in workflow
        assert '${{ steps.sync-backfill.outputs.revision }}' in workflow
        assert 'provision_sync_ledger_ttl: \'true\'' in workflow
        assert '--wait-revision-ready backend-sync-backfill=${{ steps.sync-backfill.outputs.revision }}' in workflow
        assert 'gcloud run services update-traffic backend-sync-backfill' in workflow
        assert '--cloud-run-service backend-sync-backfill' in workflow
        assert (
            '--expect-cloud-run-traffic backend-sync-backfill=${{ steps.sync-backfill.outputs.revision }}' in workflow
        )

    assert "provision_budget_alerts: 'false'" in auto_dev
    assert 'id: backfill-service' in action
    assert 'id: backfill-runtime' in action
    assert 'DROP_NAMES: GOOGLE_APPLICATION_CREDENTIALS' in action
    assert 'id: deploy-backend-sync-backfill' in action
    assert 'id: backfill-service-exists' in action
    assert "no_traffic: ${{ steps.backfill-service-exists.outputs.exists }}" in action
    assert 'REVISION="${{ inputs.service }}-sync-backfill-${{ inputs.revision_suffix }}"' in action
    assert "--format='value(status.latestCreatedRevisionName)'" in action
    assert 'render_cloud_run_clone_env.py' in action
    assert 'SYNC_TASKS_QUEUE=sync-backfill' in action
    assert '--min-instances=0' in action
    assert '--max-instances=4' in action
    assert '--concurrency=1' in action
    assert '--memory=1Gi' in action
    assert 'remove_secret_flags' not in action
    assert 'gcloud run services add-iam-policy-binding backend-sync-backfill' in action
    assert 'gcloud tasks queues create sync-backfill' in action
    assert '--max-concurrent-dispatches=4' in action
    assert 'collection-group=sync_content_ledger' in action
    assert "inputs.provision_sync_ledger_ttl == 'true'" in action
    assert "inputs.provision_budget_alerts == 'true'" in action


def test_cloud_run_default_service_lists_include_sync_backfill():
    root = Path(__file__).resolve().parents[2] / 'scripts'
    preflight = (root / 'preflight-cloud-run-deploy.py').read_text()
    repair = (root / 'repair_cloud_run_traffic.py').read_text()
    status = (root / 'deploy_status_report.py').read_text()
    manual = (Path(__file__).resolve().parents[3] / '.github/workflows/gcp_backend.yml').read_text()

    assert "DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')" in preflight
    assert "DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')" in repair
    assert "'backend-sync-backfill'" in status
    assert '--cloud-run-service backend-sync-backfill' in manual
    assert manual.index('repair-traffic:') < manual.index('--cloud-run-service backend-sync-backfill')


def test_processed_segment_marker_follows_partial_result_checkpoint():
    pipeline = (Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py').read_text()
    checkpoint = pipeline.index("update_sync_job(job_id, {'partial_result': partial})")
    durable_checkpoint = pipeline.index('checkpoint_sync_content_partial_result(uid, content_id, job_id, partial)')
    marker = pipeline.index('add_processed_segment(job_id, path)', checkpoint)

    assert checkpoint < durable_checkpoint < marker
    assert "set(partial_result.get('new_memories') or [])" in pipeline
    assert 'get_sync_content_partial_result' in pipeline


def test_segment_identity_survives_job_directory_change(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    first = tmp_path / 'job-1'
    second = tmp_path / 'job-2'
    first.mkdir()
    second.mkdir()
    (first / '1700000000_0.wav').write_bytes(b'segment-audio')
    (second / '1700000000_0.wav').write_bytes(b'segment-audio')

    assert content_id.compute_sync_segment_id(
        'uid', str(first / '1700000000_0.wav')
    ) == content_id.compute_sync_segment_id('uid', str(second / '1700000000_0.wav'))


def test_server_manifest_binds_uid_device_conversation_names_and_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'test-secret')
    audio = tmp_path / 'audio_omi_opus_16000_1_fs160_1000.bin'
    audio.write_bytes(b'captured-audio')
    digest = hashlib.sha256(b'captured-audio').hexdigest()
    token = capture_manifest.issue_capture_manifest(
        'uid',
        'ios_a1b2c3d4',
        'conversation',
        [{'name': audio.name, 'sha256': digest}],
        now=1000,
    )

    claims = capture_manifest.verify_capture_manifest(
        token,
        'uid',
        'ios_a1b2c3d4',
        'conversation',
        [audio.name],
        now=1001,
    )

    assert claims is not None
    assert capture_manifest.manifest_claims_match_paths(claims, [str(audio)]) is True
    assert (
        capture_manifest.verify_capture_manifest(
            token, 'other-uid', 'ios_a1b2c3d4', 'conversation', [audio.name], now=1001
        )
        is None
    )


def test_server_manifest_allows_only_one_content_set_per_conversation(monkeypatch):
    redis = MagicMock()
    monkeypatch.setattr(capture_manifest, 'redis_client', redis)
    claim = [{'name': 'audio_1000.bin', 'sha256': 'a' * 64}]

    redis.set.return_value = True
    assert capture_manifest.claim_conversation_manifest('uid', 'conversation', claim) is True
    fingerprint = redis.set.call_args.args[1]
    redis.set.return_value = False
    redis.get.return_value = fingerprint
    assert capture_manifest.claim_conversation_manifest('uid', 'conversation', claim) is True
    redis.get.return_value = 'different'
    assert capture_manifest.claim_conversation_manifest('uid', 'conversation', claim) is False


def test_backfill_reservation_maps_user_and_global_caps(monkeypatch):
    redis = MagicMock()
    monkeypatch.setattr(backfill, 'redis_client', redis)
    monkeypatch.setattr(backfill, 'retry_after_next_utc_day', lambda: 123)

    redis.eval.return_value = -1
    user_denied = backfill.reserve_backfill_speech('uid', 'job-1', 1000)
    redis.eval.return_value = -2
    global_denied = backfill.reserve_backfill_speech('uid', 'job-2', 1000)
    redis.eval.return_value = 1
    allowed = backfill.reserve_backfill_speech('uid', 'job-3', 1000)

    assert (user_denied.allowed, user_denied.reason, user_denied.retry_after) == (False, 'backfill_paced', 123)
    assert (global_denied.allowed, global_denied.reason, global_denied.retry_after) == (
        False,
        'backfill_capacity',
        123,
    )
    assert allowed.allowed is True


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, data=None):
        self.data = data
        self.writes = []

    def get(self, transaction=None):
        return _Snapshot(self.data)

    def set(self, data, merge=False):
        self.writes.append((data, merge))


class _Transaction:
    def __init__(self):
        self.writes = []

    def set(self, ref, data, merge=False):
        self.writes.append((ref, data, merge))


def test_durable_ledger_replays_completion_and_blocks_recent_duplicate():
    now = datetime.now(timezone.utc)
    completed_ref = _Ref({'status': 'completed', 'result': {'total_segments': 2}})
    busy_ref = _Ref({'status': 'processing', 'job_id': 'other', 'updated_at': now - timedelta(minutes=1)})

    completed = sync_ledger._claim_transaction.to_wrap(_Transaction(), completed_ref, 'new-job', 'backfill', now)
    busy = sync_ledger._claim_transaction.to_wrap(_Transaction(), busy_ref, 'new-job', 'backfill', now)

    assert completed == {'outcome': 'completed', 'result': {'total_segments': 2}}
    assert busy == {'outcome': 'busy'}


def test_durable_ledger_side_effect_is_once_only():
    now = datetime.now(timezone.utc)
    transaction = _Transaction()
    first = sync_ledger._side_effect_transaction.to_wrap(
        transaction,
        _Ref({'job_id': 'job-1'}),
        'job-1',
        'speech_ms',
        1000,
        now,
    )
    duplicate = sync_ledger._side_effect_transaction.to_wrap(
        _Transaction(),
        _Ref({'job_id': 'job-1', 'metered_at': now}),
        'job-1',
        'speech_ms',
        1000,
        now,
    )

    assert first is True
    assert transaction.writes[0][1]['speech_ms_value'] == 1000
    assert duplicate is False


def test_release_preserves_once_only_side_effect_markers():
    ref = _Ref({'status': 'processing', 'job_id': 'job-1', 'metered_at': datetime.now(timezone.utc)})
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = ref

    sync_ledger.release_sync_content_claim('uid', 'content', 'job-1', firestore_client=client)

    assert ref.writes[0][0]['status'] == 'retryable'
    assert ref.writes[0][1] is True


def test_hourly_usage_increment_and_ledger_marker_share_one_transaction():
    transaction = _Transaction()
    marker_ref = _Ref({'status': 'processing'})
    usage_ref = _Ref()

    recorded = user_usage._update_hourly_usage_once_transaction.to_wrap(
        transaction,
        marker_ref,
        usage_ref,
        {'transcription_seconds': 5},
    )
    duplicate = user_usage._update_hourly_usage_once_transaction.to_wrap(
        _Transaction(),
        _Ref({'usage_committed_at': datetime.now(timezone.utc)}),
        usage_ref,
        {'transcription_seconds': 5},
    )

    assert recorded is True
    assert len(transaction.writes) == 2
    assert transaction.writes[0][1].get('usage_committed_at') is not None
    assert duplicate is False


def test_durable_processed_segment_is_not_added_twice():
    now = datetime.now(timezone.utc)
    transaction = _Transaction()

    added = sync_ledger._processed_segment_transaction.to_wrap(
        transaction,
        _Ref({'job_id': 'job-1', 'processed_segment_ids': []}),
        'job-1',
        'segment-1',
        now,
    )
    duplicate = sync_ledger._processed_segment_transaction.to_wrap(
        _Transaction(),
        _Ref({'job_id': 'job-1', 'processed_segment_ids': ['segment-1']}),
        'job-1',
        'segment-1',
        now,
    )

    assert added is True
    assert duplicate is False
