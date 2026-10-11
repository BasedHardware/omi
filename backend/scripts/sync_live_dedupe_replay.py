"""Offline sync replay: sequential 2-5-segment intakes and source-frame audio plans.

This replays supplied STT candidates, not a transcription provider. A candidate
straddling kept and removed audio is conservatively retained whole and marked
partial_audio; transcript totals are not an estimate of post-trim STT recall.
Audio totals describe the production planner's decoded-sample retention.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.capture_evidence import bounded_envelope, merge_track_receipts
from utils.sync.audio_coverage import MAX_DECODED_FRAMES, MAX_ENVELOPES, plan_unreceived_frames, validated_live_ranges
from utils.sync.capture_repeat_evidence import capture_covered_indices
from utils.sync.live_speech_dedupe import drop_covered_repeats, drop_proven_exact_retries


def _segments(payload: dict, name: str) -> list[dict]:
    rows = payload.get(name)
    if not isinstance(rows, list):
        raise ValueError('segments must be lists')
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str):
            raise ValueError('segments require text and absolute endpoints')
        start, end = row.get('start'), row.get('end')
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
        ):
            raise ValueError('endpoints must be numbers')
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end) or end <= start or not math.isfinite(end - start):
            raise ValueError('endpoints must form a finite positive interval')
        result.append(dict(row, start=start, end=end))
    return result


def _integer(value: object, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError('frame coordinates must be nonnegative integers')
    return value


def _audio_plan(payload: dict) -> tuple[list[dict], dict]:
    coverage = payload.get('audio_coverage')
    if coverage is None:
        return [], {}
    if not isinstance(coverage, dict):
        raise ValueError('audio_coverage must be an object')
    envelopes, wals = coverage.get('live_received_ranges'), coverage.get('wal_frames')
    if (
        not isinstance(envelopes, list)
        or not isinstance(wals, list)
        or len(wals) > 20
        or len(envelopes) > MAX_ENVELOPES
    ):
        raise ValueError('coverage requires bounded live_received_ranges and wal_frames lists')
    prepared = []
    evidence_abstained = False
    for wal in wals:
        if not isinstance(wal, dict):
            raise ValueError('WAL descriptions must be objects')
        samples = wal.get('frame_samples')
        if not isinstance(samples, list) or not samples or len(samples) > MAX_DECODED_FRAMES:
            raise ValueError('WAL requires bounded decoded frame_samples')
        samples = [_integer(value, 1) for value in samples]
        first = _integer(wal.get('source_frame_start'))
        rate = _integer(wal.get('rate_hz'), 1)
        declared_count = _integer(wal.get('frame_count', len(samples)), 1)
        if len(samples) > declared_count:
            raise ValueError('decoded frames exceed the declared WAL frame count')
        claim = {
            'capture_root': wal.get('capture_root'),
            'clock_epoch': _integer(wal.get('clock_epoch')),
            'source_frame_start': first,
            'frame_count': declared_count,
            'rate_hz': rate,
            'channel': wal.get('channel', 'mono'),
            'codec': wal.get('codec', 'pcm16'),
        }
        wall_start = wal.get('wal_start_seconds')
        if wall_start is not None and (
            type(wall_start) not in (int, float) or not math.isfinite(wall_start) or wall_start <= 0
        ):
            raise ValueError('WAL wall start must be a finite positive number')
        received = validated_live_ranges(claim, envelopes, wal_start_seconds=wall_start, frame_samples=samples)
        evidence_abstained = evidence_abstained or received is None
        keep = (
            plan_unreceived_frames(samples, received, frame_start=first, sample_rate=rate)
            if received is not None
            else None
        )
        without_context = (
            plan_unreceived_frames(samples, received, frame_start=first, sample_rate=rate, context_seconds=0)
            if received is not None
            else None
        )
        offsets = [0]
        for count in samples:
            offsets.append(offsets[-1] + count)
        prepared.append((first, first + len(samples), rate, offsets, keep, without_context))
    plans, output = [], []
    kept_seconds, dropped_seconds, context_seconds = [], [], []
    for index, (first, last, rate, offsets, keep, without_context) in enumerate(prepared):
        abstained = evidence_abstained or keep is None
        retained = ((first, last),) if evidence_abstained or keep is None else keep
        retained_samples = sum(offsets[end - first] - offsets[start - first] for start, end in retained)
        novel_samples = (
            retained_samples
            if abstained or without_context is None
            else sum(offsets[end - first] - offsets[start - first] for start, end in without_context)
        )
        seconds = retained_samples / rate
        removed = (offsets[-1] - retained_samples) / rate
        margin = (retained_samples - novel_samples) / rate
        kept_seconds.append(seconds)
        dropped_seconds.append(removed)
        context_seconds.append(margin)
        plans.append({'domain': (first, last), 'keep': retained})
        output.append(
            {
                'wal_index': index,
                'decision': (
                    'abstained'
                    if abstained
                    else 'covered' if not retained else 'trimmed' if retained != ((first, last),) else 'kept'
                ),
                'kept_frame_ranges': [list(span) for span in retained],
                'kept_seconds': seconds,
                'dropped_seconds': removed,
                'context_seconds': margin,
            }
        )
    return plans, {
        'files': output,
        'totals': {
            'kept_seconds': math.fsum(kept_seconds),
            'dropped_seconds': math.fsum(dropped_seconds),
            'context_seconds': math.fsum(context_seconds),
        },
    }


def _audio_state(segment: dict, plans: list[dict]) -> tuple[bool, bool]:
    keys = ('wal_index', 'source_frame_start', 'source_frame_end')
    if not any(key in segment for key in keys):
        return False, False
    if not all(key in segment for key in keys):
        raise ValueError('segment capture coordinates must be complete')
    index, start, end = (_integer(segment[key]) for key in keys)
    if index >= len(plans) or end <= start:
        raise ValueError('segment capture coordinates are outside WAL')
    plan = plans[index]
    if start < plan['domain'][0] or end > plan['domain'][1]:
        raise ValueError('segment capture coordinates are outside WAL')
    kept = sum(max(0, min(end, high) - max(start, low)) for low, high in plan['keep'])
    return kept == 0, 0 < kept < end - start


def _batch_evidence(envelope: Any, batch: list[dict]) -> Any:
    if not isinstance(envelope, dict) or not isinstance(envelope.get('receipts'), list):
        return envelope
    ids = {row.get('id') for row in batch if isinstance(row.get('id'), str)}
    return dict(
        envelope, receipts=[r for r in envelope['receipts'] if isinstance(r, dict) and r.get('segment_id') in ids]
    )


def _persisted_evidence(existing: Any, incoming: Any) -> Any:
    if incoming is None:
        return existing
    if not isinstance(incoming, dict) or (existing is not None and not isinstance(existing, dict)):
        raise ValueError('capture envelopes must be objects')
    contributors = [existing or {}, incoming]
    mapped = [r for item in contributors for r in item.get('receipts') or []]
    if not mapped:
        return incoming
    combined = merge_track_receipts([], mapped)
    if any(
        item.get('capability') != 'source_position' or item.get('coverage') == 'incomplete' for item in contributors
    ):
        combined['coverage'] = 'incomplete'
    return bounded_envelope(combined)


def replay(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('input must be an object')
    live, sync = _segments(payload, 'live_segments'), _segments(payload, 'sync_segments')
    sizes = payload.get('intake_sizes', [2, 3, 4, 5])
    if (
        not isinstance(sizes, list)
        or not sizes
        or len(sizes) > 64
        or any(type(n) is not int or not 2 <= n <= 5 for n in sizes)
    ):
        raise ValueError('intake_sizes must contain integers from 2 through 5')
    audio_plans, audio_output = _audio_plan(payload)
    existing = [dict(row, timestamp=row['start']) for row in live]
    live_evidence = payload.get('live_capture_evidence')
    decisions, intakes, kept_durations, dropped_durations = [], [], [], []
    cursor, intake_index = 0, 0
    while cursor < len(sync):
        size = sizes[intake_index % len(sizes)]
        if len(sync) - cursor == size + 1:
            size += 1 if size < 5 else -1
        stop = min(len(sync), cursor + size)
        batch = sync[cursor:stop]
        incoming = [
            dict(
                row,
                timestamp=row['start'],
                start=0.0,
                end=row['end'] - row['start'],
                speaker_id_scope=row.get('speaker_id_scope') or f'sync:replay:{intake_index}',
            )
            for row in batch
        ]
        states = [_audio_state(row, audio_plans) for row in batch]
        incoming_evidence = _batch_evidence(payload.get('sync_capture_evidence'), batch)
        verified = capture_covered_indices(incoming, incoming_evidence, live_evidence)
        eligible_indices = [i for i, state in enumerate(states) if not state[0]]
        eligible = [incoming[i] for i in eligible_indices]
        eligible_proof = frozenset(i for i, original_index in enumerate(eligible_indices) if original_index in verified)
        lexical_kept, report = drop_covered_repeats(
            eligible, existing, live_origin=0.0, live_pinned=False, verified_capture_indices=eligible_proof
        )
        lexical_ids = {id(row) for row in lexical_kept}
        kept, _, _ = drop_proven_exact_retries(
            [(i, row) for i, row in enumerate(eligible) if id(row) in lexical_ids],
            existing,
            verified_indices=eligible_proof,
        )
        kept_ids, methods = {id(row) for row in kept}, iter(report['methods'])
        appended = []
        for offset, (original, segment) in enumerate(zip(batch, incoming)):
            covered, partial = states[offset]
            retained = id(segment) in kept_ids
            reason = (
                'audio_received_repeat'
                if covered
                else (
                    'lexical_repeat:' + next(methods)
                    if id(segment) not in lexical_ids
                    else (
                        'exact_sync_retry'
                        if not retained
                        else 'partial_audio_candidate_retained' if partial else 'not_proven_same_capture'
                    )
                )
            )
            duration = original['end'] - original['start']
            (kept_durations if retained else dropped_durations).append(duration)
            decisions.append(
                {
                    'index': cursor + offset,
                    'start': original['start'],
                    'end': original['end'],
                    'decision': 'kept' if retained else 'dropped',
                    'reason': reason,
                    'partial_audio': partial,
                }
            )
            if retained:
                appended.append(
                    dict(original, timestamp=original['start'], speaker_id_scope=segment['speaker_id_scope'])
                )
        if appended:
            live_evidence = _persisted_evidence(live_evidence, incoming_evidence)
        existing.extend(appended)
        intakes.append(
            {
                'index': intake_index,
                'first_segment': cursor,
                'segment_count': len(batch),
                'appended_segments': len(appended),
            }
        )
        cursor, intake_index = stop, intake_index + 1
    result = {
        'semantics': 'supplied_stt_candidates; partial_audio_candidates_retained_whole; not_post_trim_stt_recall',
        'segments': decisions,
        'intakes': intakes,
        'totals': {
            'kept_segments': len(kept_durations),
            'dropped_segments': len(dropped_durations),
            'kept_seconds': math.fsum(kept_durations),
            'dropped_seconds': math.fsum(dropped_durations),
        },
    }
    if audio_output:
        result['audio_coverage'] = audio_output
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'input', type=Path, help='Local JSON with absolute segment times and optional source-frame descriptions'
    )
    args = parser.parse_args()
    try:
        result = replay(json.loads(args.input.read_text(encoding='utf-8')))
    except (OSError, ValueError, OverflowError, TypeError):
        parser.exit(
            2, 'Replay input must be readable JSON with valid text, finite intervals and bounded capture coordinates.\n'
        )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
