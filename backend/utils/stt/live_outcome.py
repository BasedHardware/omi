"""Exactly-once settlement of a serving decision and its health evidence.

Socket liveness is deliberately not an input. The owner either hands this
outcome to a PendingLiveFailover, rejects a connection, or ends normally.
There is no health writer in a death getter, send, or transport close.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Any

from config.live_stt_registry import registry
from utils.stt.live_metrics import COST_SETTLEMENTS, COST_EVIDENCE_ERRORS
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
    ) -> None:
        self.target, self.language, self.uid = target, language, uid
        self.generations, self.record = generations, record
        self.claimed = False
        self.settled = False
        self.reason: str | None = None
        self.path = 'close'
        self.owner_closing = False
        self.pending: Any = None

    def claim(self, reason: str, *, connect: bool = False) -> str:
        """Transfer settlement to the serving decision before closing transport."""
        if not self.claimed and not self.settled:
            self.claimed = True
            self.reason = 'normal_close' if self.owner_closing else normalize_live_stt_reason(reason)
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
        outcome = (
            ('connect_failure' if self.path == 'connect' else 'failover')
            if self.claimed
            else ('text' if text_seen else 'no_text')
        )
        reason = self.reason or ('text' if text_seen else 'no_text')
        # Both emissions run synchronously in this one settlement. A failed
        # recorder is observable; it must never break serving or be retried as
        # a second independent socket/connect observation.
        try:
            if emit_fallback is not None:
                emit_fallback()
            if not self.uid or os.getenv('STT_ROUTING_MODE', 'off') == 'off':
                return True
            if not any(entry.id == self.target for entry in registry()):
                return True
            failed = provider_observation(outcome, reason)
            classification = 'censored' if failed is None else 'provider_failure' if failed else 'success'
            COST_SETTLEMENTS.labels(target=self.target, outcome=classification, reason=reason, path=self.path).inc()
            self.record(self.target, self.language, outcome, self.generations, self.uid, reason)
        except Exception:
            COST_EVIDENCE_ERRORS.inc()
            logger.warning('Live STT settlement evidence unavailable')
        return True

    def close(self, text_seen: bool) -> None:
        if not self.claimed:
            self.settle(text_seen=text_seen)
