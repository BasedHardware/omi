"""Shared reservation evidence with bounded Redis I/O and injected inference.

No customer data, ADC, or network at import time. Keys are project + declared
order/location scoped. Redis failure means UNKNOWN; it never authorizes refusal.
"""

import asyncio
import json
import hashlib
import logging
import os
import time
from dataclasses import asdict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import WatchError

from config.vertex_reservations import (
    ACTIVE_FRESH_SECONDS,
    RESERVATIONS,
    Evidence,
    State,
    STATE_OVERRIDE_ENV,
    PROBE_SECONDS,
    observe,
    observed_state,
)
from utils.observability.fallback import record_fallback
from utils.llm.vertex_pt_routing import COMPANY_PAID_VERTEX_TEXT_MODELS

logger = logging.getLogger(__name__)
Probe = Callable[[str, str], Awaitable[str]]


class ReservationState:
    def __init__(self, client: Any = None) -> None:
        self._client = client
        self._positive: dict[str, float] = {}

    def client(self) -> Any:
        if self._client is None:
            host = os.getenv('REDIS_DB_HOST', '').strip()
            if not host:
                return None
            self._client = Redis(
                host=host,
                port=int(os.getenv('REDIS_DB_PORT', '6379')),
                password=os.getenv('REDIS_DB_PASSWORD'),
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                decode_responses=True,
            )
        return self._client

    @staticmethod
    def key() -> str:
        # An endpoint reconfiguration must not inherit evidence from another order address.
        addresses = [
            (m, s.order, os.getenv(s.location_env, s.location) if s.location_env else s.location)
            for m, s in sorted(RESERVATIONS.items())
        ]
        revision = hashlib.sha256(json.dumps(addresses).encode()).hexdigest()[:16]
        return 'vertex-reservations:v1:' + os.getenv('GOOGLE_CLOUD_PROJECT', '') + ':' + revision

    async def transact(
        self, model: str = '', outcome: str = '', *, claim: bool = False
    ) -> tuple[dict[str, State], str | None]:
        try:
            client = self.client()
            if client is None:
                return {}, None
            async with asyncio.timeout(0.3):
                for _ in range(3):
                    async with client.pipeline(transaction=True) as pipe:
                        try:
                            await pipe.watch(self.key())
                            raw = await pipe.get(self.key())
                            doc = json.loads(raw) if raw else {}
                            seconds, micros = await pipe.time()
                            now = seconds + micros / 1_000_000
                            evidence = {m: Evidence(**doc.get('evidence', {}).get(m, {})) for m in RESERVATIONS}
                            if model in RESERVATIONS and outcome:
                                evidence[model] = observe(evidence[model], now=now, outcome=outcome)
                            states = {m: observed_state(m, evidence, now=now) for m in RESERVATIONS}
                            leases = doc.get('leases', {})
                            selected = None
                            if claim:
                                for m in RESERVATIONS:
                                    if now >= leases.get(m, 0):
                                        selected = m
                                        leases[m] = now + PROBE_SECONDS
                                        break
                            new = {
                                'evidence': {m: asdict(e) for m, e in evidence.items()},
                                'states': {m: state.value for m, (state, _) in states.items()},
                                'leases': leases,
                            }
                            pipe.multi()
                            pipe.set(self.key(), json.dumps(new), ex=172800)
                            await pipe.execute()
                            for m, (state, reason) in states.items():
                                if doc.get('states', {}).get(m, 'unknown') != state.value:
                                    logger.info(
                                        'vertex_reservation_transition model=%s state=%s reason=%s at=%d',
                                        m,
                                        state.value,
                                        reason,
                                        now,
                                    )
                            return {m: s for m, (s, _) in states.items()}, selected
                        except WatchError:
                            continue
        except Exception:
            pass
        record_fallback(
            component='llm_gateway', from_mode='redis', to_mode='none', reason='state_unavailable', outcome='degraded'
        )
        logger.warning('vertex_reservation_store_unavailable state=unknown')
        return {}, None

    async def refresh(self, probe: Probe | None = None) -> dict[str, State]:
        states, selected = await self.transact(claim=probe is not None)
        if selected and probe:
            spec = RESERVATIONS[selected]
            location = os.getenv(spec.location_env, spec.location) if spec.location_env else spec.location
            try:
                async with asyncio.timeout(1):
                    outcome = await probe(selected, location)
            except Exception:
                outcome = 'inconclusive'
            states, _ = await self.transact(selected, outcome)
        local = {
            m: State.ACTIVE for m, at in self._positive.items() if 0 <= time.monotonic() - at <= ACTIVE_FRESH_SECONDS
        }
        return effective_states(states or local, os.environ)

    async def record(self, model: str, capacity: str, status: int, traffic_type: str | None) -> None:
        if (
            model in RESERVATIONS
            and capacity == 'dedicated'
            and 200 <= status < 300
            and traffic_type == 'PROVISIONED_THROUGHPUT'
        ):
            self._positive[model] = time.monotonic()
            await self.transact(model, 'dedicated_success')


def effective_states(observed: Mapping[str, State], env: Mapping[str, str]) -> dict[str, State]:
    states = {m: observed.get(m, State.UNKNOWN) for m in RESERVATIONS}
    # Retain the existing single-order operator pin; per-model overrides win.
    pin = env.get('OMI_VERTEX_PT_MODEL', '').strip()
    # Invalid pins are rejected by routing; they cannot fabricate absence at
    # the earlier admission boundary.
    if pin in COMPANY_PAID_VERTEX_TEXT_MODELS:
        states = {m: State.ACTIVE if m == pin else State.INACTIVE for m in RESERVATIONS}
    raw = env.get(STATE_OVERRIDE_ENV, '').strip()
    if raw:
        try:
            overrides = json.loads(raw)
            if not isinstance(overrides, dict) or any(
                m not in RESERVATIONS or s not in {'active', 'inactive', 'unknown', 'auto'}
                for m, s in overrides.items()
            ):
                raise ValueError('invalid overrides')
            for m, s in overrides.items():
                states[m] = observed.get(m, State.UNKNOWN) if s == 'auto' else State(s)
        except (TypeError, ValueError):
            # Malformed emergency configuration cannot turn features off.
            logger.error('vertex_reservation_override_invalid state=unknown')
            return {m: State.UNKNOWN for m in RESERVATIONS}
    return states


reservation_state = ReservationState()
