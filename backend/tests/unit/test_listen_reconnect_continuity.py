"""Replays of the stable-client-ID reconnect shape, through real lifecycle decisions."""

from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from database import listen_continuations
from models.calendar_context import CalendarMeetingContext
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from routers.listen import conversations as controller_module
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import process_conversation as pc


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class CaptureHarness:
    def __init__(self, monkeypatch: Any) -> None:
        self.now = datetime(2026, 9, 19, 15, 30, tzinfo=timezone.utc)
        self.store = StrictFirestore()
        self.bindings: dict[str, str] = {'original': 'original'}
        self.rows: dict[str, dict[str, Any]] = {
            'original': self.row('original', status='completed', text='Previous recording')
        }
        self.store.rows[('users', 'u', 'recording_sessions', 'original')] = {
            'uid': 'u',
            'recording_session_id': 'original',
            'conversation_id': 'original',
            'lifecycle_phase': 'completed',
        }
        self.events: list[Any] = []
        self.creates = 0
        self.meetings = []
        self.deleted: list[str] = []
        self.pointer: str | None = None
        monkeypatch.setattr(listen_continuations, 'get_firestore_client', lambda: self.store)
        monkeypatch.setattr(
            controller_module.lifecycle_service, 'delete_empty_recording_conversation', self.delete_empty
        )

    def row(self, cid: str, *, status: str = 'in_progress', text: str = '') -> dict[str, Any]:
        return dict(
            id=cid,
            source='omi',
            client_device_id='phone',
            status=status,
            discarded=False,
            started_at=self.now,
            finished_at=self.now,
            created_at=self.now,
            transcript_segments=[{'text': text}] if text else [],
            photos=[],
        )

    def delete_empty(self, uid: str, cid: str, sid: str | None) -> bool:
        row = self.rows.get(cid)
        if not row or row.get('status') != 'in_progress' or row.get('transcript_segments') or row.get('has_content'):
            return False
        self.rows.pop(cid)
        self.store.rows.pop(('users', 'u', 'conversations', cid), None)
        self.deleted.append(cid)
        return True

    async def call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        name = fn.__name__
        if name == 'open_live_recording_session':
            uid, sid, proposed = args
            was_bound = sid in self.bindings
            cid = self.bindings.setdefault(sid, proposed)
            row = self.rows.get(cid)
            return dict(
                conversation_id=cid,
                requires_rollover=was_bound and row is None,
                conversation_snapshot=deepcopy(row),
                conversation_snapshot_known=was_bound,
                lifecycle_version=1,
                lifecycle_phase=(row or {}).get('status', 'in_progress'),
                lifecycle_sequence=0,
            )
        if name == 'get_conversation':
            return deepcopy(self.rows.get(args[1]))
        if name == 'create_in_progress_conversation':
            row = deepcopy(args[1])
            self.creates += 1
            self.rows[row['id']] = row
            self.store.rows[('users', 'u', 'conversations', row['id'])] = row
            return True
        if name == 'get_meetings_in_time_range':
            return deepcopy(self.meetings)
        if name == 'set_in_progress_conversation_id':
            self.pointer = args[1]
            return None
        if name == 'retrieve_in_progress_conversation':
            return deepcopy(self.rows.get(self.pointer or ''))
        if name == 'resolve_live_continuation':
            return fn(*args, **kwargs)
        if name == 'delete_empty':
            return fn(*args, **kwargs)
        raise AssertionError(name)

    def connect(self, *, client_id: str | None = 'original') -> LiveConversationController:
        host = SimpleNamespace(
            request=SimpleNamespace(
                uid='u',
                source='omi',
                conversation_role='ambient',
                geolocation=None,
                call_id=None,
                onboarding_mode=False,
            ),
            client_device_context=SimpleNamespace(client_device_id='phone', platform='ios'),
            client_conversation_id=client_id,
            recording_session_id=client_id or 'legacy-session',
            recording_session_ids_by_conversation={},
            is_multi_channel=False,
            use_custom_stt=False,
            private_cloud_sync_enabled=False,
            language='en',
            onboarding_admitted=False,
            conversation_creation_timeout=120,
            state=SimpleNamespace(current_conversation_id=None, active=True),
            persistence=SimpleNamespace(call=self.call),
            send_event=self.events.append,
            transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
            speakers=SimpleNamespace(refresh_for_conversation=AsyncMock()),
        )
        controller = LiveConversationController(host, clock=lambda: self.now)
        controller.on_conversation_processed = lambda cid: None
        return controller


@pytest.mark.anyio
@pytest.mark.parametrize('title_fields', [{'title': 'Planning sync'}, {}, {'title': None}, {'title': ''}])
async def test_live_meeting_stamp_reaches_finalization_and_meeting_aware_summary(monkeypatch, title_fields):
    harness = CaptureHarness(monkeypatch)
    harness.meetings = [
        {
            'id': 'meeting-doc',
            'calendar_event_id': 'event-1',
            'calendar_source': 'system_calendar',
            'start_time': harness.now - timedelta(minutes=30),
            'end_time': harness.now + timedelta(minutes=30),
            'duration_minutes': 60,
            **title_fields,
        }
    ]
    controller = harness.connect()
    await controller.prepare()
    row = harness.rows[controller.host.state.current_conversation_id]
    expected_title = title_fields.get('title') or ''
    stamped = CalendarMeetingContext(**row['external_data']['calendar_meeting_context'])
    assert stamped.title == expected_title
    assert row['external_data']['calendar_meeting_context']['end_time'] == harness.meetings[0]['end_time']

    # Re-load the persisted live row as finalization does, with enough captured speech.
    conversation = Conversation(**row)
    conversation.finished_at = harness.now + timedelta(minutes=6)
    conversation.transcript_segments = [
        TranscriptSegment(
            id='seg-1',
            text='We agreed to launch the project next week and review progress on Friday.',
            speaker='SPEAKER_00',
            speaker_id=0,
            is_user=True,
            start=0,
            end=360,
        )
    ]
    assert pc._stored_meeting_context(conversation) == stamped
    # The stamp must stand on its own even without a subsequent provider read.
    monkeypatch.setattr(pc, '_stored_meeting_lookup_enabled', lambda: False)
    monkeypatch.setattr(pc, '_calendar_context_read_enabled', lambda: False)
    monkeypatch.setattr(pc, '_ocr_meeting_context_enabled', lambda: False)
    pc._enrich_meeting_context('u', conversation)
    assert pc._stored_meeting_context(conversation) == stamped

    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda uid: 'en')
    transcript = conversation.transcript_segments[0].text
    monkeypatch.setattr(pc, 'conversation_transcripts_for_llm', lambda *args: (transcript, transcript, {0: 'David'}))
    monkeypatch.setattr(pc, 'track_usage', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: True)
    monkeypatch.setattr(pc, '_meeting_notes_episode_evidence_enabled', lambda uid: False)
    monkeypatch.setattr(pc, '_meeting_notes_rich_context_enabled', lambda: False)
    monkeypatch.setattr(pc, '_fetch_dedup_candidates_for_query', lambda *args: [])
    monkeypatch.setattr(pc, 'submit_relevance_shadow', lambda **kwargs: None)
    notes = Mock(return_value=Structured(title='Project launch', overview='Launch next week; review on Friday.'))
    monkeypatch.setattr(pc, 'get_conversation_notes', notes)
    prefix_builder = Mock(wraps=pc.build_conversation_prompt_prefix)
    monkeypatch.setattr(pc, 'build_conversation_prompt_prefix', prefix_builder)

    structured, discarded = pc._get_structured('u', 'en', conversation, user_kept=True)

    assert not discarded
    assert structured.title == 'Project launch'
    assert structured.overview
    assert prefix_builder.call_args.kwargs['calendar_context'] == stamped
    notes.assert_called_once()
    assert f'- Meeting title: {expected_title}' in notes.call_args.args[0].context


@pytest.mark.anyio
async def test_terminal_origin_reconnects_reuse_one_continuation_until_exact_silence_boundary(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    initial = deepcopy(harness.rows['original'])
    ids = []
    for tick in (0, 35, 70, 105, 119):
        harness.now = initial['finished_at'] + timedelta(seconds=tick)
        controller = harness.connect()
        await controller.prepare()
        ids.append(controller.host.state.current_conversation_id)
    assert len(set(ids)) == 1
    assert harness.creates == 1
    assert harness.rows['original'] == initial
    harness.now = initial['finished_at'] + timedelta(seconds=120)
    controller = harness.connect()
    await controller.prepare()
    assert controller.host.state.current_conversation_id != ids[0]
    assert ids[0] in harness.deleted
    assert len([r for r in harness.rows.values() if r['status'] == 'in_progress']) == 1


@pytest.mark.anyio
async def test_legacy_reconnect_already_reuses_empty_stub_within_window(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = harness.connect(client_id=None)
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    harness.now += timedelta(seconds=35)
    reconnect = harness.connect(client_id=None)
    await reconnect.prepare()
    assert reconnect.host.state.current_conversation_id == cid
    assert harness.creates == 1


@pytest.mark.anyio
async def test_other_device_redis_pointer_does_not_steal_durable_continuation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    harness.rows['desktop'] = dict(harness.row('desktop'), source='desktop', client_device_id='mac')
    harness.pointer = 'desktop'
    harness.now += timedelta(seconds=35)
    reconnect = harness.connect()
    await reconnect.prepare()
    assert reconnect.host.state.current_conversation_id == cid


@pytest.mark.anyio
@pytest.mark.parametrize(
    'field,value',
    [
        ('deleted', True),
        ('discarded', True),
        ('is_locked', True),
        ('client_device_id', 'other'),
        ('status', 'processing'),
    ],
)
async def test_continuation_never_resumes_a_retired_or_incompatible_row(monkeypatch, field, value):
    harness = CaptureHarness(monkeypatch)
    first = harness.connect()
    await first.prepare()
    cid = first.host.state.current_conversation_id
    harness.rows[cid][field] = value
    before = deepcopy(harness.rows[cid])
    harness.now += timedelta(seconds=35)
    second = harness.connect()
    await second.prepare()
    assert second.host.state.current_conversation_id != cid
    assert harness.rows[cid] == before


def test_competing_proposals_converge_without_changing_original_binding():
    store = StrictFirestore()
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    root = ('users', 'u', 'recording_sessions', 'origin')
    store.rows[root] = dict(uid='u', recording_session_id='origin', conversation_id='old', lifecycle_phase='completed')
    for cid in ('a', 'b'):
        store.rows[('users', 'u', 'conversations', cid)] = dict(
            status='in_progress', source='omi', client_device_id=None, finished_at=now
        )
    results = []
    for cid in ('a', 'b'):
        selected, _ = listen_continuations.resolve_live_continuation(
            'u',
            'origin',
            source='omi',
            device_id=None,
            now=now,
            timeout=120,
            proposed={'conversation_id': cid, 'recording_session_id': cid},
            firestore_client=store,
        )
        results.append(selected)
    assert results[0] == results[1]
    assert store.rows[root]['conversation_id'] == 'old'
    assert store.rows[root]['lifecycle_phase'] == 'completed'


def test_unmigrated_origin_is_not_invented_by_continuation_admission():
    store = StrictFirestore()
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    store.rows[('users', 'u', 'conversations', 'candidate')] = {
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': now,
    }
    selected, retired = listen_continuations.resolve_live_continuation(
        'u',
        'legacy-origin',
        source='omi',
        device_id=None,
        now=now,
        timeout=120,
        proposed={'conversation_id': 'candidate', 'recording_session_id': 'candidate'},
        firestore_client=store,
    )
    assert selected is None and retired is None
    assert ('users', 'u', 'recording_sessions', 'legacy-origin') not in store.rows
    assert ('users', 'u', 'conversations', 'candidate') in store.rows


@pytest.mark.anyio
async def test_lifecycle_loop_uses_exact_same_silence_boundary_as_reconnect(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    original = controller.host.state.current_conversation_id
    ticks = iter((119, 1))

    async def wait(seconds):
        delta = next(ticks, None)
        if delta is None:
            return True
        harness.now += timedelta(seconds=delta)
        return False

    controller.host.wait = wait
    await controller.lifecycle_loop()
    assert harness.creates == 2
    assert controller.host.state.current_conversation_id != original
    assert original in harness.deleted


@pytest.mark.anyio
async def test_external_processing_transition_can_still_create_an_overlapping_live_generation(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    previous = controller.host.state.current_conversation_id
    # This is a controllable mechanism, not a claim about September 18 logs.
    harness.rows[previous].update(status='processing', transcript_segments=[{'text': 'kept'}])
    controller.host.wait = AsyncMock(side_effect=[False, True])
    await controller.lifecycle_loop()
    current = controller.host.state.current_conversation_id
    assert current != previous
    assert harness.rows[current]['started_at'] == harness.rows[previous]['started_at']
    assert harness.rows[previous]['transcript_segments'] == [{'text': 'kept'}]


def meeting_context(start):
    return {
        'calendar_meeting_context': {
            'calendar_event_id': 'event-1',
            'title': 'Planning',
            'start_time': start.isoformat(),
            'duration_minutes': 120,
            'meeting_treatment_eligible': False,
        }
    }


@pytest.mark.anyio
async def test_calendar_meeting_reconnect_and_lifecycle_continue_until_scheduled_end_grace(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    row = harness.rows[cid]
    start = harness.now - timedelta(minutes=60)
    row.update(transcript_segments=[{'text': 'kept'}], external_data=meeting_context(start))
    harness.now += timedelta(minutes=15)
    reconnect = harness.connect()
    await reconnect.prepare()
    assert reconnect.host.state.current_conversation_id == cid
    assert harness.creates == 1
    reconnect.host.wait = AsyncMock(side_effect=[False, True])
    await reconnect.lifecycle_loop()
    assert harness.creates == 1
    # The exact deadline is a split, even when the context is still on the row.
    harness.now = start + timedelta(minutes=122)
    reconnect.process_conversation = AsyncMock(return_value=True)
    reconnect.host.wait = AsyncMock(side_effect=[False, True])
    await reconnect.lifecycle_loop()
    assert reconnect.host.state.current_conversation_id != cid
    reconnect.process_conversation.assert_awaited_once_with(cid)


@pytest.mark.parametrize(
    'empty,device,eligible', [(False, 'phone', False), (False, 'other', False), (True, 'phone', False)]
)
def test_meeting_continuation_keeps_device_and_empty_generation_fences(empty, device, eligible):
    from utils.conversation_continuity import resumable_continuation

    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    row = dict(
        status='in_progress',
        source='omi',
        client_device_id='phone',
        finished_at=now,
        external_data=meeting_context(now),
        transcript_segments=[] if empty else [{'text': 'kept'}],
    )
    assert resumable_continuation(
        row, source='omi', device_id=device, now=now + timedelta(minutes=10), timeout=120
    ) is (not empty and device == 'phone')


def test_metadata_only_continuation_lookup_reads_stored_calendar_context():
    store = StrictFirestore()
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    store.rows[('users', 'u', 'recording_sessions', 'origin')] = {
        'uid': 'u',
        'recording_session_id': 'origin',
        'conversation_id': 'old',
        'live_continuation': {'conversation_id': 'meeting', 'recording_session_id': 'meeting'},
    }
    store.rows[('users', 'u', 'conversations', 'meeting')] = {
        'status': 'in_progress',
        'source': 'omi',
        'client_device_id': 'phone',
        'finished_at': now,
        'has_content': True,
        'external_data': meeting_context(now),
    }
    result, retired = listen_continuations.resolve_live_continuation(
        'u',
        'origin',
        source='omi',
        device_id='phone',
        now=now + timedelta(minutes=10),
        timeout=120,
        firestore_client=store,
    )
    assert result == {'conversation_id': 'meeting', 'recording_session_id': 'meeting'}
    assert retired is None


@pytest.mark.parametrize(
    'context',
    [
        None,
        {},
        {'calendar_event_id': 'bad', 'start_time': 'bad', 'duration_minutes': 120},
        {'calendar_event_id': 'screen-activity', 'start_time': '2026-10-07T00:00:00Z', 'duration_minutes': 120},
    ],
)
def test_missing_or_invalid_calendar_context_keeps_120_second_boundary(context):
    from utils.conversation_continuity import resumable_continuation

    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    row = dict(
        status='in_progress',
        source='omi',
        client_device_id='phone',
        finished_at=now,
        external_data={'calendar_meeting_context': context},
        has_content=True,
    )
    assert resumable_continuation(row, source='omi', device_id='phone', now=now + timedelta(seconds=119), timeout=120)
    assert not resumable_continuation(
        row, source='omi', device_id='phone', now=now + timedelta(seconds=120), timeout=120
    )


def test_compressed_empty_recording_does_not_extend_meeting_deadline():
    from utils.conversation_continuity import continuation_timeout

    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    row = dict(
        finished_at=now,
        transcript_segments='compressed-empty-blob',
        transcript_segments_compressed=True,
        external_data=meeting_context(now),
    )
    assert continuation_timeout(row, 120) == 120


@pytest.mark.parametrize('identity', ['partial_context', 'external_event', 'calendar_link'])
def test_calendar_id_only_continuation_resolves_exact_users_meeting(identity):
    from database.document_ids import calendar_meeting_doc_id

    store = StrictFirestore()
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    source = 'google' if identity == 'calendar_link' else 'system_calendar'
    root = ('users', 'u', 'recording_sessions', 'origin')
    store.rows[root] = {
        'uid': 'u',
        'recording_session_id': 'origin',
        'live_continuation': {'conversation_id': 'meeting', 'recording_session_id': 'meeting'},
    }
    row = dict(status='in_progress', source='omi', client_device_id='phone', finished_at=now, has_content=True)
    if identity == 'partial_context':
        row['external_data'] = {'calendar_meeting_context': {'calendar_event_id': 'event-1'}}
    elif identity == 'external_event':
        row['external_data'] = {'calendar_event_id': 'event-1'}
    else:
        row['calendar_event'] = {'event_id': 'event-1'}
    path = ('users', 'u', 'conversations', 'meeting')
    store.rows[path] = deepcopy(row)
    event_path = ('users', 'u', 'meetings', calendar_meeting_doc_id('u', source, 'event-1'))
    store.rows[event_path] = {
        'calendar_event_id': 'event-1',
        'calendar_source': source,
        'start_time': now,
        'duration_minutes': 120,
        'title': 'Planning',
    }
    result, retired = listen_continuations.resolve_live_continuation(
        'u',
        'origin',
        source='omi',
        device_id='phone',
        now=now + timedelta(minutes=10),
        timeout=120,
        firestore_client=store,
    )
    assert result == {'conversation_id': 'meeting', 'recording_session_id': 'meeting'}
    assert retired is None
    cached = store.rows[path]['external_data']['calendar_meeting_context']
    assert cached == store.rows[event_path]
    assert {key: value for key, value in store.rows[path].items() if key != 'external_data'} == {
        key: value for key, value in row.items() if key != 'external_data'
    }


@pytest.mark.parametrize(
    'record',
    [
        None,
        {'calendar_event_id': 'other', 'calendar_source': 'system_calendar'},
        {'calendar_event_id': 'event-1', 'calendar_source': 'screen_activity'},
    ],
)
def test_calendar_id_fallback_does_not_join_a_different_event(record):
    from database.document_ids import calendar_meeting_doc_id
    from utils.conversation_continuity import resumable_continuation

    store = StrictFirestore()
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    row = dict(
        status='in_progress',
        source='omi',
        client_device_id='phone',
        finished_at=now,
        has_content=True,
        external_data={'calendar_event_id': 'event-1'},
    )
    if record:
        store.rows[('users', 'u', 'meetings', calendar_meeting_doc_id('u', 'system_calendar', 'event-1'))] = record
    resolved = listen_continuations.calendar_continuity_row('u', row, firestore_client=store)
    assert resolved is row
    assert not resumable_continuation(
        resolved, source='omi', device_id='phone', now=now + timedelta(seconds=120), timeout=120
    )


def test_calendar_lookup_failure_preserves_silence_rule_and_emits_fallback(monkeypatch):
    from unittest.mock import Mock

    record = Mock()
    monkeypatch.setattr(listen_continuations, 'record_fallback', record)
    client = Mock()
    client.collection.side_effect = RuntimeError('fixture lookup failure')
    row = {'external_data': {'calendar_event_id': 'event-1'}}
    assert listen_continuations.calendar_continuity_row('u', row, firestore_client=client) is row
    record.assert_called_once()
    assert record.call_args.kwargs['to_mode'] == 'silence_boundary'


@pytest.mark.anyio
async def test_controller_hydrates_calendar_id_before_resume_and_live_timeout(monkeypatch):
    from database.document_ids import calendar_meeting_doc_id

    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    harness.rows[cid].update(
        has_content=True, transcript_segments=[{'text': 'kept'}], external_data={'calendar_event_id': 'event-1'}
    )
    harness.store.rows[('users', 'u', 'meetings', calendar_meeting_doc_id('u', 'system_calendar', 'event-1'))] = {
        'calendar_event_id': 'event-1',
        'calendar_source': 'system_calendar',
        'start_time': harness.now,
        'duration_minutes': 120,
    }
    prior_call = harness.call

    async def call(fn, *args, **kwargs):
        if fn is listen_continuations.calendar_continuity_row:
            return fn(*args, **kwargs, firestore_client=harness.store)
        return await prior_call(fn, *args, **kwargs)

    harness.now += timedelta(minutes=10)
    reconnect = harness.connect()
    reconnect.host.persistence.call = call
    await reconnect.prepare()
    assert reconnect.host.state.current_conversation_id == cid
    reconnect.host.wait = AsyncMock(side_effect=[False, True])
    await reconnect.lifecycle_loop()
    assert harness.creates == 1


@pytest.mark.anyio
@pytest.mark.parametrize('meeting_state', ['active', 'none', 'expired', 'future', 'screen'])
async def test_live_created_row_honors_active_calendar_window(monkeypatch, meeting_state):
    harness = CaptureHarness(monkeypatch)
    if meeting_state != 'none':
        start = harness.now - timedelta(minutes=30)
        if meeting_state == 'future':
            start = harness.now + timedelta(minutes=1)
        harness.meetings = [
            {
                'id': 'meeting-doc',
                'calendar_event_id': 'event-1',
                'calendar_source': 'screen_activity' if meeting_state == 'screen' else 'system_calendar',
                'start_time': start,
                'duration_minutes': 120,
                'end_time': (
                    harness.now - timedelta(minutes=1) if meeting_state == 'expired' else start + timedelta(minutes=120)
                ),
            }
        ]
    controller = harness.connect()
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    row = harness.rows[cid]
    assert ('calendar_meeting_context' in row['external_data']) is (meeting_state == 'active')
    row.update(has_content=True, transcript_segments=[{'text': 'kept'}])
    controller.process_conversation = AsyncMock(return_value=True)
    # Active meeting survives fifteen quiet minutes; all other captures split at exactly 120 seconds.
    harness.now += timedelta(seconds=900 if meeting_state == 'active' else 120)
    controller.host.wait = AsyncMock(side_effect=[False, True])
    await controller.lifecycle_loop()
    assert (controller.host.state.current_conversation_id == cid) is (meeting_state == 'active')
    assert harness.creates == (1 if meeting_state == 'active' else 2)


@pytest.mark.anyio
async def test_lifecycle_polls_read_an_id_only_meeting_once_per_window(monkeypatch):
    from database.document_ids import calendar_meeting_doc_id
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    harness = CaptureHarness(monkeypatch)
    controller = harness.connect()
    await controller.prepare()
    cid = controller.host.state.current_conversation_id
    row = harness.rows[cid]
    row.update(has_content=True, transcript_segments=[{'text': 'kept'}])
    row['external_data']['calendar_event_id'] = 'event-1'
    event_path = ('users', 'u', 'meetings', calendar_meeting_doc_id('u', 'system_calendar', 'event-1'))
    harness.store.rows[event_path] = {
        'calendar_event_id': 'event-1',
        'calendar_source': 'system_calendar',
        'start_time': harness.now,
        'duration_minutes': 120,
    }
    reads = 0
    original_get = StrictFirestoreDocument.get

    def count_lookup(ref, *args, **kwargs):
        nonlocal reads
        if ref.path == event_path:
            reads += 1
        return original_get(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', count_lookup)
    prior_call = harness.call

    async def call(fn, *args, **kwargs):
        if fn is listen_continuations.calendar_continuity_row:
            return fn(*args, **kwargs, firestore_client=harness.store)
        return await prior_call(fn, *args, **kwargs)

    controller.host.persistence.call = call
    ticks = iter([False] * 12 + [True])

    async def wait(seconds):
        harness.now += timedelta(seconds=seconds)
        return next(ticks)

    controller.host.wait = wait
    harness.now += timedelta(minutes=15)
    await controller.lifecycle_loop()
    assert reads == 1
    assert harness.creates == 1
    assert row['external_data']['calendar_meeting_context']['duration_minutes'] == 120
    assert row['external_data']['recording_session_id'] == controller.host.recording_session_id


def test_reconnect_window_cache_defers_writes_until_candidate_reads(monkeypatch):
    from database.document_ids import calendar_meeting_doc_id
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    store = StrictFirestore()
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    root = ('users', 'u', 'recording_sessions', 'origin')
    store.rows[root] = {
        'uid': 'u',
        'recording_session_id': 'origin',
        'live_continuation': {'conversation_id': 'old', 'recording_session_id': 'old'},
    }
    event_path = ('users', 'u', 'meetings', calendar_meeting_doc_id('u', 'system_calendar', 'event-1'))
    store.rows[event_path] = {
        'calendar_event_id': 'event-1',
        'calendar_source': 'system_calendar',
        'start_time': now,
        'duration_minutes': 120,
    }
    store.rows[('users', 'u', 'conversations', 'old')] = {
        'status': 'completed',
        'source': 'omi',
        'client_device_id': 'phone',
        'finished_at': now,
        'has_content': True,
        'external_data': {'calendar_event_id': 'event-1'},
    }
    store.rows[('users', 'u', 'conversations', 'new')] = {
        'status': 'in_progress',
        'source': 'omi',
        'client_device_id': 'phone',
        'finished_at': now,
        'has_content': True,
    }
    reads = 0
    original_get = StrictFirestoreDocument.get

    def count_lookup(ref, *args, **kwargs):
        nonlocal reads
        if ref.path == event_path:
            reads += 1
        return original_get(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', count_lookup)
    for _ in range(3):
        selected, _ = listen_continuations.resolve_live_continuation(
            'u',
            'origin',
            source='omi',
            device_id='phone',
            now=now,
            timeout=120,
            proposed={'conversation_id': 'new', 'recording_session_id': 'new'},
            firestore_client=store,
        )
        assert selected == {'conversation_id': 'new', 'recording_session_id': 'new'}
    assert reads == 1
    assert (
        store.rows[('users', 'u', 'conversations', 'old')]['external_data']['calendar_meeting_context']['start_time']
        == now
    )
