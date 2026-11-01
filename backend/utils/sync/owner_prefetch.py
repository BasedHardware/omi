"""Pipeline future downloads behind the existing serial, epoch-fenced head."""

import logging
import time

from config.sync_owner_concurrency import preparation_width
from database import sync_backfill_sequencer as registry
from utils.other.storage import prefetch_syncing_temporal_file
from utils.sync.staged_prefetch import staged_prefetch

logger = logging.getLogger(__name__)
MAX_PREPARE_SECONDS = 8
MAX_PREPARE_FILES = 20


def warm_owner(uid: str, job_id: str, epoch: int) -> None:
    if preparation_width() <= 1 or not registry.production_stage():
        return
    token = staged_prefetch.acquire(uid)
    if token is None:
        return
    started = time.monotonic()
    files = 0
    cached = 0
    try:
        candidates = registry.preparation_candidates(uid, job_id, epoch)
        for candidate in candidates:
            paths = candidate.get('payload', {}).get('raw_blob_paths', [])
            if not isinstance(paths, list):
                continue
            for path in paths:
                if (
                    preparation_width() <= 1
                    or files >= MAX_PREPARE_FILES
                    or time.monotonic() - started >= MAX_PREPARE_SECONDS
                ):
                    return
                # Never allow a corrupt pending payload to warm arbitrary objects.
                if not isinstance(path, str) or not path.startswith(f'syncing/{uid}/{candidate["job_id"]}/'):
                    continue
                if staged_prefetch.contains(path):
                    continue
                files += 1
                value = prefetch_syncing_temporal_file(path)
                if value is not None:
                    if not staged_prefetch.put(uid, token, path, value):
                        return
                    cached += 1
    except Exception as error:
        # Speculation cannot fail accepted work; the ordinary download is still
        # the authoritative path, with its original retry/error behavior.
        logger.info('event=sync_owner_prefetch outcome=miss exception_type=%s', type(error).__name__)
    finally:
        staged_prefetch.release(uid, token)
        logger.info('event=sync_owner_prefetch outcome=prepared files=%d cached=%d', files, cached)
