"""Strict, transactional heartbeat authority hosted by the existing serving supervisor.

The advisory maintenance lease is deliberately not used: ownership and the gate
write share a transaction, and any error latches this process off until restart.
"""

import time
import uuid
from threading import Lock

from prometheus_client import Gauge

from config.batch_pipeline import provider_backlog_release_closed, provider_backlog_release_enabled
from config.policy.kill_switches import kill_switch
from config.batch_pipeline_backlog_release import WriterConfig
from utils.batch_pipeline.backlog_release import Gate, TOKENS_USED, WINDOW

LEASE_KEY = 'backlog_heartbeat'
LEASE_SECONDS = 120
TICK_SECONDS = 20
LAST_HEARTBEAT = Gauge('omi_batch_pipeline_backlog_heartbeat_timestamp_seconds', 'Last durable writer heartbeat')


class HeartbeatAuthority:
    def __init__(self, store, *, clock=time.time, config=WriterConfig.from_env):
        self.store, self.clock, self.config = store, clock, config
        self.holder = uuid.uuid4().hex  # Process identity, never an owner identifier.
        self.failed = False
        self.lock = Lock()

    def tick(self) -> bool:
        with self.lock:
            if self.failed:
                return False
            try:
                return self._tick()
            except Exception:
                # Even an ambiguous acknowledgement stops refresh. A replacement must
                # wait for the durable lease; the gate expires independently in 180s.
                self.failed = True
                raise

    def _tick(self) -> bool:
        config = self.config().validate()
        if not config.enabled:
            return False
        if provider_backlog_release_enabled():
            raise ValueError('heartbeat authority cannot run with legacy unmetered release configured')

        def body(tx):
            lease = tx.get_existing('leases', LEASE_KEY)
            row = tx.get_existing('backlog_release', 'gate')
            now = self.clock()  # Resampled on transaction retries.
            if type(now) not in (float, int) or not 0 <= now < float('inf'):
                raise ValueError('invalid heartbeat clock')
            if lease is not None:
                if (
                    set(lease) != {'holder', 'fence', 'expires_at', 'renewed_at'}
                    or not isinstance(lease['holder'], str)
                    or type(lease['fence']) is not int
                    or lease['fence'] < 1
                    or type(lease['expires_at']) not in (int, float)
                    or not 0 <= lease['expires_at'] < float('inf')
                    or type(lease['renewed_at']) not in (int, float)
                    or not 0 <= lease['renewed_at'] <= now
                ):
                    raise ValueError('invalid heartbeat lease or regressing clock')
            gate = Gate.parse(row) if row is not None else None
            if lease is not None and row is None:
                raise ValueError('missing backlog gate after authority initialization')
            if row is not None and gate is None:
                # A malformed count must never be repaired by resetting the budget.
                raise ValueError('invalid existing backlog gate')
            if lease is None and row is not None:
                raise ValueError('missing heartbeat lease after authority initialization')
            if gate and now < gate.updated_at:
                raise ValueError('heartbeat clock regressed')
            if lease is not None and lease['expires_at'] > now and lease['holder'] != self.holder:
                return None
            # An expired lease cannot introduce a second clock within the old
            # heartbeat's validity. Wait a full gate lifetime on takeover.
            if lease is not None and lease['holder'] != self.holder and gate and now - gate.updated_at < 180:
                return None
            window = gate.window if gate else int(now // 3600)
            used = gate.tokens_used if gate else 0
            state = config.state
            if provider_backlog_release_closed() or not kill_switch(
                'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED', log=False
            ):
                state = 'closed'
            new_gate = dict(
                state=state,
                rate_per_hour=config.rate_per_hour,
                reach_seconds=config.reach_seconds,
                window=window,
                tokens_used=used,
                updated_at=now,
                schema_version=2,
                mode=config.mode,
                owner_keys=list(config.owner_keys),
            )
            fence = 1 if lease is None else lease['fence'] + int(lease['holder'] != self.holder)
            tx.put(
                'leases',
                LEASE_KEY,
                dict(holder=self.holder, fence=fence, expires_at=now + LEASE_SECONDS, renewed_at=now),
            )
            tx.put('backlog_release', 'gate', new_gate)
            return new_gate

        row = self.store.run(body)
        if row is None:
            return False
        LAST_HEARTBEAT.set(row['updated_at'])
        TOKENS_USED.set(row['tokens_used'])
        WINDOW.set(row['window'])
        return True
