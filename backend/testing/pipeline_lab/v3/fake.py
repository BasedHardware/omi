"""The ``fake`` v3 engine: the lab's v3 plumbing with a stand-in for the product builder.

``run --engine fake`` on a v3 day proves the v3 path end to end without an emulator: the
arrival plan, the event loop with loopback tasks, one ``v3_outline`` call per stretch through
the real proxy (keyed, priced, capped, attributed), export in the v3 contract shape with
recordings, pairing by recording, the baseline and the inspector. Stretches are cut at five
minutes of silence like ``outline.stretches``; every window is one conversation titled by the
stand-in call. It says nothing about product fidelity; that is the ``product`` engine.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from testing.pipeline_lab.chain.driver import llm_call_ids_by_conversation
from testing.pipeline_lab.chain.fake import ask
from testing.pipeline_lab.stack.io import iso, parse_time, write_json
from testing.pipeline_lab.v3.driver import V3Driver, default_horizon
from testing.pipeline_lab.v3.export import normalize_v3_conversation, pair_by_recordings
from testing.pipeline_lab.v3.feed import DEFAULT_LAG, plan_arrivals, speech_segments
from testing.pipeline_lab.v3.tasks import RECONCILE_PATH, LoopbackTasks
from utils.conversations.v3.word_floor import MIN_HOME_WORDS, text_word_count

SILENCE = timedelta(minutes=5)
FAKE_UID = 'local-dev-user'
OUTLINE_SCHEMA = {'type': 'object', 'properties': {'title': {'type': 'string'}, 'kind': {'type': 'string'}}}


class _Clock:
    def __init__(self, start: datetime):
        self._now = start

    def set(self, instant: datetime) -> None:
        self._now = instant

    def now(self) -> datetime:
        return self._now


class FakeV3Ops:
    def __init__(self, *, tasks: LoopbackTasks, clock: _Clock, proxy_url: str):
        self.tasks = tasks
        self.clock = clock
        self.proxy_url = proxy_url
        self.recordings: dict[str, dict[str, Any]] = {}
        self.pending_ids: set[str] = set()
        self.conversations: dict[str, dict[str, Any]] = {}

    async def arrive(self, uid: str, arrival: Any) -> dict[str, Any]:
        row = dict(arrival.row)
        if getattr(arrival, 'partial', False):
            row['transcript_segments'] = speech_segments(arrival.row)[: arrival.segments]
        self.recordings[arrival.recording_id] = row
        self.pending_ids.add(arrival.recording_id)
        minute = int(self.clock.now().timestamp()) // 60
        self.tasks.enqueue(
            'conversations-v3',
            'http://lab.invalid' + RECONCILE_PATH,
            f'fake-{minute}',
            {'uid': uid},
            schedule_at=int(self.clock.now().timestamp()),
        )
        return {'outcome': 'partial' if getattr(arrival, 'partial', False) else 'recording'}

    def _lines(self) -> list[tuple[datetime, datetime, str, dict]]:
        lines = []
        for rid, row in self.recordings.items():
            origin = parse_time(row.get('started_at'))
            for segment in row.get('transcript_segments') or []:
                if not str(segment.get('text') or '').strip() or origin is None:
                    continue
                start = origin + timedelta(seconds=float(segment.get('start') or 0))
                end = origin + timedelta(seconds=float(segment.get('end') or 0))
                lines.append((start, max(start, end), rid, segment))
        return sorted(lines, key=lambda line: (line[0], line[2]))

    async def reconcile(self, uid: str) -> str:
        now = self.clock.now()
        groups: list[list] = []
        for line in self._lines():
            if not groups or line[0] - max(x[1] for x in groups[-1]) >= SILENCE:
                groups.append([])
            groups[-1].append(line)
        committed = 0
        for group in groups:
            end = max(x[1] for x in group)
            if now - end < SILENCE:
                continue  # still open: production wakes again at end + 5 minutes
            start = group[0][0]
            cid = hashlib.sha256(f'v3:{uid}:{start.isoformat()}'.encode()).hexdigest()[:32]
            if cid in self.conversations:
                continue
            recordings = list(dict.fromkeys(x[2] for x in group))
            text = '\n'.join(str(x[3].get('text')) for x in group)
            answer = await asyncio.to_thread(
                ask,
                self.proxy_url,
                stage='v3_outline',
                conversation_id=recordings[0],
                prompt=text,
                schema=OUTLINE_SCHEMA,
            )
            words = text_word_count(text)
            segments = [
                {**x[3], 'start': (x[0] - start).total_seconds(), 'end': (x[1] - start).total_seconds()} for x in group
            ]
            self.conversations[cid] = {
                'id': cid,
                'v3_derived': True,
                'started_at': iso(start),
                'finished_at': iso(end),
                'status': 'completed',
                'kind': answer.get('kind') or 'conversation',
                'home_hidden': words < MIN_HOME_WORDS,
                'home_hidden_reason': 'below_word_minimum' if words < MIN_HOME_WORDS else 'conversation',
                'tile_state': 'done',
                'v3_notes_written': words >= MIN_HOME_WORDS,
                'v3_recording_ids': recordings,
                'transcript_segments': segments,
                'structured': {'title': answer.get('title') or '', 'emoji': '💬'},
            }
            self.pending_ids.difference_update(recordings)
            committed += 1
        open_groups = [g for g in groups if now - max(x[1] for x in g) < SILENCE]
        for group in open_groups:
            due = max(x[1] for x in group) + SILENCE
            self.tasks.enqueue(
                'conversations-v3',
                'http://lab.invalid' + RECONCILE_PATH,
                f'fake-{int(due.timestamp()) // 60}',
                {'uid': uid},
                schedule_at=int(due.timestamp()),
            )
        return 'committed' if committed or not open_groups else 'open'

    async def sweep(self) -> int:
        return 0

    def pending(self, uid: str) -> bool:
        return False

    async def settle(self) -> dict[str, Any]:
        return {'left': 0}


def replay_v3_fake(
    *,
    run_dir: Path,
    recordings: Sequence[Mapping[str, Any]],
    production: Sequence[Mapping[str, Any]],
    proxy_url: str,
    arrival_mode: str = 'production',
    arrival_lag: timedelta = DEFAULT_LAG,
    tail: timedelta = timedelta(hours=2),
    sweeps: bool = True,
    partial_step: timedelta | None = None,
    partial_lag: timedelta = DEFAULT_LAG,
    max_events: int = 20000,
) -> dict[str, Any]:
    plan = plan_arrivals(
        recordings, lag=arrival_lag, mode=arrival_mode, partial_step=partial_step, partial_lag=partial_lag
    )
    first = plan.arrivals[0].instant if plan.arrivals else datetime.now(timezone.utc)
    clock = _Clock(first - timedelta(minutes=1))
    tasks = LoopbackTasks(clock.now)
    ops = FakeV3Ops(tasks=tasks, clock=clock, proxy_url=proxy_url)
    end = max([a.instant for a in plan.arrivals] + [first])
    driver = V3Driver(
        uid=FAKE_UID,
        ops=ops,
        tasks=tasks,
        clock=clock,
        horizon=default_horizon(plan.arrivals, end, tail),
        sweeps=sweeps,
        max_events=max_events,
    )
    report = asyncio.run(driver.run(plan.arrivals))
    rows = list(ops.conversations.values())
    calls = llm_call_ids_by_conversation(Path(run_dir) / 'llm_calls.jsonl')
    pairs = pair_by_recordings(rows, production)
    for row in rows:
        baseline_id, baseline_ids = pairs.get(row['id'], (None, []))
        ids = [c for rid in row['v3_recording_ids'] for c in calls.get(rid, [])]
        payload = normalize_v3_conversation(row, llm_call_ids=ids, baseline_id=baseline_id, baseline_ids=baseline_ids)
        write_json(Path(run_dir) / 'conversations' / f'{row["id"]}.json', payload)
    write_json(
        Path(run_dir) / 'chain.json',
        {
            'summary': {'status': report.summary()['status'], 'conversations': len(rows), 'failed': 0},
            'pipeline': 'v3',
            'engine': 'fake',
            'conversations': [{'conversation_id': r['id'], 'status': 'ok', 'lane': 'v3'} for r in rows],
        },
    )
    write_json(Path(run_dir) / 'v3_driver.json', {'plan': plan.summary(), **report.as_dict()})
    write_json(Path(run_dir) / 'day.json', {'daily_summary': None, 'goals': [], 'notifications': []})
    return {
        'plan': plan.summary(),
        'driver': report.summary(),
        'conversations': {'v3': len(rows), 'visible': sum(1 for r in rows if not r['home_hidden'])},
        'admission': {'admitted': True, 'engine': 'fake'},
    }
