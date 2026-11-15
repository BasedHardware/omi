"""Share membership observations without extending the existing sixty-second lease."""

import hashlib
import json
import logging
import os
import time
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from database.firestore_cache_metrics import record_request
from database.redis_connection import create_bounded_redis_client
from database.fsr_cache_telemetry import record_fallback

logger = logging.getLogger(__name__)
TTL_SECONDS = 60
MAX_ENTRY_BYTES = 64 * 1024
_READ = """
local now = redis.call('TIME')
return {redis.call('GET', KEYS[1]) or '', now[1] * 1000 + math.floor(now[2] / 1000)}
"""
_PUBLISH = """
local now = redis.call('TIME')
local remaining = tonumber(ARGV[2]) - (now[1] * 1000 + math.floor(now[2] / 1000))
if remaining > 0 then return redis.call('SET', KEYS[1], ARGV[1], 'PX', remaining, 'NX') end
return 0
"""


class MembershipObservation(dict):
    """A dict whose local lease ends at the original shared observation deadline."""

    def __init__(self, value, deadline):
        super().__init__(value)
        self.deadline = deadline


@lru_cache(maxsize=1)
def _redis():
    return create_bounded_redis_client(0.1)


def enabled():
    return os.getenv('OMI_ROLLOUT_MEMBERSHIP_SHARED_CACHE_ENABLED', '').strip().lower() != 'false'


@lru_cache(maxsize=2)
def _cipher(secret):
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'rollout-membership-cache-v1').derive(
        secret.encode()
    )
    return AESGCM(key)


def _valid(value):
    return isinstance(value, dict) and all(
        isinstance(flags, dict) and all(type(flag) is bool for flag in flags.values()) for flags in value.values()
    )


def _fallback():
    record_request('rollout_membership_shared', 'error')
    record_fallback(
        component='redis_cache',
        from_mode='rollout_membership',
        to_mode='firestore',
        reason='unavailable',
        outcome='degraded',
        log=logger,
    )


def read_memberships_cached(uid, client, fetch):
    secret = os.getenv('ENCRYPTION_SECRET', '')
    if not enabled() or not secret or os.getenv('FIRESTORE_EMULATOR_HOST'):
        return fetch()
    # Unknown/injected clients must never share another data plane's entries.
    project, database = getattr(client, 'project', None), getattr(client, '_database', None)
    if not isinstance(project, str) or not isinstance(database, str):
        return fetch()
    scope = hashlib.sha256(json.dumps([project, database, uid], separators=(',', ':')).encode()).hexdigest()
    key = 'rollout-membership:v1:' + scope
    started = time.monotonic()
    try:
        raw, observed_ms = _redis().eval(_READ, 1, key)
        observed_ms = int(observed_ms)
        envelope = (
            json.loads(_cipher(secret).decrypt(raw[:12], raw[12:], scope.encode()))
            if raw and len(raw) <= MAX_ENTRY_BYTES
            else None
        )
        if (
            isinstance(envelope, dict)
            and envelope.get('scope') == scope
            and type(envelope.get('deadline_ms')) is int
            and observed_ms < envelope['deadline_ms'] <= observed_ms + TTL_SECONDS * 1000
            and _valid(envelope.get('members'))
        ):
            deadline = started + (envelope['deadline_ms'] - observed_ms) / 1000
            if deadline > time.monotonic():
                record_request('rollout_membership_shared', 'hit')
                return MembershipObservation(envelope['members'], deadline)
    except Exception:
        _fallback()
        return fetch()
    # Exceptions/malformed documents never produce a shared denial or renew a lease.
    record_request('rollout_membership_shared', 'miss')
    members = fetch()
    if not _valid(members):
        return members
    deadline_ms = observed_ms + TTL_SECONDS * 1000
    try:
        nonce = os.urandom(12)
        payload = json.dumps({'scope': scope, 'deadline_ms': deadline_ms, 'members': members}).encode()
        envelope = nonce + _cipher(secret).encrypt(nonce, payload, scope.encode())
        if len(envelope) <= MAX_ENTRY_BYTES:
            stored = _redis().eval(_PUBLISH, 1, key, envelope, deadline_ms)
            record_request('rollout_membership_shared', 'stored' if stored else 'expired_or_populated')
    except Exception:
        _fallback()
    return MembershipObservation(members, started + TTL_SECONDS)
