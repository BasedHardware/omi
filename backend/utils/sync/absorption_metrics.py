"""Id-free donor absorption and published-row counters, emitted after commit.

The transaction returns bounded labels from the *pre-redirect* stored donor.
Only its successful result is consumed. Retried intake sees the existing
tombstone, and cleanup/repointing of ancestry never creates another observation.
Like every process-local Prometheus counter, a crash after commit but before
emission/scrape can lose an observation; this is not a durable billing ledger.
"""

from collections.abc import Iterable, Mapping
import logging
from typing import Any

from prometheus_client import Counter

from config.merge_before_processing import already_processed

logger = logging.getLogger(__name__)
SOURCE_KINDS = frozenset({'omi', 'phone', 'desktop', 'sdcard', 'other'})
BOOL_LABELS = ('true', 'false')
OBSERVATIONS_FIELD = '_sync_absorption_observations'
PUBLISHED_FIELD = '_sync_published_observations'

ABSORBED_TOTAL = Counter(
    'omi_sync_bridge_absorbed_total',
    'Committed sync donor absorptions by bounded source kind, intake bridge pending marker and prior enrichment',
    ['source_kind', 'pending', 'processed'],
)
PUBLISHED_TOTAL = Counter(
    'omi_sync_published_rows_total',
    'Committed created sync rows including size rollovers by bounded source kind and intake bridge pending marker',
    ['source_kind', 'pending'],
)


def _prime() -> None:
    for source_kind in SOURCE_KINDS:
        for pending in BOOL_LABELS:
            PUBLISHED_TOTAL.labels(source_kind=source_kind, pending=pending)
            for processed in BOOL_LABELS:
                ABSORBED_TOTAL.labels(source_kind=source_kind, pending=pending, processed=processed)


_prime()


def row_labels(row: Mapping[str, Any]) -> tuple[str, str]:
    source = row.get('source')
    source = getattr(source, 'value', source)
    source_kind = source if isinstance(source, str) and source in SOURCE_KINDS else 'other'
    return source_kind, str(bool(row.get('sync_bridge_pending'))).lower()


def donor_labels(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Use the metadata-only enrichment fence without changing processing policy."""
    processed = row.get('status') == 'completed' and already_processed(row)
    return *row_labels(row), str(bool(processed)).lower()


def absorption_observations(plans: Iterable[Any]) -> list[tuple[str, str, str]]:
    """Called after plan encoding; labels are transient and never written.

    Count direct donors once across all accepted size-rollover plans, excluding
    already redirected tombstones and ancestor redirect repairs.
    """
    observations = []
    seen = set()
    for plan in plans:
        for donor_id in plan.donor_updates:
            row = plan.matched[donor_id]
            if donor_id not in seen and not row.get('deleted') and not row.get('sync_merged_into'):
                observations.append(donor_labels(row))
                seen.add(donor_id)
    return observations


def capture_assignment_metrics(conversation: dict, plans: list[Any]) -> None:
    """Best-effort preparation must never abort the assignment transaction.

    Only accepted plans reach this seam, after all persistence payloads have
    been encoded. Neither observation field is written to Firestore.
    """
    try:
        observations = absorption_observations(plans)
        if observations:
            conversation[OBSERVATIONS_FIELD] = observations
    except Exception:
        logger.warning('event=sync_assignment_metrics phase=capture_absorbed outcome=dropped')
    try:
        seen = set()
        published = []
        for plan in plans:
            if plan.created and plan.canonical not in seen:
                published.append(row_labels(plan.result))
                seen.add(plan.canonical)
        if published:
            conversation[PUBLISHED_FIELD] = published
    except Exception:
        logger.warning('event=sync_assignment_metrics phase=capture_published outcome=dropped')


def record_assignment_metrics(conversation: dict) -> None:
    """Consume each family once after commit; telemetry must not fail intake."""
    for field, counter in ((OBSERVATIONS_FIELD, ABSORBED_TOTAL), (PUBLISHED_FIELD, PUBLISHED_TOTAL)):
        try:
            for observation in conversation.pop(field, []):
                source_kind, pending, *processed = observation
                labels = dict(
                    source_kind=source_kind if source_kind in SOURCE_KINDS else 'other',
                    pending=pending if pending in BOOL_LABELS else 'false',
                )
                if field == OBSERVATIONS_FIELD:
                    labels['processed'] = processed[0] if processed[0] in BOOL_LABELS else 'false'
                counter.labels(**labels).inc()
        except Exception:
            logger.warning('event=sync_assignment_metrics phase=emit outcome=dropped')
