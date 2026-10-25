"""Explicit production adapter composition, also usable with loopback emulators."""

from typing import Any
from functools import partial
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from utils.batch_pipeline.artifacts import ArtifactStore
from utils.batch_pipeline.retention import batch_artifact_authorize, batch_artifact_register
from utils.other.local_storage import create_storage_client


def artifacts_for(store: Any) -> ArtifactStore:
    """Shared IO composition; readers must not import admission or GPU stages."""
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    if not bucket:
        raise RuntimeError('durable batch staging bucket is not configured')
    return create_artifact_store(store, create_storage_client(), bucket, os.getenv('ENCRYPTION_SECRET', '').encode())


def create_artifact_store(store: Any, storage_client: Any, bucket: str, master_secret: bytes) -> ArtifactStore:
    if len(master_secret) < 32:
        raise ValueError('batch artifact encryption secret must contain at least 32 bytes')

    def key_for_owner(owner_id: str) -> bytes:
        # Same derivation as utils.encryption; no import-time secret requirement,
        # plaintext files, shared key cache, or permissive decrypt fallback.
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=owner_id.encode(), info=b'user-data-encryption').derive(
            master_secret
        )

    return ArtifactStore(
        storage_client,
        bucket=bucket,
        namespace=store.namespace,
        authorize=partial(batch_artifact_authorize, store),
        key_for_owner=key_for_owner,
        register_artifact=partial(batch_artifact_register, store),
        shadow_result=partial(shadow_result, store),
    )


def shadow_result(store, item, payload):
    from database.batch_pipeline_shadow import ShadowStore

    ShadowStore(store).finish(
        item.segment_id,
        'recovered' if payload.get('words') else 'empty',
        speech=float(payload.get('speech_seconds', 0)),
        vad='worker',
    )
