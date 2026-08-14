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


def smoke(*, target: str, base_url: str, contract_path: Path, environment: dict[str, str] | None = None) -> None:
    contract = load_contract(contract_path)
    selected = contract.targets.get(target)
    if selected is None:
        raise BrowserSmokeError("unknown public-build target")
    url = absolute_https_url(base_url)
    expected = f'data-omi-public-build-canary="{selected.candidate_acceptance.marker}"'
    errors: list[BrowserSmokeError] = []
    for browser in browser_candidates(environment):
        try:
            document = render_candidate(browser=browser, base_url=url)
        except BrowserSmokeError as exc:
            errors.append(exc)
            continue
        if expected not in document:
            raise BrowserSmokeError("client public-build canary did not become ready")
        return
    if errors:
        raise errors[-1]
    raise BrowserSmokeError("no supported headless browser is available")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    args = parser.parse_args(argv)
    try:
        smoke(target=args.target, base_url=args.base_url, contract_path=args.contract)
    except (OSError, ValueError, BrowserSmokeError):
        print(f"public-build browser smoke failed: target={args.target}", file=sys.stderr)
        return 1
    print(f"public-build browser smoke passed: target={args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
