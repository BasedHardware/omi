"""Session policy and wall-time metering for phase-4 demand-driven live STT."""

import asyncio
import time
import uuid
from typing import Any, Callable, Mapping

from config.live_demand import language_qualified, resolve_live_demand
from utils.observability.fallback import record_fallback
from utils.observability.demand_cohort import DemandTelemetry, attach_demand_telemetry, host_telemetry, telemetry_call
from config.live_stt_recovery import session_recovery_enabled
from utils.stt.live_rollout import managed_chain_enabled
from utils.stt.demand_consumers import realtime_consumer_active
from utils.stt.demand_presence import update_presence


class DemandPolicy:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.state = 'unknown'
        self.reason = 'unknown'
        self.window_permitted = False
        self.changed_at = clock()
        self.switched_at = clock()
        self.fallback = False
        self.reports = 0

    def observe(self, payload: Mapping[str, Any]) -> None:
        foreground, visible = payload.get('foreground'), payload.get('transcript_visible')
        self.reports += 1
        if (
            self.reports > 2000
            or type(foreground) is not bool
            or type(visible) is not bool
            or visible
            and not foreground
        ):
            state = 'unknown'
        else:
            state = 'visible' if visible else 'hidden'
        if state != self.state:
            self.changed_at = self.clock()
        self.state = state

    def decide(self, *, enabled: bool, visible: bool, consumer: bool | None) -> str:
        if not enabled:
            reason = 'disabled'
        elif consumer is None:
            reason = 'consumer_unknown'
        elif consumer:
            reason = 'consumer'
        elif self.state == 'unknown':
            reason = 'unknown'
        elif visible or self.state == 'visible':
            reason = 'visible'
        else:
            reason = 'fallback' if self.fallback else 'hidden'
        self.reason = reason
        self.window_permitted = reason == 'hidden'
        return 'parakeet' if self.window_permitted else 'vendor'

    def ready(self, current: str, desired: str, dwell: float) -> bool:
        if current == desired:
            return False
        # Returning to safety/visibility is immediate; cheap admission requires
        # a stable hidden interval and minimum time since the previous switch.
        if desired == 'vendor':
            return True
        return self.clock() - max(self.changed_at, self.switched_at) >= dwell

    def switched(self) -> None:
        self.switched_at = self.clock()


class LiveDemandRouting:
    def __init__(self, receiver, *, eligible: bool):
        self.receiver = receiver
        self.eligible = eligible
        self._presence_lock = asyncio.Lock()
        self._presence_unavailable = False
        self._served_window = False
        self.policy = DemandPolicy()
        self.socket_id = uuid.uuid4().hex
        self.closed = False
        self.consumer: bool | None = None
        self.consumer_checked: float | None = None
        self._publish_task = None

    @property
    def window_permitted(self) -> bool:
        return self.policy.window_permitted and not self.policy.fallback

    def observe(self, payload) -> None:
        self.policy.observe(payload)
        if self.policy.state != 'hidden':
            self.policy.window_permitted = False
        # Publish promptly; periodic reconciliation owns switching and is serial.
        if self._publish_task is None or self._publish_task.done():
            self._publish_task = self.receiver.host.spawn(self.publish(), name='live_demand_publish')

    async def publish(self) -> bool:
        async with self._presence_lock:
            snapshot = await update_presence(
                self.receiver.host.request.uid, self.socket_id, 'close' if self.closed else self.policy.state
            )
            if snapshot.unavailable and not self._presence_unavailable and not self.closed:
                record_fallback(
                    component='stt_live_session',
                    from_mode='demand_presence',
                    to_mode='vendor',
                    reason='gate_unavailable',
                    outcome='degraded',
                )
            self._presence_unavailable = snapshot.unavailable
            return snapshot.visible

    def _consumer_unavailable(self) -> None:
        if self.consumer_checked is None or self.consumer is not None:
            record_fallback(
                component='stt_live_session',
                from_mode='demand_consumer',
                to_mode='vendor',
                reason='gate_unavailable',
                outcome='degraded',
            )
        self.consumer = None

    async def can_admit_window(self) -> bool:
        # Recheck after the potentially slow candidate dial, while the old
        # vendor still owns delivery. Another client's report/consumer may
        # have changed since the periodic policy snapshot.
        visible = await self.publish()
        try:
            self.consumer = await asyncio.wait_for(realtime_consumer_active(self.receiver.host.request.uid), timeout=2)
        except Exception:
            self._consumer_unavailable()
        self.consumer_checked = time.monotonic()
        return (
            self.policy.decide(
                enabled=resolve_live_demand().admits(self.receiver.host.request.uid),
                visible=visible,
                consumer=self.consumer,
            )
            == 'parakeet'
        )

    def meter(self) -> None:
        if self.eligible:
            telemetry_call(self.receiver, 'lane_meter', 'flush', reason=self.policy.reason)

    async def run(self) -> None:
        host = self.receiver.host
        try:
            while host.state.active and not host.state.stt_terminal_failure:
                self.meter()
                visible = await self.publish()
                if not self.eligible:
                    if await host.wait(1):
                        return
                    continue
                now = time.monotonic()
                # A timed-out executor leaf can still be running. Bound
                # outage probe rate instead of filling the shared DB pool.
                interval = 60 if self.consumer is None else 5
                if self.consumer_checked is None or now - self.consumer_checked >= interval:
                    try:
                        self.consumer = await asyncio.wait_for(realtime_consumer_active(host.request.uid), timeout=2)
                    except Exception:
                        self._consumer_unavailable()
                    self.consumer_checked = time.monotonic()
                current = 'parakeet' if host.stt_model == 'parakeet-window' else 'vendor'
                if self._served_window and current == 'vendor':
                    self.policy.fallback = True
                self._served_window = current == 'parakeet'
                desired = self.policy.decide(
                    enabled=resolve_live_demand().admits(host.request.uid), visible=visible, consumer=self.consumer
                )
                self.meter()
                current = 'parakeet' if host.stt_model == 'parakeet-window' else 'vendor'
                if self.policy.ready(current, desired, resolve_live_demand().dwell_seconds):
                    if await self.receiver._switch_live_demand(desired):
                        self.policy.switched()
                        self._served_window = desired == 'parakeet'
                if await host.wait(1):
                    return
        finally:
            self.close()
            await self.publish()

    def close(self) -> None:
        if not self.closed:
            self.meter()
            self.closed = True


def attach_live_demand(receiver) -> LiveDemandRouting | None:
    host = receiver.host
    if not resolve_live_demand().enabled:
        return None
    capture_demand_admission(host)
    return LiveDemandRouting(receiver, eligible=getattr(host, '_demand_cohort', None) == 'admitted')


def capture_demand_admission(host) -> DemandTelemetry | None:
    existing = host_telemetry(host)
    if getattr(host, '_demand_cohort', None) is not None:
        return existing
    config = resolve_live_demand()
    eligible = (
        session_recovery_enabled(host)
        and managed_chain_enabled(host)
        and not host.is_multi_channel
        and not host.use_custom_stt
        and not host.request.onboarding_mode
        and host.request.source != 'phone_call'
        and language_qualified(host)
    )
    cohort = ('admitted' if config.admits(host.request.uid) else 'eligible_control') if eligible else 'ineligible'
    host._demand_cohort = cohort
    return attach_demand_telemetry(host, cohort)
