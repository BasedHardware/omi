"""Privacy control receipts must advance real owner ordering and preserve replay."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from database.batch_pipeline_privacy import privacy_owner_key
from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows, multipart
from tests.integration.test_batch_projection_delete_race_firestore import overlap
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline import projection

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('kind', ['account', 'protection', 'cycle', 'missing', 'budget'])
@pytest.mark.parametrize('async_projection', [False, True])
def test_privacy_hold_advances_chain_and_replays_retained_speech_after_repair(
    lane, monkeypatch, kind, async_projection
):
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', str(async_projection).lower())
    head = lane.seed(('head',))
    later = lane.seed(('later',), capture_at=2000)
    lane.finish(head)
    lane.finish(later)
    before_ledger = deepcopy(head.ledger.get().to_dict())
    root = lane.user.collection('conversations').document(head.items[0].conversation_id)
    created = []
    if kind == 'account':
        marker = lane.client.collection('account_deletions').document(lane.uid)
        marker.set({})
    elif kind == 'protection':
        lane.user.update({'migration_status': 'pending'})
    elif kind in {'cycle', 'missing'}:
        root.set({'deleted': True, 'sync_merged_into': 'synthetic-tail'})
        if kind == 'cycle':
            tail = lane.user.collection('conversations').document('synthetic-tail')
            tail.set({'deleted': True, 'sync_merged_into': root.id})
            created.append(tail)
    else:
        batch = lane.client.batch()
        previous = root
        for index in range(256):
            target = lane.user.collection('conversations').document(f'synthetic-hop-{index}')
            batch.set(previous, {'deleted': True, 'sync_merged_into': target.id})
            created.append(target)
            previous = target
        batch.commit()
    lane.projector.project_owner(lane.uid, limit=16, budget_seconds=60)
    store = lane.projector.store
    entry = store.ref('results', head.ids[0]).get().to_dict()
    assert entry['projection_state'] == 'quarantine_held'
    assert entry['projection_privacy_refusal']['version'] == 1
    assert (
        entry['projection_privacy_refusal']['reason']
        == {
            'account': 'account_deleted',
            'protection': 'data_protection_changed',
            'cycle': 'conversation_redirect_cycle',
            'missing': 'conversation_redirect_missing',
            'budget': 'conversation_fence_budget',
        }[kind]
    )
    assert head.ledger.get().to_dict() == before_ledger
    # The existing read-ahead may prefetch immutable results before the write
    # fence. Once held, an ordinary retry must not fetch or assign again.
    held_loads = list(lane.loads)
    assert lane.projector.project(head.ids[0]) is None
    assert lane.loads == held_loads
    assert store.projection_watermark(owner_key(lane.uid)) == later.ids[-1]
    if kind in {'account', 'protection'}:
        assert not lane.tasks and not lane.published
    else:
        # This source's malformed graph never blocks unrelated later words.
        lane.projector.project(later.ids[0])
        assert later.ledger.get().to_dict()['status'] == 'completed'
        assert any(
            row['transcript_segments'] and row['transcript_segments'][0]['text'] == 'We discussed the project.'
            for row in active_rows(lane)
        )
    if kind == 'account':
        marker.delete()  # Synthetic, cancelled intent; no production account repair.
    elif kind == 'protection':
        lane.user.update({'migration_status': None})
    else:
        root.delete()
        for reference in created:
            reference.delete()
    for batch in (head, later):
        assert lane.projector.project(batch.ids[0]) is not None
        assert batch.ledger.get().to_dict()['status'] == 'completed'
        assert batch.ledger.get().to_dict()['usage_committed_seconds'] == 4
    assert store.projection_watermark(owner_key(lane.uid)) == later.ids[-1]
    assert head.ids[0] in lane.loads
    assert sum(len(row['transcript_segments']) for row in active_rows(lane)) == 2
    before = [(row['id'], row['sync_content_revision']) for row in active_rows(lane)]
    lane.projector.project(head.ids[0])
    assert [(row['id'], row['sync_content_revision']) for row in active_rows(lane)] == before


def test_structural_donor_refusal_isolates_input_instead_of_holding_live_speech(lane, monkeypatch):
    batch = lane.seed()
    blocked, live = overlap(lane, batch, tombstoned=False)
    for reference in (blocked, lane.user.collection('conversations').document(live['id'])):
        reference.update({'sync_merged_from': ['synthetic-cycle-a']})
    for here, there in [('synthetic-cycle-a', 'synthetic-cycle-b'), ('synthetic-cycle-b', 'synthetic-cycle-a')]:
        lane.user.collection('conversations').document(here).set({'deleted': True, 'sync_merged_into': there})
    before = blocked.get().to_dict()
    monkeypatch.setattr(lane.conversations, 'get_closest_conversation_to_timestamps', lambda *args: live)
    lane.finish(batch)
    result = lane.projector.project(batch.ids[0])
    assert result is not None and result['new_memories']
    assert batch.ledger.get().to_dict()['usage_committed_seconds'] == 4
    assert blocked.get().to_dict() == before
    entry = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert not entry.get('projection_privacy_refusal')
    assert entry['projection']['speech_seconds'] == 4


def test_old_generation_hold_never_authorizes_text_but_new_generation_speech_advances(lane):
    head = lane.seed(('old-generation',))
    lane.finish(head)
    original = head.ledger.get().to_dict()
    lane.client.collection('batch_pipeline_privacy').document(privacy_owner_key(lane.uid)).set({'generation': 1})
    lane.projector.project_owner(lane.uid, limit=8, budget_seconds=60)
    assert head.ledger.get().to_dict() == original
    binding = replace(
        head.binding,
        job_id='synthetic-current-job',
        content_id='synthetic-current-content',
        segment_ids=('synthetic-current',),
        privacy_generation=1,
    )
    item = replace(
        head.items[0],
        segment_id=binding.segment_ids[0],
        capture_at=4000,
        conversation_id=lane.chunk_identity(
            lane.uid, binding.source, binding.client_device_id, binding.is_locked, 4000
        ),
        privacy_generation=1,
    )
    assert lane.admit(lane.store, [item], binding, 0, namespace=lane.store.namespace)['outcome'] == 'batch'
    leases = {}
    for _ in range(240):
        leases.update({lease.item.segment_id: lease for lease in lane.queue.pull(0, 1)})
        if item.segment_id in leases:
            break
    assert item.segment_id in leases
    fresh = SimpleNamespace(
        binding=binding,
        items=[item],
        ids=binding.segment_ids,
        leases=leases,
        ledger=lane.sync_content_ledger_ref(lane.client, lane.uid, binding.content_id),
    )
    lane.finish(fresh)
    lane.projector.project_owner(lane.uid, limit=8, budget_seconds=60)
    assert lane.projector.project(item.segment_id) is not None
    assert fresh.ledger.get().to_dict()['usage_committed_seconds'] == 4
    before = list(lane.loads)
    assert lane.projector.project(head.ids[0]) is None
    assert lane.loads == before and head.ledger.get().to_dict() == original
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == item.segment_id
    assert len(active_rows(lane)) == 1


def test_partial_multipart_privacy_hold_replays_every_part_without_rewinding(lane, monkeypatch):
    head = multipart(lane, 2)
    later = lane.seed(('later',), capture_at=4000, duration_seconds=head.items[0].duration_seconds)
    lane.finish(later)
    original = projection.build_incoming

    def crash(item, *args, **kwargs):
        if 1100 < item.capture_at < 4000:
            raise RuntimeError('synthetic crash before later part')
        return original(item, *args, **kwargs)

    monkeypatch.setattr(projection, 'build_incoming', crash)
    with pytest.raises(RuntimeError, match='synthetic crash'):
        lane.projector.project(head.ids[0])
    lane.user.update({'migration_status': 'pending'})
    lane.projector.project_owner(lane.uid, limit=16, budget_seconds=60)
    held = lane.projector.store.ref('results', head.ids[0]).get().to_dict()
    assert held['projection_parts']['0']['state'] == 'quarantined'
    assert held['projection_part_count'] == 2
    lane.user.update({'migration_status': None})
    monkeypatch.setattr(projection, 'build_incoming', original)
    assert lane.projector.project(later.ids[0]) is not None
    assert lane.projector.project(head.ids[0]) is not None
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == later.ids[0]
    assert head.ledger.get().to_dict()['usage_committed_seconds'] == 2
    assert later.ledger.get().to_dict()['usage_committed_seconds'] == 2
    rows = active_rows(lane)
    assert len(rows) == 4 and all(len(row['transcript_segments']) == 1 for row in rows)
    before = {row['id']: row['sync_content_revision'] for row in rows}
    lane.projector.project(head.ids[0])
    assert {row['id']: row['sync_content_revision'] for row in active_rows(lane)} == before
