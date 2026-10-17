"""One immutable, sealed source object and two atomic document writes per minute."""

import time
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.legal_holds import external_write_fence
from utils.sync import cap_hold


def publish(uid: str, path: str, identity: str, metadata: dict, seconds: float, *, retry: bool = False) -> None:
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(identity)
    total = cap_hold.summary_ref(uid)
    attempted = retry

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
            fields = cap_hold.upload_held_audio(uid, path, identity, metadata, immutable=True)
            body = cap_hold.hold_manifest(fields, seconds, time.time(), int(metadata['timestamp']))
            tx.create(ref, {**body, 'live_custody_version': 4})  # Already sealed; no mutable stream lease.
            tx.set(total, {'seconds': firestore.Increment(seconds), 'count': firestore.Increment(1)}, merge=True)

    try:
        commit(client.transaction())
    except AlreadyExists:
        # Atomic create + increments: a lost commit reply cannot count twice.
        # Recovery keeps a small purged tombstone so a late retry cannot revive it.
        return
