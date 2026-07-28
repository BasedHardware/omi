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


class ListenParityCapture:
    """Small listener-side adapter around the pack's generic ``CaptureTap``.

    The adapter has no effect unless the existing whitelist allows the Firebase
    UID and a restricted absolute root has been supplied. Event bodies are only
    serialized into that local root; logs contain no principal or payload data.
    """

    def __init__(self, invocation: CaptureInvocation | None) -> None:
        self._invocation = invocation
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
        root = _capture_root(env)
        if root is None:
            return cls(None)
        identity = CassetteIdentity(
            anon_session=_anonymous_id(principal_id, session_id),
            provider_lane="stt",
            route_or_model=model or provider or "live",
            call_ordinal=0,
            retry_attempt=0,
            parent_event_anon=_anonymous_id(session_id, "listen-stt"),
        )
        try:
            invocation = CaptureTap(root, CaptureWhitelist.from_environ(dict(env))).start(
                principal_id, identity, request
            )
            return cls(invocation)
        except Exception as error:
            # Capture must never make an otherwise valid listen session unavailable.
            logger.warning("Parity pack capture initialization failed error_type=%s", type(error).__name__)
            return cls(None)

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
            self._invocation.persist()
        except Exception as error:
            logger.warning("Parity pack capture persist failed error_type=%s", type(error).__name__)
