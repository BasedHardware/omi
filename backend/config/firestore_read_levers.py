"""Rollout gates for Firestore read-reduction levers; every lever defaults off.

One runtime_env key, ``FIRESTORE_READ_LEVERS``, carries a JSON object mapping lever
name to a 0-100 rollout percentage, e.g. ``{"singleton_loops": 100, "listen_poll": 5}``.
A lever is on for a key (uid, pod name) when a stable hash of ``lever:key`` falls
below its percentage. Missing, malformed or out-of-range values mean off.
"""

# LIFECYCLE: permanent

import json
import logging
import os

from config.policy.batch import cohort_bucket
from functools import lru_cache
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ENV_KEY = 'FIRESTORE_READ_LEVERS'

# Every lever the code consults. Unknown names in the env are ignored (and logged once).
KNOWN_LEVERS = frozenset(
    {
        'singleton_loops',
        'listen_poll',
        'listen_credit_backoff',
        'subscription_cache',
        'deletion_marker_cache',
        'usage_month_cache',
        'usage_month_total',
        'request_read_dedupe',
        'serving_config_cache',
        'candidates_page',
        'action_items_page',
        'conversation_page',
        'backfill_task_reads',
        'historical_scan_memo',
        'ledger_purge_coalesce',
        'people_scan_dedupe',
        'queue_age_sample_budget',
        'memory_list_index_window',
        'mcp_conversation_cards_cache',
        'canonical_statuses_dedupe',
        'batch_privacy_memoize',
        'sync_snapshot_resolve_cache',
        'conversation_list_cursor',  # conversations:_collect_visible_conversation_page
        'finjob_candidate_queries',  # conversation_finalization_jobs:{scan_in_progress,get_abandoned_byok,get_stale_processing}
    }
)


@lru_cache(maxsize=4)
def _parse(raw: str) -> Dict[str, int]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning('firestore_read_levers: %s is not valid JSON; all levers off', ENV_KEY)
        return {}
    if not isinstance(data, dict):
        logger.warning('firestore_read_levers: %s is not a JSON object; all levers off', ENV_KEY)
        return {}
    out: Dict[str, int] = {}
    for name, pct in data.items():
        if name not in KNOWN_LEVERS:
            logger.warning('firestore_read_levers: unknown lever %r ignored', name)
            continue
        if isinstance(pct, bool) or not isinstance(pct, int) or not 0 <= pct <= 100:
            logger.warning('firestore_read_levers: lever %r has invalid percentage %r; off', name, pct)
            continue
        out[name] = pct
    return out


def lever_percent(name: str) -> int:
    if name not in KNOWN_LEVERS:
        raise ValueError(f'unknown Firestore read lever: {name}')
    return _parse(os.getenv(ENV_KEY, '')).get(name, 0)


def lever_enabled(name: str, key: Optional[str] = None) -> bool:
    """True when ``name`` is rolled out for ``key``.

    ``key`` is the cohort identity (uid for per-user levers, pod/host name for
    fleet levers). Without a key only 100% counts as on.
    """
    pct = lever_percent(name)
    if pct >= 100:
        return True
    if pct <= 0 or not key:
        return False
    return cohort_bucket(key, name, bits=64, formula='modulo') < pct
