"""Owner-hash projection shards: one drain writer per owner across the fleet.

Every serving instance used to page the same global ``committed_at`` keyset and
race the others for each owner's advisory Redis claim, so most drain turns
ended ``claim_busy`` or found nothing. With shards on:

- Owners hash to one of ``count`` shards. Each shard has a short Redis lease
  held by at most one member instance; members balance to
  ``ceil(count / live members)`` shards each, and a free shard is taken on the
  next lease pass by any member below its share.
- A merge commit pushes a wake for the owner into its shard's lane (``fresh``
  for recently captured audio, ``backlog`` otherwise). Only the shard holder
  pulls wakes and drains those owners, so drains stop competing for claims.
- The maintenance leader's discovery-only backstop pages the durable result
  log and re-pushes wakes, which covers Redis loss and rows committed before
  the switch.

Nothing here is a correctness fence. Assignment ordering is still the
transactional predecessor fence and the advisory owner claim still wraps each
walk step. Every Redis error fails open: the process reports itself inactive
and the caller runs the legacy per-instance sweep, exactly as before.
"""

from __future__ import annotations

from functools import lru_cache
import logging
import math
import random
import threading
import time
from typing import Any, Callable, Iterable
import uuid

from database import redis_db

logger = logging.getLogger(__name__)

REDIS_TIMEOUT_SECONDS = 1.0
# Every serving process must agree on the count; a change re-forms the fleet
# (keys carry the count, so old and new layouts never share a lease).
PROJECTION_SHARD_COUNT = 64
LEASE_SECONDS = 30.0
# Lease passes run this often; a holder that misses two passes keeps its lease.
LEASE_REFRESH_SECONDS = LEASE_SECONDS / 3
# Idle wake keys expire; creating pushes and real notifications refresh the TTL.
WAKE_TTL_SECONDS = 7 * 24 * 3600
FRESH = 'fresh'
BACKLOG = 'backlog'
LANES = (FRESH, BACKLOG)

# KEYS: lease keys. ARGV[1]: holder, ARGV[2]: TTL ms. Renews only leases this
# holder still owns; returns 1/0 per key.
_RENEW_LUA = """
local out = {}
for i, key in ipairs(KEYS) do
  if redis.call('get', key) == ARGV[1] then
    redis.call('pexpire', key, ARGV[2])
    out[i] = 1
  else
    out[i] = 0
  end
end
return out
"""
_RELEASE_LUA = """
local n = 0
for _, key in ipairs(KEYS) do
  if redis.call('get', key) == ARGV[1] then
    n = n + redis.call('del', key)
  end
end
return n
"""
# KEYS[1]: lane zset, KEYS[2]: its push-sequence hash, KEYS[3]: opposite lane.
# ARGV: member, score, mode ('gt' newest, 'lt' oldest), ttl seconds, discovery.
# Discovery only creates a missing owner wake; replaying either existing lane
# must not invalidate a taken sequence or pull a persisted retry forward.
# Real notifications always bump the sequence, even if the score is unchanged,
# so an older take cannot erase new work. Plain ZADD GT/LT needs Redis 6.2.
_PUSH_LUA = """
local current = redis.call('zscore', KEYS[1], ARGV[1])
if ARGV[5] == '1' and (current or redis.call('zscore', KEYS[3], ARGV[1])) then
  return 0
end
local score = tonumber(ARGV[2])
if not current
  or (ARGV[3] == 'gt' and score > tonumber(current))
  or (ARGV[3] == 'lt' and score < tonumber(current)) then
  redis.call('zadd', KEYS[1], score, ARGV[1])
end
local seq = redis.call('hincrby', KEYS[2], ARGV[1], 1)
redis.call('expire', KEYS[1], ARGV[4])
redis.call('expire', KEYS[2], ARGV[4])
return seq
"""
# KEYS[1]: lane zset, KEYS[2]: sequence hash. ARGV: order, limit, due-at cutoff.
# Returns due member, score, sequence triples without mutating future wakes.
_TAKE_LUA = """
local page
if ARGV[1] == 'desc' then
  page = redis.call('zrevrangebyscore', KEYS[1], ARGV[3], '-inf', 'WITHSCORES', 'LIMIT', 0, ARGV[2])
else
  page = redis.call('zrangebyscore', KEYS[1], '-inf', ARGV[3], 'WITHSCORES', 'LIMIT', 0, ARGV[2])
end
local out = {}
for i = 1, #page, 2 do
  out[#out + 1] = page[i]
  out[#out + 1] = page[i + 1]
  out[#out + 1] = redis.call('hget', KEYS[2], page[i]) or '0'
end
return out
"""
# Removes a wake only when no push landed since it was taken. The sequence
# itself stays (it expires with the lane): resetting it would let a stale take
# of the same owner match a later push's number and settle that push away.
_SETTLE_LUA = """
local seq = redis.call('hget', KEYS[2], ARGV[1]) or '0'
if seq == ARGV[2] then
  return redis.call('zrem', KEYS[1], ARGV[1])
end
return 0
"""


# Moves a cooled wake behind every wake that is due sooner. KEYS[1]/KEYS[2]:
# the source lane zset and sequence hash, KEYS[3]/KEYS[4]: the backlog lane's.
# ARGV: member, the sequence taken, retry score, ttl seconds. A push that
# landed since the take keeps the wake where it is (it is new work). Backlog
# keeps the earlier score when the member already waits there.
_DEFER_LUA = """
local seq = redis.call('hget', KEYS[2], ARGV[1]) or '0'
if seq ~= ARGV[2] then
  return 0
end
local score = tonumber(ARGV[3])
if KEYS[1] == KEYS[3] then
  redis.call('zadd', KEYS[3], score, ARGV[1])
else
  redis.call('zrem', KEYS[1], ARGV[1])
  local current = redis.call('zscore', KEYS[3], ARGV[1])
  if not current or score < tonumber(current) then
    redis.call('zadd', KEYS[3], score, ARGV[1])
  end
end
redis.call('hincrby', KEYS[4], ARGV[1], 1)
redis.call('expire', KEYS[3], ARGV[4])
redis.call('expire', KEYS[4], ARGV[4])
return 1
"""


@lru_cache(maxsize=1)
def _redis_client():
    # Bounded socket I/O: an advisory coordinator must fail open promptly.
    return redis_db.create_bounded_redis_client(REDIS_TIMEOUT_SECONDS)


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def shard_of(owner_key: str, count: int) -> int:
    """Stable shard of a hashed owner key (hex sha256, see scheduler.owner_key)."""
    return int(owner_key[:12], 16) % count


def share(count: int, members: int) -> int:
    """Shards one member should hold so that the members cover every shard."""
    return math.ceil(count / max(1, members))


class Wake:
    __slots__ = ('owner_id', 'lane', 'shard', 'score', 'seq')

    def __init__(self, owner_id: str, lane: str, shard: int, score: float, seq: str = '0'):
        self.owner_id, self.lane, self.shard, self.score, self.seq = owner_id, lane, shard, score, seq

    def __repr__(self) -> str:  # never logged with ids; tests only
        return f'Wake(lane={self.lane}, shard={self.shard})'


class ProjectionShards:
    """Process-local view of shard leases plus the per-shard wake lanes."""

    def __init__(
        self,
        namespace: str,
        *,
        count: int,
        member: bool = True,
        client: Callable[[], Any] = _redis_client,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        holder: str | None = None,
    ):
        if count < 1:
            raise ValueError('at least one projection shard required')
        self.namespace = namespace
        self.count = count
        self.member = member
        self._client = client
        self.clock = clock
        self.monotonic = monotonic
        # Random per-process identity; no pod, host or user data.
        self.holder = holder or uuid.uuid4().hex
        self.held: set[int] = set()
        # Shards no member held at the last lease pass; their owners drain
        # wherever they are discovered (the legacy behavior).
        self.unheld: set[int] = set(range(count))
        self.members = 0
        # False until a lease pass succeeds, and after any Redis error: the
        # caller then runs the legacy sweep on this instance.
        self.healthy = False
        self.refreshed_at: float | None = None
        self._lock = threading.Lock()

    # Keys -----------------------------------------------------------------

    def _lease_key(self, shard: int) -> str:
        return f'batch_projection_shard:{self.namespace}:{self.count}:{shard}'

    def _members_key(self) -> str:
        return f'batch_projection_shard_members:{self.namespace}:{self.count}'

    def _lane_key(self, lane: str, shard: int) -> str:
        return f'batch_projection_wake:{self.namespace}:{self.count}:{lane}:{shard}'

    def shard(self, owner_key: str) -> int:
        return shard_of(owner_key, self.count)

    @property
    def active(self) -> bool:
        """Sharded serving applies on this instance: Redis answered recently."""
        if not self.healthy or self.refreshed_at is None:
            return False
        return self.monotonic() - self.refreshed_at < LEASE_SECONDS

    def owns(self, owner_key: str) -> bool:
        return self.shard(owner_key) in self.held

    def covered(self, owner_key: str) -> bool:
        """Some member held this owner's shard at the last lease pass."""
        return self.shard(owner_key) not in self.unheld

    # Leases ---------------------------------------------------------------

    def refresh_due(self) -> bool:
        return self.refreshed_at is None or self.monotonic() - self.refreshed_at >= LEASE_REFRESH_SECONDS

    def refresh(self) -> bool:
        """One lease pass: heartbeat, renew, rebalance, acquire. Fails open."""
        with self._lock:
            try:
                self._refresh()
            except Exception as error:
                self.healthy = False
                self.held = set()
                self.unheld = set(range(self.count))
                logger.warning(
                    'event=batch_projection_shards action=refresh outcome=unavailable exception_type=%s',
                    type(error).__name__,
                )
                return False
            self.healthy = True
            self.refreshed_at = self.monotonic()
            return True

    def _refresh(self) -> None:
        client = self._client()
        now = self.clock()
        keys = [self._lease_key(shard) for shard in range(self.count)]
        ttl_ms = int(LEASE_SECONDS * 1000)
        pipe = client.pipeline(transaction=False)
        if self.member:
            pipe.zadd(self._members_key(), {self.holder: now})
            pipe.expire(self._members_key(), int(LEASE_SECONDS * 4))
        pipe.zremrangebyscore(self._members_key(), 0, now - LEASE_SECONDS)
        pipe.zcard(self._members_key())
        pipe.mget(keys)
        results = pipe.execute()
        members, values = int(results[-2]), results[-1]
        self.members = members
        holders = [value.decode() if isinstance(value, bytes) else value for value in values]
        mine = {shard for shard, holder in enumerate(holders) if holder == self.holder}
        if not self.member:
            if mine:
                client.eval(_RELEASE_LUA, len(mine), *(keys[s] for s in sorted(mine)), self.holder)
            self.held = set()
            self.unheld = {shard for shard, holder in enumerate(holders) if not holder}
            return
        if mine:
            renewed = client.eval(_RENEW_LUA, len(mine), *(keys[s] for s in sorted(mine)), self.holder, ttl_ms)
            mine = {shard for shard, ok in zip(sorted(mine), renewed) if int(ok)}
        target = share(self.count, members)
        if len(mine) > target:
            # Members joined: hand back the excess so they can take it on their
            # next pass. In-flight drains finish their turn under the claim.
            extra = random.sample(sorted(mine), len(mine) - target)
            client.eval(_RELEASE_LUA, len(extra), *(keys[s] for s in extra), self.holder)
            for shard in extra:
                mine.discard(shard)
                holders[shard] = None
        free = [shard for shard, holder in enumerate(holders) if not holder and shard not in mine]
        random.shuffle(free)
        for shard in free:
            if len(mine) >= target:
                break
            if client.set(keys[shard], self.holder, nx=True, px=ttl_ms):
                mine.add(shard)
                holders[shard] = self.holder
        self.held = mine
        self.unheld = {shard for shard, holder in enumerate(holders) if not holder}

    def release(self) -> None:
        """Hand every held shard back and leave the members set, so others rebalance now.

        Used at shutdown and when a kill switch takes this process off the
        sharded path. Fails open: unreleased leases lapse after LEASE_SECONDS.
        """
        with self._lock:
            held, self.held = sorted(self.held), set()
            self.healthy = False
            self.refreshed_at = None  # Rejoin on the very next lease pass.
            try:
                client = self._client()
                if held:
                    client.eval(_RELEASE_LUA, len(held), *(self._lease_key(s) for s in held), self.holder)
                client.zrem(self._members_key(), self.holder)
            except Exception as error:
                logger.warning(
                    'event=batch_projection_shards action=release outcome=unavailable exception_type=%s',
                    type(error).__name__,
                )

    # Wakes ----------------------------------------------------------------

    def _seq_key(self, lane: str, shard: int) -> str:
        return f'batch_projection_wake_seq:{self.namespace}:{self.count}:{lane}:{shard}'

    def push(self, owner_id: str, owner_key: str, lane: str, score: float, *, discovery: bool = False) -> bool:
        """Record work, or discover an owner absent from both lanes. Fails open (False).

        True includes a discovery replay of an existing wake: its holder still
        owns the work, without changing that wake's ordering or sequence.
        """
        if lane not in LANES:
            raise ValueError('unknown projection wake lane')
        shard = self.shard(owner_key)
        try:
            self._client().eval(
                _PUSH_LUA,
                3,
                self._lane_key(lane, shard),
                self._seq_key(lane, shard),
                self._lane_key(BACKLOG if lane == FRESH else FRESH, shard),
                owner_id,
                float(score),
                'gt' if lane == FRESH else 'lt',
                WAKE_TTL_SECONDS,
                int(discovery),
            )
            return True
        except Exception as error:
            logger.warning(
                'event=batch_projection_shards action=push outcome=unavailable exception_type=%s',
                type(error).__name__,
            )
            return False

    def take(self, lane: str, limit: int, shards: Iterable[int] | None = None) -> list[Wake]:
        """Read (never remove) up to ``limit`` wakes per held shard, best first.

        Only scores at or before the wall clock are due, including after a
        holder restart. Filter before limiting so future wakes cannot hide due
        work. Fresh wakes come newest first; backlog wakes oldest first.
        Shards interleave so one deep shard cannot crowd out the others.
        """
        shards = sorted(self.held if shards is None else shards)
        if not shards or limit <= 0:
            return []
        try:
            due_at = self.clock()
            pipe = self._client().pipeline(transaction=False)
            for shard in shards:
                pipe.eval(
                    _TAKE_LUA,
                    2,
                    self._lane_key(lane, shard),
                    self._seq_key(lane, shard),
                    'desc' if lane == FRESH else 'asc',
                    limit,
                    due_at,
                )
            pages = pipe.execute()
        except Exception as error:
            # Lanes this process cannot read are lanes nobody drains: go
            # inactive so this instance runs the legacy sweep until a lease
            # pass succeeds again.
            self.healthy = False
            logger.warning(
                'event=batch_projection_shards action=take outcome=unavailable exception_type=%s',
                type(error).__name__,
            )
            return []
        columns = []
        for shard, page in zip(shards, pages):
            column = []
            for index in range(0, len(page) - 2, 3):
                member, score, seq = page[index], page[index + 1], page[index + 2]
                column.append(Wake(_text(member), lane, shard, float(_text(score)), _text(seq)))
            columns.append(column)
        merged: list[Wake] = []
        for row in range(limit):
            for column in columns:
                if row < len(column):
                    merged.append(column[row])
        return merged

    def settle(self, wake: Wake) -> bool:
        """Drop a wake whose owner drained to the end, unless it was re-pushed."""
        try:
            return bool(
                self._client().eval(
                    _SETTLE_LUA,
                    2,
                    self._lane_key(wake.lane, wake.shard),
                    self._seq_key(wake.lane, wake.shard),
                    wake.owner_id,
                    wake.seq,
                )
            )
        except Exception as error:
            logger.warning(
                'event=batch_projection_shards action=settle outcome=unavailable exception_type=%s',
                type(error).__name__,
            )
            return False

    def defer(self, wake: Wake, score: float) -> bool:
        """Re-queue a cooled wake in the backlog lane at retry ``score``.

        A stuck owner would otherwise keep its place at the head of its lane,
        and enough of them would fill every take page. Unless a push landed
        since the take, the wake moves behind every owner due sooner. Fails
        open (False): the wake stays where it was.

        When deferring both taken lanes for an owner, defer backlog first:
        moving fresh into backlog increments the backlog sequence.
        """
        try:
            return bool(
                self._client().eval(
                    _DEFER_LUA,
                    4,
                    self._lane_key(wake.lane, wake.shard),
                    self._seq_key(wake.lane, wake.shard),
                    self._lane_key(BACKLOG, wake.shard),
                    self._seq_key(BACKLOG, wake.shard),
                    wake.owner_id,
                    wake.seq,
                    float(score),
                    WAKE_TTL_SECONDS,
                )
            )
        except Exception as error:
            logger.warning(
                'event=batch_projection_shards action=defer outcome=unavailable exception_type=%s',
                type(error).__name__,
            )
            return False

    def depth(self) -> dict[str, int]:
        """Wake count per lane across the shards this process holds (gauge)."""
        out: dict[str, int] = {lane: 0 for lane in LANES}
        shards = sorted(self.held)
        if not shards:
            return out
        try:
            pipe = self._client().pipeline(transaction=False)
            for lane in LANES:
                for shard in shards:
                    pipe.zcard(self._lane_key(lane, shard))
            counts = pipe.execute()
        except Exception:
            return out
        for index, lane in enumerate(LANES):
            out[lane] = sum(int(c) for c in counts[index * len(shards) : (index + 1) * len(shards)])
        return out
