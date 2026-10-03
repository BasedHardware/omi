"""Regression evidence for preservation review: visible donor state and delivery fences."""

from copy import deepcopy

import pytest

from tests.unit.test_action_item_refresh import NOW, UID, conv_path, item, seed_donor, task_path, world
from utils.conversations import action_item_refresh as flow


@pytest.mark.parametrize(
    'state',
    [
        {'completed': True, 'completed_at': NOW},
        {'folder_id': 'user-folder', 'manual_assignment': 'person'},
        {'due_at': NOW, 'apple_reminder_id': 'linked-reminder'},
        {'external_task_id': 'separate-export', 'exported': True},
    ],
)
def test_live_duplicate_donor_retains_visible_user_state(world, state):
    seed_donor(world)
    row = world.store.rows[task_path('donor-duplicate')]
    row.update(state)
    before = deepcopy(row)
    flow.transfer_donor(UID, 'donor', 'survivor')
    transferred = world.store.rows[task_path('donor-duplicate')]
    assert not transferred.get('deleted'), 'a retained hidden row loses visible user state'
    for field, value in before.items():
        assert transferred[field] == ('survivor' if field == 'conversation_id' else value)
    world.write(['Send report', 'Call vendor'])
    world.drain()
    assert not world.external
    assert not [effect for effect in world.effects if effect[0] == 'reminder']


def test_transferred_pending_donor_never_reschedules_or_exports(world):
    seed_donor(world)
    row = world.store.rows[task_path('donor-task')]
    row.update(completed=False, exported=False, refresh_delivery='pending')
    flow.transfer_donor(UID, 'donor', 'survivor')
    world.write(['Send report', 'Call vendor'])
    world.drain()
    assert not world.external
    assert not [effect for effect in world.effects if effect[0] == 'reminder']
    assert world.store.rows[task_path('donor-task')]['refresh_delivery'] != 'pending'


@pytest.fixture
def real_sync(world, monkeypatch):
    # Keep task_sync's real already_exported/Apple logic; replace only DB/provider IO.
    from utils import task_sync

    calls = []

    async def blocking(executor, fn, *args):
        return fn(*args)

    async def create(**kwargs):
        calls.append(('cloud', kwargs['title']))
        return {'success': True, 'external_task_id': 'synthetic-external'}

    async def apple(**kwargs):
        calls.append(('apple', [row['id'] for row in kwargs['action_items']]))
        return True

    def request_sync(uid, ids):
        for task_id in ids:
            world.store.rows[task_path(task_id)]['sync_requested'] = True

    monkeypatch.setattr(task_sync, 'run_blocking', blocking)
    monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda uid: 'todoist')
    monkeypatch.setattr(task_sync.users_db, 'get_task_integration', lambda *args: {'connected': True})
    monkeypatch.setattr(
        task_sync.action_items_db, 'get_action_item', lambda uid, tid: world.store.rows.get(task_path(tid))
    )
    monkeypatch.setattr(
        task_sync.action_items_db,
        'update_action_item',
        lambda uid, tid, patch: world.store.rows[task_path(tid)].update(patch),
    )
    monkeypatch.setattr(task_sync.action_items_db, 'batch_set_sync_requested', request_sync)
    monkeypatch.setattr(task_sync, 'create_task_internal', create)
    monkeypatch.setattr(task_sync, 'send_apple_reminders_sync_push_async', apple)
    monkeypatch.setattr(flow, 'auto_sync_action_items_batch', task_sync.auto_sync_action_items_batch)
    return task_sync, calls


@pytest.mark.parametrize('platform', ['todoist', 'apple_reminders'])
def test_repeated_refresh_real_sync_sends_new_task_once_and_preserved_tasks_never(
    world, real_sync, monkeypatch, platform
):
    task_sync, calls = real_sync
    monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda uid: platform)
    world.store.rows[task_path('original')].update(due_at=NOW, apple_reminder_id='existing-apple')
    original = deepcopy(world.store.rows[task_path('original')])
    for attempt in range(4):
        world.write(['Send report', 'Book room'])
        if attempt == 0:
            new_id = next(p[-1] for p in world.store.rows if p[-2] == 'action_items' and p[-1] != 'original')
            world.store.rows[task_path(new_id)]['due_at'] = NOW
        world.drain()
    assert len(calls) == 1 and calls[0][0] == ('cloud' if platform == 'todoist' else 'apple')
    assert world.store.rows[task_path('original')] == original
    reminders = [effect for effect in world.effects if effect[0] == 'reminder']
    assert len(reminders) == 1 and reminders[0][1]['action_item_id'] == new_id


def test_executor_failure_after_claim_is_at_most_once_but_can_lose_delivery(world, monkeypatch):
    def fail(*args):
        raise RuntimeError('executor rejected')

    with monkeypatch.context() as patch:
        patch.setattr(flow, 'submit_with_context', fail)
        with pytest.raises(RuntimeError, match='executor rejected'):
            world.write(['Book room'])
    new_row = next(r for p, r in world.store.rows.items() if p[-2] == 'action_items' and p[-1] != 'original')
    assert new_row['refresh_delivery'] == 'claimed' and not new_row.get('exported')
    world.write(['Book room'])
    world.drain()
    assert not world.queue and not world.external


@pytest.mark.parametrize('bound', ['documents', 'hashes', 'aliases'])
def test_each_bound_aborts_without_blocking_another_conversation(world, bound):
    from database.action_item_refresh_policy import RECEIPT, key

    if bound == 'documents':
        for index in range(200):
            world.store.rows[task_path(f'stored-{index}')] = item('Same description')
    elif bound == 'hashes':
        world.store.rows[conv_path('survivor')][RECEIPT] = {
            'generation': 0,
            'keys': {key(f'Gone {index}'): [f'gone-{index}'] for index in range(200)},
        }
    else:
        world.store.rows[conv_path('survivor')][RECEIPT] = {
            'generation': 0,
            'keys': {key('Gone'): [f'gone-{index}' for index in range(400)]},
        }
    before = deepcopy(world.store.rows)
    with pytest.raises(ValueError, match='budget'):
        world.write(['Book room'])
    assert world.store.rows == before and not world.queue
    world.store.rows[conv_path('other')] = {'id': 'other', 'sync_content_revision': 1}
    world.store.rows[task_path('other-original')] = item('Other task', conversation_id='other')
    world.write(['New other task'], cid='other')
    world.drain()
    assert len(world.external) == 1


def test_sync_bridge_cleanup_transfers_tasks_before_retraction_and_replays(world, monkeypatch):
    from utils.sync import bridge

    seed_donor(world)
    donor = world.store.rows[conv_path('donor')]
    donor.pop('smart_merge')
    donor.update(sync_merged_into='survivor', sync_content_revision=1)
    world.store.rows[conv_path('survivor')]['sync_merged_from'] = ['donor']
    monkeypatch.setattr(
        bridge.conversations_db, 'get_conversation', lambda uid, cid: deepcopy(world.store.rows.get(conv_path(cid)))
    )
    before = deepcopy(world.store.rows[task_path('donor-task')])
    calls = []

    def retract(uid, cid):
        # The real retraction deletes every row still assigned to this donor.
        assert not any(r.get('conversation_id') == cid for p, r in world.store.rows.items() if p[-2] == 'action_items')
        calls.append(cid)
        if len(calls) == 1:
            raise RuntimeError('cleanup failed after task transfer')

    def mark(uid, cid, revision, audio_target):
        world.store.rows[conv_path(cid)]['sync_bridge_cleaned_revision'] = revision
        return True

    monkeypatch.setattr(bridge, 'retract_sync_bridge_source', retract)
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', mark)
    with pytest.raises(RuntimeError, match='cleanup failed'):
        bridge.finish_sync_bridges(UID, 'survivor')
    assert bridge.finish_sync_bridges(UID, 'survivor') == 'survivor'
    assert bridge.finish_sync_bridges(UID, 'survivor') == 'survivor'
    assert len(calls) == 2
    assert world.store.rows[task_path('donor-task')] == {**before, 'conversation_id': 'survivor'}
