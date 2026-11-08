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


def activation_surface(control: dict, priority: int, queue_key: str) -> tuple:
    """Value snapshot of the exact fields the append path can change.

    The scheduler append is the only control writer beside the pull's
    service advance and the one-time migration: it may add ``queue_key``
    to the priority's ring and ``activate`` may set ``active``, seed
    ``service`` from the cold frontier and lower the batch/live
    availability floors. A warm append — queue already in the ring,
    priority already active, floors already at or below this job's
    ``available_at`` — leaves every one of those values unchanged, so the
    control write that followed it carried byte-identical content and
    existed only to join the write set. Snapshots taken before and after
    the append's mutations turn that write into a decision: identical
    snapshots mean nothing changed and the write is skipped; any real
    difference writes exactly as before.
    """
    ring = control.get('rings', {}).get(str(int(priority))) or ()
    return (
        ('ring', int(priority), queue_key in ring, len(ring)),
        ('active', int(priority), bool(control.get(field(priority, 'active')))),
        ('service', int(priority), control.get(field(priority, 'service'))),
        ('batch_available_at', int(priority), control.get(field(priority, 'batch_available_at'))),
        ('live_available_at', int(priority), control.get(field(priority, 'live_available_at'))),
    )


def activate(tx: Transaction, control: dict, priority: int, now: float, frontier: float = 0.0) -> None:
    """Activate ``priority`` on this shard, seeding service from the rejoin hint.

    ``frontier`` is the advisory fairness seed read OUTSIDE the transaction via
    ``Store.service_frontier_hint`` (the fleet's highest committed virtual
    service). It used to be an indexed query inside the caller's transaction —
    but the max-service control document is the hottest shard under load (every
    fairness scan of the winning shard rewrites it), so a rejoining admission
    joined that abort set for a purely advisory value and burned its contention
    budget on a document it never writes. A stale seed is a bounded, self-
    correcting fairness transient: too low re-joins slightly under-served, too
    high slightly over-served; it is never authorization, custody or ordering.
    ``0.0`` (the empty-collection seed) is the degraded value.
    """
    if not control[field(priority, 'active')]:
        # Rejoining starts at the persistent frontier, never ancient or reset
        # credit. Advisory hint read, never a transactional read: no shared
        # write clock, no control hotspot, no abort-set membership.
        control[field(priority, 'service')] = max(control[field(priority, 'service')], frontier)
    control[field(priority, 'active')] = True
    for pool in ('batch', 'live'):
        key = field(priority, f'{pool}_available_at')
        control[key] = min(control[key], now)


def migrate_legacy(tx: Transaction, now: float, frontiers: dict | None = None) -> None:
    """One-time bounded transfer of pre-sharding metadata; never touches content.

    ``frontiers`` carries the advisory rejoin seeds read outside the caller's
    transaction (see ``activate``); absent priorities degrade to ``0.0``.
    """
    seeds = frontiers or {}
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
                activate(tx, shard, int(priority), now, seeds.get(int(priority), 0.0))
                tx.put('control', key, shard)
            moved += 1
    if moved:
        tx.put('control', 'scheduler', legacy)
