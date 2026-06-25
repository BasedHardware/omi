"""Stable per-install client device identity (provenance only).

Contract (see docs/memory/domain_model.md):
  client_device_id = "{platform}_{hash}"
  hash = first 8 hex chars of sha256(stable per-install id)
  Headers: X-Device-Id-Hash + X-App-Platform (+ optional X-App-Version)
  Absent headers => unknown device (all fields nullable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from starlette.requests import Request


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


def resolve_client_device_from_headers(headers) -> ClientDeviceContext:
    getter = headers.get if hasattr(headers, "get") else lambda key, default=None: headers.get(key, default)
    return resolve_client_device(
        x_app_platform=getter("x-app-platform") or getter("X-App-Platform"),
        x_device_id_hash=getter("x-device-id-hash") or getter("X-Device-Id-Hash"),
        x_app_version=getter("x-app-version") or getter("X-App-Version"),
    )
