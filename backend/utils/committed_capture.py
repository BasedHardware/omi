"""Committed live-capture proof producer state; pure, no storage or network deps.

A committed envelope claims coverage only for transcript segments that the
transcript transaction itself committed, anchored to the receipt runs that
carried their audio. The emitted envelope carries capture identity and
positions only — never text, uid, row ids, or segment ids. In process memory
the map keys pending notes by transcript segment id and acknowledgements by
conversation id; that state is per-session, bounded, and never persisted or
logged. Receipt-only evidence is produced
elsewhere; this map never fabricates coverage it did not observe.
"""

from __future__ import annotations

import math
import uuid
from typing import Iterable

MAX_COMMITTED_RUNS = 32
MAX_LIFETIME_HISTORY = 16
MAX_TRANSCRIPT_NOTES = 512
MAX_WORD_NOTE_INTERVALS = 256
MAX_ACK_GENERATIONS = 16
MAX_WALL_ANCHOR_DRIFT_SECONDS = 2.0
MAX_RUN_DURATION_SECONDS = 30.0
PROOF_KIND = 'committed_transcript_v1'


class CommittedCaptureMap:
    """Receipt-anchored source-frame runs plus transcript sample notes for one socket."""

    def __init__(self) -> None:
        self.runs: list[dict] = []
        self.history: list[dict] = []
        self.notes: dict[str, tuple[tuple[int, int], ...]] = {}
        self.complete = True
        self.incomplete = False
        self.conflicts = 0
        self._highwater: dict[tuple, int] = {}
        self._root_epoch: dict[str, int] = {}
        self._root_rate: dict[str, int] = {}
        self._last_wall: float | None = None
        self._acks: dict[str, list[dict]] = {}

    def _conflict(self) -> None:
        self.conflicts += 1

    def accept(
        self,
        claim: dict | None,
        *,
        sample_start: int,
        sample_count: int,
        rate_hz: int,
        receipt_wall_time: float | None,
    ) -> None:
        if claim is None:
            self.incomplete = True
            self.complete = False
            return
        if not self.complete:
            return
        root = claim['capture_root']
        epoch = claim['clock_epoch']
        ordinal = claim['source_frame']
        prior_epoch = self._root_epoch.get(root)
        if prior_epoch is not None and epoch < prior_epoch:
            self._conflict()
            return
        prior_rate = self._root_rate.get(root)
        if prior_rate is not None and prior_rate != rate_hz:
            self._conflict()
            return
        key = (root, epoch)
        highwater = self._highwater.get(key)
        if highwater is not None and ordinal <= highwater:
            self._conflict()
            return
        if sample_start < 0 or sample_count <= 0 or rate_hz <= 0:
            self._conflict()
            return
        if receipt_wall_time is None:
            self.complete = False
            return
        if type(receipt_wall_time) not in (int, float) or not math.isfinite(receipt_wall_time):
            self._conflict()
            return
        if self._last_wall is not None and receipt_wall_time < self._last_wall:
            self._conflict()
            return
        if key not in self._highwater and len(self._highwater) >= MAX_LIFETIME_HISTORY:
            self.complete = False
            return
        if root not in self._root_epoch and len(self._root_epoch) >= MAX_LIFETIME_HISTORY:
            self.complete = False
            return
        self._root_epoch[root] = epoch
        self._root_rate[root] = rate_hz
        self._highwater[key] = ordinal
        self._last_wall = receipt_wall_time
        wall_end = receipt_wall_time
        wall_start = receipt_wall_time - sample_count / rate_hz
        if self.runs:
            tail = self.runs[-1]
            if (
                tail['capture_root'] == root
                and tail['clock_epoch'] == epoch
                and tail['source_frame_end'] == ordinal
                and tail['decoded_sample_end'] == sample_start
                and tail['samples_per_frame'] == sample_count
                and tail['rate_hz'] == rate_hz
            ):
                predicted = tail['receipt_wall_start'] + (ordinal - tail['source_frame_start']) * (
                    tail['samples_per_frame'] / tail['rate_hz']
                )
                if (
                    abs(wall_start - predicted) <= MAX_WALL_ANCHOR_DRIFT_SECONDS
                    and wall_end - tail['receipt_wall_start'] <= MAX_RUN_DURATION_SECONDS
                ):
                    tail['source_frame_end'] += 1
                    tail['decoded_sample_end'] += sample_count
                    tail['receipt_wall_end'] = wall_end
                    self._extend_history(root, epoch, ordinal, wall_start, wall_end, rate_hz)
                    return
        self.runs.append(
            {
                'capture_root': root,
                'clock_epoch': epoch,
                'source_frame_start': ordinal,
                'source_frame_end': ordinal + 1,
                'decoded_sample_start': sample_start,
                'decoded_sample_end': sample_start + sample_count,
                'samples_per_frame': sample_count,
                'rate_hz': rate_hz,
                'channel': 'mono',
                'receipt_wall_start': wall_start,
                'receipt_wall_end': wall_end,
            }
        )
        if len(self.runs) > MAX_COMMITTED_RUNS:
            self.runs.pop(0)
            self.incomplete = True
        self._extend_history(root, epoch, ordinal, wall_start, wall_end, rate_hz)

    def _extend_history(
        self, root: str, epoch: int, ordinal: int, wall_start: float, wall_end: float, rate_hz: int
    ) -> None:
        for entry in self.history:
            if entry['capture_root'] == root and entry['clock_epoch'] == epoch:
                entry['source_frame_end'] = max(entry['source_frame_end'], ordinal + 1)
                entry['receipt_wall_start'] = min(entry['receipt_wall_start'], wall_start)
                entry['receipt_wall_end'] = max(entry['receipt_wall_end'], wall_end)
                return
        if len(self.history) >= MAX_LIFETIME_HISTORY:
            self.complete = False
            return
        self.history.append(
            {
                'capture_root': root,
                'clock_epoch': epoch,
                'source_frame_start': ordinal,
                'source_frame_end': ordinal + 1,
                'receipt_wall_start': wall_start,
                'receipt_wall_end': wall_end,
                'rate_hz': rate_hz,
            }
        )

    @staticmethod
    def _note_intervals(raw) -> tuple[tuple[int, int], ...] | None:
        if not isinstance(raw, (list, tuple)) or not raw or len(raw) > MAX_WORD_NOTE_INTERVALS:
            return None
        intervals = []
        for pair in raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return None
            start, end = pair
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                return None
            intervals.append((start, end))
        return tuple(intervals)

    def remember_transcripts(self, segments: Iterable[dict]) -> None:
        if len(self.notes) >= MAX_TRANSCRIPT_NOTES:
            self.incomplete = True
            return
        for index, segment in enumerate(segments):
            if index >= MAX_TRANSCRIPT_NOTES:
                self.incomplete = True
                return
            note = self._note_intervals(segment.get('_capture_word_ranges'))
            if note is None:
                continue
            segment_id = segment.get('id')
            if not segment_id:
                segment_id = segment['id'] = str(uuid.uuid4())
            prior = self.notes.get(segment_id)
            if prior is not None:
                if prior != note:
                    self._conflict()
                continue
            self.notes[segment_id] = note
            if len(self.notes) >= MAX_TRANSCRIPT_NOTES:
                self.incomplete = True
                return

    def committed_snapshot(self, owner: str, segments: Iterable) -> dict | None:
        if not self.complete or self.conflicts:
            return None
        fresh: list[dict] = []
        for segment in segments:
            if getattr(segment, 'audio_alignment', None) == 'unplaced' or not getattr(segment, 'text', None):
                continue
            start = getattr(segment, 'start', None)
            end = getattr(segment, 'end', None)
            if (
                not isinstance(start, (int, float))
                or isinstance(start, bool)
                or not isinstance(end, (int, float))
                or isinstance(end, bool)
            ):
                continue
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                continue
            segment_id = getattr(segment, 'id', None)
            if type(segment_id) is not str:
                continue
            note = self.notes.get(segment_id)
            if note is None:
                continue
            for interval in note:
                fresh.extend(self._note_runs(interval))
        committed = self._union_runs([*fresh, *self._acks.get(owner, ())])
        if not committed or len(committed) > MAX_COMMITTED_RUNS:
            return None
        return {
            'version': 1,
            'capability': 'source_position',
            'origin': 'live',
            'proof': PROOF_KIND,
            'coverage': 'incomplete' if self.incomplete else 'mapped',
            'conflicts': self.conflicts,
            'runs': committed,
            'lifetime': {
                'version': 1,
                'complete': True,
                'conflicts': self.conflicts,
                'history': [dict(entry) for entry in self.history],
            },
        }

    def acknowledge(self, owner: str | None, snapshot: dict | None) -> None:
        if owner is None or not isinstance(snapshot, dict) or snapshot.get('proof') != PROOF_KIND:
            return
        runs = [dict(run) for run in snapshot.get('runs') or () if isinstance(run, dict)]
        union = self._union_runs([*self._acks.get(owner, ()), *runs])
        if len(union) > MAX_COMMITTED_RUNS:
            return
        self._acks[owner] = union
        if len(self._acks) > MAX_ACK_GENERATIONS:
            self._acks.pop(next(iter(self._acks)))

    def _note_runs(self, note: tuple[int, int]) -> list[dict]:
        start, end = note
        found: list[dict] = []
        for run in self.runs:
            low = max(start, run['decoded_sample_start'])
            high = min(end, run['decoded_sample_end'])
            if high <= low:
                continue
            stride = run['samples_per_frame']
            first = -(-(low - run['decoded_sample_start']) // stride)
            last = (high - run['decoded_sample_start']) // stride
            if last <= first:
                continue
            frame_start = run['source_frame_start'] + first
            frame_end = run['source_frame_start'] + last
            decoded_start = run['decoded_sample_start'] + first * stride
            decoded_end = run['decoded_sample_start'] + last * stride
            seconds_per_frame = stride / run['rate_hz']
            found.append(
                {
                    'capture_root': run['capture_root'],
                    'clock_epoch': run['clock_epoch'],
                    'source_frame_start': frame_start,
                    'source_frame_end': frame_end,
                    'decoded_sample_start': decoded_start,
                    'decoded_sample_end': decoded_end,
                    'samples_per_frame': stride,
                    'rate_hz': run['rate_hz'],
                    'channel': 'mono',
                    'receipt_wall_start': run['receipt_wall_start'] + first * seconds_per_frame,
                    'receipt_wall_end': run['receipt_wall_start'] + last * seconds_per_frame,
                }
            )
        return found

    @staticmethod
    def _merge_run(tail: dict, run: dict) -> bool:
        if (
            tail['capture_root'] != run['capture_root']
            or tail['clock_epoch'] != run['clock_epoch']
            or tail['samples_per_frame'] != run['samples_per_frame']
            or tail['rate_hz'] != run['rate_hz']
        ):
            return False
        if (
            run['source_frame_start'] > tail['source_frame_end']
            or run['decoded_sample_start'] > tail['decoded_sample_end']
        ):
            return False
        stride = tail['samples_per_frame']
        tail_axis = tail['decoded_sample_start'] - tail['source_frame_start'] * stride
        run_axis = run['decoded_sample_start'] - run['source_frame_start'] * stride
        if run_axis != tail_axis:
            return False
        predicted_wall = tail['receipt_wall_start'] + (run['source_frame_start'] - tail['source_frame_start']) * (
            stride / tail['rate_hz']
        )
        if abs(run['receipt_wall_start'] - predicted_wall) > MAX_WALL_ANCHOR_DRIFT_SECONDS:
            return False
        source_seconds = (max(tail['source_frame_end'], run['source_frame_end']) - tail['source_frame_start']) * (
            stride / tail['rate_hz']
        )
        if source_seconds > MAX_RUN_DURATION_SECONDS:
            return False
        wall_elapsed = max(tail['receipt_wall_end'], run['receipt_wall_end']) - tail['receipt_wall_start']
        if abs(wall_elapsed - source_seconds) > MAX_WALL_ANCHOR_DRIFT_SECONDS:
            return False
        return True

    @staticmethod
    def _union_runs(runs: Iterable[dict]) -> list[dict]:
        ordered = sorted(
            runs,
            key=lambda r: (r['capture_root'], r['clock_epoch'], r['source_frame_start'], r['source_frame_end']),
        )
        merged: list[dict] = []
        for run in ordered:
            if merged and CommittedCaptureMap._merge_run(merged[-1], run):
                tail = merged[-1]
                if run['source_frame_end'] > tail['source_frame_end']:
                    tail['source_frame_end'] = run['source_frame_end']
                    tail['decoded_sample_end'] = run['decoded_sample_end']
                    tail['receipt_wall_end'] = run['receipt_wall_end']
                continue
            merged.append(dict(run))
        return merged
