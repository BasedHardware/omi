"""Id-free observations of donor redirects, emitted only after assignment commits.

The transaction returns bounded labels from the *pre-redirect* stored donor.
Only its successful result is consumed. Retried intake sees the existing
tombstone, and cleanup/repointing of ancestry never creates another observation.
Like every process-local Prometheus counter, a crash after commit but before
emission/scrape can lose an observation; this is not a durable billing ledger.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from prometheus_client import Counter

SOURCE_KINDS = frozenset({'omi', 'phone', 'desktop', 'sdcard', 'other'})
BOOL_LABELS = ('true', 'false')
OBSERVATIONS_FIELD = '_sync_absorption_observations'

ABSORBED_TOTAL = Counter(
    'omi_sync_bridge_absorbed_total',
    'Committed sync donor absorptions by bounded source kind, intake bridge pending marker and prior enrichment',
    ['source_kind', 'pending', 'processed'],
)


def _prime() -> None:
    for source_kind in SOURCE_KINDS:
        for pending in BOOL_LABELS:
            for processed in BOOL_LABELS:
                ABSORBED_TOTAL.labels(source_kind=source_kind, pending=pending, processed=processed)


_prime()


def donor_labels(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Inspect stored metadata without decrypting content or changing policy."""
    source = row.get('source')
    source = getattr(source, 'value', source)
    source_kind = source if isinstance(source, str) and source in SOURCE_KINDS else 'other'
    structured = row.get('structured')
    structured = structured if isinstance(structured, Mapping) else {}
    minimum = (
        structured.get('title_provenance') == 'server_minimum'
        or row.get('summary_title_provenance') == 'server_minimum'
    )
    processed = (
        row.get('status') == 'completed'
        and not minimum
        and bool(structured.get('title') or structured.get('overview') or structured.get('sections'))
    )
    return source_kind, str(bool(row.get('sync_bridge_pending'))).lower(), str(bool(processed)).lower()


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


def record_absorptions(conversation: dict) -> None:
    """Consume only the committed result, before retryable external effects."""
    for source_kind, pending, processed in conversation.pop(OBSERVATIONS_FIELD, []):
        try:
            ABSORBED_TOTAL.labels(
                source_kind=source_kind if source_kind in SOURCE_KINDS else 'other',
                pending=pending if pending in BOOL_LABELS else 'false',
                processed=processed if processed in BOOL_LABELS else 'false',
            ).inc()
        except Exception:
            pass
