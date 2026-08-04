"""Fail-closed dev-only parity-pack capture for the live listen STT seam."""

from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from testing.parity_pack_v0.capture import CaptureInvocation, CaptureTap
from testing.parity_pack_v0.schema import CassetteIdentity
from testing.parity_pack_v0.whitelist import CaptureWhitelist

from .parity_telemetry import record_parity_capture_event

logger = logging.getLogger(__name__)

# Cassettes are a local diagnostic aid, never an unbounded in-memory recording.
MAX_CAPTURE_EVENTS = 1_000
MAX_CAPTURE_AUDIO_BYTES = 8 * 1024 * 1024


def _anonymous_id(*parts: str) -> str:
    """Create an opaque stable-in-session identifier without retaining a UID."""
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def _capture_root(environ: Mapping[str, str]) -> Path | None:
    value = environ.get("OMI_PARITY_PACK_ROOT", "").strip()
    if not value:
        return None
    root = Path(value).expanduser()
    if not root.is_absolute():
        return None
    repository_root = Path(__file__).resolve().parents[3]
    try:
        root.resolve().relative_to(repository_root)
    except ValueError:
        return root
    return None


def _allowlist_decision_reason(whitelist: CaptureWhitelist, principal_id: str | None) -> str:
    """Classify the existing gate without retaining or emitting its principal."""
    if whitelist.allows(principal_id):
        return 'allowed'
    if not whitelist.enabled:
        return 'capture_disabled'
    if whitelist.environment != 'dev':
        return 'stage_not_dev'
    if not principal_id:
        return 'principal_missing'
    return 'allowlist_miss'


class ListenParityCapture:
    """Small listener-side adapter around the pack's generic ``CaptureTap``.

    The adapter has no effect unless the existing whitelist allows the Firebase
    UID and a restricted absolute root has been supplied. Event bodies are only
    serialized into that local root; logs contain no principal or payload data.
    """

    def __init__(
        self,
        invocation: CaptureInvocation | None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._invocation = invocation
        # Production reads the process environment lazily instead of retaining a
        # per-session copy that could include unrelated credentials. Tests may
        # inject only the narrow capture settings they exercise.
        self._environ = None if environ is None else dict(environ)
        self._event_count = 0
        self._audio_bytes = 0
        self._limit_reached = False

    @classmethod
    def from_environ(
        cls,
        *,
        principal_id: str,
        session_id: str,
        provider: str,
        model: str,
        request: Mapping[str, Any],
        environ: Mapping[str, str] | None = None,
    ) -> "ListenParityCapture":
        env = os.environ if environ is None else environ
        record_parity_capture_event('listen', 'accepted', 'none', environ=env)
        whitelist = CaptureWhitelist.from_environ(dict(env))
        decision_reason = _allowlist_decision_reason(whitelist, principal_id)
        record_parity_capture_event(
            'allowlist',
            'accepted' if decision_reason == 'allowed' else 'rejected',
            decision_reason,
            environ=env,
        )
        if decision_reason != 'allowed':
            return cls(None, environ=environ)
        root = _capture_root(env)
        if root is None:
            record_parity_capture_event('initialize', 'failed', 'root_invalid', environ=env)
            return cls(None, environ=environ)
        identity = CassetteIdentity(
            anon_session=_anonymous_id(principal_id, session_id),
            provider_lane="stt",
            route_or_model=model or provider or "live",
            call_ordinal=0,
            retry_attempt=0,
            parent_event_anon=_anonymous_id(session_id, "listen-stt"),
        )
        try:
            invocation = CaptureTap(root, whitelist).start(principal_id, identity, request)
            if invocation is None:
                record_parity_capture_event('initialize', 'failed', 'internal', environ=env)
                return cls(None, environ=environ)
            record_parity_capture_event('initialize', 'succeeded', 'none', environ=env)
            return cls(invocation, environ=environ)
        except Exception as error:
            # Capture must never make an otherwise valid listen session unavailable.
            logger.warning("Parity pack capture initialization failed error_type=%s", type(error).__name__)
            record_parity_capture_event('initialize', 'failed', 'internal', environ=env)
            return cls(None, environ=environ)

    @property
    def enabled(self) -> bool:
        return self._invocation is not None

    def observe_client_audio(self, audio: bytes) -> None:
        self._observe_audio("client", audio)

    def observe_outbound_stt(self, audio: bytes) -> None:
        self._observe_audio("outbound", audio)

    def observe_inbound_stt(self, segments: list[dict[str, Any]]) -> None:
        # Transcript processing annotates these dictionaries later; preserve the provider
        # callback as it arrived instead of retaining a mutable reference.
        if not self._can_observe():
            return
        self._observe("inbound", {"type": "transcript", "segments": deepcopy(segments)})

    def _observe_audio(self, direction: str, audio: bytes) -> None:
        # Check the raw input before allocating its base64 representation.
        if not self._can_observe(len(audio)):
            return
        self._observe(direction, {"type": "audio", "audio_b64": base64.b64encode(audio).decode("ascii")}, len(audio))

    def _can_observe(self, audio_bytes: int = 0) -> bool:
        if self._invocation is None or self._limit_reached:
            return False
        if self._event_count >= MAX_CAPTURE_EVENTS or self._audio_bytes + audio_bytes > MAX_CAPTURE_AUDIO_BYTES:
            self._limit_reached = True
            logger.warning("Parity pack capture limit reached; dropping subsequent events")
            return False
        return True

    def _observe(self, direction: str, payload: Mapping[str, Any], audio_bytes: int = 0) -> None:
        if not self._can_observe(audio_bytes):
            return
        invocation = self._invocation
        if invocation is None:
            return
        try:
            invocation.observe(direction, payload)
            self._event_count += 1
            self._audio_bytes += audio_bytes
        except Exception as error:
            logger.warning("Parity pack capture observe failed error_type=%s", type(error).__name__)

    def persist(self) -> None:
        if self._invocation is None:
            return
        try:
            path = self._invocation.persist()
        except Exception as error:
            logger.warning("Parity pack capture persist failed error_type=%s", type(error).__name__)
            record_parity_capture_event('persist', 'failed', 'internal', environ=self._environ)
            return
        record_parity_capture_event('persist', 'succeeded', 'none', environ=self._environ)
        # Durable export is best-effort and must never affect listen availability.
        try:
            from .parity_pack_export import ensure_reconcile_loop, export_cassette_file

            ensure_reconcile_loop(environ=self._environ)
            export_cassette_file(path, environ=self._environ)
        except Exception as error:
            logger.warning("Parity pack capture export failed error_type=%s", type(error).__name__)
            record_parity_capture_event('export', 'failed', 'internal', environ=self._environ)
