"""Content-free, post-commit observations of stored sync speech transfers."""

import logging
import math

from utils.sync.donor_dedupe import DonorDedupe
from utils.sync.live_speech_dedupe import eligible_live_segment, incoming_speech_span, live_speech_bounds
from utils.sync.live_speech_dedupe import bounded_span_seconds, pinned_audio_timeline

logger = logging.getLogger(__name__)

INCOMPLETE_REASONS = (
    'none',
    'target_sync',
    'segment_cap',
    'receipt_cap',
    'unsupported_content',
    'invalid_timing',
    'observation_error',
)


def count_bucket(value: int) -> str:
    return '0' if value == 0 else '1' if value == 1 else '2_5' if value <= 5 else '6_20' if value <= 20 else 'gt_20'


def seconds_bucket(value: float) -> str:
    return (
        '0'
        if value <= 0
        else '0_60' if value <= 60 else '60_300' if value <= 300 else '300_1800' if value <= 1800 else 'gt_1800'
    )


def bridge_observation(
    reference: dict, transfers: list[tuple[list[dict], DonorDedupe]], *, operation: str, target_kind: str
) -> dict:
    """Timing is an alarm only, never deletion authority. Incomplete is unknown.

    Each transfer pairs original absolute donor segments with its DonorDedupe.
    Intervals are unioned per source segment so overlapping live windows cannot
    multiply the measured overlap. No ids or transcript content leave this module.
    """
    observation = {
        'operation': operation,
        'target_kind': target_kind,
        'donor_count_bucket': count_bucket(len(transfers)),
        'kept_seconds_bucket': '0',
        'dropped_seconds_bucket': '0',
        'overlap_seconds_bucket': '0',
        'capture_proof_count_bucket': '0',
        'lexical_proof_count_bucket': '0',
        'exact_retry_count_bucket': '0',
        'outcome': 'bridge_unknown',
        'incomplete_reason': 'observation_error',
    }
    try:
        reason = 'none' if target_kind == 'live' else 'target_sync'
        origin = reference['started_at'].timestamp()
        pinned = pinned_audio_timeline(reference.get('audio_timeline'))
        live_ranges = []
        for segment in reference.get('transcript_segments') or []:
            if not eligible_live_segment(segment):
                continue
            bounds = live_speech_bounds(segment, origin, pinned)
            if bounds is None:
                reason = 'invalid_timing'
            else:
                live_ranges.append(bounds[:2])
        union = []
        for low, high in sorted(live_ranges):
            if union and low <= union[-1][1]:
                union[-1] = (union[-1][0], max(high, union[-1][1]))
            else:
                union.append((low, high))
        kept_seconds = dropped_seconds = overlap_seconds = 0.0
        capture = lexical = retry = 0
        for original, report in transfers:
            reason = report.incomplete_reason if report.incomplete_reason != 'none' else reason
            kept_seconds += bounded_span_seconds(report.kept)
            kept_objects = {id(segment) for segment in report.kept}
            dropped_seconds += bounded_span_seconds(
                [segment for segment in original if id(segment) not in kept_objects]
            )
            capture += report.capture
            lexical += report.lexical
            retry += report.exact_retry
            for segment in report.kept:
                span = incoming_speech_span(segment)
                if span is None:
                    reason = 'invalid_timing'
                    continue
                overlap_seconds += sum(max(0.0, min(span[1], high) - max(span[0], low)) for low, high in union)
        if not math.isfinite(overlap_seconds):
            reason = 'invalid_timing'
            overlap_seconds = 0
        observation.update(
            kept_seconds_bucket=seconds_bucket(kept_seconds),
            dropped_seconds_bucket=seconds_bucket(dropped_seconds),
            overlap_seconds_bucket=seconds_bucket(overlap_seconds),
            capture_proof_count_bucket=count_bucket(capture),
            lexical_proof_count_bucket=count_bucket(lexical),
            exact_retry_count_bucket=count_bucket(retry),
            outcome=(
                'bridge_overlap'
                if target_kind == 'live' and overlap_seconds > 0
                else 'bridge_clear' if reason == 'none' else 'bridge_unknown'
            ),
            incomplete_reason=reason,
        )
    except Exception:
        pass  # Observation failure must never abort content persistence.
    return observation


def log_bridge_observation(observation: dict) -> None:
    """Called only on the successful transaction result, before other effects."""
    try:
        logger.info(
            'event=sync_lineage_resolve stage=bridge outcome=%s operation=%s target_kind=%s '
            'donor_count_bucket=%s kept_seconds_bucket=%s dropped_seconds_bucket=%s overlap_seconds_bucket=%s '
            'capture_proof_count_bucket=%s lexical_proof_count_bucket=%s exact_retry_count_bucket=%s incomplete_reason=%s',
            observation['outcome'],
            observation['operation'],
            observation['target_kind'],
            observation['donor_count_bucket'],
            observation['kept_seconds_bucket'],
            observation['dropped_seconds_bucket'],
            observation['overlap_seconds_bucket'],
            observation['capture_proof_count_bucket'],
            observation['lexical_proof_count_bucket'],
            observation['exact_retry_count_bucket'],
            (
                observation['incomplete_reason']
                if observation['incomplete_reason'] in INCOMPLETE_REASONS
                else 'observation_error'
            ),
        )
    except Exception:
        pass
