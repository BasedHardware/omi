"""Synthetic orphan repair: real registration and strict transaction ordering, no cloud IO."""

from datetime import datetime, timedelta, timezone
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.record_audio import require_record_audio_barrier
from utils.conversations import lifecycle, typesense_index
from database.batch_pipeline_store import FirestoreStore
from database import recording_sessions, batch_pipeline_privacy as privacy
from utils.batch_pipeline import record_orphan_repair as repair
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit import test_conversation_quiet_finalization as quiet_tests

quiet_store = quiet_tests.store

NOW = datetime.now(timezone.utc)
UID, CID = 'synthetic-owner', 'synthetic-capture'
PATH = ('users', UID, 'conversations', CID)
SESSION = ('users', UID, 'recording_sessions', 'synthetic-session')
SCOPE = ['/'.join(PATH)]
FLAGS = {'K_SERVICE': 'backend', 'BATCH_PIPELINE_PERCENT': '0', 'BATCH_LIVE_STT_RETIRE_PERCENT': '0'}
JOB = ('batch_pipeline_dev_jobs', repair.record_identity(UID, CID)[1])


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_LIVE_ORPHAN_REPAIR_ENABLED', 'true')
    client = StrictFirestore(
        {
            ('users', UID): {'private_cloud_sync_enabled': True},
            PATH: {
                'record_lane_owner': 'batch_live_v1',
                'server_batch_only': True,
                'status': 'in_progress',
                'created_at': NOW - timedelta(days=1),
                'started_at': NOW - timedelta(days=1),
                'finished_at': NOW - timedelta(days=1),
                'source': 'omi',
                'language': 'en',
                'record_audio_closed': True,
                'server_batch_audio_closed': True,
                'server_batch_audio_received': True,
                'private_cloud_sync_enabled': True,
                'external_data': {'recording_session_id': 'synthetic-session'},
            },
            SESSION: {
                'uid': UID,
                'conversation_id': CID,
                'recording_session_id': 'synthetic-session',
                'lifecycle_phase': 'in_progress',
                'lease_expires_at': NOW - timedelta(hours=3),
            },
        }
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    artifacts = SimpleNamespace(authorize=Mock(), key_for_owner=lambda _: b'x' * 32)
    monkeypatch.setattr(repair, 'list_audio_chunks', Mock(return_value=[{'generation': 1}]))
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: (
            unit
            for unit in [
                (100.0, 2.0, [{'generation': 1, 'frames': 32000}]),
                (110.0, 3.0, [{'generation': 2, 'frames': 48000}]),
            ]
        ),
    )
    return store, client, artifacts


def plan(source, paths=SCOPE):
    return repair.plan_repair(source[0], paths, object(), source[2], server_flags=FLAGS)


def apply(source, planned):
    return repair.apply_repair(source[0], planned, planned['plan_sha256'], object(), source[2])


def no_writes(client):
    return all(not t.updates and not t.sets and not t.deletes for t in client.transactions)


def test_plan_counts_only_audio_seconds_atomic_registration_and_idempotency(source):
    result = plan(source)
    report = repair.summary(result)
    assert report['dispositions'] == {'register': 1}
    assert report['sealed_received_audio_seconds'] == 5.0  # sum spans, not the 13-second envelope
    assert report['exits'] == {'register': 'normal_batch_pipeline'}
    assert all(secret not in json.dumps(report) for secret in (UID, CID, 'synthetic-session', JOB[1]))
    assert no_writes(source[1])
    assert apply(source, result) == {'registered': 1}
    row = source[1].rows[PATH]
    assert row['has_content'] is True
    assert (row['server_batch_audio_start'], row['server_batch_audio_end']) == (100.0, 113.0)
    assert source[1].rows[JOB]['state'] == 'record_pending'
    require_record_audio_barrier(row)
    assert row['relevance_decision']['verdict'] == 'keep'
    assert row['home_transcription_deadline_at'] > row['home_transcription_pending_at']
    assert source[1].transactions[-1].sets[0][0] == JOB
    assert source[1].transactions[-1].updates[0][0] == PATH
    assert apply(source, result) == {'already_registered': 1}
    assert plan(source)['entries'][0]['disposition'] == 'already_registered'
    assert len([tx for tx in source[1].transactions if tx.sets]) == 1


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'record_upload_sessions': {'pending': True}}, 'upload_pending'),
        ({'record_upload_failed': True}, 'barrier_mismatch'),
        ({'private_cloud_sync_enabled': False}, 'privacy_skipped'),
        ({'uses_custom_stt': True}, 'privacy_skipped'),
        ({'data_protection_level': 'e2ee'}, 'privacy_skipped'),
        ({'record_audio_closed': False}, 'barrier_mismatch'),
        ({'server_batch_audio_closed': False}, 'barrier_mismatch'),
        ({'finalization_job_id': 'other'}, 'not_candidate'),
        ({'created_at': NOW}, 'not_candidate'),
        ({'deleted': True}, 'not_candidate'),
        ({'discarded': True}, 'not_candidate'),
        ({'is_locked': True}, 'not_candidate'),
        ({'server_batch_only': False}, 'barrier_mismatch'),
    ],
)
def test_dispositions_have_named_exits_and_no_write_authority(source, change, reason):
    source[1].rows[PATH].update(change)
    result = plan(source)
    entry = result['entries'][0]
    assert entry['disposition'] == reason
    assert entry['exit'] == repair.EXITS[reason]
    assert apply(source, result) == {reason: 1}
    assert no_writes(source[1])


@pytest.mark.parametrize('consent', [False, None])
def test_owner_private_sync_off_or_unknown_skips_before_storage(source, consent):
    source[1].rows[('users', UID)] = {'private_cloud_sync_enabled': consent}
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'privacy_skipped'
    assert repair.summary(result)['skipped'] == 1
    repair.list_audio_chunks.assert_not_called()
    assert no_writes(source[1])


def test_even_empty_job_is_never_overwritten(source):
    source[1].rows[JOB] = {}
    assert plan(source)['entries'][0]['disposition'] == 'already_registered'
    assert no_writes(source[1])


def test_empty_storage_with_received_audio_is_parked_never_deleted(source, monkeypatch):
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [])
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'storage_empty_received'
    assert result['entries'][0]['last_failure_code'] == 'storage_empty_received'
    assert apply(source, result) == {'storage_empty_received': 1}
    assert no_writes(source[1])


@pytest.mark.parametrize('record_closed', [False, True])
def test_delete_empty_uses_real_fenced_terminal_and_never_audio_cleanup(source, monkeypatch, record_closed):
    source[1].rows[PATH]['record_audio_closed'] = record_closed
    source[1].rows[PATH]['server_batch_audio_received'] = False
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [])
    monkeypatch.setattr(recording_sessions, 'invalidate_people_stats_cache', lambda *a: None)
    # External index/photo projection effects are irrelevant; the real recording
    # deletion transaction and raw-audio preservation path still run.
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a: None)
    monkeypatch.setattr(lifecycle.conversations_db, 'delete_conversation_photos', lambda *a: None)
    monkeypatch.setattr(lifecycle, 'delete_conversation_audio_files', Mock(side_effect=AssertionError('no GCS delete')))
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'delete_empty'
    assert apply(source, result) == {'empty_deleted': 1}
    assert PATH not in source[1].rows
    assert source[1].rows[SESSION]['lifecycle_phase'] == 'discarded'
    lifecycle.delete_conversation_audio_files.assert_not_called()
    assert plan(source)['entries'][0]['disposition'] == 'not_candidate'


@pytest.mark.parametrize(
    'change',
    [
        {'record_upload_sessions': {'racing': True}},
        {'server_batch_audio_received': False},
        {'server_batch_audio_closed': False},
        {'has_content': True},
        {'language': 'es'},
    ],
)
def test_stale_snapshot_cannot_apply(source, change):
    result = plan(source)
    source[1].rows[PATH].update(change)
    assert apply(source, result) != {'registered': 1}
    assert JOB not in source[1].rows
    assert no_writes(source[1])


def test_digest_tamper_and_wrong_approval_refuse(source):
    result = plan(source)
    with pytest.raises(ValueError, match='approval'):
        repair.apply_repair(source[0], result, 'wrong', object(), source[2])
    result['entries'][0]['proof']['end'] = 999
    with pytest.raises(ValueError, match='approval'):
        apply(source, result)
    assert no_writes(source[1])


def test_switch_defaults_off_and_stops_apply_mid_page(source, monkeypatch):
    result = plan(source)
    monkeypatch.delenv('BATCH_LIVE_ORPHAN_REPAIR_ENABLED')
    assert not repair.batch_live_orphan_repair_enabled()
    assert apply(source, result) == {'disabled': 1}
    monkeypatch.setenv('BATCH_LIVE_ORPHAN_REPAIR_ENABLED', 'typo')
    assert apply(source, result) == {'disabled': 1}
    assert no_writes(source[1])


def test_storage_proof_change_refuses_registration(source, monkeypatch):
    result = plan(source)
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: (unit for unit in [(100.0, 3.0, [{'generation': 9, 'frames': 48000}])]),
    )
    assert apply(source, result) == {'state_changed': 1}
    assert no_writes(source[1])


def test_privacy_or_job_race_is_checked_in_commit_transaction(source, monkeypatch):
    result = plan(source)
    original = repair.retained_proof

    def changed(*args):
        proof = original(*args)
        source[1].rows[('users', UID)]['private_cloud_sync_enabled'] = False
        return proof

    monkeypatch.setattr(repair, 'retained_proof', changed)
    assert apply(source, result) == {'privacy_skipped': 1}
    assert no_writes(source[1])


def test_page_bound_and_duplicate_refused(source):
    for paths in [SCOPE * 2, [f'users/{UID}/conversations/{i}' for i in range(129)]]:
        with pytest.raises(ValueError, match='bounded'):
            plan(source, paths)


def test_trace_sealed_received_window_stamp_then_record_pending(source, monkeypatch):
    trace = json.loads(
        (Path(__file__).resolve().parents[2] / 'testing/record_traces/traces/orphan_sealed_registered.json').read_text()
    )
    assert trace['schema'] == 'orphan-repair-trace/1'
    source[1].rows[PATH].update(trace['row'])
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: iter(
            (span['start'], span['seconds'], [{'generation': 1, 'frames': int(span['seconds'] * 16000)}])
            for span in trace['retained_spans']
        ),
    )
    planned = plan(source)
    assert apply(source, planned) == {'registered': 1}
    assert source[1].rows[JOB]['state'] == trace['expect']['job_state']
    assert source[1].rows[PATH]['has_content'] == trace['expect']['has_content']


@pytest.mark.parametrize('expiry,expected', [(None, 'lease_unknown'), (NOW + timedelta(days=1), 'lease_active')])
def test_unknown_and_active_leases_have_no_storage_or_write_authority(source, expiry, expected):
    source[1].rows[PATH]['server_batch_audio_received'] = False
    source[1].rows[SESSION]['lease_expires_at'] = expiry
    result = plan(source)
    assert result['entries'][0]['disposition'] == expected
    repair.list_audio_chunks.assert_not_called()
    assert no_writes(source[1])


def test_job_appearing_after_storage_proof_prevents_commit(source, monkeypatch):
    result = plan(source)
    original = repair.retained_proof

    def racing(*args):
        proof = original(*args)
        source[1].rows[JOB] = {}
        return proof

    monkeypatch.setattr(repair, 'retained_proof', racing)
    assert apply(source, result) == {'already_registered': 1}
    assert source[1].rows[JOB] == {}
    assert no_writes(source[1])


def test_switch_off_during_proof_prevents_commit(source, monkeypatch):
    result = plan(source)
    original = repair.retained_proof

    def racing(*args):
        proof = original(*args)
        monkeypatch.setenv('BATCH_LIVE_ORPHAN_REPAIR_ENABLED', 'false')
        return proof

    monkeypatch.setattr(repair, 'retained_proof', racing)
    assert apply(source, result) == {'disabled': 1}
    assert no_writes(source[1])


def test_delete_empty_late_token_or_job_cannot_cross_guard(source, monkeypatch):
    source[1].rows[PATH]['server_batch_audio_received'] = False
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [])
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'delete_empty'
    original = repair.delete_empty_recording_conversation

    def racing(*args, **kwargs):
        source[1].rows[PATH]['record_upload_sessions'] = {'new': True}
        return original(*args, **kwargs)

    monkeypatch.setattr(repair, 'delete_empty_recording_conversation', racing)
    assert apply(source, result) == {'upload_pending': 1}
    assert PATH in source[1].rows
    assert no_writes(source[1])


def test_cli_refuses_before_cloud_and_errors_are_aggregate_only(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[2] / 'scripts/repair_record_orphans.py'
    spec = importlib.util.spec_from_file_location('orphan_operator_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    monkeypatch.setattr(module, 'get_firestore_client', Mock(side_effect=AssertionError('no cloud')))
    with pytest.raises(SystemExit):
        module.main(['--next-file', '/private/sensitive-cursor', '--server-flags-file', '/private/sensitive-flags'])
    report = json.loads(capsys.readouterr().out)
    assert report == {'operation': repair.OPERATION, 'outcome': 'invalid_arguments'}
    module.get_firestore_client.assert_not_called()


@pytest.mark.parametrize('shadow', [False, True])
def test_dry_run_cannot_mint_privacy_cache_tokens(source, monkeypatch, shadow):
    enabled_levers = {'bpp_owner_memo', 'bpp_token_mint'}
    if shadow:
        enabled_levers.add('privacy_checks_shadow')
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, *a: name in enabled_levers)
    monkeypatch.setattr(
        privacy,
        'lever_percent',
        lambda name, *a: 100 if shadow and name == 'privacy_checks_shadow' else 0,
    )
    mint = Mock(side_effect=AssertionError('dry-run must never mint'))
    monkeypatch.setattr(privacy, 'schedule_token_mint', mint)
    token_path = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
    assert token_path not in source[1].rows  # Exercise the missing durable-token path.
    assert plan(source)['entries'][0]['disposition'] == 'register'
    mint.assert_not_called()
    assert no_writes(source[1])
    assert token_path not in source[1].rows


def test_report_uses_retained_sample_spans_and_separates_stt_padding(source, monkeypatch):
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: (
            unit
            for unit in [
                (
                    100.0,
                    13.0,
                    [
                        {'generation': 1, 'frames': 32000, 'start_frame': 0},
                        {'generation': 2, 'frames': 48000, 'start_frame': 160000},
                    ],
                ),
            ]
        ),
    )
    report = repair.summary(plan(source))
    assert report['sealed_received_audio_seconds'] == 5.0
    assert report['sealed_received_stt_seconds'] == 13.0


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('received', [None, True])
def test_lane_owned_markerless_custody_stays_protected(quiet_store, monkeypatch, enabled, received):
    monkeypatch.setenv('QUIET_EMPTY_EXIT_ENABLED', str(enabled))
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'off')
    row = quiet_store.rows[quiet_tests.ROW]
    row.update(
        has_content=False,
        transcript_segments=[],
        record_lane_owner='batch_live_v1',
        server_batch_audio_received=received,
    )
    quiet_tests.quiet.arm('synthetic', 'old', 120, firestore_client=quiet_store)
    quiet_tests._advance(monkeypatch, 301)
    result = quiet_tests.checks.evaluate_quiet_check(
        quiet_tests.checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=quiet_store
    )
    assert result == {'status': 'done', 'reason': 'no_content'}
    assert quiet_tests.ROW in quiet_store.rows


def test_closed_received_custody_can_register_without_old_session_metadata(source):
    del source[1].rows[SESSION]
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'register'
    assert apply(source, result) == {'registered': 1}
    require_record_audio_barrier(source[1].rows[PATH])


def test_absent_owner_preference_preserves_canonical_enabled_default(source):
    del source[1].rows[('users', UID)]['private_cloud_sync_enabled']
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'register'
    assert apply(source, result) == {'registered': 1}


@pytest.mark.parametrize('refusal', ['sync_off', 'sync_null', 'deleted', 'erasing', 'protection', 'purging'])
@pytest.mark.parametrize('phase', ['plan', 'apply_register', 'apply_delete'])
def test_owner_authority_precedes_every_row_and_job_read(source, monkeypatch, refusal, phase):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    if phase == 'apply_delete':
        source[1].rows[PATH]['server_batch_audio_received'] = False
        monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [])
    approved = plan(source) if phase != 'plan' else None
    if refusal.startswith('sync_'):
        source[1].rows[('users', UID)]['private_cloud_sync_enabled'] = False if refusal == 'sync_off' else None
    elif refusal in {'deleted', 'erasing'}:
        source[1].rows[('account_deletions', UID)] = {'wipe_status': refusal}
    elif refusal == 'protection':
        source[1].rows[('users', UID)]['data_protection_level'] = 'private'
    else:
        source[1].rows[(privacy.PRIVACY_COLLECTION, privacy.privacy_owner_key(UID))] = {'purging': True}
    original = StrictFirestoreDocument.get
    forbidden = []

    def get(ref, *args, **kwargs):
        if ref.path in {PATH, JOB}:
            forbidden.append(ref.path)
            raise AssertionError('privacy-refused owner data read')
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    if phase == 'plan':
        assert repair.summary(plan(source))['dispositions'] == {'privacy_skipped': 1}
    else:
        assert apply(source, approved) == {'privacy_skipped': 1}
    assert not forbidden
    assert no_writes(source[1])


@pytest.mark.parametrize(
    'change',
    [
        {'uses_custom_stt': True},
        {'private_cloud_sync_enabled': False},
        {'private_cloud_sync_enabled': None},
        {},  # Missing capture preference refuses, unlike the owner default.
        {'data_protection_level': 'private'},
        {'data_protection_level': 'e2ee'},
    ],
)
@pytest.mark.parametrize('phase', ['plan', 'apply_register', 'apply_delete'])
def test_capture_refusal_reads_only_privacy_projection(source, monkeypatch, change, phase):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    chunks = Mock(return_value=[] if phase == 'apply_delete' else [{'generation': 1}])
    monkeypatch.setattr(repair, 'list_audio_chunks', chunks)
    if phase == 'apply_delete':
        source[1].rows[PATH]['server_batch_audio_received'] = False
    approved = plan(source) if phase != 'plan' else None
    source[1].rows[PATH].update(change)
    if not change:
        del source[1].rows[PATH]['private_cloud_sync_enabled']
    chunks.reset_mock()
    original = StrictFirestoreDocument.get
    reads = []

    def get(ref, *args, **kwargs):
        fields = kwargs.get('field_paths')
        reads.append((ref.path, fields))
        if ref.path in {PATH, JOB}:
            assert ref.path == PATH
            assert fields == ['uses_custom_stt', 'private_cloud_sync_enabled', 'data_protection_level']
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    if phase == 'plan':
        assert repair.summary(plan(source))['dispositions'] == {'privacy_skipped': 1}
    else:
        assert apply(source, approved) == {'privacy_skipped': 1}
    assert [(path, fields) for path, fields in reads if path in {PATH, JOB}] == [
        (PATH, list(repair.CAPTURE_PRIVACY_FIELDS))
    ]
    chunks.assert_not_called()
    assert no_writes(source[1])


@pytest.mark.parametrize('phase', ['proof', 'registration'])
def test_later_authorization_checks_capture_projection_before_full_reads(source, monkeypatch, phase):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    chunks = Mock(side_effect=AssertionError('storage read before capture authority'))
    monkeypatch.setattr(repair, 'list_audio_chunks', chunks)
    source[1].rows[PATH]['uses_custom_stt'] = True
    original = StrictFirestoreDocument.get
    reads = []

    def get(ref, *args, **kwargs):
        if ref.path in {PATH, JOB}:
            reads.append((ref.path, kwargs.get('field_paths')))
            assert ref.path == PATH and kwargs.get('field_paths') == list(repair.CAPTURE_PRIVACY_FIELDS)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    with pytest.raises(privacy.BatchPrivacyBlocked):
        if phase == 'proof':
            repair.retained_proof(source[0], UID, CID, 0, object(), source[2])
        else:
            source[0].run(lambda tx: repair.RegistrationReads(tx, UID, CID))
    assert reads == [(PATH, list(repair.CAPTURE_PRIVACY_FIELDS))]
    chunks.assert_not_called()
    assert no_writes(source[1])


def test_discovery_requests_identity_only_projection():
    client = Mock()
    query = client.collection_group.return_value
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    query.stream.return_value = [SimpleNamespace(reference=SimpleNamespace(path=SCOPE[0]))]
    assert repair.discover(client, limit=128) == (SCOPE, SCOPE[0])
    client.collection_group.assert_called_once_with('conversations')
    query.select.assert_called_once_with(())
    query.limit.assert_called_once_with(128)


def test_delete_commit_guard_authorizes_before_helper_row_read(source, monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    source[1].rows[PATH]['server_batch_audio_received'] = False
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [])
    approved = plan(source)
    original_delete = repair.delete_empty_recording_conversation
    original_get = StrictFirestoreDocument.get
    forbidden = []

    def racing(*args, **kwargs):
        source[1].rows[('users', UID)]['private_cloud_sync_enabled'] = False
        return original_delete(*args, **kwargs)

    def get(ref, *args, **kwargs):
        if ref.path in {PATH, JOB} and not source[1].rows[('users', UID)]['private_cloud_sync_enabled']:
            forbidden.append(ref.path)
            raise AssertionError('helper read before owner authority')
        return original_get(ref, *args, **kwargs)

    monkeypatch.setattr(repair, 'delete_empty_recording_conversation', racing)
    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    assert apply(source, approved) == {'privacy_skipped': 1}
    assert not forbidden
    assert no_writes(source[1])


@pytest.mark.parametrize('next_file', [False, True])
def test_cli_dry_run_only_writes_explicit_private_cursor(source, monkeypatch, tmp_path, capsys, next_file):
    spec = importlib.util.spec_from_file_location(
        'orphan_cli_cursor', Path(__file__).parents[2] / 'scripts/repair_record_orphans.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(module, 'get_firestore_client', lambda: source[1])
    monkeypatch.setattr(
        module, 'FirestoreStore', lambda namespace, **kw: FirestoreStore(namespace, firestore_client=source[1])
    )
    monkeypatch.setattr(module, 'create_storage_client', object)
    monkeypatch.setattr(module, 'artifacts_for', lambda _: source[2])
    monkeypatch.setattr(module, 'read_server_flags', lambda _: FLAGS)
    monkeypatch.setattr(module, 'discover', lambda *a, **kw: (SCOPE, SCOPE[0]))
    writes = []

    def write(path, after):
        writes.append(path)
        Path(path).write_text(json.dumps({'after': after}))

    monkeypatch.setattr(module, 'write_cursor', write)
    argv = ['--server-flags-file', str(tmp_path / 'flags.json')]
    if next_file:
        argv += ['--next-file', str(tmp_path / 'next.json')]
    module.main(argv)
    report = json.loads(capsys.readouterr().out)
    assert report['apply'] is False
    assert report['dispositions'] == {'register': 1}
    assert len(writes) == int(next_file)
    assert list(tmp_path.iterdir()) == ([tmp_path / 'next.json'] if next_file else [])
    assert all(secret not in json.dumps(report) for secret in (UID, CID))
    assert no_writes(source[1])
