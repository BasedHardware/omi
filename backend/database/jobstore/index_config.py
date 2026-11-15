"""Explicit, per-query discovery-index selection; Firestore retains every durable mutation.

The index mode is selected separately from shadowing. Its default-on kill switch and the mirror write
switch both return discovery to Firestore, while retained-copy erasure keeps its independent target.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from database.jobstore.index_store import INDEX_QUERIES, IndexStore
from database.jobstore.cohort import production_policy_applies
from utils.staging_fence import jobstore_production_mirror_configured

logger = logging.getLogger(__name__)
_OFF = frozenset({'0', 'false', 'off', 'no'})
_INDEXED: dict[str, tuple[Any, frozenset[str], Any]] = {}
_LOCK = threading.Lock()


def selected_queries() -> frozenset[str]:
    raw = os.getenv('JOBSTORE_INDEX_QUERIES', 'due_leased')
    queries = frozenset(part.strip() for part in raw.split(',') if part.strip())
    if not queries <= INDEX_QUERIES:
        logger.warning('event=jobstore_index outcome=refused reason=query_allowlist')
        return frozenset()
    return queries


def reads_enabled() -> bool:
    return (
        os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower() == 'index'
        and os.getenv('JOBSTORE_INDEX_READS', '').strip().lower() not in _OFF
        and os.getenv('JOBSTORE_SHADOW_WRITES', '').strip().lower() not in _OFF
    )


def index_from_env(mirror: Any) -> Any:
    """Reuse one wrapper per mirror/query selection so constructing a store cannot reset its safety sweep."""
    queries = selected_queries()
    if not queries:
        return mirror
    with _LOCK:
        cached = _INDEXED.get(mirror.namespace)
        if cached is not None and cached[0] is mirror and cached[1] == queries:
            return cached[2]
        store = IndexStore(
            mirror,
            enabled_queries=queries,
            enabled=lambda: reads_enabled()
            and selected_queries() == queries
            and (not production_policy_applies(mirror.namespace) or jobstore_production_mirror_configured()),
            observe=mirror.observe_discovery,
        )
        _INDEXED[mirror.namespace] = (mirror, queries, store)
        return store
