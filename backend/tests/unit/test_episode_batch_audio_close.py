"""Audio custody must establish episode membership before queued transcription."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen import batch_close as close
from routers.listen.conversations import LiveConversationController
from utils.episodes import batch_close as attachment, service


def capture(**changes):
    return {
        'id': 'capture',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True},
        'server_batch_audio_closed': True,
        'server_batch_audio_start': 1000,
        'server_batch_audio_end': 1120,
        'has_content': True,
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'enhanced',
        'source': 'desktop',
        'status': 'completed',
        'finalization_status': 'queued',
        'transcript_segments': [],
        'structured': {'title': ''},
        'episode_id': None,
        # Processing/arrival clocks are deliberately unrelated to the audio.
        'started_at': datetime(2026, 11, 3, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 11, 3, 1, tzinfo=timezone.utc),
        **changes,
    }


@pytest.fixture(autouse=True)
def admitted(monkeypatch):
    monkeypatch.setattr(attachment, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(attachment, 'recorded_episodes_enabled', lambda: True)


def test_audio_bounds_reuse_canonical_attachment_without_paid_work_or_row_mutation(monkeypatch):
    row = capture()
    original = deepcopy(row)
    db = object()
    paid = Mock(side_effect=AssertionError('metadata attachment must not spend'))
    c = service.Collaborators(firestore_client=db, invoke=paid, ask=paid)
    writes = []
    memberships = set()

    def recorded(uid, cid, source, started, finished, **kwargs):
        writes.append((uid, cid, source, started, finished, kwargs))
        memberships.add((uid, cid))
        return {'id': 'recorded-episode', '_recorded_windows': []}

    monkeypatch.setattr(service.episode_timeline, 'attach_recorded', recorded)
    monkeypatch.setattr(service.episodes_db, 'get_current_episode', paid)
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', paid)
    for _ in range(2):
        assert attachment.attach_closed_batch_capture('owner', 'capture', row, collaborators=c) == 'attached'
    assert memberships == {('owner', 'capture')}
    for uid, cid, source, started, finished, kwargs in writes:
        assert (uid, cid, source) == ('owner', 'capture', 'desktop')
        assert (started.timestamp(), finished.timestamp()) == (1000, 1120)
        assert kwargs['firestore_client'] is db
        assert kwargs['choose'] is service.choose_recorded_episode
        assert kwargs['new_episode'].get('output_language') is None
    assert len(writes) == 2, 'replays use the same fenced membership primitive'
    assert row == original, 'no title, transcript, status or processing-clock writes'
    paid.assert_not_called()


@pytest.mark.parametrize(
    'changes',
    [
        {'server_batch_audio_closed': False},
        {'has_content': False},
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'data_protection_level': 'private'},
        {'deleted': True},
        {'discarded': True},
        {'is_locked': True},
        {'deferred': True},
        {'sync_merged_into': 'survivor'},
        {'dream_duplicate_of': 'primary'},
        {'record_lane_owner': 'live'},
        {'external_data': {}},
        {'server_batch_audio_start': None},
        {'server_batch_audio_start': float('nan')},
        {'server_batch_audio_start': True},
        {'server_batch_audio_end': 1000},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}},
    ],
)
def test_nonadmitted_or_unretained_audio_never_attaches(monkeypatch, changes):
    attach = Mock(side_effect=AssertionError('not eligible for attachment'))
    monkeypatch.setattr(service, 'attach_recorded', attach)
    assert attachment.attach_closed_batch_capture('owner', 'capture', capture(**changes)) == 'skipped'
    attach.assert_not_called()


@pytest.mark.parametrize('switch', ['episodes_enabled_for', 'recorded_episodes_enabled'])
def test_existing_kill_switches_disable_close_attachment(monkeypatch, switch):
    monkeypatch.setattr(attachment, switch, lambda *args: False)
    attach = Mock()
    monkeypatch.setattr(service, 'attach_recorded', attach)
    assert attachment.attach_closed_batch_capture('owner', 'capture', capture()) == 'disabled'
    attach.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('archive_present', [False, True])
async def test_real_controller_attaches_before_finalization_in_same_call(monkeypatch, archive_present):
    row = capture(server_batch_audio_closed=not archive_present)
    events = []

    def read(*args, **kwargs):
        events.append('read')
        return deepcopy(row)

    def seal(*args):
        events.append('seal')
        row['server_batch_audio_closed'] = True
        return True

    def attach(uid, cid, latest):
        assert latest['server_batch_audio_closed'] is True
        assert latest['transcript_segments'] == []
        events.append('attach')
        row['episode_id'] = 'recorded-episode'

    async def archive_close():
        events.append('archive')

    async def persisted(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        state=SimpleNamespace(current_conversation_id='capture', active=False),
        receiver=SimpleNamespace(raw_archive=SimpleNamespace(close=archive_close) if archive_present else None),
        persistence=SimpleNamespace(call=persisted),
    )
    monkeypatch.setattr(close.conversations, 'get_conversation', read)
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close, 'attach_closed_batch_capture', attach)
    controller = LiveConversationController(host)

    async def finalize(cid):
        assert cid == 'capture' and row['episode_id'] == 'recorded-episode'
        events.append('finalize')
        return True

    controller.schedule_finalization = AsyncMock(side_effect=finalize)
    assert await controller.process_conversation('capture') is True
    expected = ['read', 'archive', 'seal', 'read'] if archive_present else ['read']
    assert events == [*expected, 'attach', 'finalize']
    assert row['status'] == 'completed' and row['finalization_status'] == 'queued'


@pytest.mark.asyncio
async def test_attachment_failure_is_observed_and_cannot_block_batch_finalization(monkeypatch):
    row = capture()
    fallback = Mock()
    monkeypatch.setattr(attachment, 'record_fallback', fallback)
    monkeypatch.setattr(service, 'attach_recorded', Mock(side_effect=RuntimeError('contention')))
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))

    async def persisted(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        state=SimpleNamespace(current_conversation_id='capture', active=False),
        receiver=None,
        persistence=SimpleNamespace(call=persisted),
    )
    controller = LiveConversationController(host)
    controller.schedule_finalization = AsyncMock(return_value=True)
    assert await controller.process_conversation('capture') is True
    controller.schedule_finalization.assert_awaited_once_with('capture')
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    assert row['episode_id'] is None and row['transcript_segments'] == []


@pytest.mark.asyncio
async def test_unclosed_active_audio_does_not_gain_premature_membership(monkeypatch):
    row = capture(server_batch_audio_closed=False)
    attach = Mock(side_effect=AssertionError('archive barrier has not committed'))
    monkeypatch.setattr(close, 'attach_closed_batch_capture', attach)
    host = SimpleNamespace(state=SimpleNamespace(current_conversation_id='capture'), receiver=None)
    assert await close.close_batch_archive(host, 'capture', row) is row
    attach.assert_not_called()
