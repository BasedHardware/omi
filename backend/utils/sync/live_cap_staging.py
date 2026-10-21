"""Short durable fragments, composed into one immutable minute source.

Only staging rows may grow. A transaction serializes append, writer expiry and
seal under both privacy authorities. Published held sources never change.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound, PreconditionFailed
from google.cloud import firestore
from database._client import (
    get_data_plane_firestore_client as get_firestore_client,
    is_retryable_firestore_transaction_error,
)
from database.legal_holds import external_write_fence
from utils.encryption import encrypt
from utils.observability.held_content import record_publication_retry
from utils.other.storage import owner_storage_write_gate
from utils.sync import cap_hold
from utils.sync.live_cap_publication import UNRECOVERED, Publication, commit_publication

logger = logging.getLogger(__name__)

FRAGMENT_SECONDS = 15
MAX_FRAGMENTS = 4
MAX_FRAGMENT_BYTES = 32 * 1024
WRITER_SECONDS = 120
# A lost precondition is retried against a fresh read. The separate row is
# only for a group that has already left staging.
_STAGING_APPEND_ATTEMPTS = 3


def late_hold_identity(fragment_identity: str) -> str:
    """Seal a late fragment to its own object.

    The fragment blob is ``chunks/{uid}/cap-held/{fragment}.opus.enc``. Using
    that same id as the hold id makes seal compose onto the fragment and then
    delete it as a part.
    """
    return f'late:{fragment_identity}'


class SourceSealed(RuntimeError):
    """An expired writer must start a new source for a never-committed fragment."""


def append(uid: str, path: str, group: Publication, fragment: Publication, metadata: dict, seconds: float) -> dict:
    if group.uid != uid or fragment.uid != uid:
        raise ValueError('live staging owner changed')
    size = Path(path).stat().st_size
    if size > MAX_FRAGMENT_BYTES or not 0 < seconds <= FRAGMENT_SECONDS:
        raise ValueError('live fragment exceeds custody bound')
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(group.identity)
    fields: dict[str, Any] = {}
    staged_updates: dict[str, Any] | None = None
    attempted = fragment.is_retry(uid)

    @firestore.transactional
    def commit(tx: Any):
        nonlocal fields, attempted, staged_updates
        # Lock one attempt only. The retry helper sleeps after this returns.
        with group.lock:
            return _apply(tx)

    def _apply(tx: Any):
        nonlocal fields, attempted, staged_updates
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            row = ref.get(transaction=tx).to_dict() or {}
            parts = row.get('stage_parts') or []
            if fragment.identity in row.get('stage_fragment_ids', []) or any(
                part['id'] == fragment.identity for part in parts
            ):
                return row  # Lost commit reply: same fragment is already durable.
            if row and row.get('state') != 'staging':
                raise SourceSealed('live staging source already sealed')
            if len(parts) >= MAX_FRAGMENTS:
                raise ValueError('live staging group full')
            fields = {}
            fields = cap_hold.upload_held_audio(uid, path, fragment.identity, metadata, immutable=True)
            encoded_bytes = size
            if attempted:
                # A previous immutable put can survive failed cleanup. Re-encode
                # may change container length; the composed layout must describe
                # the stored generation, never the new local file.
                existing = cap_hold.get_private_cloud_sync_bucket().blob(
                    fields['audio_path'], generation=int(fields['audio_generation'])
                )
                existing.reload(timeout=10, retry=None)
                encrypted_bytes = existing.size
                if not isinstance(encrypted_bytes, int) or not 32 < encrypted_bytes <= MAX_FRAGMENT_BYTES + 32:
                    raise ValueError('invalid stored live fragment length')
                encoded_bytes = encrypted_bytes - 32
            attempted = True
            part = {
                'id': fragment.identity,
                'audio_path': fields['audio_path'],
                'audio_generation': fields['audio_generation'],
                'bytes': encoded_bytes,
                'frames': metadata['source_frames'],
            }
            updates = {
                'state': 'staging',
                'stage_parts': [*parts, part],
                'writer_until': time.time() + WRITER_SECONDS,
                'seconds': row.get('seconds', 0) + seconds,
                'metadata': row.get('metadata') or fields['metadata'],
                'sample_rate': metadata['sample_rate'],
                'started_at': row.get('started_at', metadata['timestamp']),
                'created_at': row.get('created_at', time.time()),
                'listed_at': row.get('listed_at', metadata['timestamp']),
                'live_custody_version': 4,
            }
            staged_updates = updates
            tx.set(ref, updates)
            return updates

    def _fragment_recorded(row: dict) -> bool:
        return fragment.identity in row.get('stage_fragment_ids', []) or any(
            part['id'] == fragment.identity for part in row.get('stage_parts') or []
        )

    def _verified_staging(target: Any, payload: dict) -> dict:
        """The write already landed. A later read must not fail the live flush."""
        try:
            stored = target.get().to_dict()
        except Exception as error:
            logger.warning(
                'event=stt_cap_live_held outcome=staged_unverified exception_type=%s',
                type(error).__name__,
            )
            record_publication_retry('staged_unverified')
            return payload
        return stored or payload

    def _late_staging_body(part: dict, updates: dict) -> dict:
        # writer_until is already expired so the redrive seals this row on its
        # own. It must not be appended onto a group the sealer has moved on.
        return {
            'state': 'staging',
            'stage_parts': [part],
            'writer_until': 0,
            'seconds': seconds,
            'metadata': updates.get('metadata'),
            'sample_rate': updates.get('sample_rate'),
            'started_at': updates.get('started_at'),
            'created_at': time.time(),
            'listed_at': updates.get('listed_at', updates.get('started_at')),
            'live_custody_version': 4,
        }

    def _row_after_create_race(target: Any, staged: dict) -> dict | None:
        """Read the row that won the create.

        None means that row does not hold this fragment. A failed read still
        returns the staged payload: the competing row may already hold it, and
        the failure must not close the socket.
        """
        try:
            current = target.get().to_dict() or {}
        except Exception as error:
            logger.warning(
                'event=stt_cap_live_held outcome=staged_unverified exception_type=%s',
                type(error).__name__,
            )
            record_publication_retry('staged_unverified')
            return staged
        if _fragment_recorded(current):
            return current
        return None

    def _stage_late_fragment(part: dict, updates: dict) -> dict | None:
        late = cap_hold.holds(uid).document(late_hold_identity(fragment.identity))
        body = _late_staging_body(part, updates)
        try:
            late.create(body)
        except AlreadyExists:
            return _row_after_create_race(late, body)
        return _verified_staging(late, body)

    def _append_while_staging(snapshot: Any, merged: dict, part: dict, updates: dict) -> dict | None:
        """Append while the group is staging. A lost precondition re-reads first."""
        for _attempt in range(_STAGING_APPEND_ATTEMPTS):
            try:
                ref.update(merged, option=firestore.LastUpdateOption(snapshot.update_time))
            except FailedPrecondition:
                try:
                    snapshot = ref.get()
                except Exception as error:
                    logger.warning(
                        'event=stt_cap_live_held outcome=staged_unverified exception_type=%s',
                        type(error).__name__,
                    )
                    record_publication_retry('staged_unverified')
                    continue
                row = snapshot.to_dict() if snapshot.exists else None
                if row and _fragment_recorded(row):
                    return row
                if not row or row.get('state') != 'staging':
                    return _stage_late_fragment(part, updates)
                merged = _merged_staging(updates, row, part)
                continue
            return _verified_staging(ref, merged)
        try:
            snapshot = ref.get()
        except Exception as error:
            logger.warning(
                'event=stt_cap_live_held outcome=staged_unverified exception_type=%s',
                type(error).__name__,
            )
            record_publication_retry('staged_unverified')
            return merged
        row = snapshot.to_dict() if snapshot.exists else None
        if row and _fragment_recorded(row):
            return row
        if not row or row.get('state') != 'staging':
            return _stage_late_fragment(part, updates)
        # Still staging, and this fragment is not in it. A second row here
        # would seal the same audio twice if the lost update had committed.
        return merged

    def _merged_staging(updates: dict, row: dict | None, part: dict) -> dict:
        merged = dict(updates)
        prior_parts = (row or {}).get('stage_parts') or []
        already = any(item.get('id') == part.get('id') for item in prior_parts)
        merged['stage_parts'] = prior_parts if already else [*prior_parts, part]
        base = float((row or {}).get('seconds') or 0)
        merged['seconds'] = base if already else base + seconds
        if row:
            merged['created_at'] = row.get('created_at', merged['created_at'])
            merged['started_at'] = row.get('started_at', merged['started_at'])
            merged['listed_at'] = row.get('listed_at', merged['listed_at'])
        return merged

    def _stage_for_redrive(updates: dict) -> dict | None:
        """Persist an uploaded fragment when every transaction id was retired.

        A plain create is not the steady path. It runs only after the bounded
        transactional budget, under the same non-transactional deletion fence.
        Appending to a staging row uses the row's update_time as a precondition
        so a cross-process sealer cannot be reset to staging. A lost
        precondition re-reads the group: a fragment already recorded there is
        returned, a group that is still staging is retried, and a separate row
        is created only after the group has left staging. That row's id is not
        the fragment id, so seal writes a different object from the part.
        Returning the row keeps the socket up: the bytes are durable, so this
        is not a 1011.
        """
        part = updates['stage_parts'][-1]
        if part.get('id') != fragment.identity:
            return None
        with external_write_fence(uid, firestore_client=client):
            snapshot = ref.get()
            row = snapshot.to_dict() if snapshot.exists else None
            if row and _fragment_recorded(row):
                return row
            merged = _merged_staging(updates, row, part)
            if not row:
                try:
                    ref.create(merged)
                except AlreadyExists:
                    current = _row_after_create_race(ref, merged)
                    if current is not None:
                        return current
                    return _stage_late_fragment(part, updates)
                return _verified_staging(ref, merged)
            if row.get('state') != 'staging':
                return _stage_late_fragment(part, updates)
            return _append_while_staging(snapshot, merged, part, updates)

    def recover(error: BaseException) -> Any:
        with group.lock:
            # Do not remove a fragment committed under a lost reply. Unknown
            # successful puts resolve their generation before exceptional cleanup.
            row = ref.get().to_dict() or {}
            if _fragment_recorded(row):
                return row
            if is_retryable_firestore_transaction_error(error) and staged_updates is not None:
                staged = _stage_for_redrive(staged_updates)
                if staged is not None:
                    logger.warning(
                        'event=stt_cap_live_held outcome=staged_for_redrive exception_type=%s',
                        type(error).__name__,
                    )
                    return staged
            blob = cap_hold.get_private_cloud_sync_bucket().blob(
                fields.get('audio_path') or f'chunks/{uid}/cap-held/{fragment.identity}.opus.enc'
            )
            try:
                generation = fields.get('audio_generation')
                if not generation:
                    blob.reload(timeout=10, retry=None)
                    generation = blob.generation
                blob.delete(if_generation_match=generation, timeout=10, retry=None)
            except (NotFound, PreconditionFailed):
                pass
            return UNRECOVERED

    return commit_publication(client, commit, recover=recover)


def cleanup(uid: str, ref: Any) -> None:
    row = ref.get(timeout=10).to_dict() or {}
    if not row.get('staging_cleanup') or row.get('state') in {'staging', 'sealing'}:
        return
    bucket = cap_hold.get_private_cloud_sync_bucket()
    for part in row.get('stage_parts') or []:
        if not part['audio_path'].startswith(f'chunks/{uid}/cap-held/'):
            raise ValueError('live staging cleanup owner mismatch')
        try:
            bucket.blob(part['audio_path']).delete(if_generation_match=part['audio_generation'], timeout=10, retry=None)
        except (NotFound, PreconditionFailed):
            pass
    # A purged tombstone may have replaced the row while cleanup ran. Never
    # resurrect it or erase newer authority fields with a full document set.
    try:
        ref.update({'staging_cleanup': False}, timeout=10)
    except NotFound:
        pass


def seal(uid: str, identity: str, *, expired_only: bool = False) -> bool:
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(identity)
    bucket = cap_hold.get_private_cloud_sync_bucket()

    @firestore.transactional
    def freeze(tx: Any):
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('state') == 'sealing':
                return True
            if row.get('state') != 'staging' or (expired_only and row.get('writer_until', 0) > time.time()):
                return False
            tx.update(ref, {'state': 'sealing'})
            return True

    try:
        if not commit_publication(client, freeze):
            cleanup(uid, ref)
            return False
    except Exception as error:
        # A staging row with parts is already in redrive custody. Raising here
        # would close the live socket with 1011 even though the audio is durable.
        return _leave_for_redrive(error, ref)

    @firestore.transactional
    def commit(tx: Any):
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('state') != 'sealing':
                return False
            parts = row['stage_parts']
            if not 0 < len(parts) <= MAX_FRAGMENTS:
                raise ValueError('invalid live staging part count')
            # Composition copies authenticated encryption frames verbatim. The
            # reader decodes each independent Opus clock before joining PCM.
            target = bucket.blob(f'chunks/{uid}/cap-held/{identity}.opus.enc')
            sources = []
            for part in parts:
                if not part['audio_path'].startswith(f'chunks/{uid}/cap-held/'):
                    raise ValueError('live staging compose owner mismatch')
                source = bucket.blob(part['audio_path'], generation=int(part['audio_generation']))
                sources.append(source)
            with owner_storage_write_gate(uid, bucket):
                try:
                    target.compose(sources, if_generation_match=0, timeout=10, retry=None)
                except PreconditionFailed:
                    target.reload(timeout=10, retry=None)
            metadata = cap_hold.metadata(uid, row)
            metadata['source_frames'] = sum(part['frames'] for part in parts)
            body = cap_hold.hold_manifest(
                {
                    'audio_path': target.name,
                    'audio_generation': target.generation,
                    'audio_codec': 'ogg_opus',
                    'sample_rate': row['sample_rate'],
                    'source_frames': metadata['source_frames'],
                    'metadata': encrypt(json.dumps(metadata), uid),
                    'opus_fragments': [{'bytes': part['bytes'], 'frames': part['frames']} for part in parts],
                },
                row['seconds'],
                row['created_at'],
                int(row['started_at']),
            )
            tx.set(ref, {**body, 'live_custody_version': 4, 'stage_parts': parts, 'staging_cleanup': True})
            tx.set(
                cap_hold.summary_ref(uid),
                {
                    'seconds': firestore.Increment(row['seconds']),
                    'count': firestore.Increment(1),
                },
                merge=True,
            )
            return True

    # No source cleanup on an uncertain compose/commit reply: it may already be
    # published. Retry resolves the same immutable destination and durable row.
    # Exhausted retries leave the staging row in place for the redrive sweep.
    try:
        result = commit_publication(client, commit)
    except Exception as error:
        return _leave_for_redrive(error, ref)
    cleanup(uid, ref)
    return result


def _leave_for_redrive(error: BaseException, ref: Any) -> bool:
    """Keep the socket up only when the fragment row is already durable."""
    if not is_retryable_firestore_transaction_error(error):
        raise error
    try:
        row = ref.get().to_dict() or {}
    except Exception:
        raise error from None
    if row.get('state') in {'staging', 'sealing'} and row.get('stage_parts'):
        logger.warning(
            'event=stt_cap_live_held outcome=staged_for_redrive exception_type=%s',
            type(error).__name__,
        )
        return False
    raise error
