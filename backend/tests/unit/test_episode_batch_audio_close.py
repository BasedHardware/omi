"""Audio custody must establish episode membership before queued transcription."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen import batch_close as close
from routers.listen.conversations import LiveConversationController
from utils.episodes import batch_close as attachment, service, home_read
from database import episode_timeline, episodes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


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
    monkeypatch.delenv('EPISODE_BATCH_CLOSE_ATTACH_ENABLED', raising=False)
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
        assert kwargs['pending_at'].tzinfo is not None
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


@pytest.mark.asyncio
async def test_failed_archive_seal_returns_before_membership_or_finalization(monkeypatch):
    row = capture(server_batch_audio_closed=False)
    archive = SimpleNamespace(close=AsyncMock())
    seal = Mock(return_value=False)
    attach = Mock(side_effect=AssertionError('uncommitted archive cannot attach'))
    read = Mock(side_effect=AssertionError('failed seal cannot reread'))
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close, 'attach_closed_batch_capture', attach)
    monkeypatch.setattr(close.conversations, 'get_conversation', read)

    async def persisted(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        state=SimpleNamespace(current_conversation_id='capture', active=False),
        receiver=SimpleNamespace(raw_archive=archive),
        persistence=SimpleNamespace(call=persisted),
    )
    assert await close.close_batch_archive(host, 'capture', row) is None
    archive.close.assert_awaited_once()
    seal.assert_called_once_with('owner', 'capture')
    attach.assert_not_called()
    read.assert_not_called()


@pytest.mark.parametrize(
    'value, expected',
    [('false', 'disabled'), ('off', 'disabled'), ('0', 'disabled'), ('no', 'disabled'), ('true', 'attached')],
)
def test_scoped_kill_switch(monkeypatch, value, expected):
    monkeypatch.setenv('EPISODE_BATCH_CLOSE_ATTACH_ENABLED', value)
    attach = Mock()
    monkeypatch.setattr(service, 'attach_recorded', attach)
    assert attachment.attach_closed_batch_capture('owner', 'capture', capture()) == expected
    assert attach.call_count == (1 if expected == 'attached' else 0)


@pytest.fixture
def timeline_store(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(episodes, 'seal', lambda uid, row: row)
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda *a, **kw: [dict(v, id=k[-1]) for k, v in store.rows.items() if k[2] == 'episodes'],
    )
    return store


@pytest.mark.parametrize('optimizations', ['true', 'false'])
@pytest.mark.parametrize('fraction', [0, 0.1234567])
def test_deadline_commits_with_membership_and_close_replay_is_a_true_noop(
    timeline_store, monkeypatch, optimizations, fraction
):
    monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', optimizations)
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = capture(
        finished_at=None, server_batch_audio_start=1000 + fraction, server_batch_audio_end=1120 + fraction
    )
    entered = datetime.now(timezone.utc)
    c = service.Collaborators(firestore_client=store, now=lambda: entered)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    assert member['episode_transcription_pending_at'] == entered
    assert member['episode_transcription_deadline_at'] == entered + timedelta(hours=2)
    assert member['episode_id']
    before = deepcopy(store.rows)
    c.now = lambda: entered + timedelta(hours=1)
    assert attachment.attach_closed_batch_capture('owner', 'capture', member, collaborators=c) == 'attached'
    assert store.rows == before, 'replay must not bump episode state_version, timeline fence, links or deadline'
    episode = store.rows[('users', 'owner', 'episodes', member['episode_id'])]
    wire = home_read.project_episode('owner', episode, members={'capture': member})
    assert wire['members'][0]['title'] == 'Transcribing…'
    assert wire['members'][0]['status'] == 'processing'
    assert wire['members'][0]['finished_at'] == datetime.fromtimestamp(1120 + fraction, timezone.utc)


@pytest.mark.parametrize('outcome', ['dead_letter', 'failed', 'upload_failed', 'deadline', 'projected'])
def test_home_pending_member_has_bounded_exit_and_can_recover(timeline_store, monkeypatch, outcome):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    now = datetime.now(timezone.utc)
    entered = now - timedelta(hours=3) if outcome in {'deadline', 'projected'} else now
    store.rows[path] = capture(finished_at=None)
    c = service.Collaborators(firestore_client=store, now=lambda: entered)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    if outcome == 'dead_letter':
        member['finalization_status'] = 'dead_letter'
    elif outcome == 'failed':
        member['status'] = 'failed'
    elif outcome == 'upload_failed':
        member['record_upload_failed'] = True
    elif outcome == 'projected':
        member.update(record_projection_revision=1, structured={'title': 'Recovered transcript'}, status='completed')
    overdue = Mock()
    monkeypatch.setattr(home_read.episode_metrics, 'record_batch_pending_overdue', overdue)
    episode = store.rows[('users', 'owner', 'episodes', member['episode_id'])]
    wire = home_read.project_episode('owner', episode, members={'capture': member})['members'][0]
    if outcome == 'projected':
        assert wire['title'] == 'Recovered transcript' and wire['status'] == 'completed'
    else:
        assert wire['title'] == "Couldn't transcribe" and wire['status'] == 'failed'
        assert wire['finished_at'].timestamp() == 1120
    assert overdue.call_count == (1 if outcome == 'deadline' else 0)


def test_kill_switch_keeps_attach_after_transcription_available(timeline_store, monkeypatch):
    store = timeline_store
    row = capture(record_projection_revision=1, structured={'title': 'Transcribed'})
    store.rows[('users', 'owner', 'conversations', 'capture')] = row
    monkeypatch.setenv('EPISODE_BATCH_CLOSE_ATTACH_ENABLED', 'off')
    c = service.Collaborators(firestore_client=store)
    assert attachment.attach_closed_batch_capture('owner', 'capture', row, collaborators=c) == 'disabled'
    result = service.attach_recorded(
        'owner',
        'capture',
        row,
        datetime.fromtimestamp(1000, timezone.utc),
        datetime.fromtimestamp(1120, timezone.utc),
        c,
    )
    assert result['conversation_ids'] == ['capture']
    assert not store.rows[('users', 'owner', 'conversations', 'capture')].get('episode_transcription_deadline_at')


@pytest.mark.parametrize('seconds, status', [(-0.001, 'processing'), (0, 'failed'), (0.001, 'failed')])
def test_deadline_is_an_exact_automatic_exit(monkeypatch, seconds, status):
    deadline = datetime(2026, 11, 4, tzinfo=timezone.utc)
    monkeypatch.setattr(
        home_read,
        'datetime',
        SimpleNamespace(
            now=lambda tz: deadline + timedelta(seconds=seconds),
            fromtimestamp=datetime.fromtimestamp,
        ),
    )
    episode = {
        'id': 'e',
        'status': 'closed',
        'started_at': deadline,
        'last_activity_at': deadline,
        'conversation_ids': ['c'],
    }
    member = {'episode_transcription_deadline_at': deadline, 'status': 'completed'}
    wire = home_read.project_episode('owner', episode, members={'c': member})['members'][0]
    assert wire['status'] == status
    assert wire['title']


def test_changed_audio_bounds_still_update_membership_without_renewing_deadline(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = capture()
    c = service.Collaborators(firestore_client=store)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    first_deadline = store.rows[path]['episode_transcription_deadline_at']
    ep_path = ('users', 'owner', 'episodes', store.rows[path]['episode_id'])
    version = store.rows[ep_path]['state_version']
    store.rows[path]['server_batch_audio_end'] = 1200
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    assert store.rows[ep_path]['state_version'] > version
    assert store.rows[ep_path]['last_activity_at'].timestamp() == 1200
    assert store.rows[path]['episode_transcription_deadline_at'] == first_deadline


@pytest.mark.parametrize('reason', ['user', 'gap'])
def test_existing_membership_gains_deadline_atomically_without_reset(timeline_store, reason):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    row = capture(record_projection_revision=1, structured={'title': 'Existing'})
    store.rows[path] = row
    c = service.Collaborators(firestore_client=store)
    result = service.attach_recorded(
        'owner',
        'capture',
        row,
        datetime.fromtimestamp(1000, timezone.utc),
        datetime.fromtimestamp(1120, timezone.utc),
        c,
    )
    store.rows[('users', 'owner', 'episodes', result['id'])]['close_reason'] = reason
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    assert store.rows[path]['episode_transcription_deadline_at']
