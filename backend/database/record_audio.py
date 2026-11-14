"""Transactional record-audio closure and cross-session upload custody metadata."""

from typing import Literal
import time

from google.cloud import firestore

from config import record_seal_rules
from database._client import get_firestore_client, run_transactional
from database import record_token_lease_metrics as lease_metrics


class RecordUploadCapacityExceeded(ValueError):
    """The persisted producer map cannot accept another token."""


RecordSealRefusal = Literal['producer_pending', 'upload_failed', 'not_batch_owner', 'deleted']


def seal_record_audio(uid: str, conversation_id: str, *, firestore_client=None) -> RecordSealRefusal | None:
    """Resolve the persisted owner at closure, across websocket sessions.

    Upload failures are sticky across reconnects. Only the separate full-proof
    repair path may clear one; a later clean session cannot certify lost audio.
    Return None on success, otherwise a closed, content-free refusal reason.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('deleted') or not row:
            return 'deleted'
        if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
            return 'not_batch_owner'
        if row.get('record_upload_failed'):
            return 'upload_failed'
        if row.get('record_upload_sessions'):
            if record_seal_rules.refused_stamp_enabled() and row.get('record_seal_refused_at') is None:
                tx.update(ref, {'record_seal_refused_at': time.time()})
            return 'producer_pending'
        if row.get('record_audio_partial'):
            # A clean late producer certifies its drain, never an earlier
            # missing tail. Repair refreshes the separate partial barrier.
            return None
        if not row.get('record_audio_closed') or row.get('record_seal_refused_at') is not None:
            patch: dict[str, bool | None] = {'record_audio_closed': True}
            if row.get('record_seal_refused_at') is not None:
                patch['record_seal_refused_at'] = None
            tx.update(ref, patch)
        return None

    return run_transactional(client, commit, transient=True)


def set_record_upload_pending(
    uid: str,
    conversation_id: str,
    session: str,
    pending: bool,
    *,
    producer=None,
    firestore_client=None,
    late_observation=None,
):
    """Track a session's buffered/in-flight audio before accepting its first frame.

    Lease expiry removes only producer liveness, never the retained-tail proof.
    Clear only this producer's token after its successful drain.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    observed = {}

    @firestore.transactional
    def commit(tx):
        observed.clear()
        row = ref.get(transaction=tx).to_dict()
        if row is None:
            return False
        if pending and row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}:
            return False  # Immutable legacy owners cannot later enter batch custody.
        sessions = dict(row.get('record_upload_sessions') or {})
        if pending:
            if session in sessions:
                token = sessions[session]
                observed['late'] = isinstance(token, dict) and bool(token.get('append_late'))
                return True
            if len(sessions) >= 128:
                raise RecordUploadCapacityExceeded('record upload session budget exceeded')
            value = producer or True
            if record_seal_rules.token_lease_mode() != 'off' and isinstance(value, dict):
                now = time.time()
                value = {
                    **value,
                    'last_signal_at': now,
                    'lease_expires_at': now + record_seal_rules.token_lease_seconds(),
                    'signal_source': 'frames',
                }
            late = record_seal_rules.token_lease_mode() != 'off' and (
                bool(row.get('record_audio_closed') or row.get('record_audio_partial'))
                or any(record_seal_rules.token_lease_lapsed(token, time.time(), row=row) for token in sessions.values())
            )
            sessions[session] = value
            patch = {
                'record_upload_sessions': sessions,
                'record_audio_closed': False,
                'record_upload_revision': int(row.get('record_upload_revision') or 0) + 1,
            }
            observed['late'] = late
            if record_seal_rules.token_lease_serving(uid):
                from database.batch_pipeline_record_lease_recovery import prepare_recovery

                recovered, recovery = prepare_recovery(
                    client, tx, uid, conversation_id, row, patch['record_upload_revision'], time.time()
                )
                patch.update(recovered)
                observed['late'] |= bool(recovery)
                if recovery:
                    tx.set(*recovery)
            if isinstance(value, dict) and record_seal_rules.token_lease_mode() != 'off':
                # The same registration after a committed-but-lost response
                # must return the original late observation.
                sessions[session]['append_late'] = bool(observed['late'])
            tx.update(ref, patch)
        elif session in sessions:
            if isinstance(sessions[session], dict) and 'abandoned_at' in sessions[session]:
                return False  # Only repair's retained-tail proof may release this fence.
            sessions.pop(session)
            tx.update(ref, {'record_upload_sessions': sessions})
        return True

    result = run_transactional(client, commit, transient=True)
    if result and late_observation is not None:
        late_observation['late'] = observed.get('late', False)
    return result


def abandon_record_upload_session(uid: str, conversation_id: str, session: str, *, firestore_client=None) -> bool:
    """Attest that one producer stopped, never that its tail was projected.

    The caller must first stop its tasks and settle all in-flight executor work.
    Preserve the token for repair's archive/tail proof; never recreate a row or
    affect a reconnect's different token. Retries preserve the first attestation.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict()
        if not row or row.get('deleted'):
            return False
        sessions = dict(row.get('record_upload_sessions') or {})
        producer = sessions.get(session)
        if not isinstance(producer, dict):
            return False  # Absent/legacy tokens cannot acquire an invented identity.
        if 'abandoned_at' not in producer:
            sessions[session] = {**producer, 'abandoned_at': time.time()}
            tx.update(ref, {'record_upload_sessions': sessions})
        return True

    return run_transactional(client, commit, transient=True)


def mark_record_upload_failed(uid: str, conversation_id: str, *, firestore_client=None) -> bool:
    """Persist a terminal upload/drop refusal before the session forgets it."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict()
        if row is None:
            return False  # Never recreate a deleted conversation.
        if row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}:
            return False  # Immutable legacy owners never enter this protocol.
        # Always write, including repeated failures: a repair plan must observe
        # a new failure even while the sticky flag was already true.
        tx.update(
            ref,
            {
                'record_upload_failed': True,
                'record_audio_closed': False,
                'record_upload_revision': int(row.get('record_upload_revision') or 0) + 1,
            },
        )
        return True

    return run_transactional(client, commit, transient=True)


def renew_record_token_lease(
    uid, conversation_id, *, source, session=None, producer=None, firestore_client=None, late_observation=None
):
    """Renew observed signals; upload custody uses a separate exact-token fence.

    Manifest heartbeats never invalidate revisions or count accepted appends.
    Serve-only frames after a complete seal re-arm partial continuation.
    """
    if record_seal_rules.token_lease_mode() == 'off':
        return False
    if source not in {'frames', 'custody_append'}:
        raise ValueError('unrecognized record lease signal')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    observed_late = False

    @firestore.transactional
    def commit(tx):
        nonlocal observed_late
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            not row
            or row.get('deleted')
            or row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}
        ):
            return False, False, []
        now = time.time()
        sessions = dict(row.get('record_upload_sessions') or {})
        gaps = []
        late = bool(row.get('record_audio_closed') or row.get('record_audio_partial'))
        reactivated = source == 'frames' and bool(row.get('record_audio_partial'))
        closed_frame = source == 'frames' and bool(row.get('record_audio_closed'))
        serving = record_seal_rules.token_lease_serving(uid)
        if closed_frame and not serving:
            return False, True, []  # Shadow observes a seal; it never mutates it.
        identified = [token for token in sessions.values() if isinstance(token, dict)]
        targets = [
            token
            for key, token in sessions.items()
            if isinstance(token, dict)
            and (session is None or key == session)
            and (
                source != 'custody_append' or token.get('signal_source') == 'custody_append' and token.get('pod') == ''
            )
        ]
        if source == 'custody_append':
            late |= any(record_seal_rules.token_lease_lapsed(token, now, row=row) for token in identified)
            # Publish only after renewal succeeds, but retain post-storage
            # observations if its committed response is lost and retried.
            observed_late |= late
            # An unowned/non-serving archive may observe lateness, never renew
            # another upload's custody. Frame renewal keeps its own contract.
            if not serving or not session:
                return False, late, []
        if (
            source == 'custody_append'
            and targets
            and all(
                (signal := record_seal_rules.lease_timestamp(token.get('last_signal_at')))
                and now - signal < record_seal_rules.producer_token_lease_seconds(token) / 2
                for token in targets
            )
        ):
            return False, late, []
        changed = False
        # Restore only this socket's identity. Serve also reopens complete
        # seals so newly retained interior audio gets a continuation pass.
        if (
            source == 'frames'
            and session is not None
            and session not in sessions
            and (not row.get('record_audio_closed') or serving)
            and isinstance(producer, dict)
            and isinstance(producer.get('pod'), str)
            and producer['pod']
            and record_seal_rules.lease_timestamp(producer.get('process_started_at'))
        ):
            if len(sessions) >= 128:
                raise RecordUploadCapacityExceeded('record upload session budget exceeded')
            sessions[session] = dict(producer)
            reactivated = late = True
        for key, token in sessions.items():
            if session is not None and key != session:
                continue
            if not isinstance(token, dict):
                continue
            if source == 'custody_append' and (
                token.get('signal_source') != 'custody_append' or token.get('pod') != ''
            ):
                continue
            clocks = record_seal_rules.token_lease_clocks(token, row=row)
            lapsed = record_seal_rules.token_lease_lapsed(token, now, row=row)
            if source == 'frames':
                reactivated |= lapsed or closed_frame and serving
            late |= lapsed
            if clocks:
                gaps.append(max(0, now - clocks[0]))
            # Clock rollback must never shorten an already committed fence.
            signal = max(now, clocks[0] if clocks else now)
            sessions[key] = {
                **token,
                'last_signal_at': signal,
                'lease_expires_at': max(
                    signal + record_seal_rules.producer_token_lease_seconds(token), clocks[1] if clocks else 0
                ),
                'signal_source': source,
            }
            sessions[key].pop('abandoned_at', None)
            changed = True
        if changed or reactivated:
            patch: dict[str, object] = {'record_upload_sessions': sessions}
            recovery = None
            if reactivated:
                revision = int(row.get('record_upload_revision') or 0) + 1
                patch['record_upload_revision'] = revision
                if source == 'frames' and serving and changed:
                    from database.batch_pipeline_record_lease_recovery import prepare_recovery

                    recovered, recovery = prepare_recovery(client, tx, uid, conversation_id, row, revision, now)
                    patch.update(recovered, record_audio_closed=False)
            if recovery:
                tx.set(*recovery)
            tx.update(ref, patch)
        return changed, late, gaps

    changed, late, gaps = run_transactional(client, commit, transient=True)
    if changed:
        lease_metrics.RENEWALS.labels(source=source).inc()
        for gap in gaps:
            lease_metrics.SIGNAL_GAP.observe(gap)
    if late_observation is not None:
        late_observation['late'] = late or observed_late
    return changed
