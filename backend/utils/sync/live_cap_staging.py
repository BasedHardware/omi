"""Short durable fragments, composed into one immutable minute source.

Only staging rows may grow. A transaction serializes append, writer expiry and
seal under both privacy authorities. Published held sources never change.
"""

import hashlib
import itertools
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
from utils.sync import cap_hold, live_cap_journal
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


def append(
    uid: str,
    path: str,
    group: Publication,
    fragment: Publication,
    metadata: dict,
    seconds: float,
    *,
    emergency: bool = False,
) -> dict:
    if group.uid != uid or fragment.uid != uid:
        raise ValueError('live staging owner changed')
    size = fragment.fields.get('audio_size', 0) - 32 if fragment.fields.get('audio_size') else Path(path).stat().st_size
    journal = emergency or group.identity == late_hold_identity(fragment.identity)
    if size > (128 * 1024 if journal else MAX_FRAGMENT_BYTES) or not 0 < seconds <= (
        60 if journal else FRAGMENT_SECONDS
    ):
        raise ValueError('live fragment exceeds custody bound')
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(group.identity)
    fields: dict[str, Any] = fragment.fields
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
            fields = fragment.fields or cap_hold.upload_held_audio(
                uid, path, fragment.identity, metadata, immutable=True
            )
            fragment.fields = dict(fields)
            encoded_bytes = size
            if attempted and not fields.get('audio_size'):
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
                'writer_until': 0 if journal else time.time() + WRITER_SECONDS,
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

    def _confirmed_fragment(target: Any) -> dict | None:
        """Return the row only when a read shows it holds this fragment.

        A failed read confirms nothing. Callers then open the deterministic
        late row, or surface a failure if that row cannot be confirmed either.
        """
        try:
            current = target.get().to_dict() or {}
        except Exception as error:
            logger.warning(
                'event=stt_cap_live_held outcome=staged_unverified exception_type=%s',
                type(error).__name__,
            )
            record_publication_retry('staged_unverified')
            return None
        if _fragment_recorded(current):
            return current
        return None

    def _stage_late_fragment(part: dict, updates: dict) -> dict | None:
        late = cap_hold.holds(uid).document(late_hold_identity(fragment.identity))
        body = _late_staging_body(part, updates)
        try:
            late.create(body)
        except AlreadyExists:
            # The id is deterministic. Return the row only when it holds this
            # fragment. Otherwise the caller must not treat the fragment as staged.
            return _confirmed_fragment(late)
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
            return _stage_late_fragment(part, updates)
        row = snapshot.to_dict() if snapshot.exists else None
        if row and _fragment_recorded(row):
            return row
        # Still missing, or the group has left staging. The late id is
        # deterministic, so a second recovery creates this row once.
        return _stage_late_fragment(part, updates)

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
        precondition re-reads the group. A fragment is returned only when a
        read shows some row holds it. Retries that never record it, and a
        re-read that fails, open the deterministic late row instead of
        reporting the uncommitted merge. That row's id is not the fragment
        id, so seal writes a different object from the part. Returning the
        confirmed row keeps the socket up. An unconfirmed fragment still fails.
        The uploaded object stays: only the seal that claimed the fragment
        deletes it.
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
                    current = _confirmed_fragment(ref)
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
            # Custody is unknown whenever no read showed this fragment. The
            # object stays for a later seal. Deleting it here can remove the
            # source a row we failed to read still names.
            if fields:
                # This attempt uploaded a fragment that no row names. Nothing
                # will seal or clean it, and the socket closes with 1011.
                record_publication_retry('source_orphaned')
            return UNRECOVERED

    return commit_publication(client, commit, recover=recover)


# One document per fragment. Creating it is the claim: a second seal cannot
# create the same id, so it cannot compose or count that fragment again.
# Claims are permanent. An expiry could let a duplicate row re-claim a
# fragment later and count it twice, so a cleanup may relax this only once it
# can prove every row referencing the fragment is terminal and the source is
# gone. The ledger is tiny, and account erasure deletes it with the user.
_FRAGMENT_CLAIMS = 'stt_cap_fragment_claims'


def _fragment_claim_ref(uid: str, fragment_id: str) -> Any:
    return get_firestore_client().collection('users').document(uid).collection(_FRAGMENT_CLAIMS).document(fragment_id)


def _fragment_claim(identity: str, fragment_id: str) -> dict:
    return {'hold_id': identity, 'fragment_id': fragment_id}


def _claim_set_digest(fragment_ids: list[str]) -> str:
    return hashlib.sha256('\n'.join(sorted(fragment_ids)).encode()).hexdigest()[:16]


def _compose_target(bucket: Any, uid: str, identity: str, fragment_ids: list[str]) -> Any:
    """The seal destination names its claim set.

    Compose runs before the claim transaction commits. A retry that lost a
    fragment to another row claims a smaller set; it must not reuse a composite
    built from the wider set, or the manifest describes fewer bytes than the
    object holds. The same set on the same row resolves to the same object, so
    a plain retry still reuses its immutable destination.
    """
    return bucket.blob(f'chunks/{uid}/cap-held/{identity}.{_claim_set_digest(fragment_ids)}.opus.enc')


def _hold_identity(ref: Any) -> str:
    path = getattr(ref, 'path', None) or getattr(ref, 'key', '')
    return str(path).rsplit('/', 1)[-1]


def _counted_seconds(row: dict, parts: list[dict], claimed: list[dict]) -> float:
    """Use the row total when this seal owns every fragment.

    A partial overlap has no per-fragment total stored on the row. Frames and
    sample rate are already on the part, and they are what the row total was
    built from.
    """
    if {part['id'] for part in claimed} == {part['id'] for part in parts}:
        return float(row.get('seconds') or 0)
    rate = float(row.get('sample_rate') or 0)
    if rate <= 0:
        return 0.0
    return sum(float(part.get('frames') or 0) / rate for part in claimed)


def _drop_unpublished_targets(
    bucket: Any, uid: str, identity: str, part_ids: list[str], claimed_ids: list[str]
) -> None:
    """Remove composes this row published before losing fragments to another row.

    Claims are never released, so every destination an earlier attempt of this
    row composed names a proper superset of what it can still claim, and no
    committed manifest names it. Only this row's seal destinations are
    candidates, never a fragment source. At most 2**MAX_FRAGMENTS - 1 names.
    """
    claimed = list(dict.fromkeys(claimed_ids))
    lost = [fragment_id for fragment_id in dict.fromkeys(part_ids) if fragment_id and fragment_id not in claimed]
    for size in range(1, len(lost) + 1):
        for extra in itertools.combinations(lost, size):
            target = _compose_target(bucket, uid, identity, [*claimed, *extra])
            try:
                target.reload(timeout=10, retry=None)
            except NotFound:
                continue
            try:
                target.delete(if_generation_match=target.generation, timeout=10, retry=None)
            except (NotFound, PreconditionFailed):
                pass


def cleanup(uid: str, ref: Any) -> None:
    row = ref.get(timeout=10).to_dict() or {}
    if not row.get('staging_cleanup') or row.get('state') in {'staging', 'sealing'}:
        return
    identity = _hold_identity(ref)
    # Rows sealed before claims existed have no list. Those deletes are the
    # previous behavior. A present list, even empty, deletes nothing this row
    # did not claim.
    claimed_ids = row.get('claimed_fragment_ids')
    legacy = claimed_ids is None
    claimed = set(claimed_ids or [])
    bucket = cap_hold.get_private_cloud_sync_bucket()
    unresolved = False
    for part in row.get('stage_parts') or []:
        if not legacy and part.get('id') not in claimed:
            continue
        if not legacy:
            try:
                claim = _fragment_claim_ref(uid, part['id']).get(timeout=10).to_dict() or {}
            except Exception as error:
                logger.warning(
                    'event=stt_cap_live_held outcome=cleanup_claim_unreadable exception_type=%s',
                    type(error).__name__,
                )
                unresolved = True
                continue
            if claim.get('hold_id') != identity:
                continue
        if not part['audio_path'].startswith(f'chunks/{uid}/cap-held/'):
            raise ValueError('live staging cleanup owner mismatch')
        try:
            bucket.blob(part['audio_path']).delete(if_generation_match=part['audio_generation'], timeout=10, retry=None)
        except (NotFound, PreconditionFailed):
            pass
    if unresolved:
        # Leave the flag set so the cleanup sweep can try this row again.
        return
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
            if row.get('stage_pending'):
                raise live_cap_journal.PendingFragment(row)
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
    except live_cap_journal.PendingFragment as pending:
        live_cap_journal.restore(uid, identity, pending.row, append)
        return seal(uid, identity, expired_only=expired_only)
    except Exception as error:
        # A staging row with parts is already in redrive custody. Raising here
        # would close the live socket with 1011 even though the audio is durable.
        return _leave_for_redrive(error, ref)

    # Composites an earlier attempt of this row composed over fragments a later
    # attempt lost are unpublished garbage. Deleting them is up to
    # 2**MAX_FRAGMENTS - 1 sequential GCS calls with 10s timeouts, so they run
    # after the commit, never inside the transaction callback.
    unpublished: tuple[list[str], list[str]] | None = None

    @firestore.transactional
    def commit(tx: Any):
        nonlocal unpublished
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            row = ref.get(transaction=tx).to_dict() or {}
            if row.get('state') != 'sealing':
                unpublished = None
                return False
            parts = row['stage_parts']
            if not 0 < len(parts) <= MAX_FRAGMENTS:
                raise ValueError('invalid live staging part count')
            # Firestore rejects a transactional read after the first queued
            # write, so every claim is read before any claim is created.
            by_id: dict[str, dict] = {}
            for part in parts:
                fragment_id = part.get('id')
                if fragment_id and fragment_id not in by_id:
                    by_id[fragment_id] = part
            holders = {
                fragment_id: (_fragment_claim_ref(uid, fragment_id).get(transaction=tx).to_dict() or {}).get('hold_id')
                for fragment_id in by_id
            }
            # Claim before compose. A fragment another row already claimed is
            # not composed and not counted. The create is the lock: Firestore
            # retries this transaction if the other seal commits first.
            claimed: list[dict] = []
            for fragment_id, part in by_id.items():
                holder = holders[fragment_id]
                if holder and holder != identity:
                    continue
                if not holder:
                    tx.create(_fragment_claim_ref(uid, fragment_id), _fragment_claim(identity, fragment_id))
                claimed.append(part)
            part_ids = list(by_id)
            claimed_ids = [part['id'] for part in claimed]
            if not claimed:
                # This attempt may already have composed, then lost the claim
                # commit and retried. Those destinations are dropped after the
                # superseded row commits. The fragment sources belong to the
                # rows that won the claims.
                unpublished = (part_ids, [])
                tx.set(
                    ref,
                    {
                        'state': 'superseded',
                        'seconds': 0,
                        'stage_parts': parts,
                        'claimed_fragment_ids': [],
                        'staging_cleanup': False,
                        'live_custody_version': 4,
                        'created_at': row.get('created_at', time.time()),
                        'started_at': row.get('started_at'),
                        'listed_at': row.get('listed_at', row.get('started_at')),
                    },
                )
                return True
            if len(claimed) < len(by_id):
                # An earlier attempt may have composed the wider set this row
                # could still claim then. That object is unpublished garbage.
                unpublished = (part_ids, claimed_ids)
            else:
                unpublished = None
            # Composition copies authenticated encryption frames verbatim. The
            # reader decodes each independent Opus clock before joining PCM.
            target = _compose_target(bucket, uid, identity, claimed_ids)
            sources = []
            for part in claimed:
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
            metadata['source_frames'] = sum(part['frames'] for part in claimed)
            counted = _counted_seconds(row, parts, claimed)
            body = cap_hold.hold_manifest(
                {
                    'audio_path': target.name,
                    'audio_generation': target.generation,
                    'audio_codec': 'ogg_opus',
                    'sample_rate': row['sample_rate'],
                    'source_frames': metadata['source_frames'],
                    'metadata': encrypt(json.dumps(metadata), uid),
                    'opus_fragments': [{'bytes': part['bytes'], 'frames': part['frames']} for part in claimed],
                },
                counted,
                row['created_at'],
                int(row['started_at']),
            )
            tx.set(
                ref,
                {
                    **body,
                    'live_custody_version': 4,
                    'stage_parts': parts,
                    'claimed_fragment_ids': [part['id'] for part in claimed],
                    'staging_cleanup': True,
                },
            )
            tx.set(
                cap_hold.summary_ref(uid),
                {
                    'seconds': firestore.Increment(counted),
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
    if unpublished is not None:
        # Post-commit cleanup, owned by the row that committed. Every candidate
        # is this hold's own compose destination — never a fragment source,
        # never another hold's object — and the committed set itself is never a
        # candidate, so a failure here can only leave garbage behind.
        _drop_unpublished_targets(bucket, uid, identity, unpublished[0], unpublished[1])
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
