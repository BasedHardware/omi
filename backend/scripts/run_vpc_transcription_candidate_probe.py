#!/usr/bin/env python3
"""Run the known-audio candidate gate from a VPC-connected Cloud Run Job.

The temporary job identity mints its own Cloud Run identity token for the exact
tagged candidate.  The deploy runner supplies the short-lived Firebase token
only as a job environment value; neither credential is emitted in the report.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path

from transcription_capability_probe import ProbeConfig, build_report

METADATA_IDENTITY_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing {name}")
    return value


def _identity_token(audience: str) -> str:
    request = urllib.request.Request(
        f"{METADATA_IDENTITY_URL}?audience={urllib.parse.quote(audience, safe='')}",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        token = response.read(8193).decode("utf-8").strip()
    if not token or len(token) > 8192:
        raise RuntimeError("invalid Cloud Run identity token")
    return token


def main() -> int:
    candidate_url = _required_env("CANDIDATE_API_URL")
    firebase_token = _required_env("FIREBASE_PROBE_TOKEN")
    identity_token = _identity_token(candidate_url)
    report = build_report(
        ProbeConfig(
            fixture_path=Path("testing/release_fixtures/transcription-release-probe.wav"),
            manifest_path=Path("testing/release_fixtures/transcription-release-probe.json"),
            api_url=candidate_url,
            bearer_token=firebase_token,
            cloud_run_identity_token=identity_token,
            timeout_seconds=30.0,
        )
    )
    firebase_token = ""
    identity_token = ""
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
