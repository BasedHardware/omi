"""Routing transitions under strict Firestore read-before-write semantics."""

from dataclasses import replace
import os
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from database import pinecone_partition_state as state
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction


@pytest.fixture
def db(monkeypatch):
    client = StrictFirestore()

    # Narrow delete extension, proved by the real-emulator completion test below.
    # Preserve the fixture's reference ownership and read-before-write checks.
    def delete(transaction, ref):
        transaction._assert_reference_belongs(ref)
        transaction.has_written = True
        transaction._database.rows.pop(ref.path, None)

    monkeypatch.setattr(StrictFirestoreTransaction, 'delete', delete)
    for name in (
        '_register_missing_route',
        '_begin_mutation',
        '_finish_mutation',
        '_mark_mutation_uncertain',
        '_reconcile_mutation',
        '_begin_migration',
        '_cancel_migration',
        '_cutover',
    ):
        monkeypatch.setattr(state, name, getattr(state, name).to_wrap)
    return client


@pytest.fixture
def key():
    return state.PartitionKey('test-index', 'ns2', 'test-owner')


def receipt(key, route, **changes):
    value = {
        'passed': True,
        'freshness_verified': True,
        'key_id': key.document_id,
        'migration_token': route.migration_token,
        'revision': route.revision,
        'source_namespace': route.source_namespace,
        'target_namespace': route.target_namespace,
        'receipt_id': uuid4().hex,
        'source_indexed_lsn': max(100, route.latest_write_lsn),
        'source_barrier_lsn': max(100, route.latest_write_lsn),
        'target_write_lsn': 7,
        'target_indexed_lsn': 7,
    }
    value.update(changes)
    return value


def switch(key, route, db, **changes):
    return state.cutover(
        key, route.migration_token, route.revision, receipt(key, route, **changes), firestore_client=db
    )


def test_absent_route_is_legacy_and_reads_are_not_cached(db, key):
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family
    route = state.begin_migration(key, 'migration', firestore_client=db)
    switch(key, route, db)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.partition_namespace


def test_first_read_registers_owner_but_existing_reads_do_not_write(db, key):
    route = state.get_route(key, firestore_client=db)
    document = db.collection(state.COLLECTION).document(key.document_id)
    assert document.get().exists
    assert document.get().to_dict()['mode'] == 'legacy'
    assert route.revision == 0
    transactions_after_registration = len(db.transactions)
    saved_row = document.get().to_dict()
    for _ in range(3):
        assert state.get_route(key, firestore_client=db) == route
    assert len(db.transactions) == transactions_after_registration
    assert document.get().to_dict() == saved_row


@pytest.mark.parametrize('transition', ['mutation', 'cutover'])
def test_read_registration_rereads_after_concurrent_route_creation(db, key, monkeypatch, transition):
    register = state._register_missing_route

    def concurrent_creation(transaction, ref, requested_key):
        if transition == 'mutation':
            state.begin_mutation(key, affected_ids=['new-vector'], firestore_client=db)
        else:
            route = state.begin_migration(key, 'migration', firestore_client=db)
            switch(key, route, db)
        return register(transaction, ref, requested_key)

    monkeypatch.setattr(state, '_register_missing_route', concurrent_creation)
    route = state.get_route(key, firestore_client=db)
    if transition == 'mutation':
        assert route.pending_count == 1
        assert route.revision == 1
    else:
        assert route.mode == 'partitioned'
        assert route.primary_namespace == key.partition_namespace


def test_namespace_bucket_count_is_bounded_and_identity_scopes_index_family_owner():
    keys = [state.PartitionKey('test-index', 'ns1', f'owner-{i}') for i in range(10_000)]
    assert len({key.partition_namespace for key in keys}) == 256
    assert len({key.document_id for key in keys}) == 10_000
    original = keys[0]
    assert original.document_id != replace(original, index_name='other-index').document_id
    assert original.document_id != replace(original, family='ns2').document_id


def test_mutation_admission_before_migration_blocks_it_and_never_expires(db, key):
    ticket = state.begin_mutation(key, affected_ids=['vector-a'], firestore_client=db)
    for _ in range(3):
        with pytest.raises(state.PartitionBusy):
            state.begin_migration(key, 'migration', firestore_client=db)
        assert state.get_route(key, firestore_client=db).pending_count == 1
    state.finish_mutation(key, ticket, write_lsn=42, firestore_client=db)
    route = state.begin_migration(key, 'migration', firestore_client=db)
    assert route.latest_write_lsn == 42
    assert route.primary_namespace == key.family


def test_dirty_scope_retained_after_ack_and_finish_is_idempotent(db, key):
    state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, affected_ids=['old-id', 'new-id'], firestore_client=db)
    route = state.finish_mutation(key, ticket, write_lsn=10, firestore_client=db)
    assert route.pending_count == 0
    assert state.finish_mutation(key, ticket, write_lsn=10, firestore_client=db) == route
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    expected = {
        'revision': ticket.revision,
        'primary_namespace': key.family,
        'migration_token': 'migration',
        'affected_ids': ['new-id', 'old-id'],
        'full_owner': False,
        'status': 'completed',
    }
    assert {key: operation.get().to_dict()[key] for key in expected} == expected
    with pytest.raises(state.PartitionConflict):
        state.begin_mutation(key, affected_ids=['different-id'], operation_id=ticket.token, firestore_client=db)


def test_unknown_scope_must_explicitly_reconcile_full_owner(db, key):
    with pytest.raises(ValueError):
        state.begin_mutation(key, firestore_client=db)
    state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    assert operation.get().to_dict()['full_owner'] is True
    assert state.get_route(key, firestore_client=db).pending_count == 1


def test_activity_after_parity_invalidates_receipt_even_if_acknowledged(db, key):
    parity_route = state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, affected_ids=['vector-a'], firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        switch(key, parity_route, db)
    pending_route = state.get_route(key, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        switch(key, pending_route, db)
    finished = state.finish_mutation(key, ticket, write_lsn=8, firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        switch(key, parity_route, db)
    assert finished.revision == parity_route.revision + 2


def test_cutover_first_routes_following_mutation_only_to_new_primary(db, key):
    route = state.begin_migration(key, 'migration', firestore_client=db)
    switch(key, route, db)
    ticket = state.begin_mutation(key, affected_ids=['vector-a'], firestore_client=db)
    assert ticket.primary_namespace == key.partition_namespace
    assert ticket.migration_token is None


def test_failed_or_unknown_provider_outcome_stays_pending_without_cleanup(db, key):
    route = state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    # The adapter intentionally never calls finish after provider timeout.
    route = state.get_route(key, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        switch(key, route, db)
    with pytest.raises(state.PartitionBusy):
        state.begin_mutation(key, full_owner=True, operation_id=ticket.token, firestore_client=db)
    assert state.get_route(key, firestore_client=db).pending_count == 1


def test_pending_capacity_is_bounded_without_discarding_unknown_operations(db, key, monkeypatch):
    monkeypatch.setattr(state, 'MAX_PENDING', 2)
    for _ in range(2):
        state.begin_mutation(key, full_owner=True, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        state.begin_mutation(key, full_owner=True, firestore_client=db)
    assert state.get_route(key, firestore_client=db).pending_count == 2


def test_uncertain_operation_releases_capacity_but_permanently_blocks_migration(db, key, monkeypatch):
    monkeypatch.setattr(state, 'MAX_PENDING', 1)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    uncertain = state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    assert uncertain.pending_count == 0
    assert uncertain.uncertain_count == 1
    assert state.mark_mutation_uncertain(key, ticket, firestore_client=db) == uncertain
    second = state.begin_mutation(key, affected_ids=['second-vector'], firestore_client=db)
    state.finish_mutation(key, second, write_lsn=20, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        state.begin_migration(key, 'migration', firestore_client=db)
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    assert operation.get().to_dict()['status'] == 'uncertain'


def test_uncertain_copying_operation_retains_dirty_scope_and_blocks_cutover(db, key):
    state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, affected_ids=['deleted-vector'], firestore_client=db)
    route = state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    assert operation.get().to_dict()['affected_ids'] == ['deleted-vector']
    with pytest.raises(state.PartitionBusy):
        switch(key, route, db)


def test_cross_owner_ticket_and_corrupt_route_fail_closed(db, key):
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        state.finish_mutation(replace(key, uid='other-owner'), ticket, firestore_client=db)
    ref = db.collection(state.COLLECTION).document(key.document_id)
    db.rows[ref.path]['primary_namespace'] = 'another-owners-namespace'
    with pytest.raises(state.PartitionStateError):
        state.get_route(key, firestore_client=db)


@pytest.mark.parametrize(
    'changes',
    [
        {'passed': False},
        {'freshness_verified': False},
        {'key_id': 'other-key'},
        {'revision': 1000},
        {'migration_token': 'other-run'},
        {'source_namespace': 'wrong-source'},
        {'target_namespace': 'wrong-target'},
        {'receipt_id': ''},
        {'source_barrier_lsn': None},
        {'source_indexed_lsn': 0},
        {'target_indexed_lsn': 6},
    ],
)
def test_cutover_requires_matching_complete_freshness_receipt(db, key, changes):
    route = state.begin_migration(key, 'migration', firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        switch(key, route, db, **changes)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_lsn_fence_monotonic_with_out_of_order_completions(db, key):
    first = state.begin_mutation(key, affected_ids=['a'], firestore_client=db)
    second = state.begin_mutation(key, affected_ids=['b'], firestore_client=db)
    state.finish_mutation(key, second, write_lsn=200, firestore_client=db)
    state.finish_mutation(key, first, write_lsn=100, firestore_client=db)
    route = state.begin_migration(key, 'migration', firestore_client=db)
    assert route.latest_write_lsn == 200
    with pytest.raises(state.PartitionConflict):
        switch(key, route, db, source_indexed_lsn=199)
    switched = switch(key, route, db)
    assert switched.latest_write_lsn == 7
    assert switched.unknown_freshness is False


def test_missing_lsn_ack_requires_new_source_barrier(db, key):
    route = state.begin_migration(key, 'migration', firestore_client=db)
    switch(key, route, db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    state.finish_mutation(key, ticket, firestore_client=db)
    route = state.begin_rollback(key, 'rollback', firestore_client=db)
    assert route.unknown_freshness is True
    with pytest.raises(state.PartitionConflict):
        switch(key, route, db, source_barrier_lsn=None)


def test_rollback_is_reverified_migration_from_current_primary(db, key):
    route = state.begin_migration(key, 'forward', firestore_client=db)
    switch(key, route, db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        state.begin_rollback(key, 'rollback', firestore_client=db)
    state.finish_mutation(key, ticket, write_lsn=20, firestore_client=db)
    rollback = state.begin_rollback(key, 'rollback', firestore_client=db)
    assert rollback.primary_namespace == key.partition_namespace
    assert rollback.target_namespace == key.family
    assert state.begin_rollback(key, 'rollback', firestore_client=db) == rollback
    with pytest.raises(state.PartitionBusy):
        state.begin_migration(key, 'stolen-run', firestore_client=db)
    assert switch(key, rollback, db).primary_namespace == key.family


def test_cancel_invalidates_generation_and_preserves_primary(db, key):
    route = state.begin_migration(key, 'forward', firestore_client=db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        state.cancel_migration(key, 'forward', firestore_client=db)
    state.finish_mutation(key, ticket, write_lsn=42, firestore_client=db)
    cancelled = state.cancel_migration(key, 'forward', firestore_client=db)
    assert cancelled.mode == 'legacy'
    assert cancelled.primary_namespace == key.family
    assert cancelled.revision > route.revision
    with pytest.raises(state.PartitionConflict):
        switch(key, route, db)
    next_route = state.begin_migration(key, 'second-run', firestore_client=db)
    switch(key, next_route, db)
    state.begin_rollback(key, 'rollback', firestore_client=db)
    assert state.cancel_migration(key, 'rollback', firestore_client=db).mode == 'partitioned'


@pytest.mark.parametrize(
    'status', ['pending_deletion', 'pending', 'running', 'completed', 'failed', '', None, 'unknown']
)
def test_account_deletion_marker_blocks_new_or_resumed_migration(db, key, status):
    ref = db.collection('account_deletions').document(key.uid)
    ref.create({'wipe_status': status})
    with pytest.raises(state.PartitionBusy, match='account deletion'):
        state.begin_migration(key, 'migration', firestore_client=db)
    assert state.get_route(key, firestore_client=db).mode == 'legacy'


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_account_restoration_status_allows_migration(db, key, status):
    db.collection('account_deletions').document(key.uid).create({'wipe_status': status})
    assert state.begin_migration(key, 'migration', firestore_client=db).mode == 'copying'


def test_deletion_blocks_same_token_resume_and_rollback(db, key):
    route = state.begin_migration(key, 'migration', firestore_client=db)
    deletion = db.collection('account_deletions').document(key.uid)
    deletion.create({'wipe_status': 'pending_deletion'})
    with pytest.raises(state.PartitionBusy, match='account deletion'):
        state.begin_migration(key, 'migration', firestore_client=db)
    state.cancel_migration(key, 'migration', firestore_client=db)
    with pytest.raises(state.PartitionBusy, match='account deletion'):
        state.begin_migration(key, 'new-token', firestore_client=db)
    # Restore, migrate, then delete: reverse migrations must obey the same fence.
    db.rows[deletion.path] = {'wipe_status': 'cancelled'}
    route = state.begin_migration(key, 'new-token', firestore_client=db)
    switch(key, route, db)
    db.rows[deletion.path] = {'wipe_status': 'pending_deletion'}
    with pytest.raises(state.PartitionBusy, match='account deletion'):
        state.begin_rollback(key, 'rollback', firestore_client=db)


def test_cancellation_preserves_uncertain_operations(db, key):
    state.begin_migration(key, 'migration', firestore_client=db)
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    cancelled = state.cancel_migration(key, 'migration', firestore_client=db)
    assert cancelled.mode == 'legacy'
    assert cancelled.pending_count == 0
    assert cancelled.uncertain_count == 1
    with pytest.raises(state.PartitionBusy):
        state.begin_migration(key, 'new-migration', firestore_client=db)


def recovery_receipt(db, key, ticket, *, disposition='applied'):
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    admitted = operation.get().to_dict()
    return {
        'key_id': key.document_id,
        'operation_id': ticket.token,
        'operation_kind': admitted['operation_kind'],
        'admission_revision': admitted['revision'],
        'revision': state.get_route(key, firestore_client=db).revision,
        'scope_digest': admitted['scope_digest'],
        'receipt_id': uuid4().hex,
        'reconciliation': {
            'authoritative_reconciled': True,
            'scope_digest': admitted['scope_digest'],
            'artifact_ref': '/synthetic-proof/authoritative-reconciliation.json',
            'artifact_sha256': 'a' * 64,
        },
        'provider_outcomes': [
            {
                'namespace': namespace,
                'disposition': disposition,
                'request_id': f'provider-confirmed-request-{i}',
                'original_request_settled': True,
                'write_lsn': 100 + i,
                'indexed_lsn': 100 + i,
                'http_status': 400,
                'no_mutation': True,
                'artifact_ref': f'/synthetic-proof/provider-request-{i}.json',
                'artifact_sha256': 'b' * 64,
            }
            for i, namespace in enumerate(admitted['attempted_namespaces'])
        ],
    }


def uncertain_delete(db, key):
    ticket = state.begin_mutation(
        key,
        full_owner=True,
        operation_kind='delete',
        attempted_namespaces=[key.family, key.partition_namespace],
        filter_digest='c' * 64,
        firestore_client=db,
    )
    state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    return ticket


@pytest.mark.parametrize('disposition', ['applied', 'rejected'])
def test_settled_provider_evidence_recovers_uncertainty_without_expiry(db, key, disposition):
    ticket = uncertain_delete(db, key)
    proof = recovery_receipt(db, key, ticket, disposition=disposition)
    route = state.reconcile_mutation(key, ticket.token, proof['revision'], proof, firestore_client=db)
    assert route.uncertain_count == 0
    assert route.pending_count == 0
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    assert operation.get().to_dict()['recovery_receipt'] == proof
    assert operation.get().to_dict()['status'] == 'reconciled'
    assert state.begin_migration(key, 'after-recovery', firestore_client=db).mode == 'copying'


def test_crashed_pending_operation_can_only_recover_with_settled_provider_trace(db, key):
    ticket = state.begin_mutation(
        key,
        affected_ids=['exact-vector'],
        operation_kind='upsert',
        firestore_client=db,
    )
    proof = recovery_receipt(db, key, ticket)
    recovered = state.reconcile_mutation(key, ticket.token, proof['revision'], proof, firestore_client=db)
    assert recovered.pending_count == 0
    assert recovered.latest_write_lsn == 100
    with pytest.raises(state.PartitionConflict):
        state.reconcile_mutation(key, ticket.token, recovered.revision, proof, firestore_client=db)


@pytest.mark.parametrize(
    'damage',
    [
        'missing_namespace',
        'missing_lsn',
        'not_indexed',
        'missing_request_id',
        'original_unknown',
        'missing_artifact',
        'wrong_scope',
        'boolean_only',
        'timeout',
        'uncertain_500',
        'stale_receipt',
    ],
)
def test_unproven_recovery_never_clears_uncertainty(db, key, damage):
    ticket = uncertain_delete(db, key)
    proof = recovery_receipt(db, key, ticket)
    if damage == 'missing_namespace':
        proof['provider_outcomes'].pop()
    elif damage == 'missing_lsn':
        proof['provider_outcomes'][0].pop('write_lsn')
    elif damage == 'not_indexed':
        proof['provider_outcomes'][0]['indexed_lsn'] = 99
    elif damage == 'missing_request_id':
        proof['provider_outcomes'][0].pop('request_id')
    elif damage == 'original_unknown':
        proof['provider_outcomes'][0]['original_request_settled'] = False
    elif damage == 'missing_artifact':
        proof['provider_outcomes'][0].pop('artifact_sha256')
    elif damage == 'wrong_scope':
        proof['reconciliation']['scope_digest'] = 'd' * 64
    elif damage == 'boolean_only':
        proof['provider_outcomes'] = [True, True]
    elif damage == 'timeout':
        proof['provider_outcomes'][0]['disposition'] = 'timeout'
    elif damage == 'uncertain_500':
        proof['provider_outcomes'][0].update(disposition='rejected', http_status=500)
    elif damage == 'stale_receipt':
        proof['revision'] -= 1
    current = state.get_route(key, firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        state.reconcile_mutation(key, ticket.token, current.revision, proof, firestore_client=db)
    assert state.get_route(key, firestore_client=db) == current


def test_recovery_cas_and_other_pending_operation_protect_current_writes(db, key):
    ticket = uncertain_delete(db, key)
    stale = recovery_receipt(db, key, ticket)
    other = state.begin_mutation(key, affected_ids=['new-vector'], operation_kind='upsert', firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        state.reconcile_mutation(key, ticket.token, stale['revision'], stale, firestore_client=db)
    current_proof = recovery_receipt(db, key, ticket)
    with pytest.raises(state.PartitionBusy):
        state.reconcile_mutation(key, ticket.token, current_proof['revision'], current_proof, firestore_client=db)
    state.finish_mutation(key, other, write_lsn=500, firestore_client=db)
    current_proof = recovery_receipt(db, key, ticket)
    recovered = state.reconcile_mutation(
        key, ticket.token, current_proof['revision'], current_proof, firestore_client=db
    )
    assert recovered.latest_write_lsn == 500


def test_unknown_operation_kind_cannot_be_recovered_from_guesses(db, key):
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    proof = recovery_receipt(db, key, ticket)
    with pytest.raises(state.PartitionConflict):
        state.reconcile_mutation(key, ticket.token, proof['revision'], proof, firestore_client=db)


def test_completed_normal_mutations_do_not_accumulate_journal_rows(db, key):
    ticket = state.begin_mutation(key, affected_ids=['exact-vector'], operation_kind='upsert', firestore_client=db)
    operation = (
        db.collection(state.COLLECTION).document(key.document_id).collection('operations').document(ticket.token)
    )
    assert operation.get().exists
    state.finish_mutation(key, ticket, write_lsn=10, firestore_client=db)
    assert not operation.get().exists


@pytest.mark.integration
def test_real_firestore_mutation_cutover_contention():
    """Optional real transaction proof; strict fixture cannot model contention."""
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('set FIRESTORE_EMULATOR_HOST for the real transaction race')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('contention proof requires a loopback emulator')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    client = firestore.Client(project='demo-pinecone-partition-state', credentials=AnonymousCredentials())
    try:
        for _ in range(3):
            key = state.PartitionKey('test-index', 'ns2', uuid4().hex)
            route = state.begin_migration(key, uuid4().hex, firestore_client=client)
            barrier = Barrier(2)

            def admit():
                barrier.wait(timeout=10)
                return state.begin_mutation(key, full_owner=True, firestore_client=client)

            def migrate():
                barrier.wait(timeout=10)
                try:
                    return switch(key, route, client)
                except (state.PartitionBusy, state.PartitionConflict):
                    return None

            with ThreadPoolExecutor(max_workers=2) as executor:
                mutation = executor.submit(admit)
                cutover = executor.submit(migrate)
                ticket, result = mutation.result(timeout=30), cutover.result(timeout=30)
            current = state.get_route(key, firestore_client=client)
            assert current.pending_count == 1
            assert ticket.primary_namespace == current.primary_namespace
            assert (result is None) == (current.mode == 'copying')
            state.finish_mutation(key, ticket, write_lsn=10, firestore_client=client)
    finally:
        client.close()


@pytest.mark.integration
def test_real_firestore_deletion_marker_migration_contention():
    """A migration may commit before deletion, but never after its marker wins."""
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('set FIRESTORE_EMULATOR_HOST for the real transaction race')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('contention proof requires a loopback emulator')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    client = firestore.Client(project='demo-pinecone-partition-state', credentials=AnonymousCredentials())
    try:
        for _ in range(3):
            key = state.PartitionKey('test-index', 'ns2', uuid4().hex)
            barrier = Barrier(2)
            marker = client.collection('account_deletions').document(key.uid)

            def delete_account():
                barrier.wait(timeout=10)
                return marker.set({'wipe_status': 'pending_deletion'})

            def migrate():
                barrier.wait(timeout=10)
                try:
                    return state.begin_migration(key, 'migration', firestore_client=client)
                except state.PartitionBusy:
                    return None

            with ThreadPoolExecutor(max_workers=2) as executor:
                deletion = executor.submit(delete_account)
                migration = executor.submit(migrate)
                deleted, migrated = deletion.result(timeout=30), migration.result(timeout=30)
            if migrated is not None:
                snapshot = client.collection(state.COLLECTION).document(key.document_id).get()
                assert snapshot.update_time <= deleted.update_time
                state.cancel_migration(key, 'migration', firestore_client=client)
            assert state.get_route(key, firestore_client=client).mode == 'legacy'
            with pytest.raises(state.PartitionBusy, match='account deletion'):
                state.begin_migration(key, 'later-migration', firestore_client=client)
    finally:
        client.close()


@pytest.mark.integration
def test_real_firestore_completion_deletes_only_completed_normal_operation():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('set FIRESTORE_EMULATOR_HOST for journal cleanup proof')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('journal proof requires a loopback emulator')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    client = firestore.Client(project='demo-pinecone-partition-state', credentials=AnonymousCredentials())
    try:
        key = state.PartitionKey('test-index', 'ns2', uuid4().hex)
        ticket = state.begin_mutation(
            key, affected_ids=['exact-vector'], operation_kind='upsert', firestore_client=client
        )
        operation = (
            client.collection(state.COLLECTION)
            .document(key.document_id)
            .collection('operations')
            .document(ticket.token)
        )
        assert operation.get().exists
        state.finish_mutation(key, ticket, write_lsn=10, firestore_client=client)
        assert not operation.get().exists
        assert state.get_route(key, firestore_client=client).pending_count == 0
        uncertain = uncertain_delete(client, key)
        proof = recovery_receipt(client, key, uncertain)
        route = state.reconcile_mutation(key, uncertain.token, proof['revision'], proof, firestore_client=client)
        assert route.uncertain_count == 0
        recovered = (
            client.collection(state.COLLECTION)
            .document(key.document_id)
            .collection('operations')
            .document(uncertain.token)
        )
        assert recovered.get().to_dict()['status'] == 'reconciled'
    finally:
        client.close()


@pytest.mark.integration
def test_real_firestore_first_read_never_reverts_concurrent_cutover():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('set FIRESTORE_EMULATOR_HOST for registration contention proof')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('registration proof requires a loopback emulator')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    client = firestore.Client(project='demo-pinecone-partition-state', credentials=AnonymousCredentials())
    try:
        for _ in range(3):
            key = state.PartitionKey('test-index', 'ns2', uuid4().hex)
            barrier = Barrier(2)

            def first_read():
                barrier.wait(timeout=10)
                return state.get_route(key, firestore_client=client)

            def migrate():
                barrier.wait(timeout=10)
                route = state.begin_migration(key, 'migration', firestore_client=client)
                return switch(key, route, client)

            with ThreadPoolExecutor(max_workers=2) as executor:
                read, migration = executor.submit(first_read), executor.submit(migrate)
                read.result(timeout=30)
                changed = migration.result(timeout=30)
            assert changed.mode == 'partitioned'
            assert state.get_route(key, firestore_client=client) == changed
    finally:
        client.close()
