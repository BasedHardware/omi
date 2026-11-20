"""``corpus add-day``: turn a local owner snapshot into one corpus day of the run store.

Reads local files only (a snapshot directory in the ``fetch-owner-audio`` exporter format
and, optionally, a directory of per-conversation audio). Never calls the network.

Writes, under ``$ROOT/corpus/<day_id>/``:

- ``day.json``: date, timezone, snapshot label, coverage (filled by the timeline);
- ``baseline/raw_conversations.jsonl``: the day's production rows in snapshot shape, uid
  remapped to the lab uid, hash fields and byte markers dropped. The chain replays these;
- ``baseline/conversations.jsonl``: the same rows normalized to the ConversationRecord shape
  (tasks and memories inline), which the inspector and the baseline compare read (RULINGS 1);
- ``baseline/memories.jsonl``, ``baseline/action_items.jsonl``: production rows of the day
  (remapped); ``baseline/daily_summary.json``: the day's production recap in contract shape;
- ``start_state/``: the account as of the day start (rows created before it), remapped to
  the lab uid. Labelled ``approximate`` (DESIGN L8);
- ``audio/`` + ``audio/index.json`` when an audio directory is given (files are copied 0600);
- ``timeline.json`` and ``day.json.coverage`` (lane per conversation, islands, unknown gaps).

The source uid never reaches the store: every row goes through the start-state rewriter
and the written files are checked for survivors.
"""

from __future__ import annotations

import json
import shutil
import wave
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

from testing.pipeline_lab.contracts import AudioIndexEntry, CorpusDay, parse_time, utc_iso
from testing.pipeline_lab.day.outputs import contract_daily_summary
from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.store import Store, atomic_write_bytes, read_json, safe_segment
from testing.pipeline_lab.v3.corpus import has_v3_export, v3_corpus

AUDIO_EXTENSIONS = {'.wav': 'pcm_s16le', '.m4a': 'aac', '.aac': 'aac', '.opus': 'opus', '.ogg': 'opus', '.bin': 'opus'}
START_STATE_ENTITIES = ('conversations', 'memories', 'action_items', 'people', 'goals', 'daily_summaries', 'meetings')


class CorpusError(ValueError):
    """A refusal; the message names the policy, never a private value."""


@dataclass(frozen=True)
class DayWindow:
    date: str
    timezone: str
    start: datetime  # UTC instant of local midnight
    end: datetime

    @classmethod
    def of(cls, date: str, tz_name: str) -> 'DayWindow':
        try:
            zone = ZoneInfo(tz_name)
        except Exception as error:  # noqa: BLE001 - unknown zone name
            raise CorpusError(f'unknown timezone: {tz_name}') from error
        local = datetime.combine(date_type.fromisoformat(date), time(0, 0), tzinfo=zone)
        start = local.astimezone(ZoneInfo('UTC'))
        end = (local + timedelta(days=1)).astimezone(ZoneInfo('UTC'))
        return cls(date=date, timezone=tz_name, start=start, end=end)

    def contains(self, value: Any) -> bool:
        moment = parse_time(value)
        return moment is not None and self.start <= moment < self.end


def _jsonl(rows: Iterable[Any]) -> bytes:
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + '\n' for row in rows).encode()


def _row_start(row: Mapping[str, Any]) -> Any:
    return row.get('started_at') or row.get('created_at')


def _audio_entries(
    audio_dir: Path, day_rows: Mapping[str, Mapping[str, Any]], sample_rate: int
) -> list[tuple[Path, AudioIndexEntry]]:
    """``<conversation_id>.<ext>`` files (or an ``index.json`` beside them) for this day's conversations."""
    index = read_json(audio_dir / 'index.json')
    found: list[tuple[Path, AudioIndexEntry]] = []
    if isinstance(index, dict):
        index = index.get('entries') or index.get('files')
    if isinstance(index, list):
        for item in index:
            cid = str(item.get('conversation_id') or '')
            if cid not in day_rows:
                continue
            source = audio_dir / str(item['path'])
            if not source.is_file():
                raise CorpusError('audio index names a missing file')
            found.append(
                (
                    source,
                    AudioIndexEntry(
                        conversation_id=cid,
                        path=source.name,
                        start=utc_iso(parse_time(item['start'])),
                        end=utc_iso(parse_time(item['end'])),
                        codec=str(item.get('codec') or AUDIO_EXTENSIONS.get(source.suffix.lower(), 'unknown')),
                        sample_rate=int(item.get('sample_rate') or sample_rate),
                    ),
                )
            )
        return found
    for source in sorted(audio_dir.iterdir()):
        codec = AUDIO_EXTENSIONS.get(source.suffix.lower())
        if codec is None or not source.is_file() or source.stem not in day_rows:
            continue
        row = day_rows[source.stem]
        start, end = parse_time(_row_start(row)), parse_time(row.get('finished_at'))
        rate = sample_rate
        if source.suffix.lower() == '.wav':
            with wave.open(str(source), 'rb') as handle:
                rate = handle.getframerate()
                end = start + timedelta(seconds=handle.getnframes() / float(rate)) if start else end
        if start is None or end is None:
            raise CorpusError('an audio file belongs to a conversation without start/finish times')
        found.append(
            (
                source,
                AudioIndexEntry(
                    conversation_id=source.stem,
                    path=source.name,
                    start=utc_iso(start),
                    end=utc_iso(end),
                    codec=codec,
                    sample_rate=rate,
                ),
            )
        )
    return found


def add_day(
    store: Store,
    snapshot_dir: Path,
    date: str,
    tz_name: str,
    *,
    day_id: Optional[str] = None,
    audio_dir: Optional[Path] = None,
    label: Optional[str] = None,
    audio_sample_rate: int = 16000,
    replace: bool = False,
) -> dict[str, Any]:
    from testing.pipeline_lab.baseline.compare import production_view
    from testing.pipeline_lab.seed.snapshot import SnapshotReader
    from testing.pipeline_lab.seed.start_state import (
        StartStateReport,
        _Rewriter,
        assert_no_source_uid,
        build_start_state,
        detect_source_uid,
    )
    from testing.pipeline_lab.timeline.build import build_day_timeline, classify_lane

    window = DayWindow.of(date, tz_name)
    day_id = safe_segment(day_id or date, 'day id')
    day_dir = store.day_dir(day_id)
    if (day_dir / 'day.json').exists() and not replace:
        raise CorpusError('corpus day already exists (pass --replace to rebuild it)')
    reader = SnapshotReader(Path(snapshot_dir).expanduser())
    manifest = reader.manifest()
    snapshot_window = manifest.get('window') or {}
    snap_start, snap_end = parse_time(snapshot_window.get('start')), parse_time(snapshot_window.get('end'))
    warnings: list[str] = []
    if snap_start and snap_start > window.start:
        warnings.append('snapshot window starts after the day start: start state misses earlier history')
    if snap_end and snap_end < window.end:
        warnings.append('snapshot window ends before the day ends: the baseline is incomplete')

    raw = {
        'conversations': list(reader.conversations()),
        'memories': list(reader.memories()),
        'action_items': list(reader.action_items()),
    }
    source_uid = detect_source_uid(
        (row for rows in (*raw.values(), reader.people(), reader.goals()) for row in rows), manifest.get('uid_prefix')
    )
    state = build_start_state(
        reader, window.start, day_date=date, source_uid=source_uid, time_zone=tz_name, target_uid=LAB_UID
    )
    assert_no_source_uid(state, source_uid)

    report = StartStateReport()
    rewrite = _Rewriter(source_uid, LAB_UID, report)

    def remap(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            new = rewrite(dict(row))
            if 'uid' in new:
                new['uid'] = LAB_UID
            out.append(new)
        return out

    day_rows = remap(row for row in raw['conversations'] if window.contains(_row_start(row)))
    day_rows.sort(key=lambda r: (str(_row_start(r) or ''), str(r.get('id'))))
    day_ids = {str(r.get('id')) for r in day_rows}

    def of_day(row: Mapping[str, Any]) -> bool:
        return str(row.get('conversation_id') or '') in day_ids or window.contains(row.get('created_at'))

    memories = remap(row for row in raw['memories'] if of_day(row))
    action_items = remap(row for row in raw['action_items'] if of_day(row))
    people = {str(p.get('id')): str(p.get('name') or '') for p in state.people if p.get('id')}
    normalized = production_view(day_rows, memories=memories, action_items=action_items, people=people)
    lanes = {str(r.get('id')): classify_lane(r)['lane'] for r in day_rows}
    for row in normalized:
        row['lane'] = lanes.get(row['id'], row.get('lane'))
    v3_meta = None
    v3_blobs: dict[str, bytes] = {}
    if has_v3_export(Path(snapshot_dir).expanduser()):
        v3_blobs, prior_recordings, v3_meta = v3_corpus(
            Path(snapshot_dir).expanduser(),
            contains=window.contains,
            day_start=window.start,
            remap=remap,
            memories=remap(raw['memories']),
            action_items=remap(raw['action_items']),
            people=people,
            legacy_day_rows=day_rows,
        )
        known = {str(row.get('id')) for row in state.conversations}
        state.conversations.extend(row for row in prior_recordings if str(row.get('id')) not in known)
    summary_row = next((r for r in reader.daily_summaries() if r.get('date') == date), None)
    daily_summary = contract_daily_summary(rewrite(dict(summary_row)) if summary_row else None)

    blobs: dict[str, bytes] = {
        'baseline/raw_conversations.jsonl': _jsonl(day_rows),
        'baseline/conversations.jsonl': _jsonl(normalized),
        'baseline/memories.jsonl': _jsonl(memories),
        'baseline/action_items.jsonl': _jsonl(action_items),
        'start_state/meta.json': json.dumps(
            {
                'uid': state.uid,
                'day_start': utc_iso(state.day_start),
                'profile': state.profile,
                'fcm_token': state.fcm_token,
                'report': state.report.as_dict(),
                'start_state': 'approximate',
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode(),
    }
    for entity in START_STATE_ENTITIES:
        blobs[f'start_state/{entity}.jsonl'] = _jsonl(getattr(state, entity))
    blobs.update(v3_blobs)
    if daily_summary is not None:
        blobs['baseline/daily_summary.json'] = json.dumps(daily_summary, ensure_ascii=False).encode()
    for name, body in blobs.items():
        if source_uid.encode() in body:
            raise CorpusError(f'source uid survived remapping in {name}')

    for name, body in blobs.items():
        atomic_write_bytes(day_dir / name, body)
    if daily_summary is None and (day_dir / 'baseline' / 'daily_summary.json').exists():
        (day_dir / 'baseline' / 'daily_summary.json').unlink()

    audio_files = 0
    if audio_dir is not None:
        entries = _audio_entries(Path(audio_dir).expanduser(), {str(r['id']): r for r in day_rows}, audio_sample_rate)
        for source, entry in entries:
            target = store.audio_path(day_id, entry.path)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o600)
        store.write_audio_index(day_id, [entry for _, entry in entries])
        audio_files = len(entries)

    day = CorpusDay(
        day_id=day_id,
        date=date,
        timezone=tz_name,
        source_snapshot=label or Path(snapshot_dir).name,
        start_state_snapshot=label or Path(snapshot_dir).name,
        extra={
            'window': {'start': utc_iso(window.start), 'end': utc_iso(window.end)},
            'start_state': 'approximate',
            'start_state_report': state.report.as_dict(),
            'added_at': utc_iso(),
            'v3': v3_meta,
            'warnings': warnings,
        },
    )
    store.write_day(day)
    timeline = build_day_timeline(day_id, root=store.root)
    return {
        'day_id': day_id,
        'date': date,
        'timezone': tz_name,
        'conversations': len(day_rows),
        'memories': len(memories),
        'action_items': len(action_items),
        'daily_summary': daily_summary is not None,
        'audio_files': audio_files,
        'v3': v3_meta,
        'start_state': state.report.as_dict()['kept'],
        'coverage': timeline['coverage'],
        'warnings': warnings,
    }


def load_start_state(store: Store, day_id: str) -> Any:
    """The materialized start state of a corpus day as a ``seed.start_state.StartState``."""
    from testing.pipeline_lab.seed.start_state import StartState, StartStateReport
    from testing.pipeline_lab.store import read_jsonl

    base = store.day_dir(day_id) / 'start_state'
    meta = read_json(base / 'meta.json')
    if meta is None:
        raise FileNotFoundError('corpus day has no start state (re-run corpus add-day)')
    report = StartStateReport(**{k: v for k, v in (meta.get('report') or {}).items() if k != 'start_state'})
    entities = {name: read_jsonl(base / f'{name}.jsonl') for name in START_STATE_ENTITIES}
    return StartState(
        uid=meta['uid'],
        day_start=parse_time(meta['day_start']),
        profile=meta.get('profile') or {},
        fcm_token=meta.get('fcm_token') or {},
        report=report,
        **entities,
    )
