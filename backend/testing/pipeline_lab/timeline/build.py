"""Day timeline from a corpus day: audio islands, VAD map, gaps, lanes, evaluability.

Inputs (store contract): ``corpus/<day_id>/audio/index.json`` and
``corpus/<day_id>/baseline/conversations.jsonl``. Outputs:

- ``corpus/<day_id>/timeline.json``: islands, gaps, per-conversation lane and
  ``evaluable.boundaries``, and the VAD map when requested;
- ``coverage`` in ``corpus/<day_id>/day.json`` (other keys are preserved).

Gaps between stored clips are ``unknown`` (DESIGN L14): the lab cannot tell
silence from audio that was never retained. A conversation's boundaries are
evaluable only when retained audio covers ``margin`` seconds on both sides of
it, because that is the evidence the production boundary decision used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from testing.pipeline_lab.contracts import parse_time
from testing.pipeline_lab.contracts import utc_iso as iso
from testing.pipeline_lab.store import atomic_write_json, lab_root, read_json, read_jsonl

LANE_RECORD = 'record'
LANE_SYNC = 'sync'
LANE_STREAMING = 'streaming'
LANES = (LANE_RECORD, LANE_SYNC, LANE_STREAMING)

# Production's default ``conversation_timeout`` (transcribe.py): the quiet span a
# boundary decision looks at. Overridable per call.
DEFAULT_BOUNDARY_MARGIN_SECONDS = 120.0
# Clips that touch within this tolerance are one island (encoder/frame rounding).
ISLAND_JOIN_SECONDS = 1.0

# Ordered (predicate, lane, evidence). First match wins; the lead can extend the
# table as more baseline fields are confirmed. ``record_lane_owner`` is the field
# config/record_audio.py and config/server_batch.py read.
LaneRule = tuple[Callable[[dict], bool], str, str]
LANE_RULES: tuple[LaneRule, ...] = (
    (lambda r: r.get('record_lane_owner') == 'batch_live_v1', LANE_RECORD, 'record_lane_owner=batch_live_v1'),
    (lambda r: r.get('record_lane_owner') == 'batch_sync_v1', LANE_RECORD, 'record_lane_owner=batch_sync_v1'),
    (
        lambda r: r.get('server_batch_audio_start') is not None or r.get('server_batch_audio_end') is not None,
        LANE_RECORD,
        'server_batch_audio_*',
    ),
    (lambda r: r.get('sync_live_target') is True, LANE_SYNC, 'sync_live_target'),
    (lambda r: bool(r.get('sync_merged_from')), LANE_SYNC, 'sync_merged_from'),
    (lambda r: r.get('source') == 'sdcard', LANE_SYNC, 'source=sdcard'),
)


@dataclass(frozen=True)
class AudioEntry:
    conversation_id: str
    path: str
    start: datetime
    end: datetime
    codec: str | None = None
    sample_rate: int | None = None

    @property
    def seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())


def classify_lane(row: dict) -> dict:
    for predicate, lane, evidence in LANE_RULES:
        try:
            if predicate(row):
                return {'lane': lane, 'evidence': evidence, 'confidence': 'field'}
        except Exception:
            continue
    # No record or sync marker: production's default capture path is streaming
    # /v4/listen. This is an inference, so it is labelled as such.
    return {'lane': LANE_STREAMING, 'evidence': 'no record/sync marker', 'confidence': 'default'}


def load_audio_index(day_dir: Path) -> list[AudioEntry]:
    raw = read_json(day_dir / 'audio' / 'index.json', default=[])
    if isinstance(raw, dict):
        raw = raw.get('entries') or raw.get('files') or []
    entries = []
    for item in raw:
        start, end = parse_time(item.get('start')), parse_time(item.get('end'))
        if start is None or end is None or end < start:
            raise ValueError('audio index entry needs start <= end')
        entries.append(
            AudioEntry(
                str(item['conversation_id']),
                str(item['path']),
                start,
                end,
                item.get('codec'),
                int(item['sample_rate']) if item.get('sample_rate') else None,
            )
        )
    return sorted(entries, key=lambda e: (e.start, e.end, e.conversation_id))


def load_baseline(day_dir: Path) -> list[dict]:
    """Production rows of the day. Lane rules need snapshot fields (``record_lane_owner``, ``source``),
    so the raw rows are preferred; ``conversations.jsonl`` (contract shape) is the fallback."""
    raw = day_dir / 'baseline' / 'raw_conversations.jsonl'
    return list(read_jsonl(raw if raw.exists() else day_dir / 'baseline' / 'conversations.jsonl'))


def build_islands(entries: Sequence[AudioEntry], *, join_seconds: float = ISLAND_JOIN_SECONDS) -> list[dict]:
    islands: list[dict] = []
    for entry in entries:
        last = islands[-1] if islands else None
        if last and entry.start <= last['_end'] + timedelta(seconds=join_seconds):
            last['_end'] = max(last['_end'], entry.end)
            last['conversation_ids'].append(entry.conversation_id)
            last['clips'] += 1
        else:
            islands.append(
                {'_start': entry.start, '_end': entry.end, 'conversation_ids': [entry.conversation_id], 'clips': 1}
            )
    out = []
    for island in islands:
        out.append(
            {
                'start': iso(island['_start']),
                'end': iso(island['_end']),
                'seconds': round((island['_end'] - island['_start']).total_seconds(), 3),
                'clips': island['clips'],
                'conversation_ids': list(dict.fromkeys(island['conversation_ids'])),
            }
        )
    return out


def build_gaps(islands: Sequence[dict], window_start: datetime, window_end: datetime) -> list[dict]:
    gaps, cursor = [], window_start
    for island in islands:
        start, end = parse_time(island['start']), parse_time(island['end'])
        if start > cursor:
            gaps.append({'start': iso(cursor), 'end': iso(min(start, window_end)), 'kind': 'unknown'})
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append({'start': iso(cursor), 'end': iso(window_end), 'kind': 'unknown'})
    return [g for g in gaps if parse_time(g['end']) > parse_time(g['start'])]


def boundary_evaluability(
    row: dict, islands: Sequence[dict], has_audio: bool, *, margin: float = DEFAULT_BOUNDARY_MARGIN_SECONDS
) -> dict:
    if not has_audio:
        return {'boundaries': False, 'reason': 'no_audio'}
    start, end = parse_time(row.get('started_at')), parse_time(row.get('finished_at'))
    if start is None or end is None:
        return {'boundaries': False, 'reason': 'no_baseline_times'}
    pad = timedelta(seconds=margin)
    for island in islands:
        i_start, i_end = parse_time(island['start']), parse_time(island['end'])
        if i_start <= end and start <= i_end:
            before, after = i_start <= start - pad, i_end >= end + pad
            if before and after:
                return {'boundaries': True, 'reason': 'audio_covers_margin'}
            return {'boundaries': False, 'reason': 'gap_before' if not before else 'gap_after'}
    return {'boundaries': False, 'reason': 'audio_outside_conversation'}


VadFn = Callable[[AudioEntry], list[dict]]


def silero_vad_map(day_dir: Path) -> VadFn:
    """Production's local Silero helper over the decoded clip (no hosted VAD)."""

    def run(entry: AudioEntry) -> list[dict]:
        from testing.pipeline_lab.lanes.audio import load_pcm16
        from utils.stt.local_vad import offline_pcm_speech_segments

        return offline_pcm_speech_segments(load_pcm16(day_dir / 'audio' / entry.path, entry))

    return run


def build_day_timeline(
    day_id: str,
    *,
    root=None,
    vad: VadFn | bool | None = None,
    margin: float = DEFAULT_BOUNDARY_MARGIN_SECONDS,
    window: tuple[datetime, datetime] | None = None,
    write: bool = True,
) -> dict:
    day_dir = lab_root(root) / 'corpus' / day_id
    entries = load_audio_index(day_dir)
    baseline = load_baseline(day_dir)
    islands = build_islands(entries)
    audio_by_conversation: dict[str, list[AudioEntry]] = {}
    for entry in entries:
        audio_by_conversation.setdefault(entry.conversation_id, []).append(entry)

    if window is None:
        window = _day_window(day_dir, entries, baseline)
    gaps = build_gaps(islands, *window) if window else []

    conversations = []
    lane_counts = {lane: 0 for lane in LANES}
    for row in sorted(baseline, key=lambda r: (str(r.get('started_at') or ''), str(r.get('id')))):
        cid = str(row.get('id'))
        lane = classify_lane(row)
        lane_counts[lane['lane']] += 1
        has_audio = cid in audio_by_conversation
        conversations.append(
            {
                'id': cid,
                'started_at': row.get('started_at'),
                'finished_at': row.get('finished_at'),
                'discarded': bool(row.get('discarded')),
                'lane': lane['lane'],
                'lane_evidence': lane['evidence'],
                'lane_confidence': lane['confidence'],
                'has_audio': has_audio,
                'audio_seconds': round(sum(e.seconds for e in audio_by_conversation.get(cid, [])), 3),
                'evaluable': boundary_evaluability(row, islands, has_audio, margin=margin),
            }
        )
    baseline_ids = {c['id'] for c in conversations}
    orphan_audio = sorted({e.conversation_id for e in entries} - baseline_ids)

    vad_map = None
    if vad:
        vad_fn = silero_vad_map(day_dir) if vad is True else vad
        vad_map = []
        for entry in entries:
            spans = vad_fn(entry)
            vad_map.append(
                {
                    'conversation_id': entry.conversation_id,
                    'speech': [
                        {
                            'start': iso(entry.start + timedelta(seconds=float(s['start']))),
                            'end': iso(entry.start + timedelta(seconds=float(s['end']))),
                        }
                        for s in spans
                    ],
                    'speech_seconds': round(sum(float(s['end']) - float(s['start']) for s in spans), 3),
                }
            )

    coverage = {
        'audio_seconds': round(sum(e.seconds for e in entries), 3),
        'conversations': len(conversations),
        'with_audio': sum(1 for c in conversations if c['has_audio']),
        'lanes': lane_counts,
        'gaps': gaps,
    }
    timeline = {
        'day_id': day_id,
        'window': {'start': iso(window[0]), 'end': iso(window[1])} if window else None,
        'boundary_margin_seconds': margin,
        'islands': islands,
        'gaps': gaps,
        'conversations': conversations,
        'orphan_audio_conversation_ids': orphan_audio,
        'evaluable_boundaries': sum(1 for c in conversations if c['evaluable']['boundaries']),
        'vad': vad_map,
        'coverage': coverage,
    }
    if write:
        atomic_write_json(day_dir / 'timeline.json', timeline)
        day = read_json(day_dir / 'day.json', default=None) or {'day_id': day_id}
        day['coverage'] = coverage
        atomic_write_json(day_dir / 'day.json', day)
    return timeline


def _day_window(day_dir: Path, entries: Iterable[AudioEntry], baseline: Iterable[dict]):
    day = read_json(day_dir / 'day.json', default=None) or {}
    date, tz = day.get('date'), day.get('timezone')
    if date:
        try:
            from zoneinfo import ZoneInfo

            start = datetime.fromisoformat(str(date)).replace(tzinfo=ZoneInfo(tz or 'UTC'))
            return start, start + timedelta(days=1)
        except (ValueError, KeyError):
            pass
    times: list[Any] = [e.start for e in entries] + [e.end for e in entries]
    for row in baseline:
        times += [parse_time(row.get('started_at')), parse_time(row.get('finished_at'))]
    times = [t for t in times if t is not None]
    return (min(times), max(times)) if times else None
