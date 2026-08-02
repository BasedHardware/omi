#!/usr/bin/env python3
"""Prove that Beta's development serving plane accepts production Firebase identity.

The probe uses the fixed non-human release identity minted by
``firebase_release_probe_token.py``. It performs one bounded, reversible
release-probe write and otherwise only authenticated reads:

* ``POST /v3/memories`` on production, followed by ``GET /v3/memories`` on the
  development Python API, proves the same generated probe memory crosses the
  production Firestore authority into Beta's intended Python route. The probe
  deletes that non-human record through production in a ``finally`` block.
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
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

FIREBASE_PROJECT = "based-hardware"
PROBE_UID = "omi-release-probe"
PRODUCTION_PYTHON_API_URL = "https://api.omi.me/"
PYTHON_API_URL = "https://api.omiapi.com/"
DESKTOP_BACKEND_URL = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"
MAX_TOKEN_CHARS = 8192
MAX_RESPONSE_BYTES = 1_048_576
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


def _authenticated_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Any:
    encoded_payload = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded_payload,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if encoded_payload is not None else {}),
        },
        method=method,
    )
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            if int(response.status) != 200:
                raise ContinuityProbeError("authenticated_read")
            final_url = getattr(response, "geturl", lambda: url)()
            if (
                urllib.parse.urlsplit(final_url).scheme != "https"
                or urllib.parse.urlsplit(final_url).netloc != urllib.parse.urlsplit(url).netloc
            ):
                raise ContinuityProbeError("authenticated_read")
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ContinuityProbeError("authenticated_read")
        return json.loads(body.decode("utf-8"))
    except ContinuityProbeError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.HTTPError,
        urllib.error.URLError,
        OSError,
        TimeoutError,
    ) as error:
        raise ContinuityProbeError("authenticated_read") from error


def _prove_production_firestore_sentinel(token: str, *, opener: Callable[..., Any]) -> None:
    """Create on production, read on Beta's dev server, and clean up on production.

    A status-only read could succeed against an empty or different Firestore
    project. This isolated release-probe record makes the same generated ID
    cross the production-authority -> development-serving boundary. It belongs
    only to the non-human probe UID and is deleted even when the dev read fails.
    """

    marker = uuid.uuid4().hex
    created = _authenticated_json(
        f"{PRODUCTION_PYTHON_API_URL}v3/memories",
        token,
        method="POST",
        payload={
            "content": f"Omi release continuity probe {marker}",
            "category": "manual",
            "tags": ["release-probe-beta-continuity"],
        },
        opener=opener,
    )
    memory_id = created.get("id") if isinstance(created, dict) else None
    content = f"Omi release continuity probe {marker}"
    if not isinstance(memory_id, str) or not memory_id:
        raise ContinuityProbeError("production_sentinel")
    try:
        if (
            created.get("uid") != PROBE_UID
            or created.get("content") != content
            or created.get("tags") != ["release-probe-beta-continuity"]
        ):
            raise ContinuityProbeError("production_sentinel")
        observed = _authenticated_json(
            f"{PYTHON_API_URL}v3/memories?limit=500",
            token,
            opener=opener,
        )
        if not isinstance(observed, list) or not any(
            isinstance(memory, dict)
            and memory.get("id") == memory_id
            and memory.get("uid") == PROBE_UID
            and memory.get("content") == content
            and memory.get("tags") == ["release-probe-beta-continuity"]
            for memory in observed
        ):
            raise ContinuityProbeError("production_sentinel")
    finally:
        _authenticated_json(
            f"{PRODUCTION_PYTHON_API_URL}v3/memories/{urllib.parse.quote(memory_id, safe='')}",
            token,
            method="DELETE",
            opener=opener,
        )


def probe(token: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    validate_production_firebase_claims(token)
    _prove_production_firestore_sentinel(token, opener=opener)
    _authenticated_json(f"{DESKTOP_BACKEND_URL}v1/config/api-keys", token, opener=opener)
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
                "production_authority_url": PRODUCTION_PYTHON_API_URL,
                "operation": "production_sentinel_development_read_cleanup",
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
