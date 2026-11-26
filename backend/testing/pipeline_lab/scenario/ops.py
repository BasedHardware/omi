"""The scenario events as product calls (need the lab environment). One class, :class:`ScenarioOps`,
which the unchanged ``v3.driver.V3Driver`` drives exactly like a day replay's arrivals.

Real product code, per event:

- ``capture_start``: capture admission and the recording row, ``triggers.mark_new`` then
  ``database.conversations.upsert_conversation_with_lifecycle`` (what listen's create path calls);
- ``finish``: the Finish route's own branch decision, ``process_conversation.retrieve_in_progress_conversation``;
  with no capture in progress, ``utils.conversations.v3.finish.finish_live_window`` (what
  ``POST /v1/conversations`` calls when nothing is in progress);
- ``admission``: ``utils.batch_pipeline.live._manual_finish_admitted`` (promotion of the stored request to the
  cut, then the detached fast-finish pass ``utils.conversations.v3.fast_finish.run`` with its real eligibility,
  refresh, fenced writer ``update_conversation_segments`` and ``cut`` -> ``triggers.changed(manual_end=True)``);
- ``transcript`` and ``sync``: the transcript write ``update_conversation_segments`` and the projection's
  post-commit wake ``triggers.committed_sync_assignment``;
- reconcile tasks, the sweep, the planner, notes and Home visibility: ``service.reconcile`` / ``service.sweep``
  (inherited from ``v3.product.ProductV3Ops``).

Stand-ins (each is listed in the README's gap table with its follow-up):

- ``STAND_IN_CAPTURE_CLOSE``: a Finish that lands while the capture is in progress is stored the way the
  finalization job's capture close does (``_complete_server_batch_capture_txn``: ``status: completed`` and
  ``v3_manual_end_requested`` in one write) when the capture seals; the job, lease and outbox are not run;
- ``STAND_IN_ADMISSION``: batch record admission (audio listing, units, staging, intake) is not run; the
  manual-finish hook gets one unit spanning the recording's audio (one retained reference, read as silence),
  a batch store whose privacy check answers allowed, and STT returns the recording's lines, with the funding
  gate open: per chunk on the chunked path that ships (``fast_finish._transcribe_words``, the lines inside
  that chunk's window, no language probe), or per unit on the kill-switch path (``fast_finish._transcribe``);
  the lines are the scenario's speech, or for an ``audio_file`` recording the cassette words the batch lane
  turned into segments (``scenario/audio.py``);
- ``STAND_IN_PROJECTION``: the canonical batch transcript lands through the live transcript writer and then
  stamps ``record_projection_revision``; the projection transaction (replace_record, its own manual-end
  promotion ``_v3_finish_update``, receipts) is not run;
- ``STAND_IN_SYNC``: a device-sync fragment is written as a completed recording with its transcript and woken
  as the projection would; ``/v2/sync-local-files`` intake and its batch job are not run.

The fast-finish privacy check (``store.run(check_privacy)``) is part of ``STAND_IN_ADMISSION``: it reads the
account's sync setting through the product reader ``users.get_user_private_cloud_sync_enabled`` and refuses
(``BatchPrivacyBlocked``) when it is off, instead of the batch privacy fence's generation read. The
in-transaction fence of the transcript write (``assert_batch_write_allowed``) is the product's own.

Operation counts (``scenario/budget.py``): the lab's own reads (snapshots, flags, the driver's pending check,
the account change of ``sync_off_at``) run under ``budget.lab_io()`` and are not budgeted; Home captures
run under the ``home`` scope; everything else, stand-in writes included, is ``pipeline``.

Every stand-in is counted in ``stand_ins``; the ones that write words also count where the words came from in
``stand_in_sources`` (``scripted``, or the cassette source). ``scenario/standins.py`` words each from those.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from typing import Any, Callable, Optional
from unittest.mock import patch

from testing.pipeline_lab.chain.barrier import ExecutorBarrier
from testing.pipeline_lab.scenario import budget
from testing.pipeline_lab.scenario.checks import conversation_row, evaluate, finish_tap_row
from testing.pipeline_lab.scenario.spec import Recording, Scenario, ScenarioEvent
from testing.pipeline_lab.sinks.capture import capture_scope
from testing.pipeline_lab.v3.product import ProductV3Ops

SCENARIO_MODULES = (
    'utils.batch_pipeline.live',
    'utils.conversations.v3.fast_finish',
    'utils.conversations.v3.finish',
    'database.conversations_v3_live',
)
STAND_IN_CAPTURE_CLOSE = 'capture_close'
STAND_IN_ADMISSION = 'record_admission'
STAND_IN_PROJECTION = 'batch_projection'
STAND_IN_SYNC = 'sync_intake'
PROJECTION_REVISION = 1
LAB_AUDIO_BUCKET = 'scenario-lab-audio'  # the admission stand-in's reference: read as silence, never from storage


class _LabPrivacy:
    """``store.run``'s transaction for the fast-finish privacy check: allowed while the account's sync
    setting (the product reader) is on; ``BatchPrivacyBlocked`` once it is off."""

    def check_privacy(self, uid: str, *args: Any, **kwargs: Any) -> int:
        from database import users as users_db
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        if not users_db.get_user_private_cloud_sync_enabled(uid):
            raise BatchPrivacyBlocked('private cloud sync is off')
        return 0


class LabBatchStore:
    """The two members ``_manual_finish_admitted`` uses of the batch store (STAND_IN_ADMISSION)."""

    def __init__(self, client: Any):
        self.client = client

    def run(self, fn: Callable[[Any], Any]) -> Any:
        return fn(_LabPrivacy())


def segment_dicts(rec: Recording, origin: float) -> list[dict[str, Any]]:
    """The recording's scripted lines as stored segments, seconds from ``origin`` (scenario seconds)."""
    from models.transcript_segment import TranscriptSegment

    out = []
    for index, line in enumerate(rec.lines):
        segment = TranscriptSegment(
            id=f'{rec.doc_id}-{index}',
            text=line.text,
            speaker=line.speaker,
            speaker_id=int(line.speaker.rsplit('_', 1)[-1]) if line.speaker.rsplit('_', 1)[-1].isdigit() else 0,
            is_user=line.is_user,
            start=round(line.start - origin, 3),
            end=round(line.end - origin, 3),
        )
        out.append(segment.model_dump())
    return out


class ScenarioOps(ProductV3Ops):
    def __init__(
        self, *, scenario: Scenario, firestore: Any, finalizer: Any, barrier: ExecutorBarrier, home: Any = None
    ):
        super().__init__(finalizer=finalizer, barrier=barrier)
        self.scenario = scenario
        # scenario/home.HomeRecorder (or None): Home captured before each checkpoint, ``on_home`` on rows.
        self.home = home
        self.firestore = firestore
        self.requested: set[str] = set()  # labels a Finish reached while capturing
        self.finish_label: Optional[str] = None
        self.fast_finish_outcomes: dict[str, str] = {}
        self.checkpoints: dict[int, dict[str, Any]] = {}
        self._transcribing: Optional[Recording] = None
        self.stand_ins: dict[str, int] = {}
        self.stand_in_sources: dict[str, dict[str, int]] = {}  # stand-in -> words source -> count
        self.stt_sources: dict[str, str] = {}  # label -> cassette source, for audio_file recordings
        self.finish_taps: list[dict[str, Any]] = []  # one row per Finish tap (checks.finish_tap_row)
        self.transcribe_calls = 0  # fast-finish STT provider calls (budget vendor_calls.stt)
        self.seeded: set[str] = set()  # handles of ``seed`` history rows: not the run's conversations

    # ---- seams installed for the run ----------------------------------------------------------

    def install(self, stack: ExitStack) -> None:
        from utils.conversations.v3 import fast_finish
        from utils.batch_pipeline import live
        from utils.stt import pre_recorded

        original_run = fast_finish.run
        original_window = fast_finish.window_pcm
        original_read = live.read_reference
        chunk_starts: dict[int, int] = {}  # id(chunk audio) -> its first frame in the unit

        def transcribe(pcm: bytes, language: Optional[str]) -> list[dict[str, Any]]:
            # STT replaced by the script (serial kill-switch path): the unit is the whole recording,
            # so seconds are from its audio start.
            rec = self._transcribing
            self.transcribe_calls += 1
            return [] if rec is None else segment_dicts(rec, rec.audio[0])

        def window_pcm(references: Any, read: Any, lo: int, hi: int, cache: Any) -> bytes:
            # Remember where each chunk starts, so the scripted provider can answer for that window.
            pcm = original_window(references, read, lo, hi, cache)
            chunk_starts[id(pcm)] = lo
            return pcm

        def transcribe_words(
            pcm: bytes, language: Optional[str], *, route: Any = None, deadline: Optional[float] = None
        ) -> list[dict[str, Any]]:
            # STT replaced by the script on the chunked path that ships (CONVERSATIONS_V3_FAST_FINISH_CHUNKED
            # on): one provider request per chunk, answered with the scripted lines inside that chunk's
            # window, as provider utterances on the chunk's own clock.
            rec = self._transcribing
            self.transcribe_calls += 1
            if rec is None:
                return []
            lo = chunk_starts.pop(id(pcm), 0) / fast_finish.SAMPLE_RATE
            hi = lo + len(pcm) / 2 / fast_finish.SAMPLE_RATE
            return [
                {
                    'timestamp': [max(line['start'], lo) - lo, min(line['end'], hi) - lo],
                    'speaker': line['speaker'],
                    'text': line['text'],
                }
                for line in segment_dicts(rec, rec.audio[0])
                if line['end'] > lo and line['start'] < hi
            ]

        def read_reference(client: Any, ref: dict[str, Any], *args: Any, **kwargs: Any) -> bytes:
            # The lab's reference holds no stored audio: silence of its length, never a storage read.
            if ref.get('bucket') == LAB_AUDIO_BUCKET:
                return bytes(ref['frames'] * 2)
            return original_read(client, ref, *args, **kwargs)

        def route(*args: Any, **kwargs: Any) -> tuple[Any, Optional[str]]:
            # No language probe: the scripted recording keeps its declared language, and no vendor is called.
            return ('scripted', None, None), args[1] if len(args) > 1 else kwargs.get('language')

        def observed_run(uid: str, conversation_id: str, *args: Any, **kwargs: Any) -> str:
            outcome = original_run(uid, conversation_id, *args, **kwargs)
            self.fast_finish_outcomes[self.scenario.label_of(conversation_id)] = outcome
            return outcome

        stack.enter_context(patch.object(fast_finish, '_transcribe', transcribe))
        stack.enter_context(patch.object(fast_finish, '_transcribe_words', transcribe_words))
        stack.enter_context(patch.object(fast_finish, 'window_pcm', window_pcm))
        stack.enter_context(patch.object(pre_recorded, 'prerecorded_bytes_route', route))
        stack.enter_context(patch.object(live, 'read_reference', read_reference))
        stack.enter_context(patch.object(fast_finish, 'funded', lambda *args, **kwargs: True))
        stack.enter_context(patch.object(fast_finish, 'run', observed_run))

    # ---- helpers --------------------------------------------------------------------------------

    def _stand_in(self, name: str, rec: Optional[Recording] = None) -> None:
        self.stand_ins[name] = self.stand_ins.get(name, 0) + 1
        if rec is not None:
            source = self.stt_sources.get(rec.label, 'scripted')
            counts = self.stand_in_sources.setdefault(name, {})
            counts[source] = counts.get(source, 0) + 1

    def _ref(self, uid: str, rec: Recording) -> Any:
        return self.firestore.collection('users').document(uid).collection('conversations').document(rec.doc_id)

    def _raw(self, uid: str, rec: Recording) -> dict[str, Any]:
        with budget.lab_io():
            return self._ref(uid, rec).get().to_dict() or {}

    def pending(self, uid: str) -> bool:
        with budget.lab_io():  # the driver's own question, not a product read
            return super().pending(uid)

    def _flags(self, uid: str, rec: Recording) -> dict[str, Any]:
        raw = self._raw(uid, rec)  # a lab read (budget.lab_io)
        keys = ('status', 'v3_manual_end', 'v3_manual_end_requested', 'v3_pending', 'record_projection_revision')
        return {k: raw.get(k) for k in keys if raw.get(k) is not None}

    def _row(self, rec: Recording, *, created: float, status: str) -> dict[str, Any]:
        origin = self.scenario.origins[rec.origin]
        start = self.scenario.at(rec.audio[0])
        row: dict[str, Any] = {
            'id': rec.doc_id,
            'created_at': self.scenario.at(created),
            'started_at': start,
            'finished_at': start if status == 'in_progress' else self.scenario.at(rec.audio[1]),
            'status': status,
            'discarded': False,
            'structured': {},
            'source': origin.source,
            'language': 'en',
            'transcript_segments': [] if status == 'in_progress' else segment_dicts(rec, rec.audio[0]),
            'audio_files': [],
            'private_cloud_sync_enabled': self.scenario.account.private_cloud_sync_enabled,
            'client_device_id': f'scenario-origin-{origin.label.lower()}',
        }
        if rec.lane == 'batch':
            if self.scenario.batch_lane:
                row.update(
                    record_lane_owner='batch_live_v1',
                    server_batch_only=True,
                    server_batch_audio_start=start.timestamp(),
                )
            row.update(
                # Listen stamps every generation of one client recording with its origin
                # (routers/listen/conversations.py); a reconnect opens a new session under it.
                external_data={
                    'recording_session_id': f'scenario-session-{(rec.session or rec.label).lower()}',
                    'recording_origin_id': f'scenario-origin-{origin.label.lower()}',
                },
            )
        return row

    def _stt(self, rec: Recording) -> dict[str, str]:
        return {'stt': self.stt_sources[rec.label]} if rec.label in self.stt_sources else {}

    def _wake(self, uid: str, rec: Recording) -> None:
        from utils.conversations.v3 import triggers

        triggers.committed_sync_assignment(uid, {'recording': True, 'id': rec.doc_id})

    # ---- events ---------------------------------------------------------------------------------

    async def arrive(self, uid: str, event: ScenarioEvent) -> dict[str, Any]:  # type: ignore[override]
        handler = getattr(self, '_on_' + event.kind)
        if event.kind in ('finish', 'checkpoint', 'account'):
            return await handler(uid, event)
        rec = self.scenario.recording(event.ref)
        with capture_scope(rec.doc_id, 'scenario_' + event.kind):
            return await handler(uid, rec)

    async def _on_capture_start(self, uid: str, rec: Recording) -> dict[str, Any]:
        recording = await asyncio.to_thread(self._seed, uid, self._row(rec, created=rec.audio[0], status='in_progress'))
        return {'outcome': 'recording' if recording else 'legacy', 'session': rec.session}

    async def _on_seal(self, uid: str, rec: Recording) -> dict[str, Any]:
        from config import server_batch

        update: dict[str, Any] = {
            'status': 'completed',
            'finished_at': self.scenario.at(rec.audio[1]),
            'record_sealed_at': self.scenario.at(rec.sealed_at or rec.audio[1]).timestamp(),
        }
        if self.scenario.batch_lane:
            update['server_batch_audio_end'] = self.scenario.at(rec.audio[1]).timestamp()
        detail: dict[str, Any] = {}
        if rec.label in self.requested:
            self._stand_in(STAND_IN_CAPTURE_CLOSE)
            if server_batch.manual_end_marker_enabled():
                update['v3_manual_end_requested'] = True
                detail['manual_end_requested'] = True
            else:
                detail['manual_end_requested'] = 'kill_switch_off'
        await asyncio.to_thread(self._ref(uid, rec).update, update)
        return {'outcome': 'sealed', **detail}

    async def _on_finish(self, uid: str, event: ScenarioEvent) -> dict[str, Any]:
        from utils.conversations.process_conversation import retrieve_in_progress_conversation
        from utils.conversations.v3.finish import finish_live_window

        tap = len(self.finish_taps) + 1
        current = await asyncio.to_thread(retrieve_in_progress_conversation, uid)
        if current:
            # Production: finalize_conversation -> client_finalize job -> capture close stores the request.
            label = self.scenario.label_of(str(current.get('id')))
            self.requested.add(label)
            if self.finish_label is None:  # a later tap does not move the Finish target
                self.finish_label = label
            self.finish_taps.append(finish_tap_row('in_progress', None, self.scenario.label_of))
            return {'outcome': 'in_progress', 'target': label, 'stand_in': STAND_IN_CAPTURE_CLOSE, 'tap': tap}
        before = {rec.label: await asyncio.to_thread(self._flags, uid, rec) for rec in self.scenario.recordings}
        response = await asyncio.to_thread(finish_live_window, uid, None, allow_recording_fallback=True)
        after = {rec.label: await asyncio.to_thread(self._flags, uid, rec) for rec in self.scenario.recordings}
        changed = [
            rec.label
            for rec in self.scenario.recordings
            if after[rec.label] != before[rec.label]
            and (after[rec.label].get('v3_manual_end') or after[rec.label].get('v3_manual_end_requested'))
        ]
        if self.finish_label is None:
            self.finish_label = changed[0] if changed else None
        conversation = getattr(response, 'conversation', None) if response else None
        tile = getattr(conversation, 'tile_state', None)
        returned = conversation.model_dump() if conversation is not None else None
        self.finish_taps.append(
            finish_tap_row('no_pointer' if response else 'not_found', returned, self.scenario.label_of)
        )
        return {
            'outcome': 'no_pointer' if response else 'not_found',
            'target': changed[0] if changed else None,
            'tile': tile,
            'tap': tap,
        }

    async def _on_account(self, uid: str, event: ScenarioEvent) -> dict[str, Any]:
        from database import users as users_db

        def turn_off() -> None:
            with budget.lab_io():  # the owner's settings change, not pipeline work
                users_db.set_user_private_cloud_sync_enabled(uid, False)

        await asyncio.to_thread(turn_off)
        return {'outcome': 'sync_off'}

    async def _on_admission(self, uid: str, rec: Recording) -> dict[str, Any]:
        from utils.batch_pipeline import live
        from utils.conversations.v3 import fast_finish

        self._stand_in(STAND_IN_ADMISSION, rec)
        current = await asyncio.to_thread(self._raw, uid, rec)
        duration = rec.audio[1] - rec.audio[0]
        # One retained reference over the whole recording, read as silence (``install``): the chunked
        # pass plans its chunks from the references, and the scripted STT answers for each chunk.
        reference = {
            'bucket': LAB_AUDIO_BUCKET,
            'path': rec.label,
            'generation': 0,
            'start_frame': 0,
            'offset_frame': 0,
            'frames': int(round(duration * fast_finish.SAMPLE_RATE)),
        }
        units = [(self.scenario.at(rec.audio[0]).timestamp(), duration, [reference])]
        self._transcribing = rec
        try:
            await live._manual_finish_admitted(
                LabBatchStore(self.firestore), uid, rec.doc_id, current, units, None, b'', privacy_generation=None
            )
            pending = list(live._FAST_FINISH_TASKS)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self._transcribing = None
        detail: dict[str, Any] = {'outcome': 'admitted', **self._flags(uid, rec)}
        if rec.label in self.fast_finish_outcomes:
            detail['fast_finish'] = self.fast_finish_outcomes[rec.label]
        return detail

    async def _on_transcript(self, uid: str, rec: Recording) -> dict[str, Any]:
        from database import conversations as conversations_db

        self._stand_in(STAND_IN_PROJECTION, rec)
        segments = segment_dicts(rec, rec.audio[0])
        wrote = await asyncio.to_thread(
            conversations_db.update_conversation_segments,
            uid,
            rec.doc_id,
            segments,
            finished_at=self.scenario.at(rec.audio[1]),
        )
        await asyncio.to_thread(
            self._ref(uid, rec).update, {'record_projection_revision': PROJECTION_REVISION, 'has_content': True}
        )
        await asyncio.to_thread(self._wake, uid, rec)
        return {'outcome': 'landed' if wrote is not False else 'refused', 'words': rec.words(), **self._stt(rec)}

    async def _on_sync(self, uid: str, rec: Recording) -> dict[str, Any]:
        self._stand_in(STAND_IN_SYNC, rec)
        row = self._row(rec, created=rec.audio[1] if rec.arrives_at is None else rec.arrives_at, status='completed')
        recording = await asyncio.to_thread(self._seed, uid, row)
        await asyncio.to_thread(
            self._ref(uid, rec).update, {'record_projection_revision': PROJECTION_REVISION, 'has_content': True}
        )
        await asyncio.to_thread(self._wake, uid, rec)
        return {'outcome': 'recording' if recording else 'legacy', 'words': rec.words(), **self._stt(rec)}

    async def _on_checkpoint(self, uid: str, event: ScenarioEvent) -> dict[str, Any]:
        check = self.scenario.checks[event.check_index or 0]
        if self.home is not None:  # Home at this instant first, so the snapshot's rows carry on_home
            await asyncio.to_thread(self.home_snapshot, check.at)
        snapshot = await asyncio.to_thread(self.snapshot, uid)
        facts = self.facts()
        result = evaluate(check, snapshot, self.finish_label, facts)
        # The facts are kept with the result so the verdict row shows what this instant saw, not the run's end.
        self.checkpoints[event.check_index or 0] = {'result': result, 'snapshot': snapshot, 'facts': facts}
        return {'outcome': 'ok' if result.ok else 'mismatch', 'conversations': len(snapshot)}

    # ---- reading --------------------------------------------------------------------------------

    def home_snapshot(self, at: Optional[float]) -> Any:
        """Home at this instant (``home.write_home_snapshot``), its reads counted under the ``home`` scope."""
        with budget.scope('home'):
            return self.home.write_home_snapshot(at)

    def facts(self) -> dict[str, Any]:
        """What the non-snapshot checks read (``checks.evaluate``): fast-finish outcomes and Finish taps."""
        return {'fast_finish': dict(self.fast_finish_outcomes), 'finish_taps': list(self.finish_taps)}

    def snapshot(self, uid: str) -> list[dict[str, Any]]:
        """Every v3 conversation now, summarized (labels, words, visibility; no text)."""
        with budget.lab_io():
            return self._snapshot(uid)

    def _snapshot(self, uid: str) -> list[dict[str, Any]]:
        from testing.pipeline_lab.v3.product import read_v3_rows
        from utils.conversations.v3.word_floor import text_word_count

        derived, _ = read_v3_rows(uid)
        rows = []
        for row in derived:
            if str(row.get('id') or '')[:8] in self.seeded:
                continue
            words = sum(text_word_count(str(s.get('text') or '')) for s in row.get('transcript_segments') or [])
            rows.append(conversation_row(row, self.scenario.label_of, words))
        rows.sort(key=lambda r: str(r.get('started_at') or ''))
        return self.home.annotate_rows(rows) if self.home is not None else rows

    def recordings(self, uid: str) -> list[dict[str, Any]]:
        with budget.lab_io():
            return self._recordings(uid)

    def _recordings(self, uid: str) -> list[dict[str, Any]]:
        out = []
        for rec in self.scenario.recordings:
            flags = self._flags(uid, rec)
            raw = self._raw(uid, rec)
            claims = raw.get('claims') or []
            row = {'label': rec.label, 'lane': rec.lane, 'words': rec.words(), 'claims': len(claims), **flags}
            out.append({**row, **self._stt(rec)})
        return out
