"""Seed only the before state; all replayed mutations use real privacy writers."""

from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection

from testing.replay_harness.gen_privacy_timeline import KINDS, FAULTS


def validate_rows(corpus):
    seed = corpus.get('privacy_cache')
    rows = seed.get('transitions') if isinstance(seed, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError('bounded privacy transitions required')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'family', 'kind', 'fault'}:
            raise ValueError('privacy transitions contain only family/kind/fault')
        if row['family'] not in KINDS or row['kind'] not in KINDS[row['family']] or row['fault'] not in FAULTS:
            raise ValueError('unknown privacy transition')
    return rows


def scenario(row, environment):
    from google.cloud import firestore
    from database import users, account_deletion_grace as grace, account_deletion_marker as marker
    from database import conversation_tombstones as tombstones, legal_holds as holds, batch_pipeline_privacy as bpp
    from database.fsr_read_cache import fresh_reads

    family, kind = row['family'], row['kind']
    client = environment.store.client
    uid = environment.harness.seed_user('synthetic-privacy', protection='enhanced')
    environment.harness.replay_users = [uid]
    user = client.collection('users').document(uid)
    cid, token, job = 'synthetic-conversation', 'synthetic-gate-token', 'synthetic-wipe-job'
    now = datetime.now(timezone.utc)
    refs = {
        'marker': client.collection('account_deletions').document(uid),
        'hold': client.collection(holds.LEGAL_HOLDS_COLLECTION).document(uid),
        'gate': client.collection(holds.LEGAL_HOLD_DELETION_GATES_COLLECTION).document(uid),
        'privacy': client.collection(bpp.PRIVACY_COLLECTION).document(bpp.privacy_owner_key(uid)),
    }
    environment.replay_documents = [refs[name] for name in ('marker', 'hold', 'gate')]
    # The mandatory product Commit fence forbids deleting this durable row.
    # Emulator-only REST teardown runs AFTER user/marker cleanup (those writes
    # rotate the token too), and before the client/network guard closes. Never
    # disable the writer fence while a replay transition is being exercised.
    from testing.replay_harness.env import emulator_endpoint

    endpoint = emulator_endpoint()

    def cleanup_authority():
        connection = HTTPConnection(endpoint, timeout=10)
        try:
            connection.request(
                'DELETE', '/v1/' + refs['privacy']._document_path, headers={'Authorization': 'Bearer owner'}
            )
            response = connection.getresponse()
            response.read()
            if response.status != 200:
                raise RuntimeError('emulator privacy teardown failed')
        finally:
            connection.close()

    environment.harness.cleanup_steps.append(cleanup_authority)
    # A valid durable token is essential: absent/malformed tokens make the real
    # cached tombstone/external/batch readers ineligible and prove nothing.
    refs['privacy'].set({'generation': 1, 'blocked': False, 'purging': False, 'memo_schema': 1, 'memo_token': 'a' * 32})
    user.set({'subscription': {'plan': 'basic'}, 'byok': {'active': False}}, merge=True)

    def marker_state(status, **extra):
        refs['marker'].set({'wipe_status': status, 'wipe_job_id': job, **extra})

    def gate_state(*, stale=False):
        refs['gate'].set(
            {
                'schema_version': holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
                'uid': uid,
                'kind': 'explicit_memory_deletion',
                'token': token,
                'state': 'running',
                'started_at': now - timedelta(seconds=holds.GATE_STALE_AFTER_SECONDS + 1) if stale else now,
                'finished_at': None,
            }
        )

    if family == 'deletion_marker':
        if kind in ('grace_actions_complete', 'restore', 'promote'):
            marker_state(
                'pending_deletion', grace_actions_complete=kind == 'restore', wipe_due_at=now + timedelta(days=1)
            )
        elif kind == 'wipe_started':
            marker_state('deleting_auth')
        elif kind in ('wipe_running', 'cancel', 'billing_failed'):
            marker_state('pending')
        elif kind in ('wipe_completed', 'wipe_failed'):
            marker_state('running')
        writers = {
            'grace_intent': lambda: grace.mark_user_deletion_grace_intent(uid, now + timedelta(days=1)),
            'grace_actions_complete': lambda: grace.mark_user_deletion_grace_actions_complete(uid, job),
            'restore': lambda: grace.restore_user_deletion(uid),
            'promote': lambda: grace.promote_grace_to_immediate(uid),
            'wipe_intent': lambda: users.mark_user_deletion_wipe_intent(uid),
            'wipe_started': lambda: users.mark_user_deletion_wipe_started(uid, job),
            'wipe_running': lambda: users.mark_user_deletion_wipe_running(uid),
            'wipe_completed': lambda: users.mark_user_deletion_wipe_completed(uid),
            'wipe_failed': lambda: users.mark_user_deletion_wipe_failed(uid),
            'billing_failed': lambda: users.mark_user_deletion_billing_failed(uid, None, 'synthetic'),
            'cancel': lambda: users.cancel_user_deletion_wipe(uid),
        }

        def read():
            result = {'status': marker.get_user_deletion_wipe_status(uid, firestore_client=client)}
            # Actions-complete is a metadata-only arc; observe its actual write
            # as well, without pretending the access verdict changed.
            if kind == 'grace_actions_complete':
                result['actions_complete'] = (
                    marker.read_account_deletion_marker(uid, firestore_client=client) or {}
                ).get('grace_actions_complete', False)
            return result

        write = writers[kind]
    elif family == 'tombstone':
        if kind == 'retry_after_purge':
            user.collection(tombstones.COLLECTION).document(cid).set({'conversation_id': cid})
        read = lambda: {'deleted': tombstones.is_deleted(uid, cid)}
        write = lambda: tombstones.record_deletion(uid, cid)
    elif family == 'legal_hold':
        if kind == 'release':
            refs['hold'].set({'schema_version': holds.LEGAL_HOLD_SCHEMA_VERSION, 'issuer': 'admin', 'active': True})
        if kind in ('finish', 'takeover'):
            gate_state(stale=kind == 'takeover')

        def read():
            result = {}
            try:
                with holds.external_write_fence(uid, firestore_client=client):
                    result['external'] = 'allow'
            except holds.DestructiveOperationInProgress:
                result['external'] = 'blocked'
            try:
                holds.assert_account_deletion_permitted(uid, firestore_client=client)
                result['destructive'] = 'allow'
            except holds.LegalHoldActive:
                result['destructive'] = 'blocked'
            return result

        writers = {
            'place': lambda: holds.place_legal_hold(uid, issuer='admin', firestore_client=client),
            'release': lambda: holds.place_legal_hold(uid, issuer='admin', active=False, firestore_client=client),
            'acquire': lambda: holds.acquire_destructive_operation(
                uid, kind='explicit_memory_deletion', token=token, firestore_client=client
            ),
            'finish': lambda: holds.finish_destructive_operation(
                uid, kind='explicit_memory_deletion', token=token, outcome='completed', firestore_client=client
            ),
            'takeover': lambda: holds.acquire_destructive_operation(
                uid, kind='explicit_memory_deletion', token='new-token', firestore_client=client
            ),
        }
        write = writers[kind]
    elif family == 'batch_privacy':
        if kind == 'finish':
            refs['privacy'].set({'generation': 1, 'purging': True}, merge=True)

        def read():
            @firestore.transactional
            def check(transaction):
                def guard(ids):
                    try:
                        return {
                            'generation': bpp.assert_batch_write_allowed(
                                client, transaction, uid, conversation_ids=ids
                            ),
                            'decision': 'allow',
                        }
                    except bpp.BatchPrivacyBlocked as error:
                        return {'decision': error.reason.value}

                first = guard(())
                # Distinct generation-memo keys force both authority walks on
                # cold attempts. Each guard must independently walk live authority,
                # including blocked decisions.
                second = guard((cid,))
                if second != first:
                    raise AssertionError('same-transaction batch guards disagree')
                return first

            return check(client.transaction())

        write = (
            (lambda: bpp.finish_privacy_purge(client, uid, 1))
            if kind == 'finish'
            else (lambda: bpp.advance_privacy_generation(client, uid, blocked=kind == 'block'))
        )
    elif family == 'subscription':
        if kind.startswith('byok'):
            user.set({'byok': {'active': kind == 'byok_disable'}}, merge=True)
            read = lambda: {'active': bool(users.get_byok_state(uid, firestore_client=client).get('active'))}
            write = (
                (lambda: users.clear_byok_active(uid))
                if kind == 'byok_disable'
                else (lambda: users.set_byok_active(uid, {'synthetic': 'a' * 64}))
            )
        else:
            user.update({'subscription': {'plan': 'unlimited' if kind == 'downgrade' else 'basic'}})
            read = lambda: {
                'plan': users.get_user_subscription(uid, firestore_client=client, read_only=True).plan.value
            }
            write = lambda: users.update_user_subscription(
                uid, {'plan': 'basic' if kind == 'downgrade' else 'unlimited'}
            )
    else:
        user.update({'data_protection_level': 'enhanced' if kind == 'enhanced_to_e2ee' else 'e2ee'})
        if kind == 'finalize_migration':
            user.update({'migration_status': {'target_level': 'enhanced', 'status': 'in_progress'}})
        read = lambda: {'level': users.get_data_protection_level(uid)}
        target = 'e2ee' if kind == 'enhanced_to_e2ee' else 'enhanced'
        write = (
            (lambda: users.finalize_migration(uid, target))
            if kind == 'finalize_migration'
            else (lambda: users.set_data_protection_level(uid, target))
        )

    def truth():
        # fresh_reads bypasses Redis/request caches. A *new* batch attempt is
        # also necessary: its independent memo does not consult that bypass.
        from database.batch_privacy_attempt import batch_privacy_attempt

        from database import privacy_check_metrics as metrics

        session = metrics._SESSION.set(None)
        try:
            with fresh_reads(), batch_privacy_attempt():
                return read()
        finally:
            metrics._SESSION.reset(session)

    return uid, read, write, truth
