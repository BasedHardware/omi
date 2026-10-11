"""Bounded reservation evidence in shared Redis or an explicitly local store.

No customer data, ADC, or network at import time. Missing configuration uses
process-local evidence; a configured Redis outage fails open, never replaying
cached negative state. Both storage modes use the same strict reducer.
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
from prometheus_client import Counter
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
from utils.executors import start_background_task
from utils.llm.vertex_reservation_response import completed_provisioned_traffic
from utils.llm.vertex_pt_routing import COMPANY_PAID_VERTEX_TEXT_MODELS

logger = logging.getLogger(__name__)
Probe = Callable[[str, str], Awaitable[str]]
UNKNOWN_SHARED_ALERT_SECONDS = 6 * 3600
UNKNOWN_SHARED_ALERT_REPEAT_SECONDS = 3600
UNKNOWN_SHARED_REQUESTS = Counter(
    'omi_vertex_reservation_unknown_shared_total',
    'Shared requests while a declared reservation with shared unknown policy is unresolved',
    ['model'],
)


class ReservationState:
    def __init__(self, client: Any = None) -> None:
        self._client = client
        self._owns_client = client is None
        self._snapshot: dict[str, State] = {}
        self._snapshot_at = 0.0
        self._snapshot_key = ''
        self._positive: dict[str, float] = {}
        self._pending_success: dict[str, float] = {}
        self._local_doc: dict[str, Any] = {}
        self._unknown_shared_since: dict[str, float] = {}
        self._unknown_warned_at: dict[str, float] = {}
        self._local_logged = False
        self._scope_key = self.key()
        self._probe_tasks: set[asyncio.Task[Any]] = set()

    def client(self) -> Any:
        if self._client is None:
            host = os.getenv('REDIS_DB_HOST', '').strip()
            if not host:
                if not self._local_logged:
                    logger.warning('vertex_reservation_storage mode=process_local reason=not_configured')
                    self._local_logged = True
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
        addresses = [
            (m, s.order, os.getenv(s.location_env, s.location) if s.location_env else s.location)
            for m, s in sorted(RESERVATIONS.items())
        ]
        revision = hashlib.sha256(json.dumps(addresses).encode()).hexdigest()[:16]
        return 'vertex-reservations:v1:' + os.getenv('GOOGLE_CLOUD_PROJECT', '') + ':' + revision

    def _check_scope(self) -> None:
        key = self.key()
        if key != self._scope_key:
            self._scope_key = key
            self._snapshot = {}
            self._positive.clear()
            self._pending_success.clear()
            self._local_doc = {}
            self._unknown_shared_since.clear()
            self._unknown_warned_at.clear()

    def note_request(self, model: str, capacity: str, state: State) -> None:
        """Bounded warning on actual shared dispatch after six hours unknown.

        The first-request timestamp is carried into the next evidence transaction;
        reads merge its earliest value across replicas. No request content/identity.
        """
        self._check_scope()
        spec = RESERVATIONS.get(model)
        if spec is None or spec.unknown_capacity != 'shared':
            return
        if state != State.UNKNOWN:
            self._unknown_shared_since.pop(model, None)
            self._unknown_warned_at.pop(model, None)
            return
        if capacity != 'shared':
            return
        UNKNOWN_SHARED_REQUESTS.labels(model).inc()
        now = time.time()
        since = self._unknown_shared_since.setdefault(model, now)
        if (
            now - since >= UNKNOWN_SHARED_ALERT_SECONDS
            and now - self._unknown_warned_at.get(model, 0) >= UNKNOWN_SHARED_ALERT_REPEAT_SECONDS
        ):
            self._unknown_warned_at[model] = now
            logger.warning(
                'vertex_reservation_discovery_overdue model=%s state=unknown capacity=shared '
                'first_requested_at=%d elapsed_seconds=%d threshold_seconds=%d',
                model,
                since,
                now - since,
                UNKNOWN_SHARED_ALERT_SECONDS,
            )

    def _advance(
        self,
        doc: dict[str, Any],
        now: float,
        model: str,
        outcome: str,
        claim: bool,
        pending: dict[str, float],
    ) -> tuple[dict[str, Any], dict[str, tuple[State, str]], str | None]:
        evidence = {m: Evidence(**doc.get('evidence', {}).get(m, {})) for m in RESERVATIONS}
        for m, at in pending.items():
            # A failed publication is retried, but cannot erase a newer remote
            # success or a failure window that began after this local success.
            own = evidence[m]
            if 0 <= now - at <= ACTIVE_FRESH_SECONDS and at > max(own.success_at, own.failure_start):
                evidence[m] = observe(own, now=at, outcome='dedicated_success')
        if model in RESERVATIONS and outcome:
            evidence[model] = observe(evidence[model], now=now, outcome=outcome)
        states = {m: observed_state(m, evidence, now=now) for m in RESERVATIONS}
        leases = {m: at for m, at in doc.get('leases', {}).items() if m in RESERVATIONS}
        selected = None
        if claim:
            for m in RESERVATIONS:
                if m in discovery_models(os.environ) and now >= leases.get(m, 0):
                    selected = m
                    leases[m] = now + PROBE_SECONDS
                    break
        unknown_since = {}
        for m, spec in RESERVATIONS.items():
            if states[m][0] == State.UNKNOWN and spec.unknown_capacity == 'shared':
                starts = [
                    v
                    for v in (doc.get('unknown_shared_since', {}).get(m), self._unknown_shared_since.get(m))
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= now
                ]
                if starts:
                    unknown_since[m] = min(starts)
        new = {
            'evidence': {m: asdict(e) for m, e in evidence.items()},
            'states': {m: state.value for m, (state, _) in states.items()},
            'leases': leases,
            'unknown_shared_since': unknown_since,
        }
        return new, states, selected

    def _committed(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        states: dict[str, tuple[State, str]],
        now: float,
        pending: dict[str, float],
        storage: str,
    ) -> None:
        for m, at in pending.items():
            if self._pending_success.get(m) == at:
                self._pending_success.pop(m, None)
        # Requests can arrive during an awaited Redis transaction. Preserve their
        # first-request timestamp unless evidence has resolved the uncertainty.
        for m, (state, _) in states.items():
            if state != State.UNKNOWN:
                self._unknown_shared_since.pop(m, None)
                self._unknown_warned_at.pop(m, None)
            elif m in after['unknown_shared_since']:
                at = after['unknown_shared_since'][m]
                self._unknown_shared_since[m] = min(at, self._unknown_shared_since.get(m, at))
        for m, (state, reason) in states.items():
            if before.get('states', {}).get(m, 'unknown') != state.value:
                own = after['evidence'][m]
                successor_success = max(
                    (
                        after['evidence'][other]['success_at']
                        for other, spec in RESERVATIONS.items()
                        if other != m and spec.order == RESERVATIONS[m].order
                    ),
                    default=0,
                )
                logger.log(
                    logging.WARNING if state == State.INACTIVE else logging.INFO,
                    'vertex_reservation_transition model=%s state=%s reason=%s storage=%s at=%d '
                    'failure_count=%d failure_start=%d failure_at=%d success_at=%d successor_success_at=%d',
                    m,
                    state.value,
                    reason,
                    storage,
                    now,
                    own['failure_count'],
                    own['failure_start'],
                    own['failure_at'],
                    own['success_at'],
                    successor_success,
                )

    async def transact(
        self, model: str = '', outcome: str = '', *, claim: bool = False
    ) -> tuple[dict[str, State], str | None]:
        self._check_scope()
        if model in RESERVATIONS and outcome == 'dedicated_success':
            self._positive[model] = time.monotonic()
            self._pending_success[model] = time.time()
        pending = dict(self._pending_success)
        failure_reason = 'timeout'
        try:
            client = self.client()
            if client is None:
                now = time.time()
                before = self._local_doc
                new, states, selected = self._advance(before, now, model, outcome, claim, pending)
                self._local_doc = new
                self._committed(before, new, states, now, pending, 'process_local')
                return {m: s for m, (s, _) in states.items()}, selected
            async with asyncio.timeout(0.3):
                for _ in range(3):
                    async with client.pipeline(transaction=True) as pipe:
                        try:
                            await pipe.watch(self.key())
                            raw = await pipe.get(self.key())
                            doc = json.loads(raw) if raw else {}
                            seconds, micros = await pipe.time()
                            now = seconds + micros / 1_000_000
                            new, states, selected = self._advance(doc, now, model, outcome, claim, pending)
                            if new == doc:
                                await pipe.unwatch()
                            else:
                                pipe.multi()
                                pipe.set(self.key(), json.dumps(new), ex=172800)
                                await pipe.execute()
                            self._committed(doc, new, states, now, pending, 'redis')
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
        self._check_scope()
        key = self.key()
        if self._snapshot and self._snapshot_key == key and 0 <= time.monotonic() - self._snapshot_at < 1:
            states = self._snapshot
        else:
            states = {}
            try:
                async with asyncio.timeout(max(0, timeout_seconds)):
                    states, selected = await self.transact(claim=probe is not None)
                    if selected and probe:
                        task = start_background_task(
                            self._run_probe(selected, probe, key), name='vertex-reservation-probe'
                        )
                        self._probe_tasks.add(task)
                        task.add_done_callback(self._probe_tasks.discard)
            except TimeoutError:
                record_fallback(
                    component='vertex_reservations',
                    from_mode='redis',
                    to_mode='none',
                    reason='timeout',
                    outcome='degraded',
                )
                logger.warning('vertex_reservation_refresh_budget_exhausted state=unknown')
            self._snapshot = states if states and State.INACTIVE not in states.values() else {}
            self._snapshot_at = time.monotonic()
            self._snapshot_key = key
        local = {
            m: State.ACTIVE for m, at in self._positive.items() if 0 <= time.monotonic() - at <= ACTIVE_FRESH_SECONDS
        }
        raw = {}
        for m in RESERVATIONS:
            state = states.get(m, State.UNKNOWN)
            # Merge per model; a stale nonempty Redis map must not hide a local
            # success whose write failed. Newer confirmed inactivity still wins.
            raw[m] = local.get(m, state) if state == State.UNKNOWN else state
        return effective_states(raw, os.environ) if apply_overrides else raw

    async def _run_probe(self, model: str, probe: Probe, key: str) -> None:
        if model not in discovery_models(os.environ) or key != self.key():
            return
        spec = RESERVATIONS[model]
        location = os.getenv(spec.location_env, spec.location) if spec.location_env else spec.location
        try:
            async with asyncio.timeout(30):
                outcome = await probe(model, location)
        except Exception:
            outcome = 'inconclusive'
        if model in discovery_models(os.environ) and key == self.key():
            await self.transact(model, outcome)
            self._snapshot = {}

    async def aclose(self) -> None:
        for task in self._probe_tasks:
            task.cancel()
        if self._probe_tasks:
            await asyncio.gather(*self._probe_tasks, return_exceptions=True)
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._snapshot = {}
        self._positive.clear()
        self._pending_success.clear()
        self._local_doc = {}
        self._unknown_shared_since.clear()
        self._unknown_warned_at.clear()

    async def record(
        self, model: str, capacity: str, status: int, traffic_type: str | None, *, timeout_seconds: float = 0.3
    ) -> None:
        self._check_scope()
        if (
            model in RESERVATIONS
            and capacity == 'dedicated'
            and 200 <= status < 300
            and traffic_type == 'PROVISIONED_THROUGHPUT'
        ):
            self._snapshot = {}
            self._positive[model] = time.monotonic()
            self._pending_success[model] = time.time()
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
        if model not in RESERVATIONS or capacity != 'dedicated':
            return False
        try:
            traffic = completed_provisioned_traffic(response.json())
        except (ValueError, AttributeError):
            return False
        await self.record(model, capacity, response.status_code, traffic)
        return 200 <= response.status_code < 300 and traffic == 'PROVISIONED_THROUGHPUT'


def discovery_models(env: Mapping[str, str]) -> frozenset[str]:
    """Operator pins suppress automatic discovery; per-model auto is explicit."""
    if env.get('OMI_VERTEX_PT_MODEL', '').strip():
        return frozenset()
    try:
        overrides = json.loads(env.get(STATE_OVERRIDE_ENV, '').strip() or '{}')
        if not isinstance(overrides, dict) or any(
            m not in RESERVATIONS or value not in {'active', 'inactive', 'unknown', 'auto'}
            for m, value in overrides.items()
        ):
            return frozenset()
        return frozenset(m for m in RESERVATIONS if overrides.get(m, 'auto') == 'auto')
    except (ValueError, TypeError):
        return frozenset()


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
