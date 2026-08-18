"""Reusable live adapters for dev-only, allowlisted parity-pack capture.

This module is intentionally small enough to use from HTTP routers and
background finalizers.  It only serializes data after ``CaptureWhitelist``
permits the principal, never accepts a repository-local root, bounds raw audio
and event count, and treats persistence/export failures as non-fatal.
"""

from __future__ import annotations

import base64
from hashlib import sha256
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from .capture import CaptureInvocation, CaptureTap
from .schema import CassetteIdentity
from .whitelist import CaptureWhitelist

logger = logging.getLogger(__name__)

MAX_CAPTURE_EVENTS = 1_000
MAX_CAPTURE_AUDIO_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_TEXT_CHARS = 16 * 1024
MAX_CAPTURE_SEQUENCE_ITEMS = 1_000


def _is_screen_surface(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("screen") or normalized.startswith("ocr")


def _anonymous_id(*parts: str) -> str:
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


def _bounded_capture_value(value: Any, *, key: str | None = None) -> Any:
    """Normalize provider objects and bound text before persistence is possible."""
    if isinstance(value, str):
        # Audio is already separately byte-bounded and must remain replayable.
        return value if key == "audio_b64" else value[:MAX_CAPTURE_TEXT_CHARS]
    if isinstance(value, Mapping):
        return {str(item_key): _bounded_capture_value(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bounded_capture_value(item) for item in value[:MAX_CAPTURE_SEQUENCE_ITEMS]]
    if hasattr(value, "model_dump"):
        try:
            return _bounded_capture_value(value.model_dump(mode="json"), key=key)
        except Exception:
            pass
    if hasattr(value, "value") and isinstance(value.value, (str, int, float, bool)):
        return _bounded_capture_value(value.value, key=key)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_CAPTURE_TEXT_CHARS]


class SurfaceParityCapture:
    """Bounded, fail-open capture for a memory-forming production seam."""

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
        surface: str,
        source: str,
        provider_lane: str,
        route_or_model: str,
        request: Mapping[str, Any],
        environ: Mapping[str, str] | None = None,
    ) -> "SurfaceParityCapture":
        env = os.environ if environ is None else environ
        if _is_screen_surface(surface) or _is_screen_surface(source):
            return cls(None)
        root = _capture_root(env)
        if root is None:
            return cls(None)
        identity = CassetteIdentity(
            anon_session=_anonymous_id(principal_id, session_id),
            provider_lane=provider_lane,
            route_or_model=route_or_model or surface,
            call_ordinal=0,
            retry_attempt=0,
            parent_event_anon=_anonymous_id(session_id, surface, source),
        )
        try:
            invocation = CaptureTap(root, CaptureWhitelist.from_environ(dict(env))).start(
                principal_id,
                identity,
                request,
                surface=surface,
                source=source,
            )
            return cls(invocation)
        except Exception as error:
            logger.warning("Parity pack surface capture initialization failed error_type=%s", type(error).__name__)
            return cls(None)

    @property
    def enabled(self) -> bool:
        return self._invocation is not None

    def observe(self, direction: str, payload: Mapping[str, Any]) -> None:
        if not self._can_observe():
            return
        payload_type = payload.get("type")
        if isinstance(payload_type, str) and _is_screen_surface(payload_type):
            return
        try:
            invocation = self._invocation
            if invocation is not None:
                invocation.observe(direction, _bounded_capture_value(payload))
                self._event_count += 1
        except Exception as error:
            logger.warning("Parity pack surface capture observe failed error_type=%s", type(error).__name__)

    def observe_audio(self, direction: str, audio: bytes) -> None:
        if not self._can_observe(len(audio)):
            return
        self.observe(direction, {"type": "audio", "audio_b64": base64.b64encode(audio).decode("ascii")})
        self._audio_bytes += len(audio)

    def _can_observe(self, audio_bytes: int = 0) -> bool:
        if self._invocation is None or self._limit_reached:
            return False
        if self._event_count >= MAX_CAPTURE_EVENTS or self._audio_bytes + audio_bytes > MAX_CAPTURE_AUDIO_BYTES:
            self._limit_reached = True
            logger.warning("Parity pack surface capture limit reached; dropping subsequent events")
            return False
        return True

    def persist(self) -> None:
        if self._invocation is None:
            return
        try:
            path = self._invocation.persist()
        except Exception as error:
            logger.warning("Parity pack surface capture persist failed error_type=%s", type(error).__name__)
            return
        try:
            # Keep the exporter as one shared implementation while it remains
            # located beside the originally shipped listen adapter.
            from routers.listen.parity_pack_export import ensure_reconcile_loop, export_cassette_file

            ensure_reconcile_loop()
            export_cassette_file(path)
        except Exception as error:
            logger.warning("Parity pack surface capture export failed error_type=%s", type(error).__name__)


def _memory_payload(value: Any) -> dict[str, Any]:
    """Return the narrow memory shape suitable for a restricted cassette."""
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump(mode="json")
        except Exception:
            value = {}
    if not isinstance(value, Mapping):
        return {"content": str(value)[:MAX_CAPTURE_TEXT_CHARS]}
    evidence = value.get("evidence")
    source_type = "unknown"
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], Mapping):
        source_type = str(evidence[0].get("source_type") or source_type)
    return {
        "id": value.get("id"),
        "content": str(value.get("content") or "")[:MAX_CAPTURE_TEXT_CHARS],
        "category": value.get("category"),
        "visibility": value.get("visibility"),
        "source_type": source_type,
    }


def capture_memory_write(
    *,
    principal_id: str,
    source: str,
    session_id: str,
    memories: list[Any],
) -> None:
    """Persist one accepted memory-write cassette without exposing a UID."""
    capture = SurfaceParityCapture.from_environ(
        principal_id=principal_id,
        session_id=session_id,
        surface="memory_write",
        source=source,
        provider_lane="memory",
        route_or_model="memory-write",
        request={"memory_count": len(memories), "source": source},
    )
    payload = [_memory_payload(memory) for memory in memories[:100]]
    capture.observe("client", {"type": "memory_write_request", "memories": payload})
    capture.observe("inbound", {"type": "accepted_memories", "memories": payload})
    capture.persist()
