"""Replays of the stable-client-ID reconnect shape, through real lifecycle decisions."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from database import listen_continuations
from routers.listen import conversations as controller_module
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


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
