"""Fail-closed dev-only parity-pack capture for the live listen STT seam."""

from __future__ import annotations

import base64
from hashlib import sha256
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from testing.parity_pack_v0.capture import CaptureInvocation, CaptureTap
from testing.parity_pack_v0.schema import CassetteIdentity
from testing.parity_pack_v0.whitelist import CaptureWhitelist

logger = logging.getLogger(__name__)


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
        invocation = CaptureTap(root, CaptureWhitelist.from_environ(dict(env))).start(principal_id, identity, request)
        return cls(invocation)

    @property
    def enabled(self) -> bool:
        return self._invocation is not None

    def observe_client_audio(self, audio: bytes) -> None:
        self._observe_audio("client", audio)

    def observe_outbound_stt(self, audio: bytes) -> None:
        self._observe_audio("outbound", audio)

    def observe_inbound_stt(self, segments: list[dict[str, Any]]) -> None:
        if self._invocation is not None:
            self._invocation.observe("inbound", {"type": "transcript", "segments": segments})

    def _observe_audio(self, direction: str, audio: bytes) -> None:
        if self._invocation is not None:
            self._invocation.observe(direction, {"type": "audio", "audio_b64": base64.b64encode(audio).decode("ascii")})

    def persist(self) -> None:
        if self._invocation is None:
            return
        try:
            self._invocation.persist()
        except Exception as error:
            logger.warning("Parity pack capture persist failed error_type=%s", type(error).__name__)
