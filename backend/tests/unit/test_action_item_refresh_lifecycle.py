"""Synthetic silence-split backend scenario; codecs/merge/late-sync/task writes are real.

Audio capture and task extraction are fixture inputs; no clients, Jev, or providers.
"""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

from tests.unit import test_conversation_smart_merge as merge
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.sync.assignment import assign_in_transaction
from utils.conversations import action_item_refresh as flow, process_conversation as pc
from utils.conversations.processing_trigger import ProcessingTrigger


def test_silence_split_merge_late_sync_and_repeated_refresh(monkeypatch):
    world = merge.World(monkeypatch)
    monkeypatch.setenv('ACTION_ITEM_REFRESH_PRESERVE_ENABLED', 'true')
    monkeypatch.delenv(merge.config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    world.add('p', 0, 10)
    world.add('n', 15, 10)  # silence split: two completed live rows from one device
    tasks = ('users', merge.UID, 'action_items')
    original = {
        'description': 'Send report',
        'conversation_id': 'p',
        'completed': True,
        'exported': True,
        'folder_id': 'manual-folder',
        'due_at': merge.T0,
    }
    donor = {
        'description': 'Call vendor',
        'conversation_id': 'n',
        'completed': False,
        'exported': True,
        'provenance': [{'kind': 'conversation', 'id': 'n'}],
    }
    world.store.rows[(*tasks, 'original')] = deepcopy(original)
    world.store.rows[(*tasks, 'donor-task')] = deepcopy(donor)
    queue, external = [], []
    monkeypatch.setattr(pc.conversation_capture, 'canonical_conversation_fields', lambda *a: {})
    monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', lambda *a: None)
    monkeypatch.setattr(flow, 'submit_with_context', lambda executor, fn, *args: queue.append(lambda: fn(*args)))

    async def export(uid, rows):
        for row in rows:
            external.append(row['id'])
            world.store.rows[(*tasks, row['id'])]['exported'] = True

    monkeypatch.setattr(flow, 'auto_sync_action_items_batch', export)

    def write(trigger):
        row = world.get(merge.UID, 'p')
        items = [
            SimpleNamespace(
                description=text,
                completed=False,
                created_at=merge.T0,
                updated_at=merge.T0,
                due_at=None,
                completed_at=None,
            )
            for text in ['Send report', 'Call vendor', 'Book room']
        ]
        conversation = SimpleNamespace(
            id='p',
            is_locked=False,
            sync_content_revision=row['sync_content_revision'],
            structured=SimpleNamespace(action_items=items),
        )
        pc._write_action_items(merge.UID, conversation, trigger)
        while queue:
            queue.pop(0)()

    def process(*args, **kwargs):
        result = world.process(*args, **kwargs)
        write(ProcessingTrigger.SMART_MERGE)
        return result

    monkeypatch.setattr(merge.smart_merge, 'process_conversation', process)
    assert world.finish('n') is True
    assert world.raw('n')['deleted'] and world.raw('n')['sync_merged_into'] == 'p'
    late = chunk('late-wal', (merge.T0 + timedelta(minutes=25, seconds=10)).timestamp(), device='pendant-1')
    result, created, _ = assign_in_transaction(
        world.store.transaction(),
        world.store.collection('users').document(merge.UID),
        late,
        candidate_id=None,
        target_id='n',
        decode=lambda raw: world.get(merge.UID, raw['id']),
        encode=lambda row: merge.conversations_db.encode_conversation_for_write(merge.UID, row, 'enhanced'),
        invalidate=lambda payload: None,
    )
    assert result['id'] == 'p' and not created
    for _ in range(3):
        write(ProcessingTrigger.SYNC_UPDATE)
    assert world.store.rows[(*tasks, 'original')] == original
    assert world.store.rows[(*tasks, 'donor-task')] == {**donor, 'conversation_id': 'p'}
    assert len(external) == len(set(external)) == 1
    assert [p[-1] for p, r in world.store.rows.items() if p[-2] == 'conversations' and not r.get('deleted')] == ['p']
