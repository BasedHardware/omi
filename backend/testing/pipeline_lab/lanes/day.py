"""Day-level ingest: record cassettes (cold, billable) and replay every conversation.

``record_day_cassettes`` is the DESIGN L2 ``record`` step: it is the only
function here that can reach a vendor, always through a ``Recorder`` (ledger +
vendor log). ``replay_day`` only plays cassettes and fails a conversation on a
miss; it never records.

Lane routing follows ``timeline.json``: ``record`` -> batch driver,
``sync`` -> sync driver. ``streaming`` captures are not replayed until the
stream lane (M3) lands; they are reported ``lane_not_replayed`` unless the run
explicitly chooses a stand-in driver (``streaming_via``), which is labelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from testing.pipeline_lab.cassette.player import CassetteMiss, PlaybackConfig, Player, SpanSource
from testing.pipeline_lab.cassette.recorder import Recorder
from testing.pipeline_lab.lanes.audio import RATE, load_pcm16
from testing.pipeline_lab.lanes.batch import BatchConversation, replay_record_lane
from testing.pipeline_lab.lanes.output import IngestResult, write_results
from testing.pipeline_lab.lanes.sync import SyncConversation, private_scratch, replay_sync_lane
from testing.pipeline_lab.timeline.build import load_audio_index, load_baseline
from testing.pipeline_lab.contracts import parse_time
from testing.pipeline_lab.contracts import utc_iso as iso
from testing.pipeline_lab.store import lab_root, read_json

MAX_FILLED_GAP_SECONDS = 600.0


@dataclass(frozen=True)
class STTSelection:
    provider: str
    model: str
    language: str | None = None  # the language production requests; None -> 'multi'
    vocabulary: tuple[str, ...] = ()

    def playback(self) -> PlaybackConfig:
        return PlaybackConfig(self.provider, self.model, self.language, self.vocabulary)


@dataclass(frozen=True)
class ConversationAudio:
    conversation_id: str
    pcm16: bytes
    audio_start: datetime
    original_bin: Path | None


def _timeline(day_id: str, root) -> dict:
    timeline = read_json(lab_root(root) / 'corpus' / day_id / 'timeline.json')
    if timeline is None:
        raise FileNotFoundError('timeline.json missing: build the day timeline first')
    return timeline


def conversation_audio(day_id: str, root=None) -> dict[str, ConversationAudio]:
    """All clips of each conversation on one clock; short gaps are zero-filled."""
    day_dir = lab_root(root) / 'corpus' / day_id
    by_id: dict[str, list] = {}
    for entry in load_audio_index(day_dir):
        by_id.setdefault(entry.conversation_id, []).append(entry)
    out = {}
    for cid, entries in by_id.items():
        pcm, cursor = bytearray(), entries[0].start
        original = None
        for entry in entries:
            path = day_dir / 'audio' / entry.path
            gap = (entry.start - cursor).total_seconds()
            if 0 < gap <= MAX_FILLED_GAP_SECONDS:
                pcm += b'\x00\x00' * int(round(gap * RATE))
            pcm += load_pcm16(path, entry)
            cursor = max(cursor, entry.end)
            if len(entries) == 1 and path.suffix == '.bin':
                original = path
        out[cid] = ConversationAudio(cid, bytes(pcm), entries[0].start, original)
    return out


def record_day_cassettes(
    day_id: str,
    recorder: Recorder,
    *,
    language: str | None = None,
    vocabulary: tuple[str, ...] = (),
    root=None,
    lanes: Iterable[str] = ('record', 'sync', 'streaming'),
    sync_exact: bool = False,  # RULINGS 13: one conversation-level cassette (span) by default
    file_vad=None,
) -> dict:
    timeline = _timeline(day_id, root)
    audio = conversation_audio(day_id, root)
    wanted = set(lanes)
    summary = {'conversations': 0, 'hits_before': recorder.hits, 'misses_before': recorder.misses}
    for row in timeline['conversations']:
        clip = audio.get(row['id'])
        if clip is None or row['lane'] not in wanted:
            continue
        summary['conversations'] += 1
        if row['lane'] == 'sync' and sync_exact:
            replay_sync_lane(
                SyncConversation(row['id'], clip.pcm16, iso(clip.audio_start), row.get('finished_at'), language),
                recorder=recorder,
                vocabulary=vocabulary,
                file_vad=file_vad,
                scratch=private_scratch(lab_root(root)),
            )
        else:
            recorder.ensure(clip.pcm16, language=language, vocabulary=vocabulary, purpose=f'stt_cassette:{row["lane"]}')
    summary['hits'] = recorder.hits - summary.pop('hits_before')
    summary['misses'] = recorder.misses - summary.pop('misses_before')
    return summary


def replay_day(
    day_id: str,
    run_id: str,
    selection: STTSelection,
    *,
    root=None,
    sync_mode: str = 'exact',
    streaming_via: str | None = None,
    vad=None,
    file_vad=None,
    only: Iterable[str] | None = None,
    write: bool = True,
) -> list[IngestResult]:
    if sync_mode not in {'exact', 'span'} or streaming_via not in {None, 'record', 'sync'}:
        raise ValueError('invalid replay mode')
    timeline = _timeline(day_id, root)
    audio = conversation_audio(day_id, root)
    baseline = {str(r.get('id')): r for r in load_baseline(lab_root(root) / 'corpus' / day_id)}
    player = Player(selection.playback(), root=root)
    stt_meta = {'provider': selection.provider, 'model': selection.model, 'language': selection.language or 'multi'}
    selected = set(only) if only else None
    results = []
    for row in timeline['conversations']:
        cid = row['id']
        if selected is not None and cid not in selected:
            continue
        lane = row['lane']
        driver_lane = lane if lane != 'streaming' else streaming_via
        base = baseline.get(cid, {})
        clip = audio.get(cid)
        if clip is None or driver_lane is None:
            results.append(
                IngestResult(
                    id=cid,
                    baseline_id=cid,
                    lane=lane,
                    started_at=row.get('started_at'),
                    finished_at=row.get('finished_at'),
                    outcome='failed',
                    evaluable=row['evaluable'],
                    error='no_audio' if clip is None else f'lane_not_replayed:{lane}',
                )
            )
            continue
        started = parse_time(row.get('started_at')) or clip.audio_start
        shift = (clip.audio_start - started).total_seconds()
        language = base.get('language') or selection.language
        try:
            if driver_lane == 'record':
                cassette = player.get(clip.pcm16)
                result = replay_record_lane(
                    BatchConversation(
                        cid,
                        clip.pcm16,
                        row.get('started_at'),
                        row.get('finished_at'),
                        cassette.detected_language or language or 'en',
                        cid,
                        row['evaluable'],
                    ),
                    SpanSource(cassette),
                    vad=vad,
                    stt={**stt_meta, 'cassettes': [cassette.key.digest]},
                    capture_epoch=clip.audio_start.timestamp(),
                )
            else:
                sync_kwargs = (
                    {'player': player} if sync_mode == 'exact' else {'span': SpanSource(player.get(clip.pcm16))}
                )
                result = replay_sync_lane(
                    SyncConversation(
                        cid,
                        clip.pcm16,
                        iso(clip.audio_start),
                        row.get('finished_at'),
                        language,
                        cid,
                        row['evaluable'],
                        clip.original_bin,
                    ),
                    file_vad=file_vad,
                    stt=dict(stt_meta),
                    scratch=private_scratch(lab_root(root)),
                    **sync_kwargs,
                )
                result.started_at = row.get('started_at')
        except CassetteMiss as miss:
            result = IngestResult(
                id=cid,
                baseline_id=cid,
                lane=lane,
                started_at=row.get('started_at'),
                finished_at=row.get('finished_at'),
                outcome='failed',
                evaluable=row['evaluable'],
                error='cassette_miss',
                stt={**stt_meta, 'miss': str(miss)},
            )
        if shift:
            for segment in result.segments:
                segment['start'] = round(segment['start'] + shift, 3)
                segment['end'] = round(segment['end'] + shift, 3)
        if lane != (driver_lane or lane):
            result.lane = lane
            result.driver['stand_in'] = f'{lane} captured, replayed with the {driver_lane} driver'
        results.append(result)
    if write:
        write_results(run_id, results, root)
    return results
