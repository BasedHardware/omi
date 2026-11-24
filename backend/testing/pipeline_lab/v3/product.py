"""The real v3 operations behind :class:`v3.driver.V3Ops` (need the lab environment).

Nothing here re-implements v3: arrivals go through the product's admission
(``triggers.mark_new``) and durable finalization (``recording_short_path`` ->
``triggers.changed``); tasks run ``service.reconcile``; the sweep is ``service.sweep``.
The lab adds only the seams production gets from its infrastructure:

- **admission evidence**: production admits an owner at stage ``beta`` when the owner's app
  has called the episodes and v3 live routes (two Redis markers). :func:`admit` writes them
  with the product's own writers, as the phone would, then asks ``conversations_v3_enabled``;
- **Cloud Tasks**: ``v3/tasks.LoopbackTasks`` (installed by the run);
- **attribution**: outline calls are tagged with the stretch's first recording id and notes
  calls with the v3 conversation id (``X-Pipeline-Lab-*`` headers through the capture scope).
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from typing import Any, Mapping

from testing.pipeline_lab.chain.barrier import ExecutorBarrier, drain_event_loop
from testing.pipeline_lab.sinks.capture import capture_scope
from testing.pipeline_lab.stack.io import parse_time
from testing.pipeline_lab.v3.feed import Arrival, pre_v3_row, speech_segments

V3_MODULES = (
    'config.conversations_v3',
    'utils.cloud_tasks',
    'utils.episodes.client_gate',
    'utils.conversations.v3.client_capability',
    'utils.conversations.v3.triggers',
    'utils.conversations.v3.outline',
    'utils.conversations.v3.models',
    'utils.conversations.v3.service',
    'utils.conversations.v3.created',
    'database.conversations_v3',
)

MARKER_KEYS = ('conversations_v3:client_capable:{uid}', 'episodes:client_seen:{uid}')


def admit(uid: str) -> dict[str, Any]:
    """Write the app-capability evidence the phone leaves, then read admission back."""
    from config.conversations_v3 import conversations_v3_enabled
    from utils.conversations.v3 import client_capability
    from utils.episodes import client_gate

    client_gate.note_client_seen(uid)
    client_capability.note_capable(uid)
    return {'admitted': bool(conversations_v3_enabled(uid))}


def clear_admission(uid: str) -> int:
    """Remove the lab uid's capability markers from the lab Redis (run hygiene)."""
    from database import redis_db

    return int(redis_db.r.delete(*[key.format(uid=uid) for key in MARKER_KEYS]) or 0)


def install_attribution(stack: ExitStack) -> None:
    """Tag outline and notes LLM calls with a conversation id (see module docstring)."""
    from unittest.mock import patch

    from utils.conversations.v3 import models, outline, service

    first_recording: dict[int, str] = {}
    original_messages = outline.messages
    original_outline = models.outline
    original_process = service._process

    # Pass every other argument through: product signatures grow keywords (cohesion=, #25786).
    def messages(group: Mapping[str, Any], *args: Any, **kwargs: Any) -> list:
        result = original_messages(group, *args, **kwargs)
        lines = group.get('lines') or []
        if lines:
            first_recording[id(result)] = str(lines[0].get('conversation_id'))
        return result

    def tagged_outline(uid: str, msgs: list, *args: Any, **kwargs: Any) -> Any:
        with capture_scope(first_recording.pop(id(msgs), None), 'v3_outline'):
            return original_outline(uid, msgs, *args, **kwargs)

    def tagged_process(uid: str, row: Mapping[str, Any], *args: Any, **kwargs: Any) -> Any:
        with capture_scope(str((row or {}).get('id') or '') or None, 'v3_notes'):
            return original_process(uid, row, *args, **kwargs)

    stack.enter_context(patch.object(outline, 'messages', messages))
    stack.enter_context(patch.object(models, 'outline', tagged_outline))
    stack.enter_context(patch.object(service, '_process', tagged_process))


class ProductV3Ops:
    def __init__(self, *, finalizer: Any, barrier: ExecutorBarrier, barrier_timeout: float = 300.0):
        self.finalizer = finalizer
        self.barrier = barrier
        self.barrier_timeout = barrier_timeout
        self.seeded: set[str] = set()  # recordings whose live row a partial update created

    @staticmethod
    def _seed(uid: str, row: dict[str, Any]) -> bool:
        from database import conversations as conversations_db
        from testing.pipeline_lab.seed.writer import assert_lab_target, restore_times
        from utils.conversations.v3 import triggers

        assert_lab_target(uid)
        row = restore_times(row)
        # Listen's create path (lifecycle.create_in_progress_conversation) calls mark_new before the
        # write. Its batch-lane reservation is left out: it would route the finished capture to the
        # audio-custody wait instead of finalization (the transcript is already here).
        triggers.mark_new(uid, row)
        conversations_db.upsert_conversation_with_lifecycle(uid, row)
        return row.get('recording') is True

    @staticmethod
    def _write_segments(uid: str, cid: str, segments: list[dict[str, Any]], finished_at: Any) -> bool:
        """Production's live transcript write; for a v3 recording it calls ``triggers.changed``."""
        from database import conversations as conversations_db
        from testing.pipeline_lab.seed.writer import assert_lab_target

        assert_lab_target(uid)
        return conversations_db.update_conversation_segments(uid, cid, segments, finished_at=finished_at) is not False

    @staticmethod
    def _end_of(row: Mapping[str, Any], segments: list[dict[str, Any]]) -> Any:
        from datetime import timedelta

        origin = parse_time(row.get('started_at'))
        if origin is None or not segments:
            return origin
        return origin + timedelta(seconds=max(float(s.get('end') or s.get('start') or 0) for s in segments))

    async def _partial(self, uid: str, arrival: Arrival) -> dict[str, Any]:
        """A live capture's speech so far: create the in-progress row once, then write segments."""
        segments = speech_segments(arrival.row)[: arrival.segments]
        detail: dict[str, Any] = {'words': arrival.words, 'segments': len(segments)}
        with capture_scope(arrival.recording_id, 'v3_capture'):
            if arrival.recording_id not in self.seeded:
                row = pre_v3_row(arrival.row)
                row['transcript_segments'] = []  # listen creates the row before any speech
                row['finished_at'] = row.get('started_at')
                row.pop('recorded_end', None)
                await asyncio.to_thread(self._seed, uid, row)
                self.seeded.add(arrival.recording_id)
            wrote = await asyncio.to_thread(
                self._write_segments, uid, arrival.recording_id, segments, self._end_of(arrival.row, segments)
            )
        detail['outcome'] = 'partial' if wrote else 'partial_refused'
        return detail

    @staticmethod
    def _read(uid: str, cid: str) -> dict[str, Any]:
        from database._client import get_firestore_client

        ref = get_firestore_client().collection('users').document(uid).collection('conversations').document(cid)
        return ref.get().to_dict() or {}

    @staticmethod
    def _wake(uid: str, cid: str, manual_end: bool) -> None:
        from utils.conversations.v3 import triggers

        triggers.changed(uid, cid, manual_end=manual_end)

    async def arrive(self, uid: str, arrival: Arrival) -> dict[str, Any]:
        if arrival.partial:
            return await self._partial(uid, arrival)
        row = pre_v3_row(arrival.row)
        detail: dict[str, Any] = {'words': arrival.words}
        with capture_scope(arrival.recording_id, 'v3_capture'):
            if arrival.recording_id in self.seeded:
                # The live row exists (partials created it, the builder may already claim it): land the
                # full transcript the way the live write does, then finalize. Re-seeding would drop claims.
                await asyncio.to_thread(
                    self._write_segments,
                    uid,
                    arrival.recording_id,
                    list(row.get('transcript_segments') or []),
                    parse_time(row.get('finished_at')) or self._end_of(row, list(row.get('transcript_segments') or [])),
                )
                recording = bool((await asyncio.to_thread(self._read, uid, arrival.recording_id)).get('recording'))
            else:
                recording = await asyncio.to_thread(self._seed, uid, row)
            detail['disposition'] = await self.finalizer.finalize(uid, arrival.recording_id, row.get('language'))
            current = await asyncio.to_thread(self._read, uid, arrival.recording_id)
            if recording and not current.get('v3_pending') and current.get('recording') and not current.get('deleted'):
                # Finalization ended without waking v3 (e.g. an empty capture discarded before
                # process_conversation): wake it the way sync intake does, and say so.
                await asyncio.to_thread(self._wake, uid, arrival.recording_id, False)
                detail['woke'] = 'lab_fallback'
            if arrival.manual_end and current.get('recording'):
                await asyncio.to_thread(self._wake, uid, arrival.recording_id, True)
                detail['manual_end'] = True
        detail['outcome'] = 'recording' if recording else 'legacy'
        return detail

    async def reconcile(self, uid: str) -> str:
        from utils.conversations.v3 import service

        with capture_scope(None, 'v3_reconcile'):
            return str(await service.reconcile(uid))

    async def sweep(self) -> int:
        from utils.conversations.v3 import service

        with capture_scope(None, 'v3_sweep'):
            return int(await service.sweep())

    def pending(self, uid: str) -> bool:
        from google.cloud.firestore_v1 import FieldFilter

        from database._client import get_firestore_client

        coll = get_firestore_client().collection('users').document(uid).collection('conversations')
        for name in ('v3_pending', 'v3_process_pending'):
            if next(iter(coll.where(filter=FieldFilter(name, '==', True)).limit(1).stream()), None) is not None:
                return True
        return False

    async def settle(self) -> dict[str, Any]:
        _, left = await drain_event_loop(60.0)
        await asyncio.to_thread(self.barrier.wait, self.barrier_timeout)
        _, left = await drain_event_loop(60.0)
        return {'left': left}


def read_v3_rows(uid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(v3 conversations, recordings)`` of the lab uid, decoded by the product reader."""
    from google.cloud.firestore_v1 import FieldFilter

    from database import conversations as conversations_db
    from database._client import get_firestore_client
    from testing.pipeline_lab.stack.io import plain

    coll = get_firestore_client().collection('users').document(uid).collection('conversations')
    out: dict[str, list[dict[str, Any]]] = {'v3_derived': [], 'recording': []}
    for name in out:
        for doc in coll.where(filter=FieldFilter(name, '==', True)).stream():
            raw = doc.to_dict() or {}
            row = conversations_db.get_conversation(uid, doc.id) or {}
            if not row:
                # Unreadable through the Home reader (e.g. deleted): keep the stored flags, no speech.
                row = {k: v for k, v in raw.items() if k != 'transcript_segments'}
            for flag in ('deleted', 'home_hidden', 'recording', 'v3_derived'):
                row.setdefault(flag, raw.get(flag))
            row['id'] = doc.id
            out[name].append(plain(row))
    derived = [r for r in out['v3_derived'] if r.get('recording') is not True]
    return derived, out['recording']


EMULATOR_ENTITY_TOO_LARGE = 'maximum entity size is'


def install_emulator_size_errors(stack: ExitStack) -> None:
    """The Firestore emulator words a document over 1 MiB differently from production.

    Production says "exceeds the maximum allowed size"; the emulator says "maximum entity size is
    1048576 bytes". Without this, ``size_error`` misses it in the lab and the product never logs which
    staged document was too large (``log_largest_write``: kind and bytes, no ids or content).
    """
    from unittest.mock import patch

    try:
        from database import conversations_v3 as store
    except ImportError:
        return
    original = getattr(store, 'size_error', None)
    if original is None:
        return

    def size_error(error: Any) -> Any:
        return original(error) or ('document' if EMULATOR_ENTITY_TOO_LARGE in str(error) else None)

    stack.enter_context(patch.object(store, 'size_error', size_error))


TRACE_ENV = 'OMI_PIPELINE_LAB_V3_TRACE'


def install_planner_trace(stack: ExitStack, target: str | None = None) -> None:
    """Diagnostics (``OMI_PIPELINE_LAB_V3_TRACE=<file>``): per builder pass, what ``store.load`` returned and
    what ``preserve_finished_windows`` planned. Times, ids, statuses and counts only; never text."""
    import json
    import os
    from unittest.mock import patch

    # Read before lab_environment clears os.environ (the caller passes it).
    target = target or os.environ.get(TRACE_ENV)
    if not target:
        return
    from database import conversations_v3 as store
    from utils.conversations.v3 import planner

    original_load = store.load
    original_preserve = planner.preserve_finished_windows

    def iso(value: Any) -> Any:
        return value.isoformat() if hasattr(value, 'isoformat') else value

    def write(row: dict[str, Any]) -> None:
        with open(target, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, default=str) + '\n')

    def load(uid: str, *args: Any, **kwargs: Any) -> Any:
        result = original_load(uid, *args, **kwargs)
        recordings, existing = result[0], result[1]
        write(
            {
                'event': 'load',
                'kwargs': sorted(kwargs),
                'recordings': [
                    {
                        'id': rid[:8],
                        'status': r.get('status'),
                        'pending': r.get('v3_pending'),
                        'claims': [
                            (str(c.get('conversation_id'))[:8], iso(c.get('start')), iso(c.get('end')))
                            for c in r.get('claims') or []
                        ],
                        'segments': len(r.get('transcript_segments') or []),
                        'continues': r.get('_v3_page_continues'),
                    }
                    for rid, r in recordings.items()
                ],
                'existing': [
                    {
                        'id': cid[:8],
                        'status': r.get('status'),
                        'unlocked': r.get('v3_unlocked'),
                        'start': iso(r.get('started_at')),
                        'end': iso(r.get('finished_at')),
                        'rids': [x[:8] for x in r.get('v3_recording_ids') or []],
                    }
                    for cid, r in existing.items()
                ],
            }
        )
        return result

    def preserve(planned: Any, existing: Any, *args: Any, **kwargs: Any) -> Any:
        before = [
            {
                'start': iso(w['lines'][0]['start']),
                'end': iso(max(l['end'] for l in w['lines'])),
                'finished': w.get('finished'),
                'locked': w.get('locked'),
                'n': len(w['lines']),
                'defer': w.get('_defer_lock'),
            }
            for w in planned
            if w.get('lines')
        ]
        result = original_preserve(planned, existing, *args, **kwargs)
        write(
            {
                'event': 'preserve',
                'planned': before,
                'result': [
                    {
                        'start': iso(w['lines'][0]['start']) if w.get('lines') else None,
                        'n': len(w.get('lines') or []),
                        'finished': w.get('finished'),
                        'existing_id': str(w.get('existing_id'))[:8],
                        'held': w.get('_held_provisional'),
                        'defer': w.get('_defer_lock'),
                    }
                    for w in result
                ],
                'kwargs': {k: v for k, v in kwargs.items() if isinstance(v, bool)},
            }
        )
        return result

    from utils.conversations.v3 import outline

    original_stretches = outline.stretches

    def stretches(members: Any, now: Any, *args: Any, **kwargs: Any) -> Any:
        groups = original_stretches(members, now, *args, **kwargs)
        write(
            {
                'event': 'stretches',
                'now': iso(now),
                'kwargs': {k: str(v) for k, v in kwargs.items()},
                'groups': [
                    {
                        'start': iso(g['lines'][0]['start']),
                        'end': iso(g['end']),
                        'n': len(g['lines']),
                        'locked': g.get('locked'),
                        'finished': g.get('finished'),
                        'outline_ready': g.get('outline_ready'),
                        'manual_end': g.get('manual_end'),
                        'rids': sorted({str(l['conversation_id'])[:8] for l in g['lines']}),
                    }
                    for g in groups
                    if g.get('lines')
                ],
            }
        )
        return groups

    stack.enter_context(patch.object(store, 'load', load))
    stack.enter_context(patch.object(planner, 'preserve_finished_windows', preserve))
    stack.enter_context(patch.object(outline, 'stretches', stretches))
