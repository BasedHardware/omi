"""Stable per-install client device identity (provenance only).

Contract (see docs/memory/domain_model.md):
  client_device_id = "{platform}_{hash}"
  hash = first 8 hex chars of sha256(stable per-install id)
  Headers: X-Device-Id-Hash + X-App-Platform (+ optional X-App-Version)
  Absent headers => unknown device (all fields nullable).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from starlette.requests import Request


class DeviceScopeValidationError(ValueError):
    """Invalid device_scope query value."""


@dataclass(frozen=True)
class DeviceScopeRequest:
    """Resolved device-scope filter for canonical memory reads."""

    device_scope: str
    client_device_id: Optional[str] = None

    @classmethod
    def resolve_from_headers(
        cls,
        *,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
        x_app_platform: Optional[str] = None,
        x_device_id_hash: Optional[str] = None,
    ) -> "DeviceScopeRequest":
        scope = cls._normalize_device_scope(device_scope)
        resolved_device_id = client_device_id
        if scope == "current":
            resolved_device_id = resolve_client_device(
                x_app_platform=x_app_platform,
                x_device_id_hash=x_device_id_hash,
            ).client_device_id
        return cls(device_scope=scope, client_device_id=resolved_device_id)

    @staticmethod
    def _normalize_device_scope(device_scope: str) -> str:
        scope = (device_scope or "all").strip().lower()
        if scope not in ("all", "current", "explicit"):
            raise DeviceScopeValidationError("device_scope must be one of: all, current, explicit")
        return scope


@dataclass(frozen=True)
class ClientDeviceContext:
    client_device_id: Optional[str] = None
    platform: Optional[str] = None
    device_hash: Optional[str] = None
    app_version: Optional[str] = None


def build_client_device_id(platform: Optional[str], device_hash: Optional[str]) -> Optional[str]:
    platform_norm = (platform or "").strip().lower()
    hash_norm = (device_hash or "").strip().lower()
    if not platform_norm or not hash_norm or hash_norm == "default":
        return None
    return f"{platform_norm}_{hash_norm}"


def resolve_client_device(
    *,
    x_app_platform: Optional[str] = None,
    x_device_id_hash: Optional[str] = None,
    x_app_version: Optional[str] = None,
) -> ClientDeviceContext:
    platform = (x_app_platform or "").strip().lower() or None
    device_hash = (x_device_id_hash or "").strip().lower() or None
    app_version = (x_app_version or "").strip() or None
    return ClientDeviceContext(
        client_device_id=build_client_device_id(platform, device_hash),
        platform=platform,
        device_hash=device_hash,
        app_version=app_version,
    )


def resolve_client_device_from_request(request: Request) -> ClientDeviceContext:
    headers = request.headers
    return resolve_client_device(
        x_app_platform=headers.get("x-app-platform"),
        x_device_id_hash=headers.get("x-device-id-hash"),
        x_app_version=headers.get("x-app-version"),
    )


def resolve_client_device_from_headers(headers: Mapping[str, str]) -> ClientDeviceContext:
    return resolve_client_device(
        x_app_platform=headers.get("x-app-platform") or headers.get("X-App-Platform"),
        x_device_id_hash=headers.get("x-device-id-hash") or headers.get("X-Device-Id-Hash"),
        x_app_version=headers.get("x-app-version") or headers.get("X-App-Version"),
    )


def resolve_client_device_from_websocket_auth_message(message: Mapping[str, Any]) -> ClientDeviceContext:
    """Resolve web capture provenance sent in the first WebSocket auth message.

    Browsers cannot attach arbitrary headers to a WebSocket upgrade. The web
    listen client therefore sends its stable device hash beside the Firebase
    token in the already-required first auth message. Platform is fixed to
    ``web`` rather than trusting a browser-provided platform value.
    """
    text = message.get("text")
    if not isinstance(text, str):
        return ClientDeviceContext()
    try:
        auth_data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return ClientDeviceContext()
    if not isinstance(auth_data, dict):
        return ClientDeviceContext()
    device_hash = auth_data.get("device_id_hash")
    return resolve_client_device(
        x_app_platform="web",
        x_device_id_hash=device_hash if isinstance(device_hash, str) else None,
    )
