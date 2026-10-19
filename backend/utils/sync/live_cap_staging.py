"""Short durable fragments, composed into one immutable minute source.

Only staging rows may grow. A transaction serializes append, writer expiry and
seal under both privacy authorities. Published held sources never change.
"""

import time
from pathlib import Path
from typing import Any

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.legal_holds import external_write_fence
from utils.encryption import encrypt
from utils.other.storage import owner_storage_write_gate
from utils.sync import cap_hold
from utils.sync.live_cap_publication import Publication
import json

FRAGMENT_SECONDS = 15
MAX_FRAGMENTS = 4
MAX_FRAGMENT_BYTES = 32 * 1024
WRITER_SECONDS = 120


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
    attempted = fragment.is_retry(uid)

    @firestore.transactional
    def commit(tx: Any):
        nonlocal fields, attempted
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
            tx.set(ref, updates)
            return updates

    # Serialize retry attempts using the same process-owned publication token.
    with group.lock:
        try:
            return commit(client.transaction())
        except Exception:
            # Do not remove a fragment committed under a lost reply. Unknown
            # successful puts resolve their generation before exceptional cleanup.
            row = ref.get().to_dict() or {}
            if fragment.identity in row.get('stage_fragment_ids', []) or any(
                part['id'] == fragment.identity for part in row.get('stage_parts') or []
            ):
                return row
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
            raise


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

    if not freeze(client.transaction()):
        cleanup(uid, ref)
        return False

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
    result = commit(client.transaction())
    cleanup(uid, ref)
    return result
