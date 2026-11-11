"""Audio custody must establish episode membership before queued transcription."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen import batch_close as close
from routers.listen import conversations as listen_conversations
from routers.listen import preview_custody
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


def admitted(**changes):
    """A capture at admission: owned, consented, no committed audio bounds yet."""
    return capture(
        server_batch_audio_closed=False,
        server_batch_audio_start=1000,
        server_batch_audio_end=None,
        has_content=False,
        episode_id=None,
        **changes,
    )


def test_admission_attaches_a_provisional_member_before_audio_close(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = admitted()
    entered = datetime.now(timezone.utc)
    c = service.Collaborators(firestore_client=store, now=lambda: entered)
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    assert member['episode_id']
    assert member['episode_transcription_pending_at'] == entered
    assert member['episode_transcription_deadline_at'] == entered + timedelta(hours=2)
    episode = store.rows[('users', 'owner', 'episodes', member['episode_id'])]
    assert episode['conversation_ids'] == ['capture']
    assert episode['last_activity_at'] == datetime.fromtimestamp(1001, timezone.utc)
    wire = home_read.project_episode('owner', episode, members={'capture': member})
    assert wire['members'][0]['title'] == 'Transcribing…'
    assert wire['members'][0]['status'] == 'processing'


def test_audio_close_finalizes_the_admitted_end_without_renewing_the_deadline(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = admitted()
    entered = datetime.now(timezone.utc)
    c = service.Collaborators(firestore_client=store, now=lambda: entered)
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    episode_id = store.rows[path]['episode_id']
    deadline = store.rows[path]['episode_transcription_deadline_at']
    store.rows[path].update(server_batch_audio_closed=True, server_batch_audio_end=1120, has_content=True)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    assert member['episode_id'] == episode_id, 'the close keeps the admission owner'
    assert member['episode_transcription_deadline_at'] == deadline, 'the close never renews the pending deadline'
    episode = store.rows[('users', 'owner', 'episodes', episode_id)]
    assert episode['last_activity_at'] == datetime.fromtimestamp(1120, timezone.utc)
    assert episode['conversation_ids'] == ['capture']


def test_late_admission_after_audio_close_cannot_undo_the_close_end(timeline_store):
    """The close attach commits first; the delayed admission task must refuse."""
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    stale_admission_row = admitted()
    store.rows[path] = admitted()
    c = service.Collaborators(firestore_client=store)
    store.rows[path].update(server_batch_audio_closed=True, server_batch_audio_end=1120, has_content=True)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    episode_id = member['episode_id']
    episode_path = ('users', 'owner', 'episodes', episode_id)
    closed_end = datetime.fromtimestamp(1120, timezone.utc)
    version = store.rows[episode_path]['state_version']
    assert store.rows[episode_path]['last_activity_at'] == closed_end
    before = deepcopy(store.rows)
    # The background admission task still holds its pre-close snapshot.
    assert (
        attachment.attach_admitted_batch_capture('owner', 'capture', stale_admission_row, collaborators=c) == 'closed'
    )
    assert store.rows == before, 'a late admission must not write after the close'
    member = store.rows[path]
    assert member['episode_id'] == episode_id, 'the member keeps its close-time episode'
    assert member['server_batch_audio_end'] == 1120
    assert store.rows[episode_path]['last_activity_at'] == closed_end, 'the finalized end survives'
    assert store.rows[episode_path]['state_version'] == version
    assert store.rows[episode_path]['conversation_ids'] == ['capture']


def test_boundary_move_moves_the_provisional_member_atomically_at_the_close_attach(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    entered = datetime(2026, 11, 3, tzinfo=timezone.utc)
    store.rows[path] = capture(
        episode_id='e1',
        episode_transcription_pending_at=entered,
        episode_transcription_deadline_at=entered + timedelta(hours=2),
        server_batch_audio_start=2000,
        server_batch_audio_end=2100,
    )
    store.rows[('users', 'owner', 'episode_links', 'capture')] = {'episode_id': 'e1', 'episode_ids': ['e1']}
    store.rows[('users', 'owner', 'episodes', 'e1')] = {
        'id': 'e1',
        'status': 'closed',
        'close_reason': 'gap',
        'started_at': datetime.fromtimestamp(1000, timezone.utc),
        'last_activity_at': datetime.fromtimestamp(1001, timezone.utc),
        'conversation_ids': ['capture', 'other'],
        'member_activity': {
            'capture': datetime.fromtimestamp(1001, timezone.utc),
            'other': datetime.fromtimestamp(1001, timezone.utc),
        },
        'recorded_members': {
            'capture': {
                'start': datetime.fromtimestamp(1000, timezone.utc),
                'end': datetime.fromtimestamp(1001, timezone.utc),
                'source': 'desktop',
            },
            'other': {
                'start': datetime.fromtimestamp(1000, timezone.utc),
                'end': datetime.fromtimestamp(1001, timezone.utc),
                'source': 'desktop',
            },
        },
        'state_version': 1,
    }
    store.rows[('users', 'owner', 'episodes', 'e2')] = {
        'id': 'e2',
        'status': 'live',
        'started_at': datetime.fromtimestamp(2000, timezone.utc),
        'last_activity_at': datetime.fromtimestamp(2100, timezone.utc),
        'conversation_ids': ['other2'],
        'member_activity': {'other2': datetime.fromtimestamp(2100, timezone.utc)},
        'recorded_members': {
            'other2': {
                'start': datetime.fromtimestamp(2000, timezone.utc),
                'end': datetime.fromtimestamp(2100, timezone.utc),
                'source': 'desktop',
            }
        },
        'state_version': 1,
    }
    c = service.Collaborators(firestore_client=store)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    assert 'capture' not in store.rows[('users', 'owner', 'episodes', 'e1')]['conversation_ids']
    assert store.rows[('users', 'owner', 'episodes', 'e1')]['conversation_ids'] == ['other']
    assert store.rows[path]['episode_id'] == 'e2'
    assert 'capture' in store.rows[('users', 'owner', 'episodes', 'e2')]['conversation_ids']


def test_detach_refuses_a_transcribed_member(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = capture(episode_id='e1', record_projection_revision=1, structured={'title': 'Transcribed'})
    store.rows[('users', 'owner', 'episode_links', 'capture')] = {'episode_id': 'e1', 'episode_ids': ['e1']}
    store.rows[('users', 'owner', 'episodes', 'e1')] = {
        'id': 'e1',
        'status': 'live',
        'started_at': datetime.fromtimestamp(1000, timezone.utc),
        'last_activity_at': datetime.fromtimestamp(1120, timezone.utc),
        'conversation_ids': ['capture', 'other'],
        'member_activity': {},
        'recorded_members': {},
        'state_version': 1,
    }
    assert episode_timeline.detach_recorded('owner', 'capture', episode_id='e1', firestore_client=store) is False
    assert store.rows[path]['episode_id'] == 'e1'


def test_admission_kill_switch_off_restores_the_audio_close_attach(timeline_store, monkeypatch):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = admitted()
    monkeypatch.setenv('EPISODE_BATCH_ADMISSION_ATTACH_ENABLED', 'off')
    c = service.Collaborators(firestore_client=store)
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'disabled'
    assert store.rows[path]['episode_id'] is None
    store.rows[path].update(server_batch_audio_closed=True, server_batch_audio_end=1120, has_content=True)
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    assert store.rows[path]['episode_id']


def test_admission_retry_does_not_attach_twice(timeline_store):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    store.rows[path] = admitted()
    entered = datetime.now(timezone.utc)
    c = service.Collaborators(firestore_client=store, now=lambda: entered)
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    episode_id = store.rows[path]['episode_id']
    version = store.rows[('users', 'owner', 'episodes', episode_id)]['state_version']
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    assert store.rows[path]['episode_id'] == episode_id
    assert store.rows[('users', 'owner', 'episodes', episode_id)]['state_version'] == version
    assert store.rows[('users', 'owner', 'episodes', episode_id)]['conversation_ids'] == ['capture']


@pytest.mark.asyncio
async def test_admission_boundaries_pass_a_clock_carrying_row(timeline_store, monkeypatch):
    """Both production call sites must hand the attach a row with a clock.

    The eligibility snapshot drops ``started_at``/``created_at``, so passing it
    alone makes the admission attach a silent no-op. Drive the real preview
    promotion and the real fresh-create path, not a hand-built row.
    """
    store = timeline_store
    monkeypatch.setattr(attachment.conversations, 'db', store)
    started = datetime(2026, 11, 3, tzinfo=timezone.utc)
    pending = []

    async def run_blocking(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def start_background_task(coro, *, name):
        pending.append(coro)

    # --- preview custody: the full claim row, not capture_snapshot(row) ---
    claimed = {
        'id': 'preview-capture',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True},
        'private_cloud_sync_enabled': True,
        'uses_custom_stt': False,
        'data_protection_level': 'enhanced',
        'language': 'en',
        'started_at': started,
        'created_at': started,
        'server_batch_audio_closed': False,
        'has_content': False,
        'episode_id': None,
    }
    store.rows[('users', 'owner', 'conversations', 'preview-capture')] = dict(claimed)
    receiver = SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(uid='owner', language='en'),
            state=SimpleNamespace(current_conversation_id='preview-capture'),
            local_preview_batch=True,
            use_custom_stt=False,
            server_batch_only=False,
            private_cloud_sync_enabled=True,
            server_batch_byok=False,
            is_multi_channel=False,
            pusher_enabled=True,
            batch_record_capture=None,
            language='en',
        ),
        cloud_live_suppressed=True,
        _cloud_live_deferred_by='local_preview',
        _preview_batch_claims=set(),
        raw_archive=SimpleNamespace(durable=True),
    )
    monkeypatch.setattr(preview_custody, 'preview_batch_custody_enabled', lambda: True)
    monkeypatch.setattr(preview_custody, 'claim_server_batch_lane', lambda *a, **kw: dict(claimed))
    monkeypatch.setattr(preview_custody, 'run_blocking', run_blocking)
    monkeypatch.setattr(preview_custody, 'start_background_task', start_background_task)
    assert await preview_custody.claim_preview_batch_custody(receiver) is True
    assert pending, 'the promotion must schedule the admission attach'
    await pending.pop()
    assert store.rows[('users', 'owner', 'conversations', 'preview-capture')]['episode_id']

    # --- fresh create: the payload clocks, not capture_snapshot(payload) ---
    async def call(function, *args, **kwargs):
        if function is listen_conversations.lifecycle_service.open_live_recording_session:
            return {'requires_rollover': False, 'conversation_id': 'listen-capture'}
        if function is listen_conversations.lifecycle_service.create_in_progress_conversation:
            payload = args[1]
            payload['record_lane_owner'] = 'batch_live_v1'
            payload['external_data'] = {**(payload.get('external_data') or {}), 'server_batch_only': True}
            payload['data_protection_level'] = 'enhanced'
            store.rows[('users', 'owner', 'conversations', 'listen-capture')] = dict(payload)
            return True
        return None

    controller = LiveConversationController.__new__(LiveConversationController)
    controller.clock = lambda: started
    controller.host = SimpleNamespace(
        request=SimpleNamespace(
            uid='owner',
            source='desktop',
            language='en',
            conversation_role=None,
            call_id=None,
            geolocation=None,
            onboarding_mode=False,
            screen_evidence_pass=False,
        ),
        state=SimpleNamespace(current_conversation_id=None),
        client_conversation_id=None,
        recording_session_id=None,
        recording_session_ids_by_conversation={},
        persistence=SimpleNamespace(call=call),
        client_device_context=SimpleNamespace(client_device_id='device', platform='macos'),
        language='en',
        private_cloud_sync_enabled=True,
        use_custom_stt=False,
        is_multi_channel=False,
        pusher_enabled=True,
        server_batch_only=False,
        batch_record_capture=None,
        conversation_creation_timeout=30,
        speakers=SimpleNamespace(refresh_for_conversation=AsyncMock()),
    )
    controller._persist_policy_and_arm_quiet_check = AsyncMock()
    controller._adopt_capture_timeline = Mock()
    controller._refresh_speakers = AsyncMock()
    controller.send_conversation_session = Mock()
    controller._active_calendar_meeting = AsyncMock(return_value=None)
    monkeypatch.setattr(listen_conversations, 'server_batch_request_eligible', lambda *a, **kw: True)
    monkeypatch.setattr(listen_conversations, 'server_batch_capture_language', lambda host: 'en')
    monkeypatch.setattr(listen_conversations, 'server_batch_capture_compatible', lambda *a, **kw: True)
    monkeypatch.setattr(listen_conversations, 'run_blocking', run_blocking)
    monkeypatch.setattr(listen_conversations, 'start_background_task', start_background_task)
    await controller.create_new_in_progress_conversation()
    assert pending, 'the fresh create must schedule the admission attach'
    await pending.pop()
    assert store.rows[('users', 'owner', 'conversations', 'listen-capture')]['episode_id']


def test_admission_deadline_survives_a_capture_longer_than_the_sla(timeline_store, monkeypatch):
    store = timeline_store
    path = ('users', 'owner', 'conversations', 'capture')
    started = datetime(2026, 11, 3, tzinfo=timezone.utc)
    store.rows[path] = capture(
        server_batch_audio_closed=False,
        server_batch_audio_start=None,
        server_batch_audio_end=None,
        has_content=False,
        episode_id=None,
        started_at=started,
        created_at=started,
    )
    c = service.Collaborators(firestore_client=store, now=lambda: started)
    assert attachment.attach_admitted_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    deadline = store.rows[path]['episode_transcription_deadline_at']
    assert deadline >= started + timedelta(seconds=7200 + 4 * 60 * 60)
    # The capture records for 8000s: past the 2h SLA, inside the 4h episode cap.
    closed_at = started + timedelta(seconds=8000)
    store.rows[path].update(
        server_batch_audio_closed=True,
        server_batch_audio_start=started.timestamp(),
        server_batch_audio_end=closed_at.timestamp(),
        has_content=True,
    )
    c.now = lambda: closed_at
    assert attachment.attach_closed_batch_capture('owner', 'capture', store.rows[path], collaborators=c) == 'attached'
    member = store.rows[path]
    assert member['episode_transcription_deadline_at'] == deadline, 'the close never renews the deadline'
    monkeypatch.setattr(
        home_read,
        'datetime',
        SimpleNamespace(now=lambda tz: closed_at, fromtimestamp=datetime.fromtimestamp),
    )
    episode = store.rows[('users', 'owner', 'episodes', member['episode_id'])]
    wire = home_read.project_episode('owner', episode, members={'capture': member})
    assert wire['members'][0]['title'] == 'Transcribing…'
    assert wire['members'][0]['status'] == 'processing'
