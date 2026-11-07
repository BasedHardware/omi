"""Owner-hash rings and per-class virtual service; no fleet-wide writer."""

import time

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
        note = getattr(tx, '_note_hinted_activation', None)
        if key is not None and note is not None and lever_enabled('admission_frontier_hint'):
            # The frontier above was read outside this transaction (admission_frontier_hint),
            # so pulls committed meanwhile are unseen. The store re-seeds the shard right after
            # this transaction commits, unless a pull reaches it first (consume_frontier_hint).
            control[frontier_hint_field(priority)] = time.time()
            note(key, priority)
    control[field(priority, 'active')] = True
    for pool in ('batch', 'live'):
        key = field(priority, f'{pool}_available_at')
        control[key] = min(control[key], now)


# A pull this soon after a hinted activation may beat the post-commit re-seed; it lifts
# the shard itself. Later pulls only consume the marker: lifting then would charge the
# joiner for service other shards earned while it waited its turn.
PULL_LIFT_WINDOW_SECONDS = 30.0


def consume_frontier_hint(tx: Transaction, control: dict, priority: int, now: float) -> bool:
    """End a hinted activation at the shard's pull; lift only if the pull beat the re-seed.

    Returns whether it lifted. The caller's control put clears the marker either way.
    """
    stamped = control.pop(frontier_hint_field(priority), None)
    if not isinstance(stamped, (int, float)) or isinstance(stamped, bool):
        return False
    if now - stamped > PULL_LIFT_WINDOW_SECONDS:
        return False
    key = field(priority, 'service')
    control[key] = max(control[key], tx.service_frontier(priority))
    return True


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
