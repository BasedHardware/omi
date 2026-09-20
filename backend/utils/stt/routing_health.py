"""Shared, bounded STT admission state. Only a transcript can close a probe."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Literal

from redis.exceptions import WatchError

from utils.observability.fallback import record_fallback

FailureReason = Literal['budget', 'payment', 'quota', 'auth', 'timeout', 'capacity', 'provider_error']
HARD_FAILURES = frozenset({'budget', 'payment', 'quota', 'auth'})
HEALTH_TTL_SECONDS = 900
PROBE_SECONDS = 30


@dataclass(frozen=True)
class Health:
    state: str = 'closed'
    failures: int = 0
    generation: int = 0
    retry_at: float = 0
    probe_until: float = 0
    probe_owner: str = ''
    reason: str = 'none'


def claim(state: Health, *, now: float, owner: str) -> tuple[Health, bool]:
    if state.state == 'closed':
        return state, True
    if now < state.retry_at or now < state.probe_until:
        return state, False
    return replace(state, state='half_open', probe_until=now + PROBE_SECONDS, probe_owner=owner), True


def fail(state: Health, reason: FailureReason, *, now: float, jitter: float) -> Health:
    if state.state == 'hard' and reason not in HARD_FAILURES:
        return state
    failures = state.failures + 1
    hard = reason in HARD_FAILURES
    opened = hard or failures >= 3 or state.state != 'closed'
    delay = (300 if hard else 30) * (1 + min(0.25, max(0, jitter)))
    return Health(
        state='hard' if hard else 'open' if opened else 'closed',
        failures=failures,
        generation=state.generation + 1,
        retry_at=now + delay if opened else 0,
        reason=reason,
    )


def transcribed(state: Health, *, generation: int, owner: str) -> Health:
    if state.generation != generation or state.state in {'hard', 'open'}:
        return state
    if state.state == 'half_open' and state.probe_owner != owner:
        return state
    return Health(generation=state.generation)


class RedisHealthStore:
    """WATCH fences late successes and competing probes; Redis owns expiry.

    Three contention attempts bound contention cost. The caller must supply a
    client with bounded socket deadlines and no retry backoff.
    Any unavailable/malformed state fails open to configured order, with telemetry.
    BYOK credentials never use this managed-account namespace.
    """

    def __init__(self, client: Any, *, namespace: str) -> None:
        if not namespace or len(namespace) > 120:
            raise ValueError('health requires a bounded environment/account/surface namespace')
        self.client = client
        self.namespace = namespace

    def change(self, provider: str, operation: Callable[[Health], tuple[Health, bool]]) -> tuple[Health, bool]:
        if provider not in {'modulate', 'soniox', 'deepgram_cloud', 'deepgram_self_hosted', 'parakeet'}:
            raise ValueError('unknown health provider')
        key = f'{self.namespace}:{provider}'
        try:
            for _ in range(3):
                try:
                    with self.client.pipeline() as pipeline:
                        pipeline.watch(key)
                        raw = pipeline.get(key)
                        state = Health(**json.loads(raw)) if raw else Health()
                        updated, admitted = operation(state)
                        if updated != state:
                            pipeline.multi()
                            pipeline.set(key, json.dumps(asdict(updated)), ex=HEALTH_TTL_SECONDS)
                            pipeline.execute()
                        return updated, admitted
                except WatchError:
                    continue
            raise RuntimeError('health contention budget exhausted')
        except Exception:
            record_fallback(
                component='stt_selection',
                from_mode='shared_health',
                to_mode='config_order',
                reason='timeout',
                outcome='degraded',
            )
            return Health(), True

    def acquire(self, provider: str, *, now: float, owner: str) -> tuple[Health, bool]:
        return self.change(provider, lambda state: claim(state, now=now, owner=owner))

    def failure(self, provider: str, reason: FailureReason, *, now: float, jitter: float) -> None:
        self.change(provider, lambda state: (fail(state, reason, now=now, jitter=jitter), False))

    def transcript(self, provider: str, *, generation: int, owner: str) -> None:
        self.change(provider, lambda state: (transcribed(state, generation=generation, owner=owner), True))
