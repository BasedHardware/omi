"""Hermetic outage drills for batch vendor routing: fake vendors, fake GPU capacity, no network.

A drill world runs the real batch code on ``SimStore`` under a discrete drill clock:

* admission: ``route_selection.select_route`` over a served route table, then
  ``batch_pipeline_intake.admit`` (GPU ring or the provider-STT enqueue hook);
* vendor health: slice C's ``VendorHealthService`` on in-memory stores (breaker, caps, probes);
* provider stage: ``ProviderSttStage`` calling the real Velma and Soniox async clients, whose
  HTTP goes to scripted fake vendor servers through ``httpx.MockTransport``;
* GPU: real ``Scheduler`` leases pulled by fake workers that can be evicted or stocked out;
* merge: real ``OrderedMerge`` (bounded head wait as shipped).

The provider-stt queue is modelled as Cloud Tasks: one outbox row per unit, a concurrency and a
dispatch-rate cap, deferrals honoured, and redelivery after the dispatch deadline when the worker
dies mid-call. Every vendor POST is recorded with the unit it carried and whether the vendor
would bill it, so invariants are checked against what the fake vendors saw, not what the stage
believes. Nothing leaves the process: no keys, no network, no cloud credentials.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field, replace
import heapq
import itertools
import json
from typing import Callable
import uuid

import httpx

from config.policy.batch import resolve_batch_policy
from database import batch_pipeline_intake
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline import provider_stt, route_selection
from utils.batch_pipeline import vendor_health as health_module
from utils.batch_pipeline import vendor_route_metrics as vendor_metrics
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_stt import PENDING, RUNNING, ProviderSttStage, UnitOutcome
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.vendor_route_contracts import VENDOR_HELD

EPOCH = 1_800_000_000.0  # drill t=0, a fixed UTC instant (never the wall clock)
MODULATE_HOST = 'modulate-developer-apis.com'
SONIOX_HOST = 'api.soniox.com'
TERMINAL_STATES = frozenset({'committed', 'quarantined', 'privacy_blocked', 'provider_superseded', 'dead'})
OPEN_STATES = frozenset({PENDING, RUNNING, VENDOR_HELD, 'ready', 'leased', 'retry', 'result_ready'})
# What the vendor bills. A 429 or a funds/auth refusal processed nothing; everything else that
# reached the paid endpoint (2xx, 5xx, a hung request, a truncated body) is counted as billed,
# the same conservative reading as vendor_route_contracts.UNBILLED_OUTCOMES.
UNBILLED_MODES = frozenset({'429', '402'})


def route_table(
    *,
    soniox: bool = True,
    selection: str = 'ordered',
    gpu_first: bool = True,
    modulate_daily_hours: float | None = None,
    soniox_daily_hours: float | None = None,
    gpu_floor_percent: float = 0.0,
) -> dict:
    """A served route table: Modulate primary for languages Parakeet cannot serve, Soniox as
    failover-only capacity, GPU first (or Modulate first) for supported languages."""

    def config(*, cap=None, failover_only=False, price=None):
        return {
            'price_usd_per_audio_hour': price,
            'daily_audio_hours_cap': cap,
            'monthly_budget_usd': None,
            'failover_only': failover_only,
            'speaker_turns': 'discard',
        }

    def option(route):
        return {'route': route, 'quality_tier': 'accepted', 'quality_source': 'staging_ladder'}

    vendors = ['modulate'] + (['soniox'] if soniox else [])
    supported = ['gpu', *vendors] if gpu_first else ['modulate', 'gpu', *vendors[1:]]
    priced = selection == 'cheapest'
    return {
        'schema_version': 1,
        'table_version': 'drill-1',
        'selection': selection,
        'gpu_floor_percent': gpu_floor_percent,
        'routes': {
            'gpu': config(price=0.04 if priced else None),
            'modulate': config(cap=modulate_daily_hours, price=0.03 if priced else None),
            'soniox': config(cap=soniox_daily_hours, failover_only=True, price=0.10 if priced else None),
        },
        'rows': [
            {'language_class': 'gpu_unsupported', 'options': [option(route) for route in vendors]},
            {'language_class': '*', 'options': [option(route) for route in supported]},
        ],
    }


@dataclass
class VendorScript:
    """A fake vendor's behaviour over drill time: ``(start, end, mode)`` windows, else ``ok``.

    Modes: ok, 5xx, 429, 402 (credits exhausted), hang (request times out), garbage (2xx with a
    truncated body), empty (2xx, no words), partial (2xx, only the first word of the speech),
    slow (ok after ``slow_seconds``).
    """

    windows: list[tuple[float, float, str]] = field(default_factory=list)
    latency: float = 4.0
    slow_seconds: float = 150.0

    def mode(self, elapsed: float) -> str:
        for start, end, mode in self.windows:
            if start <= elapsed < end:
                return mode
        return 'ok'

    @classmethod
    def flapping(cls, start: float, end: float, period: float, mode: str = '5xx') -> 'VendorScript':
        windows, t, down = [], start, True
        while t < end:
            if down:
                windows.append((t, min(end, t + period), mode))
            t, down = t + period, not down
        return cls(windows)


@dataclass(frozen=True)
class Unit:
    segment_id: str
    owner_id: str
    language: str
    capture_at: float
    duration: float
    admitted_at: float
    route: str  # gpu | modulate | soniox (admission selection)


@dataclass
class VendorPost:
    """One request a fake vendor saw on its paid endpoint."""

    at: float
    service: str
    segment_id: str
    mode: str
    billed: bool
    privacy_ok: bool


class _Clock:
    def __init__(self):
        self.now = EPOCH

    def time(self) -> float:
        return self.now

    def elapsed(self) -> float:
        return self.now - EPOCH


class DrillArtifacts:
    """Custody audio and encrypted results. Audio is only ever read; deletes are recorded."""

    def __init__(self):
        self.audio: dict[str, bytes] = {}
        self.results: dict[str, dict] = {}
        self.writes: Counter = Counter()  # segment -> result objects persisted
        self.deleted_audio: list[str] = []

    def fetch_audio(self, item):
        return self.audio[item.segment_id]

    def persist_recovery_result(self, item, payload, token):
        uri = f'gs://drill/results/{item.segment_id}/{token}.enc'
        self.results[uri] = payload
        self.writes[item.segment_id] += 1
        return uri

    def find_recovery_result(self, item, token):
        uri = f'gs://drill/results/{item.segment_id}/{token}.enc'
        return uri if uri in self.results else None

    def load_result(self, item, uri):
        return self.results[uri]


class _Outbox:
    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, tx=None, now):
        from database.outbox import EnqueueResult

        return EnqueueResult(dedupe_key, False, f'wake-{dedupe_key}')


class DrillWorld:
    """One drill. Build it, script vendors, GPU and actions, ``run`` it, then read invariants."""

    def __init__(
        self,
        monkeypatch,
        *,
        table: dict | None = None,
        modulate: VendorScript | None = None,
        soniox: VendorScript | None = None,
        gpu_workers: int = 4,
        gpu_seconds_per_audio_second: float = 0.05,
        queue_concurrency: int = 48,
        queue_rate: float = 10.0,
        armed: bool = True,
        seed: int = 7,
    ):
        self.monkeypatch = monkeypatch
        self.clock = _Clock()
        self.modulate = modulate or VendorScript()
        self.soniox = soniox or VendorScript()
        self.queue_concurrency, self.queue_rate = queue_concurrency, queue_rate
        self.gpu_seconds_per_audio_second = gpu_seconds_per_audio_second
        self.customer = CustomerData()
        self.store = SimStore(self.customer)
        self.store.customer = self.customer
        self.artifacts = DrillArtifacts()
        self.units: dict[str, Unit] = {}
        self.posts: list[VendorPost] = []
        self.events: list[tuple[float, int, str, tuple]] = []
        self._seq = itertools.count()
        self._ticked_until = 0.0
        self._calling: str | None = None
        self._crash_first = self._duplicate_first = False
        self._crashed: set[str] = set()
        self._duplicated: set[str] = set()
        self.rows: dict[str, dict] = {}  # provider-stt outbox rows by segment
        self.max_in_flight = 0
        self.stale_settles = 0
        self.refused_admissions: list[tuple[str, str]] = []  # (owner, privacy reason)
        self._dispatches: list[float] = []
        self.outcomes: list[tuple[float, str, UnitOutcome]] = []
        self.commits: list[tuple[float, str]] = []
        self.first_commit_result: dict[str, dict] = {}
        self.gpu_workers = gpu_workers
        self.gpu_busy: dict[str, tuple[str, str]] = {}  # worker -> (segment, token)
        self._gpu_generation = 0
        self.gpu_completions = 0
        self.breaker_open_seen: dict[str, float] = {}
        self._env(table if table is not None else route_table(), armed, seed)
        _reset_breaker_gauges()
        self.health = health_module.VendorHealthService(
            shared=health_module.MemoryStore(),
            local=health_module.MemoryStore(),
            routes=lambda: route_selection.current_table()[0].routes,
            enabled=lambda: True,
            clock=self.clock.time,
            rng=_Rng(seed).random,
            background=False,
        )
        monkeypatch.setattr(route_selection, '_health', self.health)
        self.stage = ProviderSttStage(
            self.store,
            self.artifacts,
            stt=self._stt,
            allowed=lambda *_: True,
            inspect=self._inspect,
            clock=self.clock.time,
            health=self.health,
        )
        self.merge = OrderedMerge(self.store)

    # -- environment ------------------------------------------------------------------------------

    def _env(self, table: dict, armed: bool, seed: int) -> None:
        mp = self.monkeypatch
        for name, value in {
            'BATCH_PIPELINE_ENABLED': 'true',
            'BATCH_PIPELINE_PERCENT': '100',
            'BATCH_VENDOR_ROUTING_ENABLED': 'true' if armed else 'false',
            'BATCH_VENDOR_ROUTING_PERCENT': '100',
            'BATCH_VENDOR_ROUTE_TABLE': json.dumps(table),
            'BATCH_VENDOR_HEALTH_ENABLED': 'true',
            # Fake credentials so the real clients build their requests; the transport is fake.
            'MODULATE_API_KEY': 'drill-not-a-key',
            'SONIOX_API_KEY': 'drill-not-a-key',
        }.items():
            mp.setenv(name, value)
        for name in (
            'BATCH_VENDOR_FAILOVER_ENABLED',
            'BATCH_VENDOR_HELD_REDRIVE_ENABLED',
            'BATCH_VENDOR_HELD_REDRIVE_SECONDS',
            'BATCH_VENDOR_HELD_STALE_GRACE_SECONDS',
            'BATCH_VENDOR_HEALTH_THRESHOLDS',
            'BATCH_VENDOR_ROUTING_UID_ALLOWLIST',
            'BATCH_VENDOR_ROUTING_SHADOW_PERCENT',
            'BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS',
        ):
            mp.delenv(name, raising=False)
        from utils.stt import vendor_guard

        vendor_guard.reset_vendor_guard_for_tests()
        mp.setattr(vendor_guard, '_clock', lambda: self.clock.now)
        from utils import http_client

        transport = httpx.MockTransport(self._vendor_http)
        mp.setattr(http_client, 'get_batch_vendor_client', lambda: httpx.AsyncClient(transport=transport))
        mp.setattr(http_client, 'get_batch_vendor_semaphore', lambda: asyncio.Semaphore(64))

    def set_env(self, name: str, value: str | None) -> None:
        if value is None:
            self.monkeypatch.delenv(name, raising=False)
        else:
            self.monkeypatch.setenv(name, value)

    # -- population -------------------------------------------------------------------------------

    def add_owner(self, owner_id: str, *, private_cloud_sync_enabled: bool | None = None) -> None:
        self.customer.add_user(owner_id)
        if private_cloud_sync_enabled is not None:
            self.customer.client.rows[('users', owner_id)]['private_cloud_sync_enabled'] = private_cloud_sync_enabled

    def upload(self, owner_id: str, language: str, at: float, *, duration: float = 30.0, live: bool = False) -> None:
        """Schedule one single-unit upload admitted at drill time ``at`` (captured just before)."""
        self._push(at, 'admit', (owner_id, language, duration, live))

    def at(self, when: float, action: Callable[['DrillWorld'], None]) -> None:
        self._push(when, 'action', (action,))

    def crash_first_calls(self) -> None:
        """From now on, the worker running each unit's first vendor call dies before it settles."""
        self._crash_first = True

    def duplicate_first_deliveries(self) -> None:
        """From now on, Cloud Tasks delivers each unit's first row twice, concurrently."""
        self._duplicate_first = True

    # -- event loop -------------------------------------------------------------------------------

    def _push(self, elapsed: float, kind: str, payload: tuple) -> None:
        heapq.heappush(self.events, (EPOCH + elapsed, next(self._seq), kind, payload))

    def _push_abs(self, when: float, kind: str, payload: tuple) -> None:
        heapq.heappush(self.events, (when, next(self._seq), kind, payload))

    def run(self, horizon: float, *, gpu_tick: float = 5.0, merge_tick: float = 30.0) -> 'DrillWorld':
        """Process events until drill time ``horizon`` (seconds after t=0); callable repeatedly."""
        start = self._ticked_until
        for t in _ticks(start, horizon, gpu_tick):
            self._push(t, 'gpu', ())
        for t in _ticks(start, horizon, merge_tick):
            self._push(t, 'merge_all', ())
        for t in _ticks(start, horizon, 15.0):
            self._push(t, 'observe', ())
        self._ticked_until = max(start, horizon + 1e-6)
        end = EPOCH + horizon
        while self.events and self.events[0][0] <= end:
            when, _, kind, payload = heapq.heappop(self.events)
            self.clock.now = max(self.clock.now, when)
            getattr(self, f'_on_{kind}')(*payload)
        self.clock.now = end
        return self

    def _on_action(self, action):
        action(self)

    def _on_admit(self, owner_id, language, duration, live):
        now = self.clock.now
        index = len(self.units)
        segment_id = f'u{index:04d}'
        content_id = f'c{index:04d}'
        conversation_id = f'conv-{index:04d}'
        self.customer.add_conversation(owner_id, conversation_id)
        if live:
            self.customer.client.rows[('users', owner_id, 'conversations', conversation_id)].update(
                record_lane_owner='batch_live_v1', private_cloud_sync_enabled=True
            )
        decision = route_selection.select_route(
            language, byok=False, uid=owner_id, batch_percent=100.0, vendor_eligible=True
        )
        route = decision.route
        provider = route.stt_route == 'provider'
        policy = replace(
            resolve_batch_policy(owner_id),
            stt_route='provider' if provider else 'parakeet',
            provider_reason=route.provider_reason if provider else 'none',
            provider_service=route.provider_service if provider else 'none',
        )
        item = WorkItem(
            segment_id,
            owner_id,
            now - duration - 1.0,
            f'gs://drill/audio/{segment_id}',
            duration,
            Priority.FRESH,
            conversation_id=conversation_id,
            privacy_generation=0,
        )
        binding = ProjectionBinding(owner_id, f'job-{content_id}', content_id, (segment_id,), language=language)
        self.artifacts.audio[segment_id] = b'drill-audio'
        enqueue = provider_stt.provider_enqueue(route, _Outbox(), {}) if provider else None
        try:
            outcome = batch_pipeline_intake.admit(
                self.store, [item], binding, now, namespace=self.store.namespace, enqueue=enqueue, policy=policy
            )
        except BatchPrivacyBlocked as error:
            # The privacy fence refused custody: no unit, no audio kept, nothing to upload.
            del self.artifacts.audio[segment_id]
            self.refused_admissions.append((owner_id, getattr(error.reason, 'value', str(error.reason))))
            return
        if outcome['outcome'] != 'batch':
            raise AssertionError('drill admission must take the batch path')
        self.units[segment_id] = Unit(segment_id, owner_id, language, item.capture_at, duration, now, decision.selected)
        if provider:
            self._push_abs(now + 2.0, 'deliver', (segment_id,))

    # -- provider-stt queue (Cloud Tasks model) ----------------------------------------------------

    # One outbox row per unit (database/outbox.py): a delivery claims it with a fresh lease token;
    # a wake while a live lease holds the row is BUSY (the watchdog re-wakes it at lease expiry); a
    # settle under a superseded claim is STALE and changes nothing.

    def _on_deliver(self, segment_id):
        now = self.clock.now
        row = self.rows.setdefault(segment_id, {'claim': 0, 'lease_until': 0.0, 'open': True})
        if not row['open']:
            return
        if row['lease_until'] > now:
            self._push_abs(row['lease_until'], 'deliver', (segment_id,))  # BUSY; watchdog keeps custody
            return
        live = sum(1 for r in self.rows.values() if r['open'] and r['lease_until'] > now)
        if live >= self.queue_concurrency:
            self._push_abs(now + 1.0, 'deliver', (segment_id,))
            return
        recent = [t for t in self._dispatches if t > now - 1.0]
        if len(recent) >= self.queue_rate:
            self._push_abs(min(recent) + 1.0, 'deliver', (segment_id,))
            return
        self._dispatches = recent + [now]
        row['claim'] += 1
        row['lease_until'] = now + provider_stt.ProviderSttConsumer.lease_seconds
        self.max_in_flight = max(self.max_in_flight, live + 1)
        # The outbox watchdog re-wakes a row whose claim outlived its lease (a dead or stuck worker).
        self._push_abs(row['lease_until'], 'watchdog', (segment_id, row['claim']))
        if self._duplicate_first and segment_id not in self._duplicated:
            # A delivery outside the outbox fence (mixed-version roll, a manual redrive): it runs
            # the stage concurrently but its claim is already stale for the outbox.
            self._duplicated.add(segment_id)
            self._push_abs(now, 'deliver_unfenced', (segment_id,))
        self._start(segment_id, row['claim'])

    def _on_watchdog(self, segment_id, claim):
        row = self.rows[segment_id]
        if row['open'] and row['claim'] == claim and 0.0 < row['lease_until'] <= self.clock.now:
            self._on_deliver(segment_id)

    def _on_deliver_unfenced(self, segment_id):
        self._start(segment_id, -1)

    def _start(self, segment_id, claim):
        plan = self.stage._guarded(segment_id, self.stage._prepare, segment_id)
        if isinstance(plan, UnitOutcome):
            self._settled(segment_id, claim, plan)
            return
        script = self.modulate if plan.service == 'modulate' else self.soniox
        mode = script.mode(self.clock.elapsed())
        response = self.stage._call_sync(plan)
        latency = _latency(plan.service, mode, script)
        if claim > 0 and self._crash_first and segment_id not in self._crashed:
            # The worker dies mid-call: nothing settles and the claim's lease runs out; the
            # watchdog's redelivery then reconciles the running intent.
            self._crashed.add(segment_id)
            return
        self._push_abs(self.clock.now + latency, 'finish', (segment_id, claim, plan, response, latency))

    def _on_finish(self, segment_id, claim, plan, response, latency):
        outcome = self.stage._guarded(segment_id, self.stage._finish, plan, response, latency)
        self._settled(segment_id, claim, outcome)

    def _settled(self, segment_id, claim, outcome: UnitOutcome):
        now = self.clock.now
        self.outcomes.append((now, segment_id, outcome))
        row = self.rows.get(segment_id)
        if row is not None and row['claim'] == claim:
            row['lease_until'] = 0.0
            if outcome.outcome in {'done', 'discarded'}:
                row['open'] = False
            elif outcome.outcome == 'deferred':
                due = outcome.available_at if outcome.available_at is not None else now
                self._push_abs(max(due, now + 2.0), 'deliver', (segment_id,))
            else:
                self._push_abs(now + provider_stt.RETRY_SECONDS, 'deliver', (segment_id,))
        else:
            self.stale_settles += 1
        self._merge_owner(self.units[segment_id].owner_id)

    # -- vendor seam ------------------------------------------------------------------------------

    def _inspect(self, item, audio):
        # Strict-VAD speech in the middle of the unit (CPU Silero is not run in drills).
        return b'\0\0' * 160, item.duration_seconds, [{'start': 0.5, 'end': min(item.duration_seconds, 4.0)}]

    def _stt(self, item, language, inspected, *, service):
        self._calling = item.segment_id
        try:
            return provider_stt.transcribe(item, language, inspected, service=service)
        finally:
            self._calling = None

    def _privacy_ok(self, segment_id: str) -> bool:
        job = self.store.get('jobs', segment_id)
        binding = job.get('projection_binding') or {}
        return not self.customer.blocked(
            job['owner_id'], [job.get('conversation_id')], binding.get('privacy_generation')
        )

    def _post(self, service: str, mode: str) -> None:
        segment_id = self._calling or '?'
        self.posts.append(
            VendorPost(
                self.clock.now, service, segment_id, mode, mode not in UNBILLED_MODES, self._privacy_ok(segment_id)
            )
        )

    def _vendor_http(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == MODULATE_HOST or 'modulate' in host:
            mode = self.modulate.mode(self.clock.elapsed())
            self._post('modulate', mode)
            return _modulate_response(request, mode)
        if host == SONIOX_HOST:
            return self._soniox_http(request, path)
        raise AssertionError('drill vendor transport saw an unknown host')

    def _soniox_http(self, request, path):
        method = request.method
        if method == 'DELETE':
            return httpx.Response(204)
        if method == 'POST' and path.endswith('/files'):
            return httpx.Response(200, json={'id': str(uuid.uuid4())})
        if method == 'POST' and path.endswith('/transcriptions'):
            # The paid step.
            mode = self.soniox.mode(self.clock.elapsed())
            self._post('soniox', mode)
            if mode in {'5xx', '429', '402'}:
                return httpx.Response({'5xx': 503, '429': 429, '402': 402}[mode], text='drill')
            if mode == 'hang':
                raise httpx.ReadTimeout('drill hang', request=request)
            return httpx.Response(200, json={'id': str(uuid.uuid4()), 'status': 'completed'})
        if method == 'GET' and path.endswith('/transcript'):
            mode = self.soniox.mode(self.clock.elapsed())
            return _soniox_transcript(mode)
        if method == 'GET':
            return httpx.Response(200, json={'id': path.rsplit('/', 1)[-1], 'status': 'completed'})
        raise AssertionError('drill Soniox transport saw an unknown request')

    # -- GPU workers ------------------------------------------------------------------------------

    def set_gpu_workers(self, count: int, *, evict: bool = False) -> None:
        """Scale the GPU pool. ``evict`` kills every running worker mid-unit (no complete/fail)."""
        if evict:
            self.gpu_busy.clear()
            self._gpu_generation += 1
        self.gpu_workers = count

    def _on_gpu(self):
        now = self.clock.now
        # Serving maintenance: expired leases (an evicted worker's) go back to retry.
        Scheduler(self.store).recover(now)
        for index in range(self.gpu_workers):
            worker = f'gpu-{index}'
            if worker in self.gpu_busy:
                continue
            leases = Scheduler(self.store, worker_id=worker).pull(now, 1)
            if not leases:
                break
            lease = leases[0]
            self.gpu_busy[worker] = (lease.item.segment_id, lease.token)
            seconds = 2.0 + lease.item.duration_seconds * self.gpu_seconds_per_audio_second
            self._push_abs(
                now + seconds, 'gpu_done', (worker, lease.item.segment_id, lease.token, self._gpu_generation)
            )

    def _on_gpu_done(self, worker, segment_id, token, generation):
        if generation != self._gpu_generation or self.gpu_busy.get(worker) != (segment_id, token):
            return  # evicted mid-unit: the lease expires and another worker re-pulls it
        del self.gpu_busy[worker]
        result = WorkResult(segment_id, f'gs://drill/gpu/{segment_id}/{token}.enc', 'success')
        if Scheduler(self.store, worker_id=worker).complete(result, token, self.clock.now):
            self.gpu_completions += 1
        self._merge_owner(self.units[segment_id].owner_id)

    # -- merge and observation --------------------------------------------------------------------

    def _merge_owner(self, owner_id: str) -> None:
        for _ in range(64):
            entry = self.merge.commit_next(owner_id, self.clock.now)
            if not entry:
                return
            segment_id = entry['segment_id']
            self.commits.append((self.clock.now, segment_id))
            self.first_commit_result.setdefault(segment_id, dict(self.store.get('jobs', segment_id)['result']))

    def _on_merge_all(self):
        for owner_id in sorted({unit.owner_id for unit in self.units.values()}):
            self._merge_owner(owner_id)

    def _on_observe(self):
        self.health.refresh()
        for service in ('modulate', 'soniox'):
            if _gauge_open(service) and service not in self.breaker_open_seen:
                self.breaker_open_seen[service] = self.clock.elapsed()

    # -- read-outs --------------------------------------------------------------------------------

    def job(self, segment_id: str) -> dict:
        return self.store.get('jobs', segment_id)

    def states(self) -> Counter:
        return Counter(self.job(segment_id).get('state') for segment_id in self.units)

    def provider_units(self) -> list[str]:
        return [s for s, unit in self.units.items() if unit.route != 'gpu']

    def provider_units_admitted_between(self, start: float, end: float) -> list[tuple[str, Unit]]:
        return [
            (s, unit)
            for s, unit in self.units.items()
            if unit.route != 'gpu' and start <= unit.admitted_at - EPOCH < end
        ]

    def billed_posts(self) -> Counter:
        return Counter((post.segment_id, post.service) for post in self.posts if post.billed)

    def vendor_cause_failed_held(self) -> list[str]:
        return [
            segment_id
            for segment_id in self.units
            if self.job(segment_id).get('recovery_state') == 'failed_held'
            and (self.job(segment_id).get('provider_intent') or {}).get('failure', {}).get('stage') == 'provider'
        ]

    def owner_log(self, owner_id: str) -> list[dict]:
        rows = [
            row for (table, _), row in self.store.rows.items() if table == 'results' and row.get('owner_id') == owner_id
        ]
        return sorted(rows, key=lambda row: row['log_sequence'])

    def first_success_after(self, elapsed: float, *, route: str) -> float | None:
        """Drill seconds of the first vendor POST to ``route`` (or GPU completion) at or after ``elapsed``
        whose answer was ok: the moment traffic actually moved."""
        times = [p.at - EPOCH for p in self.posts if p.service == route and p.mode == 'ok' and p.at - EPOCH >= elapsed]
        return min(times) if times else None


class _Rng:
    """Deterministic rng for slice C's degraded admit fraction."""

    def __init__(self, seed: int):
        self.state = seed or 1

    def random(self) -> float:
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) % 2**64
        return (self.state >> 11) / 2**53


def _ticks(start: float, end: float, step: float):
    t = start
    while t <= end:
        yield t
        t += step


def _latency(service: str, mode: str, script: VendorScript) -> float:
    if mode == 'hang':
        # Velma's read timeout; Soniox's whole-call deadline.
        return 300.0 if service == 'modulate' else 120.0
    if mode == 'slow':
        return script.slow_seconds
    if mode in {'429', '402'}:
        return 0.3
    return script.latency


def _modulate_response(request: httpx.Request, mode: str) -> httpx.Response:
    if mode == '5xx':
        return httpx.Response(503, text='drill')
    if mode == '429':
        return httpx.Response(429, text='drill')
    if mode == '402':
        return httpx.Response(402, text='drill')
    if mode == 'hang':
        raise httpx.ReadTimeout('drill hang', request=request)
    if mode == 'garbage':
        return httpx.Response(200, content=b'{"utterances": [{"text": "hel')
    if mode == 'empty':
        return httpx.Response(200, json={'utterances': [], 'text': '', 'duration_ms': 30000})
    utterances = [
        {'text': 'drill words one two three', 'start_ms': 500, 'duration_ms': 1500, 'speaker': 1, 'language': 'ja'},
        {'text': 'drill words four five six', 'start_ms': 2100, 'duration_ms': 1500, 'speaker': 2, 'language': 'ja'},
    ]
    if mode == 'partial':
        utterances = utterances[:1]
    return httpx.Response(200, json={'utterances': utterances, 'text': 'drill', 'duration_ms': 30000})


def _soniox_transcript(mode: str) -> httpx.Response:
    if mode == 'garbage':
        return httpx.Response(200, content=b'{"text": "dri')
    if mode == 'empty':
        return httpx.Response(200, json={'text': '', 'tokens': []})
    tokens = [
        {'text': 'drill ', 'start_ms': 500, 'end_ms': 900, 'speaker': '1', 'language': 'ja'},
        {'text': 'words', 'start_ms': 1000, 'end_ms': 1400, 'speaker': '1', 'language': 'ja'},
    ]
    if mode == 'partial':
        tokens = tokens[:1]
    return httpx.Response(200, json={'text': 'drill words', 'tokens': tokens})


def _gauge_open(service: str) -> bool:
    """The exported breaker gauge (the alert signal) reads open or half-open for ``service``."""
    gauge = vendor_metrics.BREAKER_STATE
    return any(gauge.labels(provider=service, state=state)._value.get() for state in ('open', 'half_open'))


def _reset_breaker_gauges() -> None:
    # The gauge is process-global; a drill starts from closed so an earlier drill cannot leak in.
    for service in ('modulate', 'soniox'):
        vendor_metrics.breaker_state(service, 'closed')


def owners_fifo_violations(world: DrillWorld) -> list[str]:
    """Result-log order is capture order except rows the merge marks late (bounded head wait)."""
    bad = []
    for owner_id in sorted({unit.owner_id for unit in world.units.values()}):
        high = None
        for row in world.owner_log(owner_id):
            position = (row['capture_at'], row['segment_id'])
            if high is not None and position < high and not row.get('late_capture'):
                bad.append(row['segment_id'])
            high = position if high is None or position > high else high
    return bad


def double_written(world: DrillWorld) -> list[str]:
    """Units whose committed result changed after commit, or with no result log for a commit."""
    bad = []
    for segment_id, first in world.first_commit_result.items():
        job = world.job(segment_id)
        if job.get('result') != first or not world.store.get('results', segment_id):
            bad.append(segment_id)
    commits = Counter(segment_id for _, segment_id in world.commits)
    bad += [segment_id for segment_id, count in commits.items() if count > 1]
    return bad


def assert_invariants(world: DrillWorld, *, all_committed: bool = True, allow_failed_held: int = 0) -> dict:
    """The fixed per-case requirements; returns a summary for the report."""
    states = world.states()
    billed = world.billed_posts()
    summary = {
        'units': len(world.units),
        'states': dict(states),
        'vendor_posts': len(world.posts),
        'billed_posts': sum(billed.values()),
        'double_billed': sorted(key for key, count in billed.items() if count > 1),
        'failed_held_vendor': world.vendor_cause_failed_held(),
        'fifo_violations': owners_fifo_violations(world),
        'double_written': double_written(world),
        'privacy_violations': [p.segment_id for p in world.posts if not p.privacy_ok],
        'audio_deleted': list(world.artifacts.deleted_audio),
        'max_in_flight': world.max_in_flight,
        'breaker_open_at': dict(world.breaker_open_seen),
    }
    assert not summary['double_billed'], summary
    assert not summary['double_written'], summary
    assert not summary['fifo_violations'], summary
    assert not summary['privacy_violations'], summary
    assert not summary['audio_deleted'], summary
    assert world.max_in_flight <= world.queue_concurrency, summary
    lost = [s for s in world.units if world.job(s).get('state') not in OPEN_STATES | TERMINAL_STATES]
    assert not lost, (lost, summary)
    for segment_id in world.units:
        # Custody: every unit that has not committed still has its audio.
        if world.job(segment_id).get('state') != 'committed':
            assert segment_id in world.artifacts.audio, summary
    assert len(summary['failed_held_vendor']) <= allow_failed_held, summary
    if all_committed:
        assert set(states) == {'committed'}, summary
    return summary
