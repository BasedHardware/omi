"""Per-upload batch intake routing outcome at the v2 sync admission seam.

One upload request resolves to exactly one outcome when a fresh batch routing
decision is made for it: the upload lands on batch, or a fresh exclusion
(heavy-owner load, language) or the ramp cohort decision sends it to legacy.
Uploads that follow a prior durable owner (a legacy record owner, a legacy
content receipt, a final-pass owner, the live-record provider escape) carry no
fresh decision and are counted by ``omi_legacy_sync_admissions_total`` instead.
"""

from dataclasses import dataclass

from prometheus_client import Counter

from utils.observability.reasons import (
    BatchIntakeOutcome,
    ReasonFamily,
    reason_label,
    reason_values,
)

OUTCOMES = reason_values(BatchIntakeOutcome)
INTAKE_OUTCOMES = Counter(
    'omi_batch_intake_outcome_total',
    'Batch intake routing outcome per v2 sync upload request',
    ('outcome',),
)
# Pre-initialise every child so rate() sees each series from the first scrape.
INTAKE_OUTCOMES.labels(outcome='batch').inc(0)
INTAKE_OUTCOMES.labels(outcome='heavy_excluded').inc(0)
INTAKE_OUTCOMES.labels(outcome='language_excluded').inc(0)
INTAKE_OUTCOMES.labels(outcome='not_cohort').inc(0)


@dataclass
class IntakeRouteEvidence:
    """Fresh exclusion decisions observed while routing one upload request.

    The router owns one instance per request and passes it down as ``evidence``;
    each decision module marks only the exclusion it itself decided, so a flag
    is set iff this request's routing actually hit that exclusion.
    """

    heavy_owner_excluded: bool = False
    language_excluded: bool = False


def record_upload_outcome(outcome: BatchIntakeOutcome | str) -> None:
    """Count one outcome; a non-member folds to ``unknown`` under the reason alert."""

    INTAKE_OUTCOMES.labels(outcome=reason_label(ReasonFamily.SYNC_DISPATCH, outcome, BatchIntakeOutcome)).inc()


def legacy_landing_outcome(
    evidence: IntakeRouteEvidence, *, candidate_batch_enabled: bool
) -> BatchIntakeOutcome | None:
    """Outcome for an upload landing on a legacy job, or None outside the set.

    Heavy-owner exclusion outranks language: it is decided first in the request
    (the ramp runs before record routing), so while both exclusions hold the
    upload stays legacy whichever language toggle moves. ``not_cohort`` is the
    cohort decision itself (the candidate policy never enabled batch).
    """

    if evidence.heavy_owner_excluded:
        return BatchIntakeOutcome.HEAVY_EXCLUDED
    if evidence.language_excluded:
        return BatchIntakeOutcome.LANGUAGE_EXCLUDED
    if not candidate_batch_enabled:
        return BatchIntakeOutcome.NOT_COHORT
    return None
