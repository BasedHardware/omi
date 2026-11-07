"""Owner-hash rings and per-class virtual service; no fleet-wide writer."""

from config.batch_pipeline import scheduler_control_key
from config.firestore_read_levers import lever_enabled
from database.batch_pipeline_store import Transaction
from utils.batch_pipeline.contracts import Priority


def field(priority: int, name: str) -> str:
    return f'p{priority}_{name}'


def read_control(tx: Transaction, key: str) -> dict:
    control = tx.get('control', key)
    control.setdefault('rings', {str(int(p)): [] for p in Priority})
    for priority in Priority:
        for name, value in (
            ('active', False),
            ('service', 0.0),
            ('batch_available_at', 0.0),
            ('live_available_at', 0.0),
        ):
            control.setdefault(field(int(priority), name), value)
    return control


def frontier_hint_field(priority: int) -> str:
    return field(priority, 'frontier_hint')


def activate(tx: Transaction, control: dict, priority: int, now: float, key: str | None = None) -> None:
    if not control[field(priority, 'active')]:
        # Rejoining starts at the persistent frontier, never ancient or reset
        # credit. Indexed read only: no shared write clock or control hotspot.
        control[field(priority, 'service')] = max(control[field(priority, 'service')], tx.service_frontier(priority))
        note = getattr(tx, 'note_hinted_activation', None)
        if key is not None and note is not None and lever_enabled('admission_frontier_hint'):
            # The frontier above was read outside this transaction (admission_frontier_hint),
            # so pulls committed meanwhile are unseen. The store re-seeds the shard right after
            # this transaction commits, unless a pull reaches it first (consume_frontier_hint).
            control[frontier_hint_field(priority)] = True
            note(key, priority)
    control[field(priority, 'active')] = True
    for pool in ('batch', 'live'):
        key = field(priority, f'{pool}_available_at')
        control[key] = min(control[key], now)


def consume_frontier_hint(control: dict, priority: int) -> None:
    """A pull reaching a hinted shard before its re-seed ends the hint without a lift.

    Lifting at pull time would charge the joiner for service other shards earned while
    it waited its turn; the post-commit re-seed then finds no marker and does nothing.
    """
    control.pop(frontier_hint_field(priority), None)


def migrate_legacy(tx: Transaction, now: float) -> None:
    """One-time bounded transfer of pre-sharding metadata; never touches content."""
    legacy = tx.get('control', 'scheduler')
    moved = 0
    for priority, ring in legacy.get('rings', {}).items():
        while ring and moved < 100:
            queue_key = ring.pop(0)
            queue = tx.get('queues', queue_key)
            if queue.get('head'):
                key = scheduler_control_key(queue_key.split('_', 1)[1])
                shard = read_control(tx, key)
                if queue_key not in shard['rings'][priority]:
                    shard['rings'][priority].append(queue_key)
                activate(tx, shard, int(priority), now, key)
                tx.put('control', key, shard)
            moved += 1
    if moved:
        tx.put('control', 'scheduler', legacy)
