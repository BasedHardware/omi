"""Unit tests for ChatGPT / Codex tier enrollment (standalone, no Firestore imports)."""

import re
from datetime import datetime, timedelta, timezone

_SHA256_HEX_RE = re.compile(r'^[a-f0-9]{64}$')
_SHA256 = 'a' * 64
_CHATGPT_TTL_SECONDS = 7 * 24 * 60 * 60


def _is_chatgpt_active_state(state: dict) -> bool:
    if not state.get('active'):
        return False
    last_seen = state.get('last_seen_at')
    if not isinstance(last_seen, datetime):
        return False
    age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    return age <= _CHATGPT_TTL_SECONDS


def test_fingerprint_must_be_sha256_hex():
    assert _SHA256_HEX_RE.match(_SHA256)
    assert not _SHA256_HEX_RE.match('not-hex')
    assert not _SHA256_HEX_RE.match('A' * 64)


def test_chatgpt_active_ttl():
    fresh = {'active': True, 'last_seen_at': datetime.now(timezone.utc) - timedelta(days=1)}
    assert _is_chatgpt_active_state(fresh) is True

    stale = {'active': True, 'last_seen_at': datetime.now(timezone.utc) - timedelta(days=30)}
    assert _is_chatgpt_active_state(stale) is False

    inactive = {'active': False, 'last_seen_at': datetime.now(timezone.utc)}
    assert _is_chatgpt_active_state(inactive) is False
