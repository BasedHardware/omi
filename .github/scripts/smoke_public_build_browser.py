#!/usr/bin/env python3
"""Execute the client public-build canary in a headless browser against a candidate."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from check_public_build_contract import (
    BROWSER_EXIT_GRACE_SECONDS,
    DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    DEFAULT_RETRY_TIMEOUT_SECONDS,
    ROOT,
    SMOKE_RETRY_ATTEMPTS,
    SMOKE_RETRY_SLEEP_SECONDS,
    load_contract,
)

DEFAULT_VIRTUAL_TIME_BUDGET_MS = 10_000
MAX_BROWSER_STDERR_CHARS = 2_000
BROWSER_VERSION_TIMEOUT_SECONDS = 5


class BrowserSmokeError(RuntimeError):
    """The candidate did not render its client public-build canary."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class RenderedDocument(str):
    """Rendered DOM with the browser stderr needed for a later content verdict."""

    stderr: str

    def __new__(cls, document: str, *, stderr: str) -> RenderedDocument:
        rendered = super().__new__(cls, document)
        rendered.stderr = stderr
        return rendered


def _captured_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _log_failure_diagnostics(*, browser: str, stdout: str, stderr: str) -> None:
    stderr_tail = _captured_text(stderr)[-MAX_BROWSER_STDERR_CHARS:]
    print(
        f"browser failure output: browser={browser} stdout_bytes={'yes' if stdout else 'no'} "
        "chrome_stderr_tail:",
        file=sys.stderr,
    )
    if stderr_tail:
        print(stderr_tail, file=sys.stderr)
    else:
        print("<empty>", file=sys.stderr)


SAFE_BROWSER_SMOKE_REASONS = frozenset(
    {
        "candidate URL must be an absolute HTTPS URL",
        "headless browser did not run",
        "headless browser timed out rendering the candidate",
        "headless browser could not render the candidate",
        "unknown public-build target",
        "client public-build canary did not become ready",
        "client public-build sha did not match",
        "no supported headless browser is available",
        "browser virtual-time budget must be a positive integer",
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
    source = os.environ if environment is None else environment
    configured = source.get("OMI_BROWSER_BIN", "").strip()
    candidates = (
        configured,
        "chrome-headless-shell",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    )
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _resolve_browser(browser: str, environment: dict[str, str] | None) -> str | None:
    """Resolve one browser candidate through PATH, including explicit paths."""

    path = environment.get("PATH") if environment is not None and "PATH" in environment else None
    return shutil.which(browser, path=path)


def _browser_version(browser: str) -> str | None:
    """Return a single-line browser version, or None when it cannot be read."""

    try:
        result = subprocess.run(
            [browser, "--version"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=BROWSER_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = _captured_text(result.stdout) or _captured_text(getattr(result, "stderr", ""))
    version = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return version.replace("\r", " ")[:300] or None


def _available_browsers(environment: dict[str, str] | None) -> tuple[str, ...]:
    """Resolve candidates and log each candidate's version once for this smoke."""

    available: list[str] = []
    version_by_path: dict[str, str | None] = {}
    for candidate in browser_candidates(environment):
        resolved = _resolve_browser(candidate, environment)
        if resolved is None:
            print(f"browser candidate: name={candidate} version=absent", file=sys.stderr)
            continue
        if resolved not in version_by_path:
            version_by_path[resolved] = _browser_version(resolved)
        version = version_by_path[resolved]
        print(
            f"browser candidate: name={candidate} path={resolved} "
            f"version={version or 'unavailable'}",
            file=sys.stderr,
        )
        if resolved not in available:
            available.append(resolved)
    return tuple(available)


def render_candidate(
    *,
    browser: str,
    base_url: str,
    timeout_seconds: int = DEFAULT_CANDIDATE_TIMEOUT_SECONDS,
    retry_timeout_seconds: int = DEFAULT_RETRY_TIMEOUT_SECONDS,
    virtual_time_budget_ms: int = DEFAULT_VIRTUAL_TIME_BUDGET_MS,
) -> RenderedDocument:
    browser_label = Path(browser).name or "browser"
    for attempt in range(SMOKE_RETRY_ATTEMPTS):
        started = time.monotonic()
        try:
            document = _render_candidate_once(
                browser=browser,
                base_url=base_url,
                timeout=timeout_seconds if attempt == 0 else retry_timeout_seconds,
                virtual_time_budget_ms=virtual_time_budget_ms,
            )
        except BrowserSmokeError as exc:
            _log_failure_diagnostics(browser=browser_label, stdout=exc.stdout, stderr=exc.stderr)
            duration = time.monotonic() - started
            print(f"attempt={attempt + 1} browser={browser_label} duration={duration:.1f}s", file=sys.stderr)
            if attempt == SMOKE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(SMOKE_RETRY_SLEEP_SECONDS)
        else:
            duration = time.monotonic() - started
            print(f"attempt={attempt + 1} browser={browser_label} duration={duration:.1f}s", file=sys.stderr)
            return document


def _render_candidate_once(
    *, browser: str, base_url: str, timeout: int, virtual_time_budget_ms: int
) -> RenderedDocument:
    try:
        with tempfile.TemporaryDirectory(prefix="omi-public-build-browser-") as profile_dir:
            result = subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-crash-reporter",
                    "--disable-breakpad",
                    "--disable-component-update",
                    "--disable-sync",
                    "--disable-features=MediaSessionService,MediaRouter",
                    "--no-first-run",
                    "--disable-gpu-sandbox",
                    f"--user-data-dir={profile_dir}",
                    f"--virtual-time-budget={virtual_time_budget_ms}",
                    "--dump-dom",
                    f"--timeout={timeout * 1000}",
                    base_url,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout + BROWSER_EXIT_GRACE_SECONDS,
            )
    except subprocess.TimeoutExpired as exc:
        raise BrowserSmokeError(
            "headless browser timed out rendering the candidate",
            stdout=_captured_text(exc.stdout),
            stderr=_captured_text(exc.stderr),
        ) from exc
    except OSError as exc:
        raise BrowserSmokeError("headless browser did not run") from exc
    if result.returncode != 0:
        raise BrowserSmokeError(
            "headless browser could not render the candidate",
            stdout=_captured_text(result.stdout),
            stderr=_captured_text(getattr(result, "stderr", "")),
        )
    return RenderedDocument(
        _captured_text(result.stdout),
        stderr=_captured_text(getattr(result, "stderr", "")),
    )


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
    virtual_time_budget_ms: int = DEFAULT_VIRTUAL_TIME_BUDGET_MS,
) -> None:
    if type(virtual_time_budget_ms) is not int or virtual_time_budget_ms <= 0:
        raise BrowserSmokeError("browser virtual-time budget must be a positive integer")
    contract = load_contract(contract_path)
    selected = contract.targets.get(target)
    if selected is None:
        raise BrowserSmokeError("unknown public-build target")
    url = absolute_https_url(base_url)
    render_url = f"{url}{selected.candidate_acceptance.path}"
    marker = selected.candidate_acceptance.marker
    wants_sha = "{sha}" in selected.candidate_acceptance.command
    sha = (expect_sha or "").strip() or None
    if wants_sha and sha is None:
        raise BrowserSmokeError("client public-build sha did not match")
    if not wants_sha:
        sha = None
    errors: list[BrowserSmokeError] = []
    browsers = _available_browsers(environment)
    for browser in browsers:
        try:
            document = render_candidate(
                browser=browser,
                base_url=render_url,
                timeout_seconds=selected.candidate_acceptance.timeout_seconds,
                retry_timeout_seconds=selected.candidate_acceptance.retry_timeout_seconds,
                virtual_time_budget_ms=virtual_time_budget_ms,
            )
        except BrowserSmokeError as exc:
            errors.append(exc)
            continue
        if not acceptance_document_matches(document, marker=marker, expect_sha=sha):
            _log_failure_diagnostics(
                browser=Path(browser).name or "browser",
                stdout=_captured_text(document),
                stderr=getattr(document, "stderr", ""),
            )
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
    parser.add_argument(
        "--virtual-time-budget-ms",
        type=int,
        default=DEFAULT_VIRTUAL_TIME_BUDGET_MS,
        help="Chrome virtual-time budget in milliseconds (default: 10000)",
    )
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    args = parser.parse_args(argv)
    try:
        smoke(
            target=args.target,
            base_url=args.base_url,
            contract_path=args.contract,
            expect_sha=args.expect_sha,
            virtual_time_budget_ms=args.virtual_time_budget_ms,
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
