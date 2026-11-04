"""Lossless JSON codec for pure folds and per-user encrypted fact payloads."""

import hashlib
import json
from datetime import datetime
from enum import Enum


def _encode(value):
    if isinstance(value, datetime):
        return {'$episode_datetime': value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_encode(v) for v in (sorted(value) if isinstance(value, (set, frozenset)) else value)]
    return value


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {'$episode_datetime'}:
            return datetime.fromisoformat(value['$episode_datetime'])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def dumps(value):
    return json.dumps(_encode(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def loads(value):
    return _decode(json.loads(value))


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()
