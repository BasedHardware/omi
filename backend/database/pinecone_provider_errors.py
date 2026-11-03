"""Only explicit provider namespace absence is a successful delete no-op."""

import json
from typing import Any
from uuid import uuid4

BARRIER_ID = '__omi_partition_freshness_v1'


def barrier_record(dimension: int) -> dict:
    """An internal namespace watermark, excluded by every owner UID filter."""
    return {
        'id': BARRIER_ID,
        'values': [1.0] + [0.0] * (dimension - 1),
        'metadata': {'_omi_internal': 'partition_freshness', 'nonce': uuid4().hex},
    }


def is_missing_namespace(error: Exception) -> bool:
    status = getattr(error, 'status', None)
    body: Any = getattr(error, 'body', None)
    response = getattr(error, 'response', None)
    if response is not None:
        status = response.status_code
        body = response.text
    if status != 404:
        return False
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get('code') == 5 and payload.get('message') == 'Namespace not found'
