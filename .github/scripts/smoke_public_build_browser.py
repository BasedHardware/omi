#!/usr/bin/env python3
"""Execute the client public-build canary in a headless browser against a candidate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from check_public_build_contract import ROOT, load_contract


class BrowserSmokeError(RuntimeError):
    """The candidate did not render its client public-build canary."""


SAFE_BROWSER_SMOKE_REASONS = frozenset(
    {
        "candidate URL must be an absolute HTTPS URL",
        "headless browser did not run",
        "headless browser could not render the candidate",
        "unknown public-build target",
        "client public-build canary did not become ready",
        "client public-build sha did not match",
        "no supported headless browser is available",
    }
)


def sanitized_browser_smoke_reason(error: BrowserSmokeError) -> str:
    """Return a useful, non-sensitive diagnostic for CI output."""

    reason = str(error)
    if reason in SAFE_BROWSER_SMOKE_REASONS:
        return reason
    return "unspecified browser smoke failure"


def absolute_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or value != value.strip():
        raise BrowserSmokeError("candidate URL must be an absolute HTTPS URL")
    return value.rstrip("/")


def browser_candidates(environment: dict[str, str] | None = None) -> tuple[str, ...]:
    configured = (environment or os.environ).get("OMI_BROWSER_BIN", "").strip()
    return tuple(
        candidate
        for candidate in (configured, "google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
        if candidate
    )


def render_candidate(*, browser: str, base_url: str) -> str:
    try:
        result = subprocess.run(
            [
                browser,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--dump-dom",
                base_url,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BrowserSmokeError("headless browser did not run") from exc
    if result.returncode != 0:
        raise BrowserSmokeError("headless browser could not render the candidate")
    return result.stdout


def acceptance_document_matches(
    document: str,
    *,
    marker: str,
    expect_sha: str | None = None,
) -> bool:
    """Return whether dumped DOM satisfies the ready marker and optional revision SHA."""

    if f'data-omi-public-build-canary="{marker}"' not in document:
        return False
    if expect_sha is not None and f'data-omi-public-build-sha="{expect_sha}"' not in document:
        return False
    return True


def smoke(
    *,
    target: str,
    base_url: str,
    contract_path: Path,
    environment: dict[str, str] | None = None,
    expect_sha: str | None = None,
) -> None:
    contract = load_contract(contract_path)
    selected = contract.targets.get(target)
    if selected is None:
        raise BrowserSmokeError("unknown public-build target")
    url = absolute_https_url(base_url)
    marker = selected.candidate_acceptance.marker
    wants_sha = "{sha}" in selected.candidate_acceptance.command
    sha = (expect_sha or "").strip() or None
    if wants_sha and sha is None:
        raise BrowserSmokeError("client public-build sha did not match")
    if not wants_sha:
        sha = None
    errors: list[BrowserSmokeError] = []
    for browser in browser_candidates(environment):
        try:
            document = render_candidate(browser=browser, base_url=url)
        except BrowserSmokeError as exc:
            errors.append(exc)
            continue
        if not acceptance_document_matches(document, marker=marker, expect_sha=sha):
            if sha is not None and f'data-omi-public-build-canary="{marker}"' in document:
                raise BrowserSmokeError("client public-build sha did not match")
            raise BrowserSmokeError("client public-build canary did not become ready")
        return
    if errors:
        raise errors[-1]
    raise BrowserSmokeError("no supported headless browser is available")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expect-sha", default="")
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    args = parser.parse_args(argv)
    try:
        smoke(
            target=args.target,
            base_url=args.base_url,
            contract_path=args.contract,
            expect_sha=args.expect_sha,
        )
    except BrowserSmokeError as exc:
        print(
            f"public-build browser smoke failed: target={args.target} " f"reason={sanitized_browser_smoke_reason(exc)}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError):
        print(f"public-build browser smoke failed: target={args.target}", file=sys.stderr)
        return 1
    print(f"public-build browser smoke passed: target={args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
