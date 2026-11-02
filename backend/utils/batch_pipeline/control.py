"""Owner-hash rings and per-class virtual service; no fleet-wide writer."""

from config.batch_pipeline import scheduler_control_key
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


def activate(tx: Transaction, control: dict, priority: int, now: float) -> None:
    if not control[field(priority, 'active')]:
        # Rejoining starts at the persistent frontier, never ancient or reset
        # credit. Indexed read only: no shared write clock or control hotspot.
        control[field(priority, 'service')] = max(control[field(priority, 'service')], tx.service_frontier(priority))
    control[field(priority, 'active')] = True
    for pool in ('batch', 'live'):
        key = field(priority, f'{pool}_available_at')
        control[key] = min(control[key], now)


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
                activate(tx, shard, int(priority), now)
                tx.put('control', key, shard)
            moved += 1
    if moved:
        tx.put('control', 'scheduler', legacy)
