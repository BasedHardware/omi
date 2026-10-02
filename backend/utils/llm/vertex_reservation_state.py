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

import httpx

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
        self._owns_client = client is None
        self._snapshot: dict[str, State] = {}
        self._snapshot_at = 0.0
        self._snapshot_key = ""
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
        failure_reason = 'timeout'
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
                            leases = dict(doc.get('leases', {}))
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
                            if not outcome and selected is None and new == doc:
                                await pipe.unwatch()
                                return {m: s for m, (s, _) in states.items()}, None
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
        except (ValueError, TypeError, AttributeError):
            failure_reason = 'malformed_doc'
        except TimeoutError:
            pass
        except Exception:
            failure_reason = 'connection_lost'
        record_fallback(
            component='vertex_reservations',
            from_mode='redis',
            to_mode='none',
            reason=failure_reason,
            outcome='degraded',
        )
        logger.warning('vertex_reservation_store_unavailable state=unknown reason=%s', failure_reason)
        return {}, None

    async def refresh(
        self, probe: Probe | None = None, *, timeout_seconds: float = 1.6, apply_overrides: bool = True
    ) -> dict[str, State]:
        key = self.key()
        if self._snapshot and self._snapshot_key == key and 0 <= time.monotonic() - self._snapshot_at < 1:
            states = self._snapshot
        else:
            states = {}
            try:
                async with asyncio.timeout(max(0, timeout_seconds)):
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
            except TimeoutError:
                states = {}
                record_fallback(
                    component='vertex_reservations',
                    from_mode='redis',
                    to_mode='none',
                    reason='timeout',
                    outcome='degraded',
                )
                logger.warning('vertex_reservation_refresh_budget_exhausted state=unknown')
            # Never cache a refusal-capable snapshot: outage/recovery must be
            # checked on every request. Positive/unknown snapshots may lag 1s.
            self._snapshot = states if states and State.INACTIVE not in states.values() else {}
            self._snapshot_at = time.monotonic()
            self._snapshot_key = key
        local = {
            m: State.ACTIVE for m, at in self._positive.items() if 0 <= time.monotonic() - at <= ACTIVE_FRESH_SECONDS
        }
        raw = {m: (states or local).get(m, State.UNKNOWN) for m in RESERVATIONS}
        return effective_states(raw, os.environ) if apply_overrides else raw

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._snapshot = {}
        self._positive.clear()

    async def record(
        self, model: str, capacity: str, status: int, traffic_type: str | None, *, timeout_seconds: float = 0.3
    ) -> None:
        if (
            model in RESERVATIONS
            and capacity == 'dedicated'
            and 200 <= status < 300
            and traffic_type == 'PROVISIONED_THROUGHPUT'
        ):
            self._snapshot = {}
            self._positive[model] = time.monotonic()
            if timeout_seconds <= 0:
                return
            try:
                async with asyncio.timeout(min(0.3, timeout_seconds)):
                    await self.transact(model, 'dedicated_success')
            except TimeoutError:
                record_fallback(
                    component='vertex_reservations',
                    from_mode='redis',
                    to_mode='none',
                    reason='timeout',
                    outcome='degraded',
                )
                logger.warning('vertex_reservation_publish_budget_exhausted state=local_positive')

    async def record_response(self, model: str, capacity: str, response: httpx.Response) -> bool:
        """Only positive metadata on a dedicated response updates shared evidence."""
        if model not in RESERVATIONS or capacity != 'dedicated':
            return False
        try:
            traffic = response.json().get('usageMetadata', {}).get('trafficType')
        except (ValueError, AttributeError):
            return False
        await self.record(model, capacity, response.status_code, traffic)
        return 200 <= response.status_code < 300 and traffic == 'PROVISIONED_THROUGHPUT'


def effective_states(
    observed: Mapping[str, State], env: Mapping[str, str], *, admission: bool = False
) -> dict[str, State]:
    states = {m: observed.get(m, State.UNKNOWN) for m in RESERVATIONS}
    # Retain the existing single-order operator pin; per-model overrides win.
    pin = env.get('OMI_VERTEX_PT_MODEL', '').strip()
    # Invalid pins are rejected by routing; they cannot fabricate absence at
    # the earlier admission boundary. Non-reservation pins only affect routing;
    # they cannot manufacture evidence for feature refusal.
    if pin in (RESERVATIONS if admission else COMPANY_PAID_VERTEX_TEXT_MODELS):
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
