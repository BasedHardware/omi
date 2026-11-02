#!/usr/bin/env python3
"""Capture-health check for store rollout hops (read-only PostHog).

The iOS phased jump to 100% and each Android staged-rollout hop expand
exposure. Before either one, this module judges the build under rollout on its
pendant capture-wedge rate.

It mirrors the operator gate's judge (Hermes `omi_capture_wedge.py`, owned by
Observability; thresholds ratified by David 2026-10-20), so the two agree:
- rate = wedge users / pendant users per (`$os`, `$app_build`) over the window;
  pendant users are distinct users with `Device Session Ended` (kept at 100%);
- wedge users are reweighted by 100 / `omi_sample_pct` (ingestion sampled the
  event by distinct_id from 10-17 to 10-20 16:16Z), so windows compare;
- BAD when the rate is more than RATE_MULTIPLE times the previous build's, or
  when the build has more than USERS_PER_DAY_CAP wedge users per day;
- the previous build is the one with the most pendant users below the
  candidate on that platform (with at least MIN_PENDANT_USERS of them);
- the rate is compared only with at least MIN_PENDANT_USERS pendant users and
  MIN_RATIO_WEDGE_USERS wedge users; a thinner build is reported, not compared.

Two deliberate differences from the operator gate:
- The wedge triggers are CAPTURE_LOSS_TRIGGERS: the operator gate's
  `connected_no_bytes`, plus `connected_not_capturing` from the app's
  CaptureContinuityMonitor (a connected pendant with no capture session at
  all, the 1.0.560-563 state that `connected_no_bytes` cannot see).
- A build with no data HOLDS (fail closed), as does any query error.
  TRAIN_CAPTURE_HEALTH_OVERRIDE=<reason> lets one run's hops through and
  prints the reason in the train log.

The queries return per-build aggregates only; no user identifiers leave PostHog.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

WINDOW_HOURS = 48
RATE_MULTIPLE = 2.0
USERS_PER_DAY_CAP = 50.0
MIN_PENDANT_USERS = 20
MIN_RATIO_WEDGE_USERS = 3.0
CAPTURE_LOSS_TRIGGERS = ("connected_no_bytes", "connected_not_capturing")
OVERRIDE_ENV = "TRAIN_CAPTURE_HEALTH_OVERRIDE"
KEY_ENV = "POSTHOG_PERSONAL_API_KEY"
DEFAULT_HOST = "https://us.posthog.com"
DEFAULT_PROJECT_ID = "302298"
QUERY_TIMEOUT_SECONDS = 240
POLL_SECONDS = 3
PLATFORM_OS = {"ios": "iOS", "android": "Android"}

QueryRunner = Callable[[str], list]


class CaptureHealthError(Exception):
    pass


@dataclass(frozen=True)
class BuildStats:
    wedge_users: float
    pendant_users: int
    version: str | None

    @property
    def rate(self) -> float | None:
        return self.wedge_users / self.pendant_users if self.pendant_users else None


Stats = dict[tuple[str, str], BuildStats]


@dataclass(frozen=True)
class Verdict:
    hold: bool
    reason: str


def _identifier(value: str) -> str:
    """A HogQL string literal for a fixed identifier (validated, never free text)."""
    if not value or any(ch not in "0123456789.+-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for ch in value):
        raise CaptureHealthError(f"refusing to query an unexpected identifier {value!r}")
    return f"'{value}'"


def wedge_query(hours: int = WINDOW_HOURS) -> str:
    triggers = ", ".join(_identifier(t) for t in CAPTURE_LOSS_TRIGGERS)
    return f"""
SELECT os, build, sum(w) FROM (
  SELECT properties['$os'] AS os, toString(properties['$app_build']) AS build, person_id,
         max(100.0 / greatest(coalesce(toFloatOrNull(toString(properties['omi_sample_pct'])), 100.0), 0.01)) AS w
  FROM events
  WHERE event = 'Capture Wedge Detected' AND properties['trigger'] IN ({triggers})
    AND timestamp >= now() - INTERVAL {int(hours)} HOUR AND properties['$os'] IN ('iOS', 'Android')
  GROUP BY os, build, person_id)
GROUP BY os, build
"""


def pendant_query(hours: int = WINDOW_HOURS) -> str:
    return f"""
SELECT properties['$os'] AS os, toString(properties['$app_build']) AS build,
       any(properties['$app_version']), uniq(person_id)
FROM events
WHERE event = 'Device Session Ended' AND timestamp >= now() - INTERVAL {int(hours)} HOUR
  AND properties['$os'] IN ('iOS', 'Android')
GROUP BY os, build
"""


def build_stats(run: QueryRunner, hours: int = WINDOW_HOURS) -> Stats:
    stats: Stats = {}
    for os_name, build, version, users in run(pendant_query(hours)):
        stats[(str(os_name), str(build))] = BuildStats(0.0, int(users), version if isinstance(version, str) else None)
    for os_name, build, weighted in run(wedge_query(hours)):
        key = (str(os_name), str(build))
        row = stats.get(key, BuildStats(0.0, 0, None))
        stats[key] = BuildStats(float(weighted or 0), row.pendant_users, row.version)
    return stats


def _num(build: str) -> int:
    try:
        return int(build)
    except (TypeError, ValueError):
        return -1


def previous_build(stats: Stats, os_name: str, build: str) -> tuple[str | None, BuildStats | None]:
    lower = [
        (key[1], row)
        for key, row in stats.items()
        if key[0] == os_name and 0 <= _num(key[1]) < _num(build) and row.pendant_users >= MIN_PENDANT_USERS
    ]
    if not lower:
        return None, None
    return max(lower, key=lambda item: item[1].pendant_users)


def judge(stats: Stats, os_name: str, build: str, hours: int = WINDOW_HOURS) -> Verdict:
    """The operator gate's judge for one build; a build with no data holds."""
    row = stats.get((os_name, str(build)))
    if row is None or row.rate is None:
        return Verdict(True, f"{os_name} {build}: no pendant sessions in the last {hours}h; cannot judge capture health")
    per_day = row.wedge_users * 24.0 / hours
    parts = [
        f"{os_name} {build} ({row.version}): {per_day:.0f} wedge users/day, "
        f"rate {100 * row.rate:.1f}% of {row.pendant_users} pendant users"
    ]
    hold = per_day > USERS_PER_DAY_CAP
    if hold:
        parts.append(f"over the {USERS_PER_DAY_CAP:.0f}/day cap")
    prev_build, prev = previous_build(stats, os_name, str(build))
    if prev is not None and row.pendant_users >= MIN_PENDANT_USERS:
        prev_rate = prev.rate or 0.0
        parts.append(f"previous build {prev_build} rate {100 * prev_rate:.1f}%")
        if row.rate > RATE_MULTIPLE * prev_rate and row.wedge_users >= MIN_RATIO_WEDGE_USERS:
            hold = True
            parts.append(f"more than {RATE_MULTIPLE:.0f}x the previous build")
    elif row.pendant_users < MIN_PENDANT_USERS:
        parts.append(f"thin sample (<{MIN_PENDANT_USERS} pendant users): rate not compared")
    return Verdict(hold, "; ".join(parts))


def _rows(payload: object) -> list:
    """HogQL rows from a query response: a row list, or a response object
    (`{"columns": ..., "results": [...]}`, as async polling returns it)."""
    if isinstance(payload, dict):
        payload = payload.get("results")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise CaptureHealthError(f"unexpected PostHog results shape: {type(payload).__name__}")
    return payload


def posthog_runner(api_key: str, *, host: str = DEFAULT_HOST, project_id: str = DEFAULT_PROJECT_ID) -> QueryRunner:
    """Runs HogQL with refresh=async and polls: blocking queries cap at ~10 s."""
    base = f"{host.rstrip('/')}/api/projects/{project_id}/query/"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def request(url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CaptureHealthError(f"PostHog query failed: {exc}") from exc

    def run(hogql: str) -> list:
        started = request(base, {"query": {"kind": "HogQLQuery", "query": hogql}, "refresh": "async"})
        if isinstance(started.get("results"), list):
            return _rows(started)
        query_id = (started.get("query_status") or {}).get("id")
        if not query_id:
            raise CaptureHealthError(f"PostHog returned neither results nor a query id: {list(started)}")
        deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            status = request(f"{base}{query_id}/").get("query_status") or {}
            if status.get("error"):
                raise CaptureHealthError(f"PostHog query error: {str(status.get('error_message') or 'unknown')[:200]}")
            if status.get("complete"):
                return _rows(status.get("results"))
        raise CaptureHealthError(f"PostHog query did not finish within {QUERY_TIMEOUT_SECONDS}s")

    return run


def check_rollout(
    platform: str,
    *,
    build: str | None,
    env: dict[str, str] | None = None,
    runner: QueryRunner | None = None,
) -> Verdict:
    """HOLD or proceed for one rollout hop on the exact store [build] (Android
    version code, iOS CFBundleVersion). Never raises: any error HOLDS."""
    env = dict(os.environ) if env is None else env
    override = env.get(OVERRIDE_ENV, "").strip()
    try:
        os_name = PLATFORM_OS.get(platform.lower())
        if os_name is None:
            raise CaptureHealthError(f"unknown platform {platform!r}")
        if not build:
            raise CaptureHealthError("the build under rollout has no readable build number")
        if runner is None:
            key = env.get(KEY_ENV, "").strip()
            if not key:
                raise CaptureHealthError(f"{KEY_ENV} is not configured for this workflow")
            runner = posthog_runner(
                key,
                host=env.get("POSTHOG_HOST", "").strip() or DEFAULT_HOST,
                project_id=env.get("POSTHOG_PROJECT_ID", "").strip() or DEFAULT_PROJECT_ID,
            )
        verdict = judge(build_stats(runner), os_name, str(build))
    except Exception as exc:  # noqa: BLE001 - the train must hold, never crash, on any read failure
        verdict = Verdict(True, f"capture health unknown ({exc}); failing closed")
    if verdict.hold and override:
        return Verdict(False, f"OVERRIDDEN ({OVERRIDE_ENV}={override!r}): {verdict.reason}")
    return verdict
