"""Stable, privacy-safe identities for sync batches across job re-uploads."""

import hashlib
import hmac
import os
from pathlib import Path
from typing import Iterable


def compute_sync_content_id(uid: str, paths: Iterable[str], *, operation: str | None = None) -> str:
    secret = os.getenv('SYNC_CONTENT_ID_SECRET') or os.getenv('ENCRYPTION_SECRET')
    if not secret:
        raise RuntimeError('SYNC_CONTENT_ID_SECRET or ENCRYPTION_SECRET is required for durable sync idempotency')

    file_digests: list[str] = []
    for path in paths:
        digest = hashlib.sha256()
        with open(path, 'rb') as audio_file:
            while chunk := audio_file.read(1024 * 1024):
                digest.update(chunk)
        # The basename carries the capture timestamp/codec in the sync
        # protocol. Include it so two distinct recordings with identical
        # bytes (notably silence) cannot collapse onto one ledger entry, while
        # remaining stable across temporary job directories.
        file_digests.append(f'{Path(path).name}:{digest.hexdigest()}')

    canonical = '\n'.join(sorted(file_digests))
    # Preserve the deployed merge identity across rolling revisions. New
    # mutation contracts add a domain tag so the same bytes cannot converge
    # onto a ledger result produced under different write semantics.
    identity = f'{uid}\n{canonical}' if operation is None else f'{uid}\n{operation}\n{canonical}'
    return hmac.new(secret.encode(), identity.encode(), hashlib.sha256).hexdigest()


def compute_sync_segment_id(uid: str, path: str) -> str:
    """Stable identity for one VAD segment across job-directory changes."""
    secret = os.getenv('SYNC_CONTENT_ID_SECRET') or os.getenv('ENCRYPTION_SECRET')
    if not secret:
        raise RuntimeError('SYNC_CONTENT_ID_SECRET or ENCRYPTION_SECRET is required for durable sync idempotency')
    digest = hashlib.sha256()
    with open(path, 'rb') as audio_file:
        while chunk := audio_file.read(1024 * 1024):
            digest.update(chunk)
    logical_name = Path(path).name
    payload = f'{uid}\n{logical_name}\n{digest.hexdigest()}'
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
