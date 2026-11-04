"""Read-only pod inventory proof for abandoned recording producers; no TTL."""

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time
from config.record_audio import PRODUCER_START_MARGIN_SECONDS

NAMESPACE = 'prod-omi-backend'


def _timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timezone-aware producer proof required')
    return parsed.timestamp()


def load_pusher_pod_proof(path, captured_at):
    return parse_pusher_pod_proof(Path(path).read_bytes(), captured_at)


def parse_pusher_pod_proof(payload, captured_at):
    """Shared file/API parser; callers never need to persist cluster inventory."""
    raw = json.loads(payload)
    captured = _timestamp(captured_at)
    if not math.isfinite(captured) or not 0 <= time.time() - captured <= 300:
        raise ValueError('fresh pod inventory required')
    if (
        raw.get('kind') not in {'List', 'PodList'}
        or raw.get('apiVersion') != 'v1'
        or not (raw.get('metadata') or {}).get('resourceVersion')
        or (raw.get('metadata') or {}).get('continue')
        or not isinstance(raw.get('items'), list)
    ):
        raise ValueError('authoritative pod list required')
    pods = {}
    for item in raw['items']:
        metadata = item.get('metadata') or {}
        name = metadata.get('name')
        if (
            metadata.get('namespace') != NAMESPACE
            or not isinstance(name, str)
            or not name
            or (metadata.get('labels') or {}).get('app.kubernetes.io/name') != 'pusher'
            or name in pods
        ):
            raise ValueError('scoped pusher pod list required')
        statuses = (item.get('status') or {}).get('containerStatuses') or []
        starts = []
        for status in statuses:
            started = ((status.get('state') or {}).get('running') or {}).get('startedAt')
            if not started:
                starts = []
                break
            value = _timestamp(started)
            if not math.isfinite(value) or value > captured:
                raise ValueError('invalid pod start proof')
            starts.append(value)
        # Every regular container must be newer to prove a process restart.
        # An unknown/mixed-age sidecar makes the proof conservative.
        pods[name] = min(starts) if starts else None
    return {
        'namespace': NAMESPACE,
        'captured_at': captured,
        'resource_version': raw['metadata']['resourceVersion'],
        'pods': pods,
        'file_sha256': hashlib.sha256(payload).hexdigest(),
    }


def producer_tokens_dead(tokens, proof, *, producers_stopped=False):
    if not isinstance(tokens, dict):
        return False
    if proof is not None:
        if (
            proof.get('namespace') != NAMESPACE
            or not isinstance(proof.get('pods'), dict)
            or not 0 <= time.time() - proof.get('captured_at', 0) <= 300
        ):
            return False
    for value in tokens.values():
        if value is True:
            if not producers_stopped:
                return False
            continue  # Explicit operator fallback for pre-identity tokens only.
        if not isinstance(value, dict) or proof is None:
            return False
        pod, started = value.get('pod'), value.get('process_started_at')
        if (
            not isinstance(pod, str)
            or not pod
            or not isinstance(started, (int, float))
            or isinstance(started, bool)
            or not math.isfinite(started)
            or not 0 < started
            or started + PRODUCER_START_MARGIN_SECONDS > proof['captured_at']
        ):
            return False
        if pod not in proof['pods']:
            continue
        current_start = proof['pods'][pod]
        if current_start is None or current_start <= started + PRODUCER_START_MARGIN_SECONDS:
            return False
    return True
