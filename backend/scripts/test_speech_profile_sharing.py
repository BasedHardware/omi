#!/usr/bin/env python3
"""Smoke test for speech profile sharing endpoints.

Usage:
    TOKEN_A=<jwt_a> TOKEN_B=<jwt_b> python backend/scripts/test_speech_profile_sharing.py
"""
from __future__ import annotations

import os
import sys

import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TOKEN_A = os.environ["TOKEN_A"]   # sharer
TOKEN_B = os.environ["TOKEN_B"]   # recipient

_headers = lambda token: {"Authorization": f"Bearer {token}"}  # noqa: E731


def _uid_from_token(token: str) -> str:
    """Decode uid from Firebase JWT (base64, no verification needed for smoke test)."""
    import base64, json as _json
    payload = token.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return _json.loads(base64.urlsafe_b64decode(payload))["user_id"]


def test_share() -> str:
    uid_b = _uid_from_token(TOKEN_B)
    resp = requests.post(
        f"{BASE_URL}/v3/speech-profile/share",
        json={"recipient_user_id": uid_b, "display_name": "Alice"},
        headers=_headers(TOKEN_A),
        timeout=10,
    )
    assert resp.status_code == 200, f"share failed: {resp.text}"
    share_id = resp.json()["share_id"]
    print(f"[PASS] share  → share_id={share_id}")
    return share_id


def test_duplicate_share_rejected() -> None:
    uid_b = _uid_from_token(TOKEN_B)
    resp = requests.post(
        f"{BASE_URL}/v3/speech-profile/share",
        json={"recipient_user_id": uid_b, "display_name": "Alice"},
        headers=_headers(TOKEN_A),
        timeout=10,
    )
    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
    print("[PASS] duplicate share → 409 Conflict")


def test_list_shared() -> None:
    resp = requests.get(
        f"{BASE_URL}/v3/speech-profile/shared",
        headers=_headers(TOKEN_B),
        timeout=10,
    )
    assert resp.status_code == 200, f"list failed: {resp.text}"
    data = resp.json()
    assert len(data) >= 1, "expected at least one shared profile"
    assert data[0]["display_name"] == "Alice"
    print(f"[PASS] list   → {len(data)} profiles")


def test_revoke() -> None:
    uid_b = _uid_from_token(TOKEN_B)
    resp = requests.post(
        f"{BASE_URL}/v3/speech-profile/revoke",
        json={"recipient_user_id": uid_b},
        headers=_headers(TOKEN_A),
        timeout=10,
    )
    assert resp.status_code == 200, f"revoke failed: {resp.text}"
    print("[PASS] revoke → success")


def test_revoke_gone() -> None:
    uid_b = _uid_from_token(TOKEN_B)
    resp = requests.post(
        f"{BASE_URL}/v3/speech-profile/revoke",
        json={"recipient_user_id": uid_b},
        headers=_headers(TOKEN_A),
        timeout=10,
    )
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"
    print("[PASS] double-revoke → 404 Not Found")


def test_list_empty_after_revoke() -> None:
    resp = requests.get(
        f"{BASE_URL}/v3/speech-profile/shared",
        headers=_headers(TOKEN_B),
        timeout=10,
    )
    data = resp.json()
    assert not any(d["sharer_uid"] == _uid_from_token(TOKEN_A) for d in data)
    print("[PASS] list after revoke → profile absent")


if __name__ == "__main__":
    try:
        test_share()
        test_duplicate_share_rejected()
        test_list_shared()
        test_revoke()
        test_revoke_gone()
        test_list_empty_after_revoke()
        print("\n✅ All smoke tests passed.")
    except AssertionError as exc:
        print(f"\n❌ FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
