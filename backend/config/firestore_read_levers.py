"""Rollout gates for Firestore read-reduction levers; levers default off unless listed in DEFAULT_PERCENTAGES.

One runtime_env key, ``FIRESTORE_READ_LEVERS``, carries a JSON object mapping lever
name to a 0-100 rollout percentage, e.g. ``{"singleton_loops": 100, "listen_poll": 5}``.
A lever is on for a key (uid, pod name) when a stable hash of ``lever:key`` falls
below its percentage. Missing values use DEFAULT_PERCENTAGES (otherwise off); invalid explicit percentages mean off.
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
        'batch_timeliness_leader',  # ship-on election and capped backlog counts; 0 restores legacy sampling
        'batch_metrics_oldest_leader',  # ship-on queue sample election; 0 restores per-instance reads
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
        'bpp_generation_memo',  # batch privacy task-attempt memo; absent = 0/off
        'privacy_checks_shadow',  # compares live decisions; never authorizes writes
        'privacy_negative_lookup_cache',  # WQ26-token-certified NOT_FOUND reads; 0 is the kill switch
        'legal_hold_fence_cache',
        'privacy_session_token',
        'tombstone_negative_cache',
        'sync_snapshot_resolve_cache',
        'episode_members_singleflight',  # ship-on: concurrent identical reads only; 0 restores independent reads
        'episode_members_cache',  # Home member projections may be stale for <= 60s; absent = 0/off
        'conversation_list_cursor',  # conversations:_collect_visible_conversation_page
        'finjob_candidate_queries',  # conversation_finalization_jobs:{scan_in_progress,get_abandoned_byok,get_stale_processing}
        'bpp_decision_cache',  # batch privacy: token-validated generation reuse across attempts, <= 60s
        'bpp_attempt_scope',  # batch privacy: per-call attempt scope for store.run + retention entry points
        'bpp_token_mint',  # batch privacy: lazily mint memo tokens so decisions become memo-eligible
        'privacy_ttl60',  # legal-hold fence, tombstone and deletion-marker decisions reused <= 60s, no token read
        'action_items_ttl120',  # action_items_cache: 120s default reuse under action_items_page
        'lifecycle_record_pending_head',  # lifecycle_metrics_queries:record_pending head(1)+count, key=serving replica
        'admission_frontier_hint',  # ship-on: owner activation reads the service frontier outside the txn; 0 restores the txn query
        'sync_allowance_single_resolve',  # ship-on: one admission answer; 0 restores the legacy two-call race
    }
)


DEFAULT_PERCENTAGES = {
    'episode_members_cache': 0,
    'episode_members_singleflight': 100,
    'batch_metrics_oldest_leader': 100,
    'batch_timeliness_leader': 100,
    'admission_frontier_hint': 100,
    'sync_allowance_single_resolve': 100,
}


@lru_cache(maxsize=4)
def _parse(raw: str) -> Dict[str, int]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning('firestore_read_levers: %s is not valid JSON; using lever defaults', ENV_KEY)
        return {}
    if not isinstance(data, dict):
        logger.warning('firestore_read_levers: %s is not a JSON object; using lever defaults', ENV_KEY)
        return {}
    out: Dict[str, int] = {}
    for name, pct in data.items():
        if name not in KNOWN_LEVERS:
            logger.warning('firestore_read_levers: unknown lever %r ignored', name)
            continue
        if isinstance(pct, bool) or not isinstance(pct, int) or not 0 <= pct <= 100:
            logger.warning('firestore_read_levers: lever %r has invalid percentage %r; off', name, pct)
            out[name] = 0
            continue
        out[name] = pct
    return out


def lever_percent(name: str) -> int:
    if name not in KNOWN_LEVERS:
        raise ValueError(f'unknown Firestore read lever: {name}')
    return _parse(os.getenv(ENV_KEY, '')).get(name, DEFAULT_PERCENTAGES.get(name, 0))


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
