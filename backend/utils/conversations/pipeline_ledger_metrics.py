"""Bounded-label Prometheus gauges for the C2 ledger census.

The census route refreshes these on every successful read. Stage is a bounded
enum; no uid, conversation id, title or content is ever a label. A missing
sample is covered by the sample-stale alert, never a healthy zero.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from prometheus_client import REGISTRY, Gauge

STUCK_STAGES = ('capturing', 'sealed', 'transcribed', 'noted')


def _gauge(name: str, doc: str, labels: tuple[str, ...] = ()) -> Any:
    return getattr(REGISTRY, '_names_to_collectors', {}).get(name) or Gauge(name, doc, list(labels))


_STUCK_ROWS = _gauge('omi_pipeline_ledger_stuck_rows', 'Stuck ledger rows by stage.', ('stage',))
_STUCK_USERS = _gauge('omi_pipeline_ledger_stuck_users', 'Distinct owners with stuck rows by stage.', ('stage',))
_OLDEST_STUCK = _gauge('omi_pipeline_ledger_oldest_stuck_age_seconds', 'Oldest stuck row age by stage.', ('stage',))
_NEW_STUCK = _gauge('omi_pipeline_ledger_new_stuck_per_hour', 'Rows that became stuck in the last hour.', ('stage',))
_UNKNOWN_END_SHARE = _gauge('omi_pipeline_ledger_unknown_end_type_share', 'Share of rows with an unknown end type.')
_REFRESHED_AT = _gauge('omi_pipeline_ledger_refreshed_at_seconds', 'Unix time of the last census refresh.')


def refresh_gauges(result: Mapping[str, Any]) -> None:
    """Publish the census as bounded-label gauges; never a healthy zero for unknown data."""
    stuck = result.get('stuck') or {}
    new_stuck = (result.get('new_stuck_per_hour') or {}).get('by_stage') or {}
    for stage in STUCK_STAGES:
        _STUCK_ROWS.labels(stage=stage).set(float((stuck.get('by_stage') or {}).get(stage, 0)))
        _STUCK_USERS.labels(stage=stage).set(float((stuck.get('affected_users') or {}).get(stage, 0)))
        _OLDEST_STUCK.labels(stage=stage).set(float((stuck.get('oldest_age_seconds') or {}).get(stage, 0)))
        _NEW_STUCK.labels(stage=stage).set(float(new_stuck.get(stage, 0)))
    _UNKNOWN_END_SHARE.set(float((result.get('end_types') or {}).get('unknown_share', 0.0)))
    _REFRESHED_AT.set(float(result.get('generated_at') or time.time()))
