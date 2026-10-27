"""Conservative stored-sync transfer policy against a frozen live snapshot.

Callers own the rollout gate and pass the transactionally decoded, pre-merge
reference. No evolving donor union can become evidence for another donor.
"""

from dataclasses import dataclass

from utils.capture.frame_proof import covered_indices
from utils.sync.capture_repeat_evidence import MAX_INCOMING_SEGMENTS, MAX_RECEIPTS, capture_covered_indices
from utils.sync.live_speech_dedupe import MAX_LIVE_SEGMENTS, drop_covered_repeats, drop_proven_exact_retries
from utils.sync.live_speech_dedupe import pinned_audio_timeline


@dataclass(frozen=True)
class DonorDedupe:
    kept: list[dict]
    capture: int = 0
    lexical: int = 0
    exact_retry: int = 0
    incomplete_reason: str = 'none'


def live_reference(row: dict) -> bool:
    return bool(
        row.get('sync_live_target')
        or not row.get('sync_content_revision')
        or (row.get('capture_evidence') or {}).get('origin') == 'live'
    )


def dedupe_donor(incoming: list[dict], donor: dict, live: dict) -> DonorDedupe:
    """Frame coverage, documented lexical fallback, then proven exact retry.

    Inputs already carry absolute ``timestamp`` values; offsets may be rebased.
    Receipt uniqueness is checked over the entire original donor, never slices.
    Over-budget donors stay intact rather than claiming proof on a truncated pool.
    """
    stored = live.get('transcript_segments') or []
    if len(incoming) > MAX_INCOMING_SEGMENTS or len(stored) > MAX_LIVE_SEGMENTS:
        return DonorDedupe(list(incoming), incomplete_reason='segment_cap')
    try:
        evidence = donor.get('capture_evidence')
        receipts = evidence.get('receipts') if isinstance(evidence, dict) else None
        if isinstance(receipts, list) and len(receipts) > MAX_RECEIPTS:
            return DonorDedupe(list(incoming), incomplete_reason='receipt_cap')
        origin = live['started_at'].timestamp()
        verified = capture_covered_indices(incoming, donor.get('capture_evidence'), live.get('capture_evidence'))
        # Unlike capture_repeat_evidence's legacy WAL-context seam, committed
        # frame proof can validate the persisted transcript ledger directly.
        verified |= covered_indices(incoming, donor, [live])
        lexical, report = drop_covered_repeats(
            incoming,
            stored,
            live_origin=origin,
            live_pinned=pinned_audio_timeline(live.get('audio_timeline')),
            verified_capture_indices=verified,
            require_capture_proof=False,
        )
        reference = [dict(segment, timestamp=origin + segment['start']) for segment in stored]
        lexical_kept_ids = {id(segment) for segment in lexical}
        kept, retries, _ = drop_proven_exact_retries(
            [(index, segment) for index, segment in enumerate(incoming) if id(segment) in lexical_kept_ids],
            reference,
            verified_indices=verified,
        )
        capture = report['methods'].count('source_frame_lexical')
        return DonorDedupe(kept, capture, report['dropped_segments'] - capture, retries)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        # Unsupported stored content is preserved; the bridge cannot certify it.
        return DonorDedupe(list(incoming), incomplete_reason='unsupported_content')
