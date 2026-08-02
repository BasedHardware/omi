from collections.abc import Mapping
from typing import Any

ALLOWED_AGENT_VM_BACKEND_URLS = frozenset({"https://api.omi.me", "https://api.omiapi.com"})


def validate_agent_vm_backend_url(value: str) -> str:
    backend_url = value.strip().rstrip("/")
    if backend_url not in ALLOWED_AGENT_VM_BACKEND_URLS:
        raise RuntimeError("agent VM backend URL is not an allowed backend")
    return backend_url


def backend_url_metadata(instance: Mapping[str, Any], backend_url: str) -> dict[str, Any] | None:
    backend_url = validate_agent_vm_backend_url(backend_url)
    metadata = instance.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RuntimeError("GCE instance metadata is unavailable")
    fingerprint = metadata.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise RuntimeError("GCE instance metadata fingerprint is unavailable")
    raw_items = metadata.get("items", [])
    if not isinstance(raw_items, list):
        raise RuntimeError("GCE instance metadata items are invalid")

    items: list[dict[str, Any]] = []
    current_backend_url: str | None = None
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise RuntimeError("GCE instance metadata item is invalid")
        key = item.get("key")
        if key == "backend-url":
            value = item.get("value")
            current_backend_url = value if isinstance(value, str) else None
            continue
        items.append(dict(item))

    if current_backend_url == backend_url:
        return None

    items.append({"key": "backend-url", "value": backend_url})
    return {"fingerprint": fingerprint, "items": items}
