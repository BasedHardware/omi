"""Read-only pod/abandon proof plus opt-in server-observed token leases."""

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time
from config.record_audio import PRODUCER_START_MARGIN_SECONDS
from config import record_seal_rules as lease

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


def producer_tokens_dead(tokens, proof, *, producers_stopped=False, uid=None, row=None, job=None, lease_shadow=False):
    if not isinstance(tokens, dict):
        return False
    proof_valid = proof is not None and (
        proof.get('namespace') == NAMESPACE
        and isinstance(proof.get('pods'), dict)
        and 0 <= time.time() - proof.get('captured_at', 0) <= 300
    )
    if proof is not None and not proof_valid and not tokens:
        return False  # Cluster repair also uses the empty map to validate inventory freshness.
    use_lease = lease.token_lease_serving(uid) or (lease_shadow and lease.token_lease_mode() != 'off')
    now = time.time()
    for value in tokens.values():
        if value is True:
            if not producers_stopped or (proof is not None and not proof_valid):
                return False
            continue  # Explicit operator fallback for pre-identity tokens only.
        if not isinstance(value, dict):
            return False
        pod, started = value.get('pod'), value.get('process_started_at')
        if (
            not isinstance(started, (int, float))
            or isinstance(started, bool)
            or not math.isfinite(started)
            or not 0 < started
        ):
            return False
        # Only serve can mint the podless custody fence. Its own observed
        # lease remains its exit after rollback; frame pod proof is unchanged.
        if pod == '' and value.get('signal_source') == 'custody_append':
            if not lease.token_lease_lapsed(value, now, row=row, job=job):
                return False
            continue
        if use_lease:
            clocks = lease.token_lease_clocks(value, row=row, job=job)
            if clocks:
                signal = lease.lease_timestamp(value.get('last_signal_at'))
                abandoned = lease.lease_timestamp(value.get('abandoned_at'))
                # Observed activity supersedes earlier stoppage evidence, even
                # if a stale token still carries that evidence after renewal.
                # A computed stock seed is never evidence of activity.
                if signal and (
                    (abandoned and abandoned >= started and signal > abandoned)
                    or (proof_valid and signal > proof['captured_at'])
                ):
                    return False
                if lease.token_lease_lapsed(value, now, row=row, job=job):
                    continue
                # A custody uploader can outlive its pusher. Actual server
                # signals re-fence an abandoned/gone identity. A computed stock
                # seed is not a live signal and preserves the original proofs.
                if 'last_signal_at' in value:
                    return False
        if 'abandoned_at' in value:
            abandoned = value['abandoned_at']
            if (
                not isinstance(abandoned, (int, float))
                or isinstance(abandoned, bool)
                or not math.isfinite(abandoned)
                or abandoned < started
            ):
                return False
            continue  # Producer attested stoppage after settling all executor I/O.
        if (
            not isinstance(pod, str)
            or not pod
            or not proof_valid
            or started + PRODUCER_START_MARGIN_SECONDS > proof['captured_at']
        ):
            return False
        if pod not in proof['pods']:
            continue
        current_start = proof['pods'][pod]
        if current_start is None or current_start <= started + PRODUCER_START_MARGIN_SECONDS:
            return False
    return True


def leases_would_release(tokens, proof, *, uid=None, row=None, job=None, producers_stopped=False):
    """Content-free shadow diagnostic; never grants write authority."""
    return bool(
        tokens
        and lease.token_lease_mode() != 'off'
        and producer_tokens_dead(
            tokens,
            proof,
            uid=uid,
            row=row,
            job=job,
            producers_stopped=producers_stopped,
            lease_shadow=True,
        )
        and any(lease.token_lease_lapsed(value, time.time(), row=row, job=job) for value in tokens.values())
    )
