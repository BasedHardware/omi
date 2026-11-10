"""Feeds a shard holder's owner drains from its shards' wake lanes.

The pump runs on the serving event loop. Each tick it renews shard leases
when due, then pulls wakes into free drain slots: fresh wakes first (newest
capture first), with ``backlog_reserve`` slots kept for backlog wakes (oldest
commit first) whenever backlog is waiting, so fresh audio reaches the user
first and the backlog still drains. A wake leaves Redis only after its owner's
drain walks to the chain end, and only if no newer push landed meanwhile. A
stuck owner cools down in process memory and its wake moves to the backlog
lane at its retry time, behind every owner due sooner.

Every Redis call runs off the event loop and fails open.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Callable

from config.batch_pipeline import (
    owner_chain_projection_enabled,
    owner_drain_enabled,
    projection_backlog_reserve,
    projection_pending_page_enabled,
    sweep_owner_chain_enabled,
)
from utils.batch_pipeline.metrics import (
    PROJECTION_SHARD_WAKE_DEPTH,
    PROJECTION_SHARD_WAKES,
    PROJECTION_SHARDS_HELD,
    PROJECTION_SHARDS_UNHELD,
)
from utils.batch_pipeline.projection_shards import BACKLOG, FRESH, ProjectionShards, Wake
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback

if TYPE_CHECKING:
    from utils.batch_pipeline.projection import Projector

logger = logging.getLogger(__name__)
# A drain that stopped short of the chain end waits this long before its
# owner is taken again (a stuck head, an error, a lost claim race).
STUCK_RETRY_SECONDS = 120.0
CLAIM_RETRY_SECONDS = 15.0
CLAIM_STOPS = frozenset({'claim_busy', 'claim_held', 'blocked_projection_assignment_claim_busy'})
MAX_TAKE = 256
MAX_COOLDOWN = 20_000
# The backstop spends at most this much of one supervisor tick, in pages of
# 100 rows: one pass over a 180k-row backlog is about 20 minutes of 150 reads/s.
BACKSTOP_SECONDS = 10.0
BACKSTOP_PAGES = 30
# Tail discovery: rows committed since the last leader pass (the GPU worker's
# merge commits push no wake). Up to 500 rows per 20 s supervisor tick; a full
# page resumes at its cursor on the next tick.
TAIL_PAGES = 5
TAIL_OVERLAP_SECONDS = 60.0
TAIL_SLACK_SECONDS = 10.0
# Commits of audio captured this recently take the fresh lane (the sync fresh
# lane's age, utils/sync/lanes.py).
FRESH_CAPTURE_SECONDS = 6 * 3600.0
# Shard pump cadence on the event loop.
TICK_SECONDS = 1.0


class ShardPump:
    def __init__(
        self,
        projector: Projector,
        shards: ProjectionShards,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.projector = projector
        self.shards = shards
        self.monotonic = monotonic
        # Owner -> the wakes this pump handed to the drain for it.
        self.inflight: dict[str, list[Wake]] = {}
        # Owner -> monotonic time before which the pump does not take it again.
        self.cooldown: dict[str, float] = {}
        # Wakes to settle on the next tick (Redis stays off the event loop).
        self.settling: list[Wake] = []
        # Cooled wakes to move behind due work on the next tick, with retry scores.
        self.deferring: list[tuple[Wake, float]] = []
        self.attached = False

    # Any thread -----------------------------------------------------------

    @property
    def engaged(self) -> bool:
        """Sharded serving applies: shards answer and the drain it relies on is on.

        The pump only feeds the owner drain, and the leader backstop leaves
        persisted/ready rows to the sweep's finish page. When any of those kill
        switches is off, this process serves exactly as it did before shards.
        """
        return self.shards.active and self.switches_on

    @property
    def switches_on(self) -> bool:
        """Every existing drain kill switch the sharded path relies on is on."""
        return (
            owner_chain_projection_enabled()
            and sweep_owner_chain_enabled()
            and owner_drain_enabled()
            and projection_pending_page_enabled()
        )

    def route(self, owner_id: str, score: float | None = None) -> bool:
        """Projector router: True keeps the drain request in this process.

        With shards engaged, an owner whose shard some member holds becomes a
        backlog wake for that holder (this process included, so its pump owns
        the bookkeeping). Unheld shards and Redis failures keep the legacy
        local drain, so no owner is ever left without a walker.
        """
        return not self.wake(owner_id, None, self.shards.clock() if score is None else score)

    def wake(self, owner_id: str, capture_at: float | None, committed_at: float, *, discovery: bool = False) -> bool:
        """Push one wake to the owner's shard holder. True when a holder will drain it.

        Audio captured within ``FRESH_CAPTURE_SECONDS`` takes the fresh lane,
        scored by capture time; future or older captures use backlog, scored by commit.
        Discovery creates only a missing wake; existing lanes and retry scores stay put.
        False (not engaged, shard unheld, push failed) means drain it locally.
        """
        if not self.engaged:
            return False
        key = owner_key(owner_id)
        if not self.shards.covered(key):
            return False
        now = self.shards.clock()
        if capture_at is not None and 0 <= now - capture_at <= FRESH_CAPTURE_SECONDS:
            lane, score = FRESH, float(capture_at)
        else:
            lane, score = BACKLOG, float(committed_at)
        pushed = self.shards.push(owner_id, key, lane, score, discovery=discovery)
        PROJECTION_SHARD_WAKES.labels(lane=lane, outcome='pushed' if pushed else 'push_failed').inc()
        return pushed

    def committed(self, owner_id: str, entries: list[dict]) -> None:
        """Merge committed ``entries`` for ``owner_id``: wake its shard holder. Blocking."""
        if not entries or not self.engaged:
            return  # Not engaged: this process sweeps, as before shards.
        now = self.shards.clock()
        captures = [
            float(e['capture_at'])
            for e in entries
            if isinstance(e.get('capture_at'), (int, float)) and not isinstance(e.get('capture_at'), bool)
        ]
        fresh = [c for c in captures if 0 <= now - c <= FRESH_CAPTURE_SECONDS]
        commits = [float(e['committed_at']) for e in entries if isinstance(e.get('committed_at'), (int, float))]
        capture_at = max(fresh) if fresh else None
        if not self.wake(owner_id, capture_at, min(commits) if commits else now):
            # Unheld shard or Redis error: followers no longer sweep, so drain here.
            self.projector.request_local_drain(owner_id)

    def backstop(self) -> dict:
        """Leader-only discovery that re-pushes wakes for pending owners. Blocking.

        First the tail (rows committed since the last pass, which covers the
        GPU worker's own merge commits), then a bounded slice of the whole
        pending log from a resuming cursor (lost wakes, pre-switch rows).
        """

        def route(owner_id: str, committed_at: float, capture_at: float | None) -> None:
            if not self.wake(owner_id, capture_at, committed_at, discovery=True):
                self.projector.request_local_drain(owner_id)

        tail = self.projector.discover_tail(
            route, pages=TAIL_PAGES, overlap_seconds=TAIL_OVERLAP_SECONDS, slack_seconds=TAIL_SLACK_SECONDS
        )
        counts = self.projector.discover_owners(route, pages=BACKSTOP_PAGES, budget_seconds=BACKSTOP_SECONDS)
        logger.info(
            'event=batch_projection_shards action=backstop tail_rows=%d tail_owners=%d pages=%d rows=%d owners=%d'
            ' wrapped=%d',
            tail['rows'],
            tail['owners'],
            counts['pages'],
            counts['rows'],
            counts['owners'],
            counts['wrapped'],
        )
        return {**counts, 'tail_rows': tail['rows'], 'tail_owners': tail['owners']}

    # Event loop -----------------------------------------------------------

    def attach(self) -> None:
        drains = self.projector.ensure_drains()
        drains.on_idle = self.idle
        drains.yield_continuation = self.yield_continuation
        self.attached = True

    def yield_continuation(self, owner: str) -> bool:
        """Shard-owned admissions get one turn before competing with due wakes again."""
        return self.engaged and owner in self.inflight

    def idle(self, owner: str, stop: str) -> None:
        """OwnerDrains hook: ``owner`` left the drain after a turn ending ``stop``."""
        wakes = self.inflight.pop(owner, None)
        if wakes is None:
            return
        if stop == 'end':
            self.settling.extend(wakes)
            return
        # Productive owners yield for one pump tick, not the stuck-head backoff.
        # Their backlog retry score leaves already-due work ahead of them.
        delay = (
            TICK_SECONDS
            if stop == 'yielded'
            else (CLAIM_RETRY_SECONDS if stop in CLAIM_STOPS else STUCK_RETRY_SECONDS) * random.uniform(0.8, 1.2)
        )
        # Local privacy/live-target holds can outlast the pump's backoff. Keep
        # their wake out of the due prefix until the owner can actually run.
        delay = max(delay, self.projector.ensure_drains().retry_delay(owner))
        if len(self.cooldown) < MAX_COOLDOWN:
            self.cooldown[owner] = self.monotonic() + delay
        # Every stopped owner, including claim refusals, gives up its place in
        # the due prefix while cooling so later owners remain reachable.
        retry_at = self.shards.clock() + delay
        # Defer the taken backlog wake before moving fresh into backlog:
        # that move bumps the backlog sequence and would stale its take.
        self.deferring.extend((wake, retry_at) for wake in sorted(wakes, key=lambda wake: wake.lane != BACKLOG))
        PROJECTION_SHARD_WAKES.labels(lane=wakes[0].lane, outcome='cooled').inc()

    async def tick(self) -> int:
        """One pump pass; returns the number of owners handed to the drain."""
        if not self.attached:
            self.attach()
        shards = self.shards
        if not self.switches_on:
            # A kill switch took this process off the sharded path. It must not
            # keep shard leases: members route wakes to holders, and these lanes
            # would wait unread. Hand them back so an engaged member takes them.
            if shards.held or shards.healthy:
                await run_blocking(db_executor, shards.release)
                PROJECTION_SHARDS_HELD.set(0)
            if self.projector.owes_drains:
                self.projector.start_drains()
            return 0
        if shards.refresh_due():
            await run_blocking(db_executor, shards.refresh)
            PROJECTION_SHARDS_HELD.set(len(shards.held))
            PROJECTION_SHARDS_UNHELD.set(len(shards.unheld))
        if self.settling:
            settling, self.settling = self.settling, []
            settled = await run_blocking(db_executor, lambda: [shards.settle(w) for w in settling])
            for wake, done in zip(settling, settled):
                PROJECTION_SHARD_WAKES.labels(lane=wake.lane, outcome='settled' if done else 'repushed').inc()
        if self.deferring:
            deferring, self.deferring = self.deferring, []
            await run_blocking(db_executor, lambda: [shards.defer(w, score) for w, score in deferring])
            if not shards.healthy:
                # Keep the batch's order and deadlines across Redis errors.
                # Sequence checks make replay (including lost replies) safe;
                # stale takes return False without making shards unhealthy.
                self.deferring[:0] = deferring
                await run_blocking(db_executor, shards.release)
                PROJECTION_SHARDS_HELD.set(0)
                record_fallback(
                    component='other',
                    from_mode='projection_shards',
                    to_mode='legacy_sweep',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
        projector = self.projector
        if projector.owes_drains:
            # Local requests: unheld-shard fallback and Redis failures.
            projector.start_drains()
        if not self.engaged or not shards.held:
            return 0
        drains = projector.ensure_drains()
        free = drains.free_slots
        if free <= 0:
            return 0
        now = self.monotonic()
        if self.cooldown:
            self.cooldown = {owner: until for owner, until in self.cooldown.items() if until > now}
        # Per held shard: this pass's share of the slots, plus room to skip
        # owners already draining or cooling.
        held = max(1, len(shards.held))
        fetch = min(MAX_TAKE, -(-free * 4 // held) + len(self.cooldown) + len(self.inflight))
        fresh, backlog = await run_blocking(
            db_executor, lambda: (shards.take(FRESH, fetch), shards.take(BACKLOG, fetch))
        )
        picked = self.pick(fresh, backlog, free, drains)
        for owner, wakes in picked.items():
            self.inflight[owner] = wakes
            PROJECTION_SHARD_WAKES.labels(lane=wakes[0].lane, outcome='taken').inc()
        if picked:
            drains.request(list(picked))
        return len(picked)

    def pick(self, fresh: list[Wake], backlog: list[Wake], free: int, drains) -> dict[str, list[Wake]]:
        """Fresh first, keeping ``backlog_reserve`` slots for waiting backlog."""
        now = self.monotonic()
        due_at = self.shards.clock()

        settling = {w.owner_id for w in self.settling} | {w.owner_id for w, _ in self.deferring}

        def eligible(wake: Wake) -> bool:
            owner = wake.owner_id
            return (
                wake.score <= due_at
                and owner not in self.inflight
                and owner not in settling
                and not drains.busy(owner)
                and owner not in self.projector.draining
                and self.cooldown.get(owner, 0.0) <= now
            )

        fresh_ok = [w for w in fresh if eligible(w)]
        backlog_ok = [w for w in backlog if eligible(w)]
        reserve = min(projection_backlog_reserve(), free) if backlog_ok else 0
        picked: dict[str, list[Wake]] = {}

        def take(wakes: list[Wake], room: int) -> None:
            for wake in wakes:
                if wake.owner_id in picked:
                    continue
                if len(picked) >= room:
                    return
                picked[wake.owner_id] = [wake]

        take(fresh_ok, free - reserve)
        take(backlog_ok, free)
        take(fresh_ok, free)  # Backlog ran short: give fresh the reserve back.
        # A picked owner waiting in the other lane settles with it when its drain ends.
        for wake in fresh_ok + backlog_ok:
            wakes = picked.get(wake.owner_id)
            if wakes is not None and all(w.lane != wake.lane for w in wakes):
                wakes.append(wake)
        return picked

    async def depth(self) -> None:
        counts = await run_blocking(db_executor, self.shards.depth)
        for lane, count in counts.items():
            PROJECTION_SHARD_WAKE_DEPTH.labels(lane=lane).set(count)
