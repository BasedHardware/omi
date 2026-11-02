"""Legacy staging cleanup requires a completed ledger and surviving originals.

The receipt is stored alongside the content-ledger success result. Old jobs with
no receipt retain their staging; neither a terminal failure nor time alone is
permission to destroy the last server copy. Privacy erasure uses its own purge.
"""

import base64
import hashlib
import logging
import os
from pathlib import Path
import json
from collections.abc import Iterable, Sequence
from typing import TypedDict

from google.api_core.exceptions import NotFound

from database import _client as firestore_clients, sync_ledger
from utils.audio_cleanup_custody import cleanup_hold_reason
from utils.other import local_storage, storage
from utils.request_validation import parse_sync_filename_timestamp

logger = logging.getLogger(__name__)


class OriginalCustody(TypedDict):
    path: str
    archive: str
    sha256: str


class StagedCustody(TypedDict):
    path: str
    md5: str


class StagingCustodyReceipt(TypedDict):
    version: int
    originals: list[OriginalCustody]
    staging: list[StagedCustody]


def _digests(path: str) -> tuple[str, str]:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with open(path, 'rb') as source:
        while chunk := source.read(1024 * 1024):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), base64.b64encode(md5.digest()).decode()


def make_staging_custody_receipt(
    uid: str, raw_paths: Sequence[str], archive_paths: Sequence[str]
) -> StagingCustodyReceipt | None:
    """Bind every source byte to an archive; generated segments are derivatives.

    This runs before local cleanup and before the completion ledger commit.
    Archive paths contain the plaintext SHA-256 minted by archive_capture_bytes.
    Cleanup rechecks those archive objects before deleting generation-pinned
    staging, and compares staging MD5 to these original local bytes.
    """
    if not raw_paths or not archive_paths:
        return None
    originals: list[OriginalCustody] = []
    digests: dict[str, str] = {}
    for path in raw_paths:
        sha, md5 = _digests(path)
        digests[path] = md5
        candidates = [
            archive
            for archive in archive_paths
            if archive
            in {
                f'raw-sync/{uid}/{Path(path).name}/{sha}.bin',
                f'raw-sync/{uid}/{Path(path).name}/{sha}.bin.enc',
                f'raw-mobile-batch/{uid}/{Path(path).name}/{sha}.bin',
                f'raw-mobile-batch/{uid}/{Path(path).name}/{sha}.bin.enc',
            }
        ]
        if len(candidates) != 1:
            return None
        originals.append({'path': path, 'archive': candidates[0], 'sha256': sha})
    staging: list[StagedCustody] = []
    for path in dict.fromkeys(raw_paths):
        if not path.startswith(f'syncing/{uid}/') or any(part in {'.', '..'} for part in path.split('/')):
            return None
        md5 = digests[path] if path in digests else _digests(path)[1]
        staging.append({'path': path, 'md5': md5})
    return {'version': 1, 'originals': originals, 'staging': staging}


def add_staging_derivatives(
    uid: str, receipt: StagingCustodyReceipt | None, segment_paths: Iterable[str]
) -> StagingCustodyReceipt | None:
    if not receipt:
        return None
    staging = list(receipt['staging'])
    for path in sorted(segment_paths):
        if not path.startswith(f'syncing/{uid}/') or any(part in {'.', '..'} for part in path.split('/')):
            return None
        staging.append({'path': path, 'md5': _digests(path)[1]})
    result: StagingCustodyReceipt = {**receipt, 'staging': staging}
    # Custody bookkeeping must not turn a successful long capture into an
    # oversized Firestore completion. Missing proof always retains staging.
    return result if len(json.dumps(result).encode()) <= 128 * 1024 else None


def cleanup_sync_staging(
    paths: Sequence[str], *, uid: str | None = None, content_id: str | None = None, job_id: str | None = None
) -> int:
    """Fail closed on missing receipts, storage/ledger errors, or held ranges."""
    if not uid or not content_id or not job_id:
        logger.info('event=sync_staging_cleanup outcome=retained reason=missing_receipt')
        return 0
    ledger = (
        sync_ledger.sync_content_reference(firestore_clients.get_firestore_client(), uid, content_id).get().to_dict()
        or {}
    )
    result = ledger.get('result') or {}
    receipt = ledger.get('staging_custody') or {}
    if (
        ledger.get('status') != 'completed'
        or ledger.get('job_id') != job_id
        or not sync_ledger.is_valid_completed_sync_content_result(result)
        or receipt.get('version') != 1
        or not receipt.get('originals')
        or not receipt.get('staging')
    ):
        logger.info('event=sync_staging_cleanup outcome=retained reason=unproven_success')
        return 0
    staging = {item['path']: item['md5'] for item in receipt['staging']}
    if any(
        path not in staging
        or not path.startswith(f'syncing/{uid}/')
        or any(part in {'.', '..'} for part in path.split('/'))
        for path in paths
    ):
        logger.warning('event=sync_staging_cleanup outcome=retained reason=source_mismatch')
        return 0
    # Check the original capture range, not a VAD fragment's timestamp. Legacy
    # filenames lack a certified end, so pre-window unknown ends remain held.
    for original in receipt['originals']:
        archive = original['archive']
        if (
            original['path'] not in staging
            or not archive.startswith((f'raw-sync/{uid}/', f'raw-mobile-batch/{uid}/'))
            or any(part in {'.', '..'} for part in archive.split('/'))
        ):
            return 0
        try:
            capture_at = parse_sync_filename_timestamp(original['path'])
        except ValueError:
            capture_at = None
        reason = cleanup_hold_reason(capture_at)
        if reason:
            logger.info('event=sync_staging_cleanup outcome=held reason=%s', reason)
            return 0
        blob = storage.get_private_cloud_sync_bucket().blob(archive)
        blob.reload()
        if (blob.metadata or {}).get('sha256') != original['sha256']:
            logger.warning('event=sync_staging_cleanup outcome=retained reason=archive_mismatch')
            return 0
    cleaned = 0
    storage_client = local_storage.create_storage_client()
    for path in paths:
        for name in dict.fromkeys(filter(None, (storage.syncing_local_bucket, os.getenv('BUCKET_AUDIO_DERIVED')))):
            bucket = storage_client.bucket(name)
            blob = bucket.blob(path)
            try:
                blob.reload()
                generation = getattr(blob, 'generation', None)
                if getattr(blob, 'md5_hash', None) != staging[path] or generation is None:
                    logger.warning('event=sync_staging_cleanup outcome=retained reason=generation_changed')
                    continue
                with storage.owner_storage_write_gate(uid, bucket):
                    blob.delete(if_generation_match=int(generation))
                cleaned += 1
            except NotFound:
                pass
    return cleaned
