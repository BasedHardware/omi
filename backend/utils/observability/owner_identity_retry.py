"""Bounded candidate funnel, independent of identity and finalization outcomes."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
from typing import Iterator, Optional

from prometheus_client import REGISTRY, Counter

logger = logging.getLogger(__name__)
PASSES = frozenset({'first', 'late'})
FUNNEL_REASONS = {
    'entry': frozenset({'candidate'}),
    'eligible': frozenset({'candidate'}),
    'skipped': frozenset(
        {
            'slot_limit',
            'scan_limit',
            'pass_limit',
            'missing',
            'not_completed',
            'deleted',
            'discarded',
            'locked',
            'channel_source',
            'private_cloud_disabled',
            'missing_revision',
            'already_resolved_owner',
            'id_mismatch',
            'empty_transcript',
            'manual_receipt_unavailable',
            'read_error',
            'processing_error',
            'submission_error',
        }
    ),
    'cas_refused': frozenset(
        {
            'missing',
            'account_deleting',
            'deleted',
            'discarded',
            'locked',
            'not_completed',
            'revision_changed',
        }
    ),
    'cas_committed': frozenset({'done'}),
    # This stage counts segments per invocation, not candidate attempts.
    'segment_abstained': frozenset({'zero_text_window', 'invalid_text_window'}),
    'resolver_exit': frozenset(
        {
            'resolved',
            'partial',
            'disabled',
            'no_audio',
            'all_short',
            'no_eligible',
            'no_vectors',
            'global_manifest_ambiguity',
            'zero_text_window',
            'invalid_text_window',
            'uncovered_window',
            'manifest_unvalidated',
            'capture_coverage_hole',
            'placement_deadline',
            'no_proven_window',
            'listing_limit',
            'inventory_metadata_invalid',
            'manifest_inventory_invalid',
            'inventory_count_mismatch',
            'inventory_pair_mismatch',
            'blob_missing',
            'blob_read_failed',
            'blob_decode_failed',
            'read_budget',
            'decoded_duration_mismatch',
            'decoded_overlap',
            'decoded_coverage_hole',
            'embedding_budget',
            'embedding_failed',
            'other',
        }
    ),
}
PAIRS = frozenset((stage, reason) for stage, reasons in FUNNEL_REASONS.items() for reason in reasons)


def _counter() -> Counter:
    try:
        return Counter(
            'omi_owner_identity_retry_total',
            'Candidate attempts at first finalization and late identity repair; resolver exits are intermediate',
            ['pass', 'stage', 'reason'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_owner_identity_retry_total']  # type: ignore[attr-defined]


OWNER_IDENTITY_RETRY = _counter()
# Children are lazy: a closed table bounds series without spending capacity on idle zeros.


def record_retry(pass_name: str, stage: str, reason: str, count: int = 1) -> None:
    """Telemetry failure and unknown labels cannot change a product outcome."""
    try:
        if pass_name not in PASSES:
            return
        if (stage, reason) not in PAIRS:
            stage, reason = 'skipped', 'processing_error'
        OWNER_IDENTITY_RETRY.labels(**{'pass': pass_name, 'stage': stage, 'reason': reason}).inc(count)
    except Exception:
        logger.warning('owner_identity_retry_record_failed')


@dataclass
class ResolverTrace:
    pass_name: str
    reason: str = 'other'


_TRACE: ContextVar[Optional[ResolverTrace]] = ContextVar('owner_identity_retry_trace', default=None)


@contextmanager
def identity_pass(pass_name: Optional[str]) -> Iterator[None]:
    """Invocation-local diagnostics only; neither model fields nor stored payloads."""
    token = _TRACE.set(ResolverTrace(pass_name) if pass_name in PASSES else None)
    try:
        yield
    finally:
        _TRACE.reset(token)


def resolver_trace() -> Optional[ResolverTrace]:
    return _TRACE.get()


def resolver_reason(reason: str) -> None:
    trace = _TRACE.get()
    if trace is not None:
        trace.reason = reason if reason in FUNNEL_REASONS['resolver_exit'] else 'other'
