from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def stable_hash(*parts: Any, length: int = 32) -> str:
    payload = "\x1f".join(canonical_json(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def stable_hmac(key: str, value: str, length: int = 32) -> str:
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()[:length]


class StableIdFactory:
    def __init__(self, namespace: str):
        self.namespace = namespace

    def new_id(self, prefix: str, *parts: Any) -> str:
        return f"{prefix}_{stable_hash(self.namespace, prefix, *parts, length=24)}"
