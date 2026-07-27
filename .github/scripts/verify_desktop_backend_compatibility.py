#!/usr/bin/env python3
"""Verify the narrow desktop-backend /health chat compatibility contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


EXPECTED_STATUS = "healthy"
EXPECTED_SERVICE = "omi-desktop-backend"
PRODUCTION_BASE_URL = "https://desktop-backend-hhibjajaja-uc.a.run.app"
CONTRACT_VERSION_RE = re.compile(r"^[1-9][0-9]{0,5}$")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_RESPONSE_BYTES = 1024 * 1024
_MISSING = object()


class CompatibilityError(RuntimeError):
    """The health endpoint did not prove the required compatibility contract."""


def _describe_actual(value: object) -> object:
    if value is _MISSING:
        return "<missing>"
    return f"<redacted {type(value).__name__}>"


def validate_compatibility(
    payload: object,
    *,
    expected_contract_version: str,
) -> dict[str, object]:
    """Validate and return only the bounded compatibility fields."""
    if not isinstance(payload, dict):
        raise CompatibilityError("health response must be a JSON object")
    expected = {
        "status": EXPECTED_STATUS,
        "service": EXPECTED_SERVICE,
        "chat_contract_version": expected_contract_version,
    }
    mismatches: dict[str, dict[str, object]] = {}
    for field, expected_value in expected.items():
        actual = payload.get(field, _MISSING)
        if actual != expected_value:
            mismatches[field] = {
                "actual": _describe_actual(actual),
                "expected": expected_value,
            }
    if mismatches:
        raise CompatibilityError(
            "health response is incompatible: "
            f"{json.dumps(mismatches, sort_keys=True, separators=(',', ':'))}"
        )
    return {
        "chat_contract_version": expected_contract_version,
        "service": EXPECTED_SERVICE,
        "status": EXPECTED_STATUS,
    }


def _health_url(base_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base_url)
        _ = parsed.port
    except ValueError as error:
        raise CompatibilityError("base URL has an invalid port") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CompatibilityError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CompatibilityError("base URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise CompatibilityError("base URL must not contain a path")
    hostname = parsed.hostname.lower()
    if hostname not in LOOPBACK_HOSTS:
        production = urllib.parse.urlsplit(PRODUCTION_BASE_URL)
        if (
            parsed.scheme != production.scheme
            or hostname != production.hostname
            or parsed.port not in {None, 443}
        ):
            raise CompatibilityError(
                "non-loopback base URL must use the canonical production desktop-backend origin"
            )
    return f"{base_url.rstrip('/')}/health"


def request_health(base_url: str, *, timeout_seconds: float) -> object:
    request = urllib.request.Request(
        _health_url(base_url),
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise CompatibilityError(f"health request returned HTTP {error.code}") from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise CompatibilityError("health request failed before a valid HTTP response") from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise CompatibilityError(f"health response exceeds {MAX_RESPONSE_BYTES} bytes")
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompatibilityError("health response is not valid UTF-8 JSON") from error


def verify_base_url(
    base_url: str,
    *,
    expected_contract_version: str,
    timeout_seconds: float = 15.0,
) -> dict[str, object]:
    compatibility = validate_compatibility(
        request_health(base_url, timeout_seconds=timeout_seconds),
        expected_contract_version=expected_contract_version,
    )
    return {"schema_version": 1, **compatibility}


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-contract-version", default="1")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)

    if not CONTRACT_VERSION_RE.fullmatch(args.expected_contract_version):
        parser.error("--expected-contract-version must be a positive decimal version")
    if not 0 < args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be greater than 0 and at most 60")

    try:
        evidence = verify_base_url(
            args.base_url,
            expected_contract_version=args.expected_contract_version,
            timeout_seconds=args.timeout_seconds,
        )
    except CompatibilityError as error:
        print(f"desktop-backend compatibility failed: {error}", file=sys.stderr)
        return 1

    _write_evidence(args.evidence, evidence)
    print(
        "desktop-backend compatibility verified: "
        f"service={EXPECTED_SERVICE} contract={args.expected_contract_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
