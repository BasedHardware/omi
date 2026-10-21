"""One immutable, sealed source object and two atomic document writes per minute."""

import logging
import time
from typing import Any

from google.api_core.exceptions import AlreadyExists, NotFound, PreconditionFailed
from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client
from database._client import is_retryable_firestore_transaction_error, run_transactional
from database.legal_holds import external_write_fence
from utils.observability.held_content import record_erasure
from utils.sync import cap_hold
from utils.sync.live_cap_publication import UNRECOVERED, Publication, commit_publication

logger = logging.getLogger(__name__)


def publish(uid: str, path: str, source: Publication, metadata: dict, seconds: float) -> None:
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
        # The publication lock covers one attempt. Retry backoff runs after this
        # returns, so a sleep cannot stall another session's source.
        with source.lock:
            # Hold both account authorities through upload AND manifest commit.
            # A destructive writer either precedes this read (we refuse) or waits /
            # conflicts with it. Nested GCS gates reuse this exact transaction scope.
            with external_write_fence(uid, firestore_client=client, transaction=tx):
                existing = ref.get(transaction=tx)
                prior = existing.to_dict() if existing.exists else None
                if prior and prior.get('state') == 'purged':
                    record_erasure('post_delete_publication')
                    return  # Tombstone wins. A commit over it is post_delete_publication.
                if prior and prior.get('usage_applied'):
                    return  # Receipt and its summary increment already committed together.
                if existing.exists:
                    # The receipt landed and the increment did not. The flag and
                    # the summary move in this same transaction, so a retry that
                    # sees the flag cannot count the audio twice.
                    tx.update(ref, {'usage_applied': True})
                    tx.set(
                        total,
                        {'seconds': firestore.Increment(seconds), 'count': firestore.Increment(1)},
                        merge=True,
                    )
                    return
                attempted = True
                source.put_started = True
                source.fields = {}  # A later failed put must not inherit a deleted generation.
                fields = cap_hold.upload_held_audio(uid, path, identity, metadata, immutable=True)
                source.fields = dict(fields)
                body = cap_hold.hold_manifest(fields, seconds, time.time(), int(metadata['timestamp']))
                tx.create(ref, {**body, 'live_custody_version': 4, 'usage_applied': True})
                tx.set(
                    total,
                    {'seconds': firestore.Increment(seconds), 'count': firestore.Increment(1)},
                    merge=True,
                )

    def _publish_for_recovery() -> bool:
        """Write the held receipt outside the retired transaction id.

        The receipt and the summary increment commit in one transaction, and
        ``usage_applied`` is set in that same transaction. A receipt left behind
        by a create that never reached its increment is repaired here, once.
        """
        fields = source.fields

        @firestore.transactional
        def commit_recovery(tx: Any) -> bool:
            with external_write_fence(uid, firestore_client=client, transaction=tx):
                existing = ref.get(transaction=tx)
                row = existing.to_dict() if existing.exists else None
                if row and row.get('state') == 'purged':
                    record_erasure('post_delete_publication')
                    return True
                if row and row.get('usage_applied'):
                    return True
                if existing.exists:
                    tx.update(ref, {'usage_applied': True})
                else:
                    if not fields:
                        return False
                    body = cap_hold.hold_manifest(fields, seconds, time.time(), int(metadata['timestamp']))
                    tx.create(ref, {**body, 'live_custody_version': 4, 'usage_applied': True})
                tx.set(
                    total,
                    {'seconds': firestore.Increment(seconds), 'count': firestore.Increment(1)},
                    merge=True,
                )
                return True

        try:
            return bool(run_transactional(client, commit_recovery, attempts=1))
        except AlreadyExists:
            return False

    def recover(error: BaseException) -> Any:
        if isinstance(error, AlreadyExists):
            # The create lost to a receipt that already exists. Repair usage
            # only when that receipt never recorded the increment.
            if _publish_for_recovery():
                return None
            return UNRECOVERED
        with source.lock:
            snapshot = ref.get()
            row = snapshot.to_dict() if snapshot.exists else None
            if row and row.get('usage_applied'):
                return None
            if row and row.get('state') == 'purged':
                record_erasure('post_delete_publication')
                return None
            needs_usage = bool(row) and not row.get('usage_applied')
            # The audio is durable and the held receipt is what recovery reads.
            # Returning keeps the socket up instead of closing it with 1011.
            if (
                is_retryable_firestore_transaction_error(error)
                and (source.put_started or needs_usage)
                and _publish_for_recovery()
            ):
                logger.warning(
                    'event=stt_cap_live_held outcome=staged_for_redrive exception_type=%s',
                    type(error).__name__,
                )
                return None
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
        return UNRECOVERED

    commit_publication(client, commit, recover=recover)
