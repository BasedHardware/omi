"""Small fail-closed reader for paired PostHog enable and kill switches."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from utils.executors import posthog_flag_executor, run_blocking

logger = logging.getLogger(__name__)


class TriState(str, Enum):
    ENABLED = 'enabled'
    DISABLED = 'disabled'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class PairedFlagEvaluation:
    rollout: TriState
    kill_switch: TriState


class PostHogPairedFlagProvider:
    """Read two owner-scoped flags in one bounded PostHog request."""

    def __init__(
        self,
        *,
        rollout_flag_key: str,
        kill_switch_flag_key: str,
        timeout_seconds: float = 2.0,
        client_factory: Callable[[], Any | None] | None = None,
    ) -> None:
        if not rollout_flag_key.strip() or not kill_switch_flag_key.strip():
            raise ValueError('both PostHog flag keys are required')
        if timeout_seconds <= 0 or timeout_seconds > 5:
            raise ValueError('timeout_seconds must be in (0, 5]')
        self.rollout_flag_key = rollout_flag_key
        self.kill_switch_flag_key = kill_switch_flag_key
        self.timeout_seconds = timeout_seconds
        self.client_factory = client_factory or self._build_client
        self._client: Any | None = None
        self._client_lock = threading.Lock()

    def _build_client(self) -> Any | None:
        api_key = (os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY') or '').strip()
        if not api_key:
            return None
        module = importlib.import_module('posthog')
        return module.Posthog(
            project_api_key=api_key,
            host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
            send=False,
            sync_mode=True,
            feature_flags_request_timeout_seconds=self.timeout_seconds,
        )

    def _read(self, uid: str) -> PairedFlagEvaluation:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self.client_factory()
        if self._client is None:
            raise LookupError('posthog_unconfigured')
        flags = self._client.get_feature_variants(uid)
        if not isinstance(flags, Mapping):
            raise TypeError('malformed_feature_flags')

        def state(key: str) -> TriState:
            value = flags.get(key, False)
            if value is True:
                return TriState.ENABLED
            if value is False or value is None:
                return TriState.DISABLED
            return TriState.UNKNOWN

        return PairedFlagEvaluation(state(self.rollout_flag_key), state(self.kill_switch_flag_key))

    async def __call__(self, uid: str) -> PairedFlagEvaluation:
        try:
            return await asyncio.wait_for(
                run_blocking(posthog_flag_executor, self._read, uid), timeout=self.timeout_seconds
            )
        except Exception as exc:
            logger.warning('paired PostHog flag lookup failed error_type=%s', type(exc).__name__)
            return PairedFlagEvaluation(TriState.UNKNOWN, TriState.UNKNOWN)
