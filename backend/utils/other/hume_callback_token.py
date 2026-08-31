"""A signed, short-lived token that says a Hume callback belongs to a job WE submitted.

`POST /v1/agents/hume/callback` cannot be authenticated the usual way: Hume calls it, and Hume has no
user token. Until this existed, the `job_id` in the body was the only thing tying a payload to a
conversation — so anyone who learned a job id could POST arbitrary prosody predictions and have them
stored as a user's measured emotions (BACKLOG L42). Guessing is not the only way to learn one: the id
travels through Hume's dashboard, our logs, and the callback itself.

**What is signed, and why it is not the job id.** The job id is chosen by HUME and only arrives in the
response to our submission — there is nothing of ours to sign at the moment we ask. What we do choose,
just before submitting, is the Task row's own id. Signing that binds the callback to one specific
submission of ours, and the route can then check that the task the job id resolves to is that task.

Shape: ``<task_id>.<expires_at>.<signature>``, carried as the ``t`` query parameter of the callback URL
Hume is told to call back on. Mirrors the referral-code helper next door (same HMAC-SHA256 over
``ENCRYPTION_SECRET``, same urlsafe-b64 without padding), with a domain-separated prefix so a token from
one surface can never be replayed on the other.

The expiry is deliberately generous. Hume's batch prosody jobs finish in minutes, but a queue on their
side is not our business to predict, and a token that outlives its usefulness by an hour is far less
harmful than one that expires under a slow job and silently drops a user's result.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

_PREFIX = 'omi-hume-callback'
DEFAULT_TTL_SECONDS = 6 * 60 * 60


class HumeCallbackTokenError(ValueError):
    pass


def _secret(secret: Optional[bytes] = None) -> bytes:
    if secret is not None:
        return secret
    value = os.getenv('ENCRYPTION_SECRET', '')
    if len(value) < 32:
        # Loud rather than unsigned: a deployment without a signing secret must not quietly fall back to
        # an open callback, which is the hole this closes.
        raise HumeCallbackTokenError('missing_hume_callback_signing_secret')
    return value.encode('utf-8')


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _sign(signed_value: str, secret: Optional[bytes]) -> str:
    return _encode(hmac.new(_secret(secret), f'{_PREFIX}:{signed_value}'.encode('ascii'), hashlib.sha256).digest())


def mint(task_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, now: Optional[int] = None, secret=None) -> str:
    """Sign one submission. Raises rather than returning an unsigned token."""
    if not task_id or '.' in task_id:
        # '.' is the field separator; a task id carrying one would let a crafted id shift the boundaries.
        raise HumeCallbackTokenError('invalid_task_id')
    expires_at = (int(time.time()) if now is None else now) + ttl_seconds
    signed_value = f'{task_id}.{expires_at}'
    return f'{signed_value}.{_sign(signed_value, secret)}'


def task_id_from_token(token: str, *, now: Optional[int] = None, secret=None) -> str:
    """The task this callback claims to belong to, or raise. Never returns on a bad signature."""
    parts = (token or '').split('.')
    if len(parts) != 3:
        raise HumeCallbackTokenError('malformed_hume_callback_token')
    task_id, expires_at, signature = parts
    if not hmac.compare_digest(_sign(f'{task_id}.{expires_at}', secret), signature):
        raise HumeCallbackTokenError('invalid_hume_callback_signature')
    # Expiry is checked AFTER the signature, so an attacker cannot learn anything from the difference
    # between "not signed by us" and "signed by us but old".
    try:
        deadline = int(expires_at)
    except ValueError as error:
        raise HumeCallbackTokenError('malformed_hume_callback_expiry') from error
    if (int(time.time()) if now is None else now) > deadline:
        raise HumeCallbackTokenError('expired_hume_callback_token')
    return task_id


__all__ = ['mint', 'task_id_from_token', 'HumeCallbackTokenError', 'DEFAULT_TTL_SECONDS']
