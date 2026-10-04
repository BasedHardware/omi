"""Exactly-once settlement of a serving decision and its health evidence.

Socket liveness is deliberately not an input. The owner either hands this
outcome to a PendingLiveFailover, rejects a connection, or ends normally.
There is no health writer in a death getter, send, or transport close.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Any

from config.live_stt_registry import registry, DEFAULT_TARGETS
from utils.stt.live_metrics import (
    COST_SETTLEMENTS,
    COST_IGNORED_DEATHS,
    COST_EVIDENCE_ERRORS,
    COST_EMISSION_ACK_ERRORS,
    MANAGED_LEGS_OPENED,
    MANAGED_LEGS_SETTLED,
    MANAGED_LEGS_OPEN,
)
from utils.stt.live_reason import normalize_live_stt_reason
from utils.stt.live_signal import provider_observation

logger = logging.getLogger(__name__)


class LiveLegOutcome:
    def __init__(
        self,
        target: str,
        language: str,
        uid: str | None,
        generations: dict[str, int] | None,
        record: Callable[..., Any],
        *,
        client_has_left: Callable[[], bool] | None = None,
        text_seen: Callable[[], bool] | None = None,
    ) -> None:
        self.target, self.language, self.uid = target, language, uid
        self.generations, self.record = generations, record
        self.client_has_left, self.text_seen = client_has_left, text_seen
        self.excluded_death = False
        self.death_observed = False
        self.death_eligible = False
        self.claimed = False
        self.settled = False
        self.reason: str | None = None
        self.path = 'close'
        self.owner_closing = False
        self.recovery_enabled: bool | None = None
        self.pending: Any = None
        self.handed_off = False
        self.transport_released = False

    def observe_death(self) -> None:
        """Freeze whether this provider death was observed while serving was eligible."""
        if self.death_observed:
            return
        self.death_observed = True
        self.death_eligible = not (self.owner_closing or bool(self.client_has_left and self.client_has_left()))

    def claim(self, reason: str, *, connect: bool = False) -> str:
        """Transfer settlement to the serving decision before closing transport."""
        if not self.claimed and not self.settled:
            self.claimed = True
            bounded_reason = normalize_live_stt_reason(reason)
            self.excluded_death = (
                not self.death_eligible
                if self.death_observed
                else self.owner_closing or bool(self.client_has_left and self.client_has_left())
            )
            self.reason = 'normal_close' if self.excluded_death else bounded_reason
            if self.excluded_death:
                try:
                    if os.getenv('STT_ROUTING_MODE', 'off').strip().lower() != 'off' and any(
                        entry.id == self.target for entry in registry()
                    ):
                        COST_IGNORED_DEATHS.labels(
                            target=self.target,
                            reason=bounded_reason,
                            boundary='owner_teardown' if self.owner_closing else 'client_gone',
                        ).inc()
                except Exception:
                    logger.debug('Cost ignored-death diagnostic unavailable; retaining lifecycle fence')
            self.path = 'connect' if connect else 'failover'
            # Connect rejection belongs to the gate at rejection, not the
            # generation captured before awaiting the provider handshake.
            if connect:
                self.generations = None
        return self.reason or normalize_live_stt_reason(reason)

    def settle(self, *, text_seen: bool = False, emit_fallback: Callable[[], None] | None = None) -> bool:
        if self.settled:
            return False
        self.settled = True
        if self.handed_off:
            MANAGED_LEGS_SETTLED.labels(target=self.target).inc()
        if self.excluded_death:
            text_seen = text_seen or bool(self.text_seen and self.text_seen())
        outcome = (
            ('connect_failure' if self.path == 'connect' else 'failover')
            if self.claimed and not self.excluded_death
            else ('text' if text_seen else 'no_text')
        )
        reason = (None if self.excluded_death else self.reason) or ('text' if text_seen else 'no_text')
        # Both emissions run synchronously in this one settlement. A failed
        # recorder is observable; it must never break serving or be retried as
        # a second independent socket/connect observation.
        try:
            if emit_fallback is not None and not self.excluded_death:
                emit_fallback()
            if not self.uid or os.getenv('STT_ROUTING_MODE', 'off') == 'off':
                return True
            if not any(entry.id == self.target for entry in registry()):
                return True
            failed = provider_observation(outcome, reason)
            classification = 'censored' if failed is None else 'provider_failure' if failed else 'success'
            COST_SETTLEMENTS.labels(target=self.target, outcome=classification, reason=reason, path=self.path).inc()
            acknowledged = self.record(self.target, self.language, outcome, self.generations, self.uid, reason)
            if acknowledged is not True:
                COST_EMISSION_ACK_ERRORS.inc()
        except Exception:
            COST_EVIDENCE_ERRORS.inc()
            COST_EMISSION_ACK_ERRORS.inc()
            logger.warning('Live STT settlement evidence unavailable')
        return True

    def close(self, text_seen: bool) -> None:
        if not self.claimed:
            self.settle(text_seen=text_seen)


def record_managed_leg_handoff(socket: Any) -> None:
    """Called by the connector, independently of the terminal settlement path."""
    outcome = getattr(socket, 'leg_outcome', None)
    if not isinstance(outcome, LiveLegOutcome) or outcome.handed_off:
        return
    try:
        targets = registry()
    except (ValueError, TypeError):
        targets = DEFAULT_TARGETS  # Telemetry must preserve configured-order fail-open.
    if not any(entry.id == outcome.target for entry in targets):
        return
    outcome.handed_off = True
    MANAGED_LEGS_OPENED.labels(target=outcome.target).inc()
    if getattr(socket, '_open_gauge_released', False):
        outcome.transport_released = True
    else:
        MANAGED_LEGS_OPEN.labels(target=outcome.target).inc()
