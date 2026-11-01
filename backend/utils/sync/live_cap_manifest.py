"""One immutable, sealed source object and two atomic document writes per minute."""

import logging
import time
from typing import Any

from google.api_core.exceptions import AlreadyExists
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
            # The live upload checks both account authorities independently;
            # these reads still fence its receipt commit against destructive work.
            # Synchronous recovery callers upload inside this same scope.
            with external_write_fence(uid, firestore_client=client, transaction=tx):
                existing = ref.get(transaction=tx)
                prior = existing.to_dict() if existing.exists else None
                if prior and prior.get('state') == 'purged':
                    record_erasure('post_delete_publication')
                    return  # Tombstone wins. A commit over it is post_delete_publication.
                if existing.exists:
                    # Every writer that can leave this receipt — the one deployed
                    # today and this path — commits the receipt and its summary
                    # increment in one transaction. A receipt without the marker
                    # predates the marker; the audio is already counted. Stamp the
                    # marker for the readers and never increment again.
                    if not (prior or {}).get('usage_applied'):
                        tx.update(ref, {'usage_applied': True})
                    return
                attempted = True
                source.put_started = True
                fields = source.fields or cap_hold.upload_held_audio(uid, path, identity, metadata, immutable=True)
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

        The receipt and its summary increment commit in one transaction, and
        every writer that can leave a receipt did so — including the writer
        deployed before ``usage_applied`` existed. A receipt that already
        exists, with or without the marker, is already counted: only the
        marker is stamped here, and the summary moves only with a create.
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
                if existing.exists:
                    if not (row or {}).get('usage_applied'):
                        tx.update(ref, {'usage_applied': True})
                    return True
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
            # The create lost to a receipt that already exists. That receipt was
            # counted by the transaction that created it; at most its marker is
            # missing, and stamping it never moves the summary.
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
            needs_marker = bool(row) and not row.get('usage_applied')
            # The audio is durable and the held receipt is what recovery reads.
            # Returning keeps the socket up instead of closing it with 1011.
            if (
                is_retryable_firestore_transaction_error(error)
                and (source.put_started or needs_marker)
                and _publish_for_recovery()
            ):
                logger.warning(
                    'event=stt_cap_live_held outcome=staged_for_redrive exception_type=%s',
                    type(error).__name__,
                )
                return None
            # A missing receipt cannot fence an earlier commit that is still in
            # flight. Keep the identity and generation even on a permanent error;
            # unreferenced storage is preferable to a receipt naming deleted audio.
        return UNRECOVERED

    commit_publication(client, commit, recover=recover)
