#!/usr/bin/env python3
"""Read-only OpenAI Platform admin helpers for incident triage."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://api.openai.com"
SKILL_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = SKILL_DIR / "references" / ".env"
USAGE_ENDPOINTS = [
    "audio_speeches",
    "audio_transcriptions",
    "code_interpreter_sessions",
    "completions",
    "embeddings",
    "images",
    "moderations",
]


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: redact_secret(v) if is_secret_field(k) and not isinstance(v, (dict, list)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def is_secret_field(key: str) -> bool:
    key = key.lower()
    return key in {"key", "secret", "token"} or key.endswith("_key") or key.endswith("_token")


def redact_secret(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= 12:
        return "[redacted]"
    return f"{text[:6]}...{text[-4:]}"


def api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    key = os.environ.get("OPENAI_ADMIN_KEY")
    if not key:
        raise SystemExit(f"OPENAI_ADMIN_KEY missing; expected it in {ENV_PATH}")
    url = BASE_URL + path
    if params:
        query: list[tuple[str, str]] = []
        for name, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                query.extend((name, str(item)) for item in value)
            else:
                query.append((name, str(value)))
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        try:
            parsed = redact(json.loads(body))
        except Exception:
            parsed = body
        raise SystemExit(
            json.dumps({"error": "http_error", "status": exc.code, "path": path, "body": parsed}, indent=2)
        )


def dump(data: Any) -> None:
    print(json.dumps(redact(data), indent=2, sort_keys=True))


def iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def trailing_start(minutes: int) -> int:
    return int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).timestamp())


def epoch_days_ago(days: int) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(now.year, now.month, now.day, tzinfo=dt.timezone.utc) - dt.timedelta(days=days)
    return int(start.timestamp())


def usage_metric(result: dict[str, Any]) -> int:
    for name in ["num_model_requests", "num_requests", "num_sessions", "num_seconds"]:
        if result.get(name) is not None:
            return int(result.get(name) or 0)
    return int(result.get("input_tokens") or result.get("output_tokens") or 0)


def iter_pages(path: str, params: dict[str, Any] | None = None, cursor_name: str = "after"):
    params = dict(params or {})
    while True:
        page = api_get(path, params)
        yield page
        after = page.get("last_id") or page.get("after")
        if not page.get("has_more") or not after:
            break
        params[cursor_name] = after


def list_projects(_args: argparse.Namespace) -> None:
    projects: list[Any] = []
    for page in iter_pages("/v1/organization/projects", {"limit": 100}):
        projects.extend(page.get("data", []))
    dump({"count": len(projects), "data": projects})


def list_project_keys(project_id: str) -> list[Any]:
    keys: list[Any] = []
    for page in iter_pages(f"/v1/organization/projects/{project_id}/api_keys", {"limit": 100}):
        keys.extend(page.get("data", []))
    return keys


def find_key(args: argparse.Namespace) -> None:
    needle = args.needle.lower()
    projects: list[Any] = []
    for page in iter_pages("/v1/organization/projects", {"limit": 100}):
        projects.extend(page.get("data", []))
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for project in projects:
        project_id = project.get("id")
        if not project_id:
            continue
        try:
            keys = list_project_keys(project_id)
        except SystemExit as exc:
            errors.append({"project_id": project_id, "error": str(exc)[:500]})
            continue
        for key in keys:
            haystack = " ".join(
                str(key.get(field, ""))
                for field in ["id", "name", "redacted_value", "created_at", "owner", "service_account_id"]
            ).lower()
            if needle in haystack:
                matches.append({"project": project, "api_key": key})
    dump(
        {
            "needle": args.needle,
            "project_count": len(projects),
            "match_count": len(matches),
            "matches": matches,
            "errors": errors,
        }
    )


def key_inventory(args: argparse.Namespace) -> None:
    projects: list[Any] = []
    for page in iter_pages("/v1/organization/projects", {"limit": 100}):
        projects.extend(page.get("data", []))
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for project in projects:
        project_id = project.get("id")
        if not project_id:
            continue
        try:
            keys = list_project_keys(project_id)
        except SystemExit as exc:
            errors.append({"project_id": project_id, "error": str(exc)[:500]})
            continue
        for key in keys:
            owner = key.get("owner") or {}
            owner_user = owner.get("user") or {}
            rows.append(
                {
                    "id": key.get("id"),
                    "name": key.get("name"),
                    "project_id": project_id,
                    "project_name": project.get("name"),
                    "owner_email": owner_user.get("email"),
                    "owner_type": owner.get("type"),
                    "created_at": key.get("created_at"),
                    "created_at_iso": iso(key.get("created_at")),
                    "last_used_at": key.get("last_used_at"),
                    "last_used_at_iso": iso(key.get("last_used_at")),
                    "owner_project_access": key.get("owner_project_access"),
                    "redacted_value": key.get("redacted_value"),
                }
            )
    if args.recent_hours:
        cutoff = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.recent_hours)).timestamp())
        rows = [
            row for row in rows if (row.get("created_at") or 0) >= cutoff or (row.get("last_used_at") or 0) >= cutoff
        ]
    rows.sort(key=lambda row: (row.get("last_used_at") or 0, row.get("created_at") or 0), reverse=True)
    dump({"count": len(rows), "projects": len(projects), "errors": errors, "keys": rows[: args.limit]})


def org(args: argparse.Namespace) -> None:
    candidates = [
        "/v1/organization/projects",
        "/v1/organization/admin_api_keys",
    ]
    out = {}
    for path in candidates:
        try:
            out[path] = api_get(path, {"limit": 1})
        except SystemExit as exc:
            out[path] = {"error": str(exc)[:500]}
    dump(out)


def usage(args: argparse.Namespace) -> None:
    group_by = [item.strip() for item in args.group_by.split(",") if item.strip()]
    params: dict[str, Any] = {
        "start_time": args.start_time or epoch_days_ago(args.days),
        "bucket_width": args.bucket_width,
        "limit": args.limit,
        "group_by[]": group_by,
    }
    if args.end_time:
        params["end_time"] = args.end_time
    dump(api_get("/v1/organization/usage/completions", params))


def costs(args: argparse.Namespace) -> None:
    group_by = [item.strip() for item in args.group_by.split(",") if item.strip()]
    params: dict[str, Any] = {
        "start_time": args.start_time or epoch_days_ago(args.days),
        "bucket_width": args.bucket_width,
        "limit": args.limit,
        "group_by[]": group_by,
    }
    if args.end_time:
        params["end_time"] = args.end_time
    dump(api_get("/v1/organization/costs", params))


def audit_logs(args: argparse.Namespace) -> None:
    params: dict[str, Any] = {"limit": args.limit}
    if args.start_time:
        params["effective_at[gte]"] = args.start_time
    if args.end_time:
        params["effective_at[lte]"] = args.end_time
    if args.event_type:
        params["event_types[]"] = args.event_type
    if args.actor_id:
        params["actor_ids[]"] = args.actor_id
    if args.actor_email:
        params["actor_emails[]"] = args.actor_email
    if args.resource_id:
        params["resource_ids[]"] = args.resource_id
    dump(api_get("/v1/organization/audit_logs", params))


def summarize_usage(args: argparse.Namespace) -> None:
    params = {
        "start_time": args.start_time or epoch_days_ago(args.days),
        "bucket_width": args.bucket_width,
        "limit": args.limit,
        "group_by[]": ["api_key_id", "model", "user_id", "project_id"],
    }
    if args.api_key_id:
        params["api_key_ids[]"] = [args.api_key_id]
    data = api_get("/v1/organization/usage/completions", params)
    rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for bucket in data.get("data", []):
        start = bucket.get("start_time")
        end = bucket.get("end_time")
        for item in bucket.get("results", []):
            key = (
                str(item.get("api_key_id") or ""),
                str(item.get("model") or ""),
                str(item.get("user_id") or ""),
                str(item.get("project_id") or ""),
            )
            row = rows.setdefault(
                key,
                {
                    "api_key_id": key[0],
                    "model": key[1],
                    "user_id": key[2],
                    "project_id": key[3],
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "input_cached_tokens": 0,
                    "first_start_time": start,
                    "last_end_time": end,
                },
            )
            row["requests"] += int(item.get("num_model_requests") or 0)
            row["input_tokens"] += int(item.get("input_tokens") or 0)
            row["output_tokens"] += int(item.get("output_tokens") or 0)
            row["input_cached_tokens"] += int(item.get("input_cached_tokens") or 0)
            row["first_start_time"] = min(row["first_start_time"], start)
            row["last_end_time"] = max(row["last_end_time"], end)
    top = sorted(rows.values(), key=lambda r: (r["output_tokens"], r["requests"], r["input_tokens"]), reverse=True)
    dump({"row_count": len(top), "top": top[: args.top]})


def recent_abuse_report(args: argparse.Namespace) -> None:
    start_time = args.start_time or trailing_start(args.minutes)
    end_time = args.end_time
    params: dict[str, Any] = {
        "start_time": start_time,
        "bucket_width": "1m",
        "limit": args.limit or args.minutes,
        "group_by[]": ["api_key_id", "model", "user_id", "project_id"],
    }
    if end_time:
        params["end_time"] = end_time
    completions = api_get("/v1/organization/usage/completions", params)
    per_key: dict[str, dict[str, Any]] = collections.defaultdict(
        lambda: {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "first_active": None,
            "last_active": None,
            "models": collections.Counter(),
            "users": collections.Counter(),
            "projects": collections.Counter(),
            "minute_counts": [],
        }
    )
    active_minutes: list[dict[str, Any]] = []
    for bucket in completions.get("data", []):
        ts = bucket.get("start_time")
        minute_keys: collections.Counter[str] = collections.Counter()
        for item in bucket.get("results", []):
            key_id = item.get("api_key_id") or "null"
            requests = int(item.get("num_model_requests") or 0)
            if not requests:
                continue
            row = per_key[key_id]
            row["requests"] += requests
            row["input_tokens"] += int(item.get("input_tokens") or 0)
            row["output_tokens"] += int(item.get("output_tokens") or 0)
            row["cached_input_tokens"] += int(item.get("input_cached_tokens") or 0)
            row["first_active"] = min(row["first_active"], ts) if row["first_active"] else ts
            row["last_active"] = max(row["last_active"], ts) if row["last_active"] else ts
            row["models"][item.get("model") or "null"] += requests
            row["users"][item.get("user_id") or "null"] += requests
            row["projects"][item.get("project_id") or "null"] += requests
            minute_keys[key_id] += requests
        if minute_keys:
            active_minutes.append(
                {
                    "start_time": ts,
                    "start_time_iso": iso(ts),
                    "keys": dict(minute_keys),
                    "requests": sum(minute_keys.values()),
                }
            )
            for key_id, count in minute_keys.items():
                per_key[key_id]["minute_counts"].append(count)

    endpoint_totals: dict[str, dict[str, int]] = {}
    for endpoint in USAGE_ENDPOINTS:
        if endpoint == "completions":
            continue
        endpoint_params: dict[str, Any] = {
            "start_time": start_time,
            "bucket_width": "1m",
            "limit": args.limit or args.minutes,
            "group_by[]": ["api_key_id"],
        }
        if end_time:
            endpoint_params["end_time"] = end_time
        try:
            endpoint_data = api_get(f"/v1/organization/usage/{endpoint}", endpoint_params)
        except SystemExit as exc:
            endpoint_totals[endpoint] = {"__error__": 1, "__message__": str(exc)[:300]}  # type: ignore[assignment]
            continue
        totals: collections.Counter[str] = collections.Counter()
        for bucket in endpoint_data.get("data", []):
            for item in bucket.get("results", []):
                metric = usage_metric(item)
                if metric:
                    totals[item.get("api_key_id") or "null"] += metric
        endpoint_totals[endpoint] = dict(totals)

    suspicious_models = set(args.suspicious_model or [])
    expected_models = set(args.expected_model or [])
    keys: list[dict[str, Any]] = []
    for key_id, row in per_key.items():
        minute_counts = row.pop("minute_counts")
        max_rpm = max(minute_counts) if minute_counts else 0
        sorted_minutes = sorted(minute_counts)
        p95_rpm = sorted_minutes[int(len(sorted_minutes) * 0.95) - 1] if sorted_minutes else 0
        models = row["models"]
        unexpected = [model for model in models if expected_models and model not in expected_models]
        suspicious_hits = [model for model in models if model in suspicious_models]
        reasons = []
        if args.old_key and key_id == args.old_key:
            reasons.append("old_key_still_active")
        if args.new_key and key_id == args.new_key:
            reasons.append("new_rotated_key_active")
        if max_rpm >= args.suspicious_rpm:
            reasons.append(f"rpm_max>={args.suspicious_rpm}")
        if suspicious_hits:
            reasons.append("suspicious_models:" + ",".join(suspicious_hits[:5]))
        if unexpected:
            reasons.append("unexpected_models:" + ",".join(unexpected[:5]))
        keys.append(
            {
                "api_key_id": key_id,
                "requests": row["requests"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cached_input_tokens": row["cached_input_tokens"],
                "first_active": iso(row["first_active"]),
                "last_active": iso(row["last_active"]),
                "active_minutes": len(minute_counts),
                "rpm_max": max_rpm,
                "rpm_p95": p95_rpm,
                "top_models": models.most_common(args.top_models),
                "top_users": row["users"].most_common(5),
                "top_projects": row["projects"].most_common(5),
                "reasons": reasons,
            }
        )
    keys.sort(key=lambda item: (len(item["reasons"]), item["requests"], item["rpm_max"]), reverse=True)
    dump(
        {
            "window_start": iso(start_time),
            "window_end": iso(end_time) if end_time else dt.datetime.now(dt.timezone.utc).isoformat(),
            "has_more": completions.get("has_more"),
            "next_page": completions.get("next_page"),
            "key_count": len(keys),
            "keys": keys,
            "endpoint_totals_by_key": endpoint_totals,
            "last_active_minutes": active_minutes[-args.tail_minutes :],
        }
    )


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("org")
    p.set_defaults(func=org)

    p = sub.add_parser("list-projects")
    p.set_defaults(func=list_projects)

    p = sub.add_parser("find-key")
    p.add_argument("--needle", required=True)
    p.set_defaults(func=find_key)

    p = sub.add_parser("key-inventory")
    p.add_argument("--recent-hours", type=int, help="Only keys created or used in the trailing N hours")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=key_inventory)

    p = sub.add_parser("recent-abuse-report")
    p.add_argument("--minutes", type=int, default=90)
    p.add_argument("--start-time", type=int)
    p.add_argument("--end-time", type=int)
    p.add_argument("--limit", type=int)
    p.add_argument("--old-key")
    p.add_argument("--new-key")
    p.add_argument("--expected-model", action="append")
    p.add_argument(
        "--suspicious-model",
        action="append",
        default=[
            "gpt-4o-mini-2024-07-18",
            "gpt-4o-2024-08-06",
            "gpt-5-nano-2025-08-07",
            "gpt-5.4-nano-2026-03-17",
            "gpt-5.5-pro-2026-04-23",
        ],
    )
    p.add_argument("--suspicious-rpm", type=int, default=100)
    p.add_argument("--top-models", type=int, default=12)
    p.add_argument("--tail-minutes", type=int, default=20)
    p.set_defaults(func=recent_abuse_report)

    for name, func in [("usage", usage), ("costs", costs), ("summarize-usage", summarize_usage)]:
        p = sub.add_parser(name)
        p.add_argument("--days", type=int, default=7)
        p.add_argument("--start-time", type=int)
        p.add_argument("--end-time", type=int)
        p.add_argument("--bucket-width", default="1d")
        p.add_argument("--limit", type=int, default=31)
        p.add_argument("--group-by", default="api_key_id,model,user_id,project_id")
        p.add_argument("--api-key-id")
        p.add_argument("--top", type=int, default=50)
        p.set_defaults(func=func)

    p = sub.add_parser("audit-logs")
    p.add_argument("--start-time", type=int)
    p.add_argument("--end-time", type=int)
    p.add_argument("--event-type", action="append")
    p.add_argument("--actor-id", action="append")
    p.add_argument("--actor-email", action="append")
    p.add_argument("--resource-id", action="append")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=audit_logs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
