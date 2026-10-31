"""Occasion retention precedes rules and paid rejection; only actual merges absorb."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import occasion_relevance
from utils.conversations import relevance_io
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import Neighbor, decide_relevance
from tests.unit.test_late_audio_recorded_time import T0, NOW, timeline_store, _attach  # noqa: F401
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture(autouse=True)
def admitted_episode_client(monkeypatch):
    from utils.episodes import client_gate

    monkeypatch.setattr(client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'true')


def decide(*, member=None, neighbor=None, text='Mm-hmm.', model=None):
    return decide_relevance(
        trigger=ProcessingTrigger.SYNC_UPDATE,
        texts=[text],
        speech_seconds=5,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=model,
        calendar_retains=lambda: False,
        occasion_retains=lambda: member,
        neighbor=lambda: neighbor,
    )


@pytest.mark.parametrize('context', ['occasion_member', 'occasion_neighbor', 'occasion_context'])
@pytest.mark.parametrize('text', ['Mm-hmm.', 'Coming over there in a second.'])
def test_related_content_never_has_an_independent_rule_or_model_discard(context, text):
    model = Mock(return_value=True)
    decision = decide(member=context, text=text, model=model)
    assert not decision.discard and decision.reason == context
    model.assert_not_called()


def test_neighbor_content_is_kept_until_absorption_and_isolated_clip_can_discard():
    model = Mock(return_value=True)
    decision = decide(neighbor=Neighbor('kept', 12, 'before'), text='Coming over there in a second.', model=model)
    assert not decision.discard and decision.reason == 'occasion_neighbor'
    assert decision.neighbor_id == 'kept'
    assert decide(text='Mm-hmm.').discard
    assert decide(text='Coming over there in a second.', model=model).discard
    model.assert_called_once()


def test_kill_switch_restores_independent_rules_and_intake(monkeypatch):
    monkeypatch.delenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', raising=False)
    assert occasion_relevance.enabled()
    assert not intake(StrictFirestore(), chunk('a', T0.timestamp(), 'Mm-hmm.'))[0]['discarded']
    monkeypatch.setenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'false')
    assert not occasion_relevance.enabled()
    assert decide(member='occasion_member').discard
    assert intake(StrictFirestore(), chunk('a', T0.timestamp(), 'Mm-hmm.'))[0]['discarded']


@pytest.mark.parametrize(
    'membership,covering,neighbor,reason',
    [
        ({'id': 'e', 'conversation_ids': ['other']}, None, None, 'occasion_member'),
        (None, {'id': 'closed', 'conversation_ids': ['other']}, None, 'occasion_member'),
        ({'id': 'self', 'conversation_ids': ['c']}, None, None, None),
        (None, None, Neighbor('kept', 10, 'before'), 'occasion_neighbor'),
        (None, None, None, None),
    ],
)
def test_production_context_reads_recorded_ownership_and_neighbors(monkeypatch, membership, covering, neighbor, reason):
    from database import episodes, episode_timeline
    from utils.episodes import timeline

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', lambda *a: membership)
    monkeypatch.setattr(timeline, 'episode_owning_recorded_time', lambda *a, **kw: covering)
    attach = Mock()
    monkeypatch.setattr(episode_timeline, 'attach_existing_recorded', attach)
    monkeypatch.setattr(
        relevance_io.conversations_db,
        'get_conversation_raw_snapshot',
        lambda *a, **kw: {'started_at': T0, 'finished_at': T0 + timedelta(seconds=20)},
    )
    monkeypatch.setattr(relevance_io, 'adjacent_conversation', lambda *a, **kw: neighbor)
    conversation = SimpleNamespace(id='c', started_at=T0, finished_at=T0 + timedelta(seconds=18))
    assert relevance_io.occasion_retention('u', conversation) == reason
    assert attach.call_count == (1 if reason == 'occasion_member' else 0)


@pytest.mark.parametrize('order', ['attach_first', 'relevance_first'])
@pytest.mark.parametrize('context', ['isolated', 'adjacent', 'discarded_neighbor', 'outside_gap'])
def test_attachment_order_cannot_supply_its_own_retention(monkeypatch, timeline_store, order, context):
    from database import episodes, episode_timeline
    from utils.episodes import service

    store = timeline_store
    monkeypatch.setattr(episodes, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(episode_timeline, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(relevance_io.conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(relevance_io.conversations_db, 'get_conversations_finished_after', lambda *a, **kw: [])
    start, end = T0, T0 + timedelta(seconds=5)
    if context != 'isolated':
        before = 31 * 60 if context == 'outside_gap' else 60
        other = dict(
            id='real',
            started_at=T0 - timedelta(seconds=before),
            finished_at=T0 - timedelta(seconds=before - 30),
            discarded=context == 'discarded_neighbor',
            status='completed',
        )
        store.rows[('users', 'u', 'conversations', 'real')] = other
        if context != 'discarded_neighbor':
            _attach(store, 'real', other['started_at'], other['finished_at'])
    clip = dict(id='clip', started_at=start, finished_at=end, discarded=False, status='completed')
    store.rows[('users', 'u', 'conversations', 'clip')] = clip
    if order == 'attach_first':
        _attach(store, 'clip', start, end)
    reason = relevance_io.occasion_retention('u', SimpleNamespace(**clip))
    assert reason == ('occasion_member' if context == 'adjacent' else None)
    result = decide(
        member=reason,
        text='Coming over there in a second.' if context == 'adjacent' else 'Mm-hmm.',
        model=Mock(return_value=True),
    )
    assert result.discard == (context != 'adjacent')
    clip['discarded'] = result.discard
    if order == 'relevance_first' and not result.discard:
        _attach(store, 'clip', start, end)
    c = service.Collaborators(firestore_client=store, now=lambda: NOW)
    episode = service.episode_for_conversation('u', 'clip', collaborators=c)
    assert (episode is not None) == (context == 'adjacent')
    stored = episodes.get_episode_for_conversation('u', 'clip', firestore_client=store)
    if stored is None:
        assert result.discard
        return
    assert (service.episode_by_id('u', stored['id'], collaborators=c) is not None) == (context == 'adjacent')
    # The poll cache must re-check member visibility after relevance commits.
    store.rows[('users', 'u', 'episode_links', 'last_closed')] = {'episode_id': stored['id']}
    service.reset_for_tests()
    assert (service.last_closed_episode('u', collaborators=c) is not None) == (context == 'adjacent')
    if context == 'adjacent':
        clip['discarded'] = True
        store.rows[('users', 'u', 'conversations', 'real')]['discarded'] = True
        assert service.last_closed_episode('u', collaborators=c) is None
    monkeypatch.setenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'false')
    assert service.episode_by_id('u', stored['id'], collaborators=c) is None


def test_missing_ownership_read_is_not_proof_of_isolation(monkeypatch):
    from database import episodes

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', Mock(side_effect=RuntimeError('offline')))
    assert (
        relevance_io.occasion_retention('u', SimpleNamespace(id='c', started_at=T0, finished_at=T0))
        == 'occasion_lookup_unavailable'
    )


def test_failed_membership_claim_cannot_report_occasion_member(monkeypatch):
    from database import episode_timeline, episodes
    from utils.episodes import timeline

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', lambda *a: None)
    monkeypatch.setattr(
        timeline, 'episode_owning_recorded_time', lambda *a, **kw: {'id': 'owner', 'conversation_ids': ['other']}
    )
    monkeypatch.setattr(
        relevance_io.conversations_db,
        'get_conversation_raw_snapshot',
        lambda *a, **kw: {'started_at': T0, 'finished_at': T0 + timedelta(seconds=20)},
    )
    monkeypatch.setattr(
        episode_timeline,
        'attach_existing_recorded',
        Mock(side_effect=episodes.EpisodeConflict('recorded_owner_changed')),
    )
    assert (
        relevance_io.occasion_retention('u', SimpleNamespace(id='clip', started_at=T0, finished_at=T0))
        == 'occasion_lookup_unavailable'
    )


@pytest.fixture(scope='module')
def discard_prompt_module():
    # Import/setup cost is separate from the fast policy behavior under test.
    from utils.llm import conversation_processing

    return conversation_processing


def test_neighbor_prompt_cannot_reject_unabsorbed_content(monkeypatch, discard_prompt_module):
    conversation_processing = discard_prompt_module
    model = Mock(side_effect=AssertionError('continuation must never buy a discard call'))
    monkeypatch.setattr(conversation_processing, 'get_llm', model)
    assert not conversation_processing.should_discard_conversation('Coming over there.', neighbor_gap_seconds=10)
    model.assert_not_called()


def test_full_neighbor_page_cannot_prove_isolation(monkeypatch):
    rows = [
        dict(id=f'future-{i}', started_at=T0 + timedelta(hours=3), finished_at=T0 + timedelta(hours=4))
        for i in range(10)
    ]
    monkeypatch.setattr(relevance_io.conversations_db, 'get_conversations_finished_after', lambda *a, **kw: rows)
    with pytest.raises(RuntimeError, match='neighbor_window_incomplete'):
        relevance_io.adjacent_conversation(
            'u', SimpleNamespace(id='c', started_at=T0, finished_at=T0), 'c', require_complete=True
        )


def test_hidden_neighbor_candidates_count_toward_isolation_proof(monkeypatch):
    seen = {}

    def read(*a, **kw):
        seen.update(kw)
        return [dict(id=f'donor-{i}', deleted=True) for i in range(10)]

    monkeypatch.setattr(relevance_io.conversations_db, 'get_conversations_finished_after', read)
    with pytest.raises(RuntimeError, match='neighbor_window_incomplete'):
        relevance_io.adjacent_conversation(
            'u', SimpleNamespace(id='c', started_at=T0, finished_at=T0), 'c', require_complete=True
        )
    assert seen['include_hidden'] is True


@pytest.mark.parametrize('skew', [-600, 600])
@pytest.mark.parametrize('arrival_delay', [0, 6 * 60 * 60])
def test_neighbor_discovery_retains_recorded_adjacency_despite_skew_and_delayed_ingest(
    monkeypatch, skew, arrival_delay
):
    from database import episodes
    from utils.episodes import timeline

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', lambda *a: None)
    monkeypatch.setattr(timeline, 'episode_owning_recorded_time', lambda *a, **kw: None)
    neighbor = dict(
        id='kept',
        status='completed',
        discarded=False,
        started_at=T0 - timedelta(seconds=90),
        finished_at=T0 + timedelta(seconds=skew - 10),
        recorded_start=T0 - timedelta(seconds=90),
        recorded_end=T0 - timedelta(seconds=10),
        clock='live_capture',
        arrival_at=T0,
    )
    far = dict(neighbor, id='far', recorded_start=T0 - timedelta(hours=3), recorded_end=T0 - timedelta(hours=2))

    def query(uid, *, status, finished_after, limit, **kwargs):
        return [row for row in [far, neighbor] if row['status'] == status and row['finished_at'] >= finished_after][
            :limit
        ]

    monkeypatch.setattr(relevance_io.conversations_db, 'get_conversations_finished_after', query)
    conversation = SimpleNamespace(
        id='new',
        started_at=T0,
        finished_at=T0 + timedelta(seconds=20 + arrival_delay),
        recorded_start=T0,
        recorded_end=T0 + timedelta(seconds=20),
        clock='device',
        arrival_at=T0 + timedelta(seconds=20 + arrival_delay),
    )
    assert relevance_io.adjacent_conversation('u', conversation, 'new') == Neighbor('kept', 10, 'before')
    assert relevance_io.occasion_retention('u', conversation) == 'occasion_neighbor'


@pytest.mark.parametrize('gate', ['kill_switch', 'cohort', 'client', 'recorded_time', 'admitted'])
def test_relevance_context_does_not_bypass_episode_write_admission(timeline_store, monkeypatch, gate):
    from database import episodes, episode_timeline
    from utils.episodes import client_gate

    store = timeline_store
    _attach(store, 'other', T0, T0 + timedelta(minutes=20))
    store.rows[('users', 'u', 'conversations', 'other')] = dict(
        id='other',
        source='omi',
        started_at=T0,
        recorded_start=T0,
        recorded_end=T0 + timedelta(minutes=20),
        status='completed',
    )
    clip = dict(
        id='clip',
        source='desktop',
        started_at=T0 + timedelta(minutes=10),
        recorded_start=T0 + timedelta(minutes=10),
        recorded_end=T0 + timedelta(minutes=12),
    )
    store.rows[('users', 'u', 'conversations', 'clip')] = clip
    monkeypatch.setattr(episodes, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(episode_timeline, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(relevance_io.conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setenv('EPISODES_UID_ALLOWLIST', '')
    if gate == 'kill_switch':
        monkeypatch.setenv('EPISODES_ENABLED', 'off')
    elif gate == 'cohort':
        monkeypatch.setenv('EPISODES_PERCENT', '0')
    elif gate == 'client':
        monkeypatch.setattr(client_gate, 'client_seen', lambda uid: False)
    elif gate == 'recorded_time':
        monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'false')
    before = dict(store.rows)
    assert relevance_io.occasion_retention('u', SimpleNamespace(**clip)) == (
        'occasion_member' if gate == 'admitted' else 'occasion_context'
    )
    if gate == 'admitted':
        assert store.rows[('users', 'u', 'episode_links', 'clip')]['episode_id'] == clip['episode_id']
    else:
        assert store.rows == before
        assert ('users', 'u', 'episode_links', 'clip') not in store.rows
        assert 'episode_id' not in clip
