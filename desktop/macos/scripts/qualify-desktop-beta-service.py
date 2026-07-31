#!/usr/bin/env python3
"""Autonomously qualify a desktop beta candidate tag (evidence-only, no promote).

Generic replacement for per-version `omi-macos-0NN-qualification-service.py`
scripts. Takes the release tag as a CLI argument, discovers tools and paths at
runtime, persists retry state, dual-logs to stdout and a file, exposes a small
health endpoint for watchdog probes, and shuts down cleanly on SIGTERM/SIGINT.

Usage:
  qualify-desktop-beta-service.py v0.12.89+12089-macos
  qualify-desktop-beta-service.py --health-port 8765 --interval 300 TAG

Environment (all optional):
  OMI_QUAL_REPO_CACHE     Bare/mirror clone used as worktree parent
                          (default: ~/.cache/hermes/omi)
  OMI_QUAL_STATE_DIR      State JSON directory (default: ~/.hermes/state)
  OMI_QUAL_LOG_DIR        Log directory (default: ~/.hermes/logs)
  OMI_QUAL_REPO           GitHub repo slug (default: BasedHardware/omi)
  PYTHON                  Python used inside qualify-desktop-beta.sh
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REQUIRED_ASSETS = {"Omi.zip", "desktop-smoke-result.json"}
DEFAULT_INTERVAL = 300
MAX_INTERVAL = 1800
BACKOFF_FACTOR = 1.5
QUALIFY_TIMEOUT = 3600


class ShutdownRequested(Exception):
    """Raised when a signal asks the service loop to exit."""


class ServiceState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.phase = "starting"
        self.tag = ""
        self.attempt = 0
        self.detail = ""
        self.started_at = now()
        self.updated_at = self.started_at
        self.shutdown = False
        self.last_heartbeat = self.started_at

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "ok": not self.shutdown,
                "phase": self.phase,
                "tag": self.tag,
                "attempt": self.attempt,
                "detail": self.detail[-500:] if self.detail else "",
                "started_at": self.started_at,
                "updated_at": self.updated_at,
                "last_heartbeat": self.last_heartbeat,
                "pid": os.getpid(),
            }

    def update(self, **values: Any) -> None:
        with self.lock:
            for key, value in values.items():
                setattr(self, key, value)
            self.updated_at = now()
            self.last_heartbeat = self.updated_at

    def request_shutdown(self) -> None:
        with self.lock:
            self.shutdown = True
            self.phase = "shutting_down"
            self.updated_at = now()

    def should_stop(self) -> bool:
        with self.lock:
            return self.shutdown


LOG = logging.getLogger("qualify-desktop-beta-service")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


STATE = ServiceState()


def tag_slug(tag: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "-" for ch in tag)


def which(name: str, *fallbacks: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for candidate in fallbacks:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise FileNotFoundError(f"required executable not found on PATH: {name}")


def discover_python() -> str:
    env = os.environ.get("PYTHON")
    if env and Path(env).is_file():
        return env
    home = Path.home()
    for candidate in (
        home / "workspace/omi/backend/.venv/bin/python",
        home / ".cache/hermes/omi/backend/.venv/bin/python",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return which("python3", "/opt/homebrew/bin/python3", "/usr/bin/python3")


def discover_repo_cache() -> Path:
    override = os.environ.get("OMI_QUAL_REPO_CACHE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache/hermes/omi"


def state_path_for(tag: str) -> Path:
    root = Path(os.environ.get("OMI_QUAL_STATE_DIR", Path.home() / ".hermes/state")).expanduser()
    return root / f"qualify-desktop-beta-{tag_slug(tag)}.json"


def log_path_for(tag: str) -> Path:
    root = Path(os.environ.get("OMI_QUAL_LOG_DIR", Path.home() / ".hermes/logs")).expanduser()
    return root / f"qualify-desktop-beta-{tag_slug(tag)}.log"


def configure_logging(tag: str) -> Path:
    path = log_path_for(tag)
    path.parent.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = time.gmtime  # type: ignore[assignment]
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(path)):
        handler.setFormatter(formatter)
        LOG.addHandler(handler)
    return path


def save_state(path: Path, **values: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, object] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    current.update(values)
    current["updated_at"] = now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
    STATE.update(
        phase=str(values.get("phase", STATE.phase)),
        attempt=int(values.get("attempt", STATE.attempt) or 0),
        detail=str(values.get("detail", "") or ""),
        tag=str(values.get("tag", STATE.tag) or STATE.tag),
    )


def sleep_interruptible(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if STATE.should_stop():
            raise ShutdownRequested()
        time.sleep(min(1.0, deadline - time.monotonic()))


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def release(repo: str, tag: str, gh: str, cwd: Path) -> dict[str, object] | None:
    result = run(
        [gh, "release", "view", tag, "--repo", repo, "--json", "tagName,isDraft,isPrerelease,publishedAt,assets,url"],
        cwd=cwd,
        timeout=60,
    )
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def ready_assets(data: dict[str, object]) -> bool:
    if data.get("isDraft") or data.get("isPrerelease"):
        return False
    names = {asset.get("name") for asset in data.get("assets", []) if isinstance(asset, dict)}
    has_dmg = any(isinstance(name, str) and name.lower().endswith(".dmg") for name in names)
    return REQUIRED_ASSETS.issubset(names) and has_dmg


def qualification_asset(data: dict[str, object]) -> str | None:
    for asset in data.get("assets", []):
        if isinstance(asset, dict):
            name = asset.get("name")
            if isinstance(name, str) and name.startswith("qualification-evidence-") and name.endswith(".json"):
                return name
    return None


def ensure_repo_cache(root: Path, repo: str, git: str) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists() or (root / "HEAD").exists():
        return
    url = f"https://github.com/{repo}.git"
    LOG.info("cloning %s into %s", url, root)
    result = run([git, "clone", "--filter=blob:none", url, str(root)], timeout=600)
    if result.returncode:
        raise RuntimeError(result.stdout[-2000:] or f"git clone failed for {url}")


def ensure_worktree(root: Path, worktree: Path, tag: str, git: str, make: str) -> None:
    fetch = run([git, "-C", str(root), "fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}"], timeout=180)
    if fetch.returncode:
        raise RuntimeError(fetch.stdout[-2000:] or f"git fetch failed for {tag}")
    if not worktree.exists():
        add = run(
            [git, "-C", str(root), "worktree", "add", "--detach", str(worktree), tag],
            timeout=300,
        )
        if add.returncode:
            raise RuntimeError(add.stdout[-2000:] or f"git worktree add failed for {tag}")
        setup = run([make, "setup"], cwd=worktree, timeout=600)
        if setup.returncode:
            raise RuntimeError(setup.stdout[-2000:] or "make setup failed")
    head = run([git, "rev-parse", "HEAD"], cwd=worktree, timeout=60)
    tag_head = run([git, "rev-list", "-n1", tag], cwd=worktree, timeout=60)
    if head.returncode or tag_head.returncode or head.stdout.strip() != tag_head.stdout.strip():
        raise RuntimeError(f"qualification worktree is not at the exact tag {tag}")


def clean_stale_nested_registration(root: Path, worktree: Path, tag: str, git: str) -> None:
    nested = worktree / ".qualification-worktrees" / tag
    run([git, "-C", str(root), "worktree", "prune"], timeout=60)
    if not nested.exists():
        return
    status = run([git, "-C", str(nested), "status", "--porcelain"], timeout=60)
    if status.returncode == 0 and not status.stdout.strip():
        run([git, "-C", str(root), "worktree", "remove", "--force", str(nested)], timeout=120)
        run([git, "-C", str(root), "worktree", "prune"], timeout=60)


def qualify(worktree: Path, tag: str, python: str) -> tuple[int, str]:
    script = worktree / "desktop/macos/scripts/qualify-desktop-beta.sh"
    if not script.is_file():
        raise RuntimeError(f"missing qualifier script: {script}")
    env = os.environ.copy()
    path_parts = [
        str(Path(python).parent),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        env.get("PATH", ""),
    ]
    env.update(
        {
            "PYTHON": python,
            "PATH": ":".join(p for p in path_parts if p),
            # Only the disposable omi-qualification-* bundle (enforced by run.sh).
            "OMI_ALLOW_ADHOC_SIGN": "1",
        }
    )
    result = run([str(script), "--no-promote", tag], cwd=worktree, timeout=QUALIFY_TIMEOUT, env=env)
    return result.returncode, result.stdout


def make_health_handler() -> type[BaseHTTPRequestHandler]:
    class HealthHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            LOG.debug("health: " + format, *args)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in {"/health", "/healthz", "/"}:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(STATE.snapshot(), indent=2).encode()
            code = 503 if STATE.should_stop() else 200
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return HealthHandler


def start_health_server(port: int) -> ThreadingHTTPServer | None:
    if port <= 0:
        return None
    server = ThreadingHTTPServer(("127.0.0.1", port), make_health_handler())
    thread = threading.Thread(target=server.serve_forever, name="qual-health", daemon=True)
    thread.start()
    LOG.info("health endpoint listening on http://127.0.0.1:%s/health", port)
    return server


def install_signal_handlers() -> None:
    def _handle(signum: int, _frame: object) -> None:
        name = signal.Signals(signum).name
        LOG.info("received %s; requesting graceful shutdown", name)
        STATE.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle)


def next_interval(current: float, *, failed: bool) -> float:
    if not failed:
        return float(DEFAULT_INTERVAL)
    return min(MAX_INTERVAL, current * BACKOFF_FACTOR)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Immutable v*-macos candidate tag to qualify")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"base poll interval seconds (default {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.environ.get("OMI_QUAL_HEALTH_PORT", "8765")),
        help="loopback health HTTP port (0 disables; default 8765)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("OMI_QUAL_REPO", "BasedHardware/omi"),
        help="GitHub repo slug",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="single pass: exit after one qualify attempt or while still waiting",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    tag = args.tag.strip()
    if not tag:
        print("tag is required", file=sys.stderr)
        return 2

    log_file = configure_logging(tag)
    state_file = state_path_for(tag)
    repo_cache = discover_repo_cache()
    worktree = repo_cache / ".worktrees" / f"qualify-{tag_slug(tag)}"
    python = discover_python()
    git = which("git", "/usr/bin/git")
    gh = which("gh", "/opt/homebrew/bin/gh", "/usr/local/bin/gh")
    make = which("make", "/usr/bin/make")

    STATE.update(tag=tag, phase="starting")
    install_signal_handlers()
    health = start_health_server(args.health_port)

    LOG.info(
        "starting qualification service tag=%s state=%s log=%s cache=%s worktree=%s python=%s",
        tag,
        state_file,
        log_file,
        repo_cache,
        worktree,
        python,
    )
    save_state(
        state_file,
        phase="waiting_for_release",
        tag=tag,
        worktree=str(worktree),
        repo_cache=str(repo_cache),
        health_port=args.health_port,
    )

    attempts = 0
    interval = float(max(5, args.interval))
    exit_code = 0

    try:
        while not STATE.should_stop():
            try:
                ensure_repo_cache(repo_cache, args.repo, git)
                data = release(args.repo, tag, gh, repo_cache)
            except ShutdownRequested:
                break
            except Exception as exc:  # noqa: BLE001 — persist and retry
                save_state(
                    state_file,
                    phase="release_query_error",
                    tag=tag,
                    detail=str(exc)[-4000:],
                )
                LOG.warning("release query failed: %s", exc)
                if args.once:
                    exit_code = 1
                    break
                interval = next_interval(interval, failed=True)
                sleep_interruptible(interval)
                continue

            if data is None:
                save_state(state_file, phase="waiting_for_release", tag=tag)
                if args.once:
                    LOG.info("tag %s not published yet; --once exiting", tag)
                    exit_code = 0
                    break
                LOG.info("tag %s not published yet; sleeping %.0fs", tag, interval)
                interval = next_interval(interval, failed=False)
                try:
                    sleep_interruptible(interval)
                except ShutdownRequested:
                    break
                continue

            evidence = qualification_asset(data)
            if evidence:
                save_state(
                    state_file,
                    phase="qualified",
                    tag=tag,
                    evidence_asset=evidence,
                    release_url=data.get("url"),
                    qualified_by="external_or_prior",
                )
                LOG.info("%s already qualified: %s", tag, evidence)
                exit_code = 0
                break

            if not ready_assets(data):
                asset_names = [a.get("name") for a in data.get("assets", []) if isinstance(a, dict)]
                save_state(
                    state_file,
                    phase="waiting_for_signed_assets",
                    tag=tag,
                    release_url=data.get("url"),
                    assets=asset_names,
                )
                if args.once:
                    LOG.info("waiting for signed assets on %s; --once exiting", tag)
                    exit_code = 0
                    break
                LOG.info("waiting for signed assets on %s; sleeping %.0fs", tag, interval)
                interval = next_interval(interval, failed=False)
                try:
                    sleep_interruptible(interval)
                except ShutdownRequested:
                    break
                continue

            attempts += 1
            save_state(
                state_file,
                phase="qualifying",
                tag=tag,
                attempt=attempts,
                release_url=data.get("url"),
            )
            LOG.info("qualifying %s attempt=%s", tag, attempts)
            failed = False
            try:
                ensure_worktree(repo_cache, worktree, tag, git, make)
                clean_stale_nested_registration(repo_cache, worktree, tag, git)
                code, output = qualify(worktree, tag, python)
            except ShutdownRequested:
                break
            except Exception as exc:  # noqa: BLE001 — retry next cycle
                failed = True
                save_state(
                    state_file,
                    phase="qualification_setup_failed",
                    tag=tag,
                    attempt=attempts,
                    detail=str(exc)[-4000:],
                )
                LOG.warning("setup failed attempt=%s: %s", attempts, exc)
                if args.once:
                    exit_code = 1
                    break
                interval = next_interval(interval, failed=True)
                try:
                    sleep_interruptible(interval)
                except ShutdownRequested:
                    break
                continue

            if code == 0:
                confirmed = release(args.repo, tag, gh, repo_cache)
                evidence = qualification_asset(confirmed) if confirmed else None
                if evidence:
                    save_state(
                        state_file,
                        phase="qualified",
                        tag=tag,
                        attempt=attempts,
                        evidence_asset=evidence,
                        release_url=(confirmed or {}).get("url"),
                        qualified_by="local_official",
                    )
                    LOG.info("%s qualified: %s", tag, evidence)
                    exit_code = 0
                    break
                failed = True
                save_state(
                    state_file,
                    phase="qualification_succeeded_evidence_pending",
                    tag=tag,
                    attempt=attempts,
                    detail=output[-4000:],
                )
                LOG.warning("qualify returned 0 but evidence asset not yet on release")
            else:
                failed = True
                save_state(
                    state_file,
                    phase="qualification_failed_retrying",
                    tag=tag,
                    attempt=attempts,
                    detail=output[-6000:],
                )
                LOG.warning("qualify failed attempt=%s rc=%s", attempts, code)

            if args.once:
                exit_code = 1 if failed else 0
                break

            interval = next_interval(interval, failed=failed)
            try:
                sleep_interruptible(interval)
            except ShutdownRequested:
                break
    except ShutdownRequested:
        pass
    finally:
        save_state(state_file, phase="stopped" if STATE.should_stop() else STATE.phase, tag=tag)
        if health is not None:
            health.shutdown()
            health.server_close()
        LOG.info("service stopped tag=%s exit=%s", tag, exit_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
