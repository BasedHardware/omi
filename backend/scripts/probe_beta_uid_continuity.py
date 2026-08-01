#!/usr/bin/env python3
"""Prove that Beta's development serving plane accepts production Firebase identity.

The probe uses the fixed non-human release identity minted by
``firebase_release_probe_token.py``.  It makes only authenticated reads:

* ``GET /v3/memories?limit=1`` on the development Python API proves a Firebase
  UID can read its Firestore-scoped data through the intended Beta Python route.
* ``GET /v1/config/api-keys`` on the development desktop backend proves that
  same production Firebase token is accepted by the Gemini/embedding proxy
  authority without exposing the returned key material.

It deliberately never prints bearer tokens, response bodies, or customer data.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any, Callable

FIREBASE_PROJECT = "based-hardware"
PROBE_UID = "omi-release-probe"
PYTHON_API_URL = "https://api.omiapi.com/"
DESKTOP_BACKEND_URL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"
MAX_TOKEN_CHARS = 8192
TIMEOUT_SECONDS = 30


class ContinuityProbeError(RuntimeError):
    """A public, content-free release-proof failure."""


def _private_file_text(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or stat.S_IMODE(file_stat.st_mode) & 0o077:
            raise ContinuityProbeError("token_file")
        payload = os.read(descriptor, MAX_TOKEN_CHARS + 1).decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise ContinuityProbeError("token_file") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not payload or len(payload) > MAX_TOKEN_CHARS or any(character.isspace() for character in payload):
        raise ContinuityProbeError("token_file")
    return payload


def _jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ContinuityProbeError("token_claims")
    try:
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ContinuityProbeError("token_claims") from error
    if not isinstance(claims, dict):
        raise ContinuityProbeError("token_claims")
    return claims


def validate_production_firebase_claims(token: str) -> None:
    claims = _jwt_claims(token)
    expected = {
        "aud": FIREBASE_PROJECT,
        "iss": f"https://securetoken.google.com/{FIREBASE_PROJECT}",
        "sub": PROBE_UID,
        "user_id": PROBE_UID,
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise ContinuityProbeError("token_claims")


def _authenticated_get(
    url: str,
    token: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            if int(response.status) != 200:
                raise ContinuityProbeError("authenticated_read")
            # Consume a byte so a malformed, immediately aborted response cannot
            # count as a successful read. Never retain or inspect body content.
            response.read(1)
    except ContinuityProbeError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as error:
        raise ContinuityProbeError("authenticated_read") from error


def probe(token: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    validate_production_firebase_claims(token)
    _authenticated_get(f"{PYTHON_API_URL}v3/memories?limit=1", token, opener=opener)
    _authenticated_get(f"{DESKTOP_BACKEND_URL}v1/config/api-keys", token, opener=opener)
    return {
        "schema_version": 1,
        "status": "passed",
        "firebase_auth": {
            "project": FIREBASE_PROJECT,
            "release_probe_uid": PROBE_UID,
            "token_claims": "production_project_verified",
        },
        "development_serving_reads": {
            "python": {
                "url": PYTHON_API_URL,
                "operation": "authenticated_firestore_user_read",
                "status": "passed",
            },
            "desktop_backend": {
                "url": DESKTOP_BACKEND_URL,
                "operation": "authenticated_proxy_authority_read",
                "status": "passed",
            },
        },
        "redaction": {"customer_content_printed": False, "tokens_printed": False},
    }


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ContinuityProbeError("evidence_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        encoded = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    except OSError as error:
        raise ContinuityProbeError("evidence_path") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove production Firebase UID continuity for the Beta serving plane.")
    parser.add_argument("--bearer-token-file", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = probe(_private_file_text(args.bearer_token_file))
        _write_private_json(args.evidence, result)
    except ContinuityProbeError as error:
        print(f"beta UID continuity probe failed: {error}", file=sys.stderr)
        return 1
    print("beta UID continuity accepted: production Firebase identity read both development serving authorities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
