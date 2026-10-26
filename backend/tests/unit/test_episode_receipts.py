"""Receipt window semantics: the base keeps the most recent ids, the oldest spill."""

from datetime import datetime, timezone

from database import episode_receipts

AT = datetime(2026, 10, 25, tzinfo=timezone.utc)


def test_plan_write_spills_only_the_oldest_overflow_and_keeps_insertion_order():
    existing = {'ids': [f'old-{i:05d}' for i in range(episode_receipts.SHARD_SIZE)], 'shards': 0}
    # The new ids sort below every existing one: an alphabetical window would
    # archive exactly these and keep the old ids instead.
    late = ['aaa-late-1', 'aaa-late-2']
    payload, archives = episode_receipts.plan_write(existing, late, now=AT)
    assert [(index, ids) for index, ids in archives] == [(0, ['old-00000', 'old-00001'])]
    assert payload['ids'] == existing['ids'][2:] + late
    assert payload['shards'] == 1 and payload['updated_at'] == AT


def test_plan_write_below_the_cap_archives_nothing_and_drops_duplicates():
    payload, archives = episode_receipts.plan_write(None, ['b', 'a', 'b'], now=AT)
    assert archives == []
    assert payload['ids'] == ['b', 'a']
    assert payload['shards'] == 0
    # An id already recorded keeps its original position; only new ids append.
    again = episode_receipts.plan_write({'ids': ['b', 'a']}, ['b', 'c'], now=AT)
    assert again[0]['ids'] == ['b', 'a', 'c'] and again[1] == []


def test_plan_write_spills_across_successive_small_batches():
    """Many small writes past the cap spill the oldest ids one batch at a time."""
    window = [f'seg-{i:05d}' for i in range(episode_receipts.SHARD_SIZE)]
    payload, archives = episode_receipts.plan_write(None, window, now=AT)
    assert archives == []
    spilled = []
    for step in range(1, 4):
        payload, archives = episode_receipts.plan_write(payload, [f'new-{step}-{i:05d}' for i in range(100)], now=AT)
        assert len(payload['ids']) == episode_receipts.SHARD_SIZE
        assert payload['shards'] == step
        assert len(archives) == 1 and archives[0][0] == step - 1
        spilled.extend(archives[0][1])
    assert spilled == window[:300]
    fresh = [f'new-{step}-{i:05d}' for step in range(1, 4) for i in range(100)]
    assert payload['ids'] == window[300:] + fresh
