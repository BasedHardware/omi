"""Review regressions: stale scheduling snapshots, landing order, and full rollback."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
import os

import pytest

from config import episode_attach as flags, episodes as episode_config
from database import episode_attach_memo, episode_timeline, episodes
from tests.unit.test_episode_attach_cost import seed
from tests.unit.test_episode_live_integrity import lane, row, T0, assert_timeline  # noqa: F401
from utils.conversations.episode_attach_key import should_schedule
from utils.episodes import finalize, service


@pytest.mark.parametrize('entry', ['intake', 'finalize'])
@pytest.mark.parametrize('mutation', ['discarded', 'deleted', 'missing'])
def test_hidden_after_snapshot_cannot_suppress_hook(lane, monkeypatch, entry, mutation):
    store, c, _ = lane
    service._attach_synced('u', 'same', seed(store), c)
    visible = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    episode_attach_memo.complete('u', 'same', visible, None, finalized=True, firestore_client=store)
    # Neither the link nor the snapshot changes. Only the current conversation
    # changes after the caller's read, before the scheduling memo lookup.
    if mutation == 'missing':
        del store.rows[('users', 'u', 'conversations', 'same')]
    else:
        store.rows[('users', 'u', 'conversations', 'same')][mutation] = True
    monkeypatch.setattr(episode_attach_memo, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(finalize, 'episodes_enabled_for', lambda _: True)
    monkeypatch.setattr(finalize, 'lifecycle_executor', lambda *a, **kw: object())
    submit = Mock()
    monkeypatch.setattr(finalize, 'submit_with_context', submit)
    if entry == 'intake':
        finalize.schedule_synced_intake_attach('u', 'same', visible)
    else:
        finalize.schedule_after_finalization('u', 'same', finalize.ProcessingTrigger.SYNC_UPDATE, row=visible)
    assert submit.call_count == 1
    if entry == 'finalize' and mutation != 'missing':
        # Run the submitted hook with its normal fresh read: bookkeeping must
        # actually retire the member, beyond just submitting executor work.
        monkeypatch.setattr(
            service.conversations_db,
            'get_conversation',
            lambda *_: deepcopy(store.rows[('users', 'u', 'conversations', 'same')]),
        )
        original = service.on_conversation_finalized
        monkeypatch.setattr(service, 'on_conversation_finalized', lambda *a, **kw: original(*a, **kw, collaborators=c))
        args = submit.call_args.args
        args[1](*args[2:])
        owner = episodes.get_episode('u', visible['episode_id'], firestore_client=store)
        assert 'same' in owner['discarded_conversation_ids']


@pytest.mark.parametrize('order', ['attach_first', 'composer_first'])
@pytest.mark.parametrize('field', ['title', 'overview', 'action_items'])
def test_summary_schedule_follows_composer_capability_and_runtime_rollback(monkeypatch, order, field):
    before = row('c', episode_id='e', structured={'title': 'A', 'overview': 'B', 'action_items': []})
    after = deepcopy(before)
    after['structured'][field] = [{'description': 'Ship it'}] if field == 'action_items' else 'Changed'

    # Use #24579's public config capability rather than importing its composer.
    def settle_enabled():
        return os.getenv('EPISODE_COMPOSE_SETTLE_ENABLED', 'true').lower() not in {'off', 'false', '0', 'no'}

    monkeypatch.setenv('EPISODE_COMPOSE_SETTLE_ENABLED', 'true')
    if order == 'attach_first':
        monkeypatch.delattr(episode_config, 'episode_compose_settle_enabled', raising=False)
        assert should_schedule(before, after)  # env alone does not prove new composer code
    monkeypatch.setattr(episode_config, 'episode_compose_settle_enabled', settle_enabled, raising=False)
    assert not should_schedule(before, after)
    for off in ['off', 'false', '0', 'no']:
        monkeypatch.setenv('EPISODE_COMPOSE_SETTLE_ENABLED', off)
        assert should_schedule(before, after)
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLE_ENABLED', 'true')
    assert not should_schedule(before, after)
    after['transcript_segments'][0]['text'] = 'Real new speech'
    assert should_schedule(before, after)


def test_umbrella_overrides_all_individual_switches(monkeypatch):
    names = [
        'content_gate',
        'noop_schedule',
        'owner_reuse',
        'membership_dedupe',
        'row_visibility',
        'walk_context',
        'duplicates_dedupe',
    ]
    for name in names:
        monkeypatch.setenv('EPISODE_ATTACH_' + name.upper() + '_ENABLED', 'true')
    for value in ['off', 'false', '0', 'no']:
        monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', value)
        assert all(not getattr(flags, name + '_enabled')() for name in names)


def test_umbrella_off_repartitions_and_rewrites_even_with_completed_proof(lane, monkeypatch):
    store, c, _ = lane
    service._attach_synced('u', 'same', seed(store), c)
    member = deepcopy(store.rows[('users', 'u', 'conversations', 'same')])
    owner = episodes.get_episode_for_conversation('u', 'same', firestore_client=store)
    assert owner.get('recorded_partition')
    query = Mock(wraps=episode_timeline.recorded_candidates)
    monkeypatch.setattr(episode_timeline, 'recorded_candidates', query)
    monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', 'off')
    assert service._attach_synced('u', 'same', member, c) == 'recorded'
    assert query.called
    updated = episodes.get_episode_for_conversation('u', 'same', firestore_client=store)
    assert updated['state_version'] > owner['state_version']
    assert updated['conversation_ids'] == owner['conversation_ids']
    assert not episode_attach_memo.matches('u', 'same', member, firestore_client=store)
    assert_timeline(store)


@pytest.mark.parametrize('enabled', [True, False])
def test_umbrella_restores_candidate_queries_at_fixed_boundary(lane, monkeypatch, enabled):
    store, c, _ = lane
    service.attach_conversation('u', 'live', 'omi', started_at=T0, collaborators=c)
    member = seed(store)
    query = Mock(wraps=episode_timeline.recorded_candidates)
    monkeypatch.setattr(episode_timeline, 'recorded_candidates', query)
    monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', str(enabled))
    service._attach_recorded('u', 'same', member, T0, T0 + timedelta(seconds=30), c)
    # Canonical lookup, fixed-boundary lookup and window validation used to
    # issue separate queries. The umbrella restores all three reads.
    assert query.call_count == (1 if enabled else 3)
    assert_timeline(store)
