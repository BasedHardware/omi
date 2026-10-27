"""Real writer + atomic token proof; explicitly run against a loopback emulator.

No cloud fallback. Outer conversation encryption/cache decorators are bypassed
only in the lifecycle-body cases; the actual transactional persistence owners,
SDK encoding, Commit hooks, and server atomicity are exercised.
"""

from copy import deepcopy
from datetime import datetime, timezone
import inspect
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def world(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('explicit loopback Firestore emulator required')
    assert host.startswith(('127.0.0.1:', 'localhost:')), 'no cloud fallback'
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from google.cloud.firestore_v1.types import CommitRequest
    from database import _client, batch_pipeline_privacy as privacy, batch_privacy_write_fence as fence
    from database import conversations, users, account_deletion_marker, recording_sessions

    client = firestore.Client(project='demo-wq26', credentials=AnonymousCredentials())
    uid = 'wq26-' + uuid4().hex
    user = client.document(f'users/{uid}')
    source = user.collection('conversations').document('source')
    token = client.document(f'batch_pipeline_privacy/{privacy.privacy_owner_key(uid)}')
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(account_deletion_marker, 'get_data_plane_firestore_client', lambda: client)
    for module in (users, conversations):
        monkeypatch.setattr(module, 'db', client)
    for module in (conversations, recording_sessions):
        monkeypatch.setattr(module, 'invalidate_people_stats_cache', lambda *a, **k: None)
        monkeypatch.setattr(module, 'stop_quiet_check_for_conversation', lambda *a, **k: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a, **k: None)
    monkeypatch.setattr(conversations, '_delete_conversation_search_index', lambda *a, **k: None)
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, uid: name == 'bpp_generation_memo')
    user.set({'data_protection_level': 'standard', 'private_cloud_sync_enabled': True})
    source.set({'id': 'source', 'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True})
    token.set({'generation': 7}, merge=True)
    requests = []
    transport = client._firestore_api._transport
    original = transport._wrapped_methods[transport.commit]

    def capture(request, **kwargs):
        requests.append(CommitRequest(request))
        return original(request, **kwargs)

    monkeypatch.setitem(transport._wrapped_methods, transport.commit, capture)

    def check():
        @firestore.transactional
        def authorize(tx):
            return privacy.assert_batch_write_allowed(
                client, tx, uid, conversation_ids=['source'], expected_generation=7
            )

        return authorize(client.transaction())

    yield SimpleNamespace(
        client=client,
        uid=uid,
        user=user,
        source=source,
        token=token,
        check=check,
        requests=requests,
        privacy=privacy,
        fence=fence,
        conversations=conversations,
        users=users,
    )
    client.close()  # Unique synthetic owners live only in this disposable emulator.


WRITERS = [
    'consent',
    'retraction',
    'tombstone',
    'protection_start',
    'migration_start',
    'migration_complete',
    'lifecycle_upsert',
    'lifecycle_result',
    'lifecycle_create',
    'lifecycle_create_waiting',
    'generic_patch',
    'ownership_cas',
    'account_marker_create',
    'account_marker_complete',
    'account_marker_late_cleanup',
    'sync_merge',
    'smart_merge',
    'recording_delete',
    'hard_delete',
    'legal_hold',
    'legal_gate',
    'epoch_advance',
    'purge_finish',
    'admission_ownership',
]


@pytest.mark.parametrize('writer', WRITERS)
def test_actual_writer_rotates_token_in_source_commit_and_revalidates(world, monkeypatch, writer):
    from google.cloud import firestore
    from database import speaker_auto_enroll, conversation_tombstones, from_segments_chunks, batch_pipeline_purge
    from database import account_deletion_transitions, legal_holds, recording_sessions, smart_merge
    from database.batch_privacy_attempt import batch_privacy_attempt
    from utils.sync.assignment import assign_in_transaction

    w = world
    denial = None
    # Establish the before-state without counting setup commits as writer proof.
    if writer.startswith('lifecycle_create'):
        w.source.delete()
    if writer in {'ownership_cas', 'admission_ownership'}:
        w.source.update({'record_lane_owner': firestore.DELETE_FIELD})
        w.user.update({'private_cloud_sync_enabled': False})
    if writer in {'account_marker_complete', 'account_marker_late_cleanup'}:
        w.client.document(f'account_deletions/{w.uid}').set({'wipe_status': 'cancelled'})
    if writer in {'recording_delete', 'hard_delete', 'sync_merge', 'smart_merge'}:
        w.source.update({'deleted': True, 'sync_merged_into': 'target'})
        w.user.collection('conversations').document('target').set({'id': 'target', 'status': 'in_progress'})
    if writer in {'sync_merge', 'smart_merge'}:
        # Merge a target into a denied survivor. A stale cached redirect walk
        # would otherwise keep allowing the source.
        w.user.collection('conversations').document('survivor').set({'id': 'survivor', 'deleted': True})
    if writer == 'smart_merge':
        w.user.collection('conversations').document('target').update({'sync_merged_from': ['ancestor']})
        w.user.collection('conversations').document('ancestor').set(
            {'id': 'ancestor', 'deleted': True, 'sync_merged_into': 'target'}
        )
    before = w.token.get().to_dict()
    w.requests.clear()
    with batch_privacy_attempt():
        assert w.check() == 7  # Warm the cross-transaction decision.
        if writer == 'consent':
            speaker_auto_enroll.update_privacy(w.uid, {'private_cloud_sync_enabled': False}, firestore_client=w.client)
            denial = 'recording_privacy_changed'
        elif writer == 'retraction':
            speaker_auto_enroll.retract_conversation(w.uid, 'source', firestore_client=w.client)
            denial = 'conversation_deleted'
        elif writer == 'tombstone':
            monkeypatch.setattr(conversation_tombstones, 'db', w.client)
            monkeypatch.setattr(from_segments_chunks, 'purge_chunks', lambda *a, **k: None)

            def failed_cleanup(*a, **k):
                raise RuntimeError('cleanup boundary')

            monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', failed_cleanup)
            with pytest.raises(RuntimeError, match='cleanup boundary'):
                conversation_tombstones.record_deletion(w.uid, 'source')
            denial = 'conversation_deleted'
        elif writer in {'protection_start', 'migration_start'}:

            def failed_purge(*a, **k):
                raise RuntimeError('purge boundary')

            monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', failed_purge)
            call = w.users.set_data_protection_level if writer == 'protection_start' else w.users.set_migration_status
            with pytest.raises(RuntimeError, match='purge boundary'):
                call(w.uid, 'e2ee')
            denial = 'data_protection_changed'
        elif writer == 'migration_complete':
            w.users.finalize_migration(w.uid, 'e2ee')
            denial = 'data_protection_changed'
        elif writer.startswith('lifecycle_'):
            payload = {'id': 'source', 'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': False}
            if writer == 'lifecycle_create_waiting':
                payload['processing_deferred'] = True
            function = {
                'lifecycle_upsert': w.conversations.upsert_conversation_with_lifecycle,
                'lifecycle_result': w.conversations.persist_processing_result_with_lifecycle,
                'lifecycle_create': w.conversations.create_conversation_if_absent_with_lifecycle,
                'lifecycle_create_waiting': w.conversations.create_conversation_if_absent_with_lifecycle,
            }[writer]
            # Keep persistence, lifecycle and backlog transactions real. Bypass
            # decorators for encryption/cache/derived notification effects.
            inspect.unwrap(function)(w.uid, payload)
            denial = 'recording_privacy_changed'
        elif writer == 'generic_patch':
            inspect.unwrap(w.conversations.update_conversation)(w.uid, 'source', {'uses_custom_stt': True})
            denial = 'recording_privacy_changed'
        elif writer == 'ownership_cas':
            revision = w.source.get().update_time
            result = w.conversations.claim_record_lane_owner(
                w.uid, 'source', 'batch_live_v1', revision, firestore_client=w.client
            )
            assert result == w.source.get().update_time and result != revision
            denial = 'recording_privacy_changed'
        elif writer == 'admission_ownership':
            from database.batch_pipeline_store import FirestoreStore

            monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
            store = FirestoreStore('batch_pipeline_dev', firestore_client=w.client)
            store.run(
                lambda view: view.patch('conversations', f'{w.uid}/source', {'record_lane_owner': 'batch_live_v1'})
            )
            denial = 'recording_privacy_changed'
        elif writer == 'account_marker_create':
            w.users.set_user_deletion_feedback(w.uid, 'synthetic', None)
            denial = 'account_deleted'
        elif writer == 'account_marker_complete':
            ref = w.client.document(f'account_deletions/{w.uid}')
            assert account_deletion_transitions.mark_wipe_completed(w.client.transaction(), ref)
            denial = 'account_deleted'
        elif writer == 'account_marker_late_cleanup':
            ref = w.client.document(f'account_deletions/{w.uid}')
            ref.update({'wipe_status': 'pending'})
            assert account_deletion_transitions.record_late_agent_vm_cleanup(w.client.transaction(), ref, 'vm', 'zone')
            denial = 'account_deleted'
        elif writer == 'recording_delete':
            assert recording_sessions.tombstone_and_delete_empty_conversation(
                w.uid, 'target', None, firestore_client=w.client
            )
            denial = 'conversation_redirect_missing'
        elif writer == 'hard_delete':
            # The SDK direct-delete surface used after delete_conversation's
            # separately exercised retraction, child cleanup and search effects.
            w.user.collection('conversations').document('target').delete()
            denial = 'conversation_redirect_missing'
        elif writer == 'sync_merge':
            incoming = {
                'id': 'incoming',
                'started_at': datetime.fromtimestamp(1000, timezone.utc),
                'finished_at': datetime.fromtimestamp(1010, timezone.utc),
                'source': 'omi',
                'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': 'Synthetic test speech.'}],
            }

            # New canonical with a dynamically encoded privacy patch.
            @firestore.transactional
            def assign(tx):
                return assign_in_transaction(
                    tx,
                    w.user,
                    incoming,
                    decode=deepcopy,
                    encode=lambda row: {**row, 'uses_custom_stt': True},
                    invalidate=lambda row: None,
                )

            assign(w.client.transaction())
        elif writer == 'smart_merge':
            target = w.user.collection('conversations').document('target')
            survivor = w.user.collection('conversations').document('survivor')
            survivor.update({'deleted': False})
            # Codec and optional audit discovery are separate from the writer.
            monkeypatch.setattr(smart_merge, '_decode_row', lambda uid, row: (row, []))
            monkeypatch.setattr(smart_merge, 'has_intervening_discarded', lambda *a, **k: False)
            monkeypatch.setattr(smart_merge, 'smart_merge_flatten_enabled', lambda: True)
            monkeypatch.setattr(smart_merge.audit_db, 'gate_skip', lambda *a, **k: 'disabled')

            def plan(*a):
                return (
                    None,
                    {'smart_merge': {'revision': 1}, 'deleted': True},
                    {'deleted': True, 'sync_merged_into': 'survivor'},
                    {'ancestor': {'sync_merged_into': 'survivor'}},
                )

            result = smart_merge.absorb_conversation(
                w.uid, 'survivor', 'target', expected_revision=0, plan=plan, firestore_client=w.client
            )
            assert result.outcome == 'absorbed'
            assert (
                w.user.collection('conversations').document('ancestor').get().to_dict()['sync_merged_into']
                == 'survivor'
            )
            denial = 'conversation_deleted'
        elif writer == 'legal_hold':
            legal_holds.place_legal_hold(w.uid, issuer='admin', firestore_client=w.client)
            with pytest.raises(legal_holds.LegalHoldActive):
                legal_holds.assert_account_deletion_permitted(w.uid, firestore_client=w.client)
        elif writer == 'legal_gate':
            legal_holds.acquire_destructive_operation(
                w.uid, kind='account_deletion', token='synthetic', firestore_client=w.client
            )
        elif writer == 'epoch_advance':
            assert w.privacy.advance_privacy_generation(w.client, w.uid, blocked=True) == 8
            denial = 'privacy_generation_changed'
        elif writer == 'purge_finish':
            w.privacy.finish_privacy_purge(w.client, w.uid, 7)
        else:
            raise AssertionError(writer)
        after = w.token.get().to_dict()
        assert after['memo_token'] != before['memo_token']
        assert after['generation'] == (8 if writer == 'epoch_advance' else 7)
        # Every source Commit must contain its token, not an earlier/later RPC.
        changing = [r for r in w.requests if w.fence.authority_tokens(r.writes)]
        assert changing
        for request in changing:
            token_paths = w.fence.authority_tokens(request.writes)
            for path in token_paths:
                assert any(
                    write.update.name == path and 'memo_token' in write.update.fields for write in request.writes
                )
        if denial:
            with pytest.raises(w.privacy.BatchPrivacyBlocked, match=denial):
                w.check()
        else:
            assert w.check() == 7  # Legal holds do not change batch authorization policy.


def test_failed_cas_rolls_back_source_and_token(world):
    from google.api_core.exceptions import FailedPrecondition
    from google.cloud import firestore

    w = world
    snapshot = w.source.get()
    before = w.token.get().to_dict()
    # A false source precondition must not rotate the appended token.
    with pytest.raises(FailedPrecondition):
        w.source.update(
            {'deleted': True}, option=w.client.write_option(last_update_time=datetime(2000, 1, 1, tzinfo=timezone.utc))
        )
    assert w.source.get().to_dict() == snapshot.to_dict()
    assert w.token.get().to_dict() == before


def test_sync_bridge_fences_canonical_and_donor_together(world):
    from google.cloud import firestore
    from utils.sync.assignment import assign_in_transaction

    w = world

    def chunk(cid, second):
        return {
            'id': cid,
            'started_at': datetime.fromtimestamp(second, timezone.utc),
            'finished_at': datetime.fromtimestamp(second + 9.5, timezone.utc),
            'source': 'omi',
            'client_device_id': 'synthetic',
            'discarded': False,
            'status': 'completed',
            'transcript_segments': [{'start': 0.0, 'end': 9.5, 'text': 'Synthetic bridge speech.', 'speaker_id': 0}],
        }

    def assign(row):
        @firestore.transactional
        def body(tx):
            return assign_in_transaction(tx, w.user, row, decode=deepcopy, encode=deepcopy, invalidate=lambda row: None)

        return body(w.client.transaction())

    assign(chunk('a', 1000))
    assign(chunk('b', 1240))
    w.requests.clear()
    before = w.token.get().to_dict()
    result, created, _ = assign(chunk('bridge', 1120))
    assert result['sync_merged_from'] and not created
    assert w.token.get().to_dict()['memo_token'] != before['memo_token']
    assert len(w.requests) == 1
    request = w.requests[0]
    paths = {write.update.name for write in request.writes}
    assert w.token._document_path in paths
    assert w.user.collection('conversations').document(result['id'])._document_path in paths
    for donor in result['sync_merged_from']:
        assert w.user.collection('conversations').document(donor)._document_path in paths
        assert w.user.collection('conversations').document(donor).get().to_dict()['sync_merged_into'] == result['id']


def test_transport_replay_cannot_restore_a_cached_token(world):
    """Replay the exact wire request, below the fence, as GAPIC Retry does."""
    from database.batch_privacy_attempt import batch_privacy_attempt

    w = world
    # A metadata upsert participates because it can also create the user.
    w.user.set({'name': 'synthetic'}, merge=True)
    prepared = w.requests[-1]
    first = w.token.get()
    with batch_privacy_attempt():
        assert w.check() == 7
        w.user.update({'private_cloud_sync_enabled': False})
        transport = w.client._firestore_api._transport
        transport._wrapped_methods[transport.commit](prepared)
        replayed = w.token.get()
        assert replayed.to_dict()['memo_token'] == first.to_dict()['memo_token']
        assert replayed.update_time != first.update_time
        # The source upsert did not revert the intervening consent denial.
        assert not w.user.get().to_dict()['private_cloud_sync_enabled']
        with pytest.raises(w.privacy.BatchPrivacyBlocked, match='recording_privacy_changed'):
            w.check()


def test_actual_nonatomic_bulk_pairs_each_authority_with_token(world):
    from google.cloud.firestore_v1.types import Write, Document

    w = world
    before = w.token.get().to_dict()
    result = w.client._firestore_api.batch_write(
        metadata=(('authorization', 'Bearer owner'),),  # Emulator-only admin identity.
        request={
            'database': w.client._database_string,
            'writes': [
                Write(
                    update=Document(name=w.source._document_path, fields={'deleted': {'boolean_value': True}}),
                    update_mask={'field_paths': ['deleted']},
                    current_document={'exists': True},
                ),
                Write(
                    delete=w.user.collection('conversations').document('missing')._document_path,
                    current_document={'exists': True},
                ),
                Write(
                    update=Document(
                        name=w.client.document('unrelated/test')._document_path, fields={'ok': {'boolean_value': True}}
                    )
                ),
            ],
        },
    )
    assert [status.code for status in result.status] == [0, 5, 0]  # Preserve server NotFound.
    assert len(result.write_results) == 3
    assert w.token.get().to_dict()['memo_token'] != before['memo_token']
    assert w.source.get().to_dict()['deleted']
    assert len(w.requests) == 2  # One atomic Commit per authority, including failed CAS.
    assert all(request.writes[-1].update.name == w.token._document_path for request in w.requests)


def test_real_account_subtree_wipe_keeps_blocked_token_outside_user_walk(world, monkeypatch):
    from database import batch_pipeline_purge, user_data_deletion
    from database._client import delete_collection_recursive
    from database.batch_privacy_attempt import batch_privacy_attempt

    w = world
    monkeypatch.setattr(batch_pipeline_purge, 'get_data_plane_firestore_client', lambda: w.client)
    monkeypatch.delenv('BUCKET_BATCH_PIPELINE', raising=False)
    with batch_privacy_attempt():
        assert w.check() == 7
        before = w.token.get().to_dict()
        # Only the cache wrapper is bypassed; erasure and both namespace scans,
        # recursive deletes, epoch advance and finish use production code.
        result = inspect.unwrap(user_data_deletion.purge_user_subtree)(w.uid, w.client, delete_collection_recursive)
        assert result['status'] == 'ok'
        assert not w.user.get().exists
        after = w.token.get().to_dict()
        assert after['generation'] == 8 and after['blocked'] and not after['purging']
        assert after['memo_token'] != before['memo_token']
        with pytest.raises(w.privacy.BatchPrivacyBlocked, match='account_missing'):
            w.check()


def test_standalone_platform_backfill_installs_fence_before_admin_client(world, monkeypatch):
    import sys
    from scripts import backfill_user_signup_platform as backfill

    w = world
    w.user.collection('fcm_tokens').document('macos_synthetic').set({'created_at': datetime.now(timezone.utc)})
    before = w.token.get().to_dict()
    w.requests.clear()
    installed = []
    install = w.fence.install_write_fence

    def record_install():
        install()
        installed.append(True)

    monkeypatch.setattr(w.fence, 'install_write_fence', record_install)
    monkeypatch.setattr(sys, 'argv', ['backfill', '--force', '--limit', '1', '--no-scan-conversations'])
    monkeypatch.setattr(backfill.fa, 'initialize_app', lambda: None)
    # Limit enumeration to this synthetic owner, retaining the real document
    # reference and writer, protobuf encoding, Commit and server behavior.
    query = SimpleNamespace()
    query.order_by = query.limit = query.start_after = lambda *a: query
    query.stream = lambda: iter([w.user.get()])

    def client():
        assert installed, 'standalone producer must install before client construction'
        return SimpleNamespace(collection=lambda name: query)

    monkeypatch.setattr(backfill.fs, 'client', client)
    backfill.main()
    assert w.user.get().to_dict()['signup_platform'] == 'desktop'
    assert w.token.get().to_dict()['memo_token'] != before['memo_token']
    assert w.token.get().to_dict()['generation'] == 7
    assert len(w.requests) == 1
    assert w.requests[0].writes[-1].update.name == w.token._document_path
