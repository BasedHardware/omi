"""Privacy-safe, fail-open telemetry for dev parity-pack capture."""

from __future__ import annotations

import logging
import os
from typing import Mapping

from prometheus_client import Counter

logger = logging.getLogger(__name__)

OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL = Counter(
    'omi_parity_pack_capture_events_total',
    'Dev-only parity-pack capture lifecycle events by closed stage, outcome, and reason class',
    ['stage', 'outcome', 'reason_class'],
)

_STAGES = frozenset({'listen', 'allowlist', 'initialize', 'persist', 'export'})
_OUTCOMES = frozenset({'accepted', 'rejected', 'succeeded', 'failed', 'attempted', 'skipped'})
_REASON_CLASSES = frozenset(
    {
        'none',
        'allowed',
        'capture_disabled',
        'stage_not_dev',
        'principal_missing',
        'allowlist_miss',
        'root_invalid',
        'configured',
        'target_unconfigured',
        'root_unconfigured',
        'local_file_missing',
        'upload_error',
        'internal',
        'other',
    }
)

# Export the complete expected lifecycle even before dev traffic arrives. This
# distinguishes a healthy, idle listen scrape target from an absent family.
for _stage, _outcome, _reason_class in (
    ('listen', 'accepted', 'none'),
    ('allowlist', 'accepted', 'allowed'),
    ('allowlist', 'rejected', 'capture_disabled'),
    ('allowlist', 'rejected', 'stage_not_dev'),
    ('allowlist', 'rejected', 'principal_missing'),
    ('allowlist', 'rejected', 'allowlist_miss'),
    ('initialize', 'succeeded', 'none'),
    ('initialize', 'failed', 'root_invalid'),
    ('initialize', 'failed', 'internal'),
    ('persist', 'succeeded', 'none'),
    ('persist', 'failed', 'internal'),
    ('export', 'attempted', 'configured'),
    ('export', 'succeeded', 'none'),
    ('export', 'failed', 'local_file_missing'),
    ('export', 'failed', 'upload_error'),
    ('export', 'failed', 'internal'),
    ('export', 'skipped', 'target_unconfigured'),
    ('export', 'skipped', 'root_unconfigured'),
):
    OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL.labels(
        stage=_stage,
        outcome=_outcome,
        reason_class=_reason_class,
    )


def record_parity_capture_event(
    stage: str,
    outcome: str,
    reason_class: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Emit one bounded dev-only counter/log event without principal or payload data."""
    env = os.environ if environ is None else environ
    if env.get('OMI_ENV_STAGE', '').strip().lower() != 'dev':
        return

    safe_stage = stage if stage in _STAGES else 'other'
    safe_outcome = outcome if outcome in _OUTCOMES else 'other'
    safe_reason = reason_class if reason_class in _REASON_CLASSES else 'other'
    try:
        OMI_PARITY_PACK_CAPTURE_EVENTS_TOTAL.labels(
            stage=safe_stage,
            outcome=safe_outcome,
            reason_class=safe_reason,
        ).inc()
        logger.info(
            'parity_pack_capture_event stage=%s outcome=%s reason_class=%s',
            safe_stage,
            safe_outcome,
            safe_reason,
        )
    except Exception:
        # Observability must never affect a listen session or cassette export.
        pass
