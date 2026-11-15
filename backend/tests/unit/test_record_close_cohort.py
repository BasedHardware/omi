"""Account selection is independent on both peers and never changes legacy bytes."""

import json
import struct
from unittest.mock import AsyncMock, Mock

import pytest

from config.pusher_record import close_notify_enabled
from config.refactor_modes import uid_digest
from routers import pusher
from tests.unit.test_audio_durable_outbox import Socket, inline_session, remote
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session
from utils import listen_pusher_session

SWITCH = 'PUSHER_RECORD_CLOSE_NOTIFY_ENABLED'
PERCENT = SWITCH + '_SERVE_PERCENT'
DIGESTS = SWITCH + '_SERVE_UID_SHA256S'


def select(monkeypatch, membership):
    monkeypatch.delenv(SWITCH, raising=False)
    monkeypatch.setenv(PERCENT, '0')
    monkeypatch.setenv(DIGESTS, '')
    if membership != 'absent':
        monkeypatch.setenv(SWITCH, 'true')
    if membership == 'fleet':
        monkeypatch.delenv(PERCENT, raising=False)
        monkeypatch.delenv(DIGESTS, raising=False)
    elif membership == 'member':
        # Synthetic fixture identity only; no account material enters the test.
        monkeypatch.setenv(DIGESTS, uid_digest('owner'))
    elif membership == 'other':
        monkeypatch.setenv(DIGESTS, uid_digest('another-synthetic-owner'))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'listen_cohort,pusher_cohort',
    [
        ('member', 'member'),
        ('fleet', 'fleet'),
        ('fleet', 'other'),
        ('other', 'fleet'),
        ('member', 'other'),
        ('other', 'member'),
        ('absent', 'absent'),
        ('zero', 'zero'),
        ('other', 'other'),
    ],
)
async def test_both_account_cohorts_must_qualify_v3(inline_session, monkeypatch, listen_cohort, pusher_cohort):
    select(monkeypatch, listen_cohort)
    selected = listen_cohort in {'member', 'fleet'}
    if not selected:
        reject = Mock(side_effect=AssertionError('non-cohort protocol allocated'))
        monkeypatch.setattr(listen_pusher_session, 'ListenRecordBoundary', reject)
        monkeypatch.setattr(listen_pusher_session, 'PendingClose', reject)
    offered = []
    socket = FakePusherWebSocket()
    active = {'active': True}

    async def connect(*args, **kwargs):
        offered.append(kwargs)
        return socket

    session = make_session(
        ws=socket,
        active_ref=active,
        config_overrides={'uid': 'owner'},
        deps_overrides={'connect_to_pusher': connect, 'finish_recording_audio': AsyncMock(return_value=True)},
    )
    await session.connect()
    version = offered[0].get('record_close_protocol')
    assert version == (3 if selected else None)
    if not selected:
        assert session.record_boundary is session.pending_record_closes is None
        assert session.record_close_boundaries is session.deferred_record_closes is None
        with session.audio_frame('conv-1') as frame:
            assert frame is None
        session.audio_bytes_send(b'abcd', received_at=100)
        assert session.audio_runs[-1].conversation_id is None
        await session._audio_bytes_flush()
        assert socket.sent == [struct.pack('<I', 103) + b'conv-1', struct.pack('<Id', 101, 100 - 2 / 8000) + b'abcd']

    select(monkeypatch, pusher_cohort)
    expected = selected and pusher_cohort in {'member', 'fleet'}
    if not expected:
        monkeypatch.setattr(
            pusher, 'PusherCloseState', Mock(side_effect=AssertionError('unqualified pusher allocated'))
        )
    peer = Socket([])
    await pusher._websocket_util_trigger(peer, 'owner', 16000, record_close_protocol=version)
    acknowledgments = [frame for frame in peer.sent if struct.unpack('<I', frame[:4])[0] == 204]
    assert bool(acknowledgments) is expected
    if expected:
        assert json.loads(acknowledgments[0][4:]) == {'type': 'record_close_ack', 'version': 3, 'abort_to_legacy': True}
    select(monkeypatch, listen_cohort)
    socket.incoming.extend([*acknowledgments, b''])
    socket.on_recv = lambda: active.update(active=len(socket.incoming) > 1)
    session.pending_request_event.set()
    session.pending_conversation_requests['unrelated'] = {'sent_at': 1000, 'retries': 0}
    await session.pusher_receive()
    assert session.record_close_supported is expected
    assert session.record_close_abort_supported is expected
    assert not socket.closed_codes


@pytest.mark.parametrize('switch', [None, 'false', 'invalid'])
def test_disabled_switch_ignores_even_a_complete_cohort(monkeypatch, switch):
    select(monkeypatch, 'member')
    if switch is None:
        monkeypatch.delenv(SWITCH)
    else:
        monkeypatch.setenv(SWITCH, switch)
    monkeypatch.setenv(PERCENT, '100')
    assert not close_notify_enabled('owner')


def test_existing_percentage_parser_is_used(monkeypatch):
    select(monkeypatch, 'zero')
    assert not close_notify_enabled('owner')
    monkeypatch.setenv(PERCENT, '100')
    assert close_notify_enabled('owner')
    assert not close_notify_enabled(None)
