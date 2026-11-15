"""Synthetic scanner identity for existing custody/cursor rehearsals."""

import time

from config.batch_pipeline_leader import UPLOAD_COALESCING_SCAN, UPLOAD_COALESCING_SCAN_TTL
from utils.batch_pipeline.leader import LeaderLease


def scanner(store, *, now=None):
    leader = LeaderLease(
        store,
        UPLOAD_COALESCING_SCAN,
        ttl_seconds=UPLOAD_COALESCING_SCAN_TTL,
        holder='synthetic-scanner',
        clock=time.time if now is None else lambda: now,
    )
    assert leader.acquire()
    return leader
