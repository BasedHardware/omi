"""One immutable, sealed source object and two atomic document writes per minute."""

import time
from typing import Any

from google.api_core.exceptions import AlreadyExists, NotFound, PreconditionFailed
from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.legal_holds import external_write_fence
from utils.sync import cap_hold
from utils.sync.live_cap_publication import Publication


def publish(uid: str, path: str, source: Publication, metadata: dict, seconds: float) -> None:
    with source.lock:
        _publish(uid, path, source, metadata, seconds)


def _publish(uid: str, path: str, source: Publication, metadata: dict, seconds: float) -> None:
    attempted = source.is_retry(uid)
    identity = source.identity
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(identity)
    total = cap_hold.summary_ref(uid)

    @firestore.transactional
    def commit(tx: Any) -> None:
        nonlocal attempted
        # Hold both account authorities through upload AND manifest commit.
        # A destructive writer either precedes this read (we refuse) or waits /
        # conflicts with it. Nested GCS gates reuse this exact transaction scope.
        with external_write_fence(uid, firestore_client=client, transaction=tx):
            if attempted and ref.get(transaction=tx).exists:
                return  # Includes purged receipts; never recreate recovered audio.
            attempted = True
            source.put_started = True
            source.fields = {}  # A later failed put must not inherit a deleted generation.
            fields = cap_hold.upload_held_audio(uid, path, identity, metadata, immutable=True)
            source.fields = dict(fields)
            body = cap_hold.hold_manifest(fields, seconds, time.time(), int(metadata['timestamp']))
            tx.create(ref, {**body, 'live_custody_version': 4})  # Already sealed; no mutable stream lease.
            tx.set(total, {'seconds': firestore.Increment(seconds), 'count': firestore.Increment(1)}, merge=True)

    try:
        commit(client.transaction())
    except AlreadyExists:
        # Atomic create + increments: a lost commit reply cannot count twice.
        # Recovery keeps a small purged tombstone so a late retry cannot revive it.
        return
    except Exception:
        # Exceptional path only: an upload may have succeeded before an aborted
        # commit or a deletion marker won. Never delete a committed source on a
        # lost reply, nor a replacement generation. Retain failures for retry.
        if source.put_started and not ref.get().exists:
            fields = source.fields
            blob = cap_hold.get_private_cloud_sync_bucket().blob(
                fields.get('audio_path') or f'chunks/{uid}/cap-held/{identity}.opus.enc'
            )
            try:
                generation = fields.get('audio_generation')
                if not generation:
                    blob.reload(timeout=10, retry=None)  # Ambiguous reply; exceptional Class B only.
                    generation = blob.generation
                if not generation:
                    raise RuntimeError('held source generation unavailable for cleanup')
                blob.delete(if_generation_match=generation)
            except (NotFound, PreconditionFailed):
                pass
        raise
