#!/usr/bin/env python3
"""Read-only product telemetry scorecard and experiment evidence CLI.

The CLI intentionally consumes a small, normalized event envelope.  It can
read JSONL exported by a warehouse/job, PostHog's query response, or the
checked-in fixtures.  It never writes product data and it refuses to fetch
PostHog data unless the caller supplies an explicit HogQL query and all
connection settings through the environment.

Examples::

    scorecard.py scorecard --input events.jsonl --as-of 2026-09-22T00:00:00Z
    scorecard.py experiment --input events.jsonl --experiment-id ui-v2
    scorecard.py workflow --input events.jsonl --baseline-build 1.0.0 \
        --candidate-build 1.1.0 --output packet.json

Event time is authoritative for cohorts and windows.  ``ingested_at`` is
retained only to expose late arrivals.  Duplicate ``event_id`` values are
counted once per namespace/environment/build isolation boundary.  Missing
event time, user id, or event name makes an event unusable and contributes to
the completeness report; it never becomes a confident zero.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit


SCHEMA_VERSION = "product-scorecard.v1"
DEFAULT_DEFINITION_PATH = Path(__file__).resolve().parents[2] / "contracts/product-telemetry/metric-definitions.json"
TERMINAL_OUTCOMES = {"success", "empty", "failure", "cancelled", "superseded", "unobserved"}
SUCCESS_OUTCOMES = {"success"}
PENDING_AFTER = timedelta(hours=1)
DEFAULT_EXPERIMENT_VARIANTS = frozenset({"control", "candidate", "treatment", "holdout", "compact", "default"})
EXPERIMENT_METRICS = frozenset({"success", "failure", "helpful", "value"})
POSTHOG_RESULT_LIMIT = 50001


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _json_time(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def definition_schema_version(path: Path = DEFAULT_DEFINITION_PATH) -> str:
    """Return the checked-in metric contract version used by this CLI."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    return str(payload.get("schema_version") or "unknown") if isinstance(payload, Mapping) else "unknown"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in {"true", "1", "yes", "y"}:
            return True
        if value.lower() in {"false", "0", "no", "n"}:
            return False
    return None


def _event_name(raw: Mapping[str, Any]) -> str:
    return str(raw.get("event_name") or raw.get("event") or raw.get("name") or "").strip()


@dataclass(frozen=True)
class Event:
    event_id: str
    name: str
    user_id: str
    occurred_at: datetime
    ingested_at: datetime | None
    namespace: str
    environment: str
    server_environment: str
    app_build: str
    properties: Mapping[str, Any]
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Event | None":
        props = raw.get("properties")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except json.JSONDecodeError:
                props = {}
        merged: dict[str, Any] = dict(props) if isinstance(props, Mapping) else {}
        merged.update({k: v for k, v in raw.items() if k not in {"properties"} and k not in merged})
        name = _event_name(raw)
        user_id = str(raw.get("user_id") or raw.get("distinct_id") or merged.get("user_id") or merged.get("distinct_id") or "").strip()
        # Product event time wins over PostHog's ingestion timestamp.  A
        # warehouse export may put the product clock in properties while
        # PostHog's ``timestamp`` remains at the top level.
        occurred = _parse_time(
            merged.get("occurred_at")
            or merged.get("event_time")
            or raw.get("occurred_at")
            or raw.get("event_time")
            or raw.get("timestamp")
        )
        if not name or not user_id or occurred is None:
            return None
        event_id = str(
            raw.get("event_id")
            or raw.get("id")
            or raw.get("uuid")
            or raw.get("$insert_id")
            or merged.get("event_id")
            or merged.get("uuid")
            or merged.get("$insert_id")
            or merged.get("billing_event_id")
            or ""
        ).strip()
        ingested = _parse_time(raw.get("ingested_at") or merged.get("ingested_at"))
        return cls(
            event_id=event_id,
            name=name,
            user_id=user_id,
            occurred_at=occurred,
            ingested_at=ingested,
            namespace=str(
                raw.get("client_app_namespace")
                or merged.get("client_app_namespace")
                or raw.get("$app_namespace")
                or merged.get("$app_namespace")
                or raw.get("namespace")
                or merged.get("namespace")
                or "default"
            ),
            environment=str(
                raw.get("client_app_profile")
                or merged.get("client_app_profile")
                or raw.get("environment")
                or raw.get("$environment")
                or merged.get("environment")
                or merged.get("$environment")
                or "unknown"
            ),
            server_environment=str(
                raw.get("server_environment")
                or raw.get("environment")
                or raw.get("$environment")
                or merged.get("server_environment")
                or merged.get("environment")
                or merged.get("$environment")
                or "unknown"
            ),
            app_build=str(raw.get("app_build") or raw.get("$app_build") or merged.get("app_build") or merged.get("$app_build") or "unknown"),
            properties=merged,
            raw=raw,
        )

    def prop(self, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in self.properties and self.properties[key] is not None:
                return self.properties[key]
        return default

    @property
    def correlation_id(self) -> str:
        return str(self.prop("correlation_id", "attempt_id", "session_id", "recording_id", default=""))


@dataclass(frozen=True)
class LoadReport:
    read: int
    valid: int
    invalid: int
    duplicates: int
    late: int
    late_seconds: int


class InsufficientEvidence(ValueError):
    """Raised only by the CLI when no metric can be computed at all."""


def read_jsonl(path: Path) -> tuple[list[Event], LoadReport]:
    events: list[Event] = []
    read = invalid = duplicates = late = late_seconds = 0
    seen: set[tuple[str, str, str, str]] = set()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            read += 1
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if not isinstance(raw, Mapping):
                invalid += 1
                continue
            event = Event.from_mapping(raw)
            if event is None:
                invalid += 1
                continue
            dedupe_key = (event.namespace, event.environment, event.app_build, event.event_id)
            if event.event_id and dedupe_key in seen:
                duplicates += 1
                continue
            if event.event_id:
                seen.add(dedupe_key)
            if event.ingested_at and event.ingested_at > event.occurred_at:
                late += 1
                late_seconds += max(0, int((event.ingested_at - event.occurred_at).total_seconds()))
            events.append(event)
    return events, LoadReport(read, len(events), invalid, duplicates, late, late_seconds)


def events_from_posthog_response(payload: Mapping[str, Any]) -> list[Event]:
    """Adapt PostHog ``/query`` results without depending on the PostHog SDK."""
    rows = payload.get("results")
    columns = payload.get("columns")
    if not isinstance(rows, list):
        raise RuntimeError("PostHog response results must be a row list")
    if isinstance(columns, list):
        if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
            raise RuntimeError("PostHog response contains malformed rows; use a complete local export")
        events = [Event.from_mapping(dict(zip(columns, row))) for row in rows]
    elif all(isinstance(row, Mapping) for row in rows):
        events = [Event.from_mapping(row) for row in rows]
    else:
        raise RuntimeError("PostHog response has no usable columns or row objects; use a complete local export")
    if any(event is None for event in events):
        raise RuntimeError("PostHog response contains unusable event rows; use a complete local export")
    return [event for event in events if event is not None]


def _posthog_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _posthog_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _validate_posthog_completeness(payload: Mapping[str, Any]) -> None:
    """Reject query responses whose rows may be truncated or partial."""
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise RuntimeError("PostHog response has no results rows; use a bounded local export or a narrower window")
    if len(rows) >= POSTHOG_RESULT_LIMIT:
        raise RuntimeError(
            f"PostHog response reached the {POSTHOG_RESULT_LIMIT - 1}-row safety cap; narrow --since/--until or use a complete local export"
        )
    for key in ("error", "errors", "exception"):
        value = payload.get(key)
        if value:
            raise RuntimeError(f"PostHog response is incomplete ({key}); narrow --since/--until or use a complete local export")
    for key in ("partial", "is_partial", "truncated", "is_truncated"):
        value = payload.get(key)
        if value is not None and (_posthog_bool(value) is not False):
            raise RuntimeError(f"PostHog response is incomplete ({key}); narrow --since/--until or use a complete local export")
    status = str(payload.get("status") or "").strip().lower()
    if status in {"error", "partial", "truncated", "incomplete"}:
        raise RuntimeError(f"PostHog response is incomplete (status={status}); narrow --since/--until or use a complete local export")

    has_more_keys = [key for key in ("hasMore", "has_more") if key in payload]
    if has_more_keys:
        values = {key: payload[key] for key in has_more_keys}
        if any(_posthog_bool(value) is True for value in values.values()):
            raise RuntimeError("PostHog response has more rows; narrow --since/--until or use a complete local export")
        if not all(_posthog_bool(value) is False for value in values.values()):
            raise RuntimeError("PostHog response has an ambiguous hasMore marker; use a complete local export")
        return

    row_count = next((payload[key] for key in ("total_rows", "totalRows") if key in payload), None)
    parsed_row_count = _posthog_int(row_count)
    if parsed_row_count is None or parsed_row_count != len(rows):
        raise RuntimeError(
            "PostHog response lacks an explicit complete row-count proof; narrow --since/--until or use a complete local export"
        )


def _render_posthog_query(query: str, *, since: str, until: str) -> str:
    if "{date_from}" not in query or "{date_to}" not in query:
        raise ValueError("HogQL query must contain both {date_from} and {date_to} placeholders")
    if not re.search(r"\bLIMIT\s+50001\b", query, flags=re.IGNORECASE):
        raise ValueError("HogQL query must include LIMIT 50001 as the completeness sentinel")
    start = _parse_time(since)
    end = _parse_time(until)
    if start is None or end is None or end <= start:
        raise ValueError("PostHog --since/--until must be valid increasing UTC timestamps")
    replacements = {
        "{date_from}": "toDateTime(%r)" % _json_time(start),
        "{date_to}": "toDateTime(%r)" % _json_time(end),
    }
    rendered = query
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    return rendered


def fetch_posthog_events(query: str, *, since: str, until: str) -> list[Event]:
    host = os.getenv("POSTHOG_HOST", "").strip().rstrip("/")
    project_id = os.getenv("POSTHOG_PROJECT_ID", "").strip()
    api_key = os.getenv("POSTHOG_PERSONAL_API_KEY") or os.getenv("POSTHOG_API_KEY")
    if not host or not project_id or not api_key:
        raise RuntimeError("PostHog fetch requires POSTHOG_HOST, POSTHOG_PROJECT_ID, and POSTHOG_PERSONAL_API_KEY")
    parsed_host = urlsplit(host)
    if (
        parsed_host.scheme != "https"
        or not parsed_host.hostname
        or parsed_host.username
        or parsed_host.password
        or parsed_host.path not in {"", "/"}
        or parsed_host.query
        or parsed_host.fragment
    ):
        raise RuntimeError("POSTHOG_HOST must be an HTTPS origin without embedded credentials or a path")
    if not re.fullmatch(r"[1-9][0-9]*", project_id):
        raise RuntimeError("POSTHOG_PROJECT_ID must be a positive numeric project id")
    rendered_query = _render_posthog_query(query, since=since, until=until)
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": rendered_query}}).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/projects/{project_id}/query/",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise RuntimeError("PostHog redirect refused")

        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PostHog query failed: {type(exc).__name__}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("PostHog query returned a non-object response")
    _validate_posthog_completeness(payload)
    events = events_from_posthog_response(payload)
    if len(events) != len(payload["results"]):
        raise RuntimeError("PostHog response dropped event rows; use a complete local export")
    return events


def _matches(event: Event, *, namespace: str | None, environment: str | None, build: str | None) -> bool:
    return (
        (namespace is None or event.namespace == namespace)
        and (environment is None or event.environment == environment)
        and (build is None or event.app_build == build)
    )


def filtered(events: Iterable[Event], *, namespace: str | None = None, environment: str | None = None, build: str | None = None, since: datetime | None = None, until: datetime | None = None) -> list[Event]:
    return [
        e
        for e in events
        if _matches(e, namespace=namespace, environment=environment, build=build)
        and (since is None or e.occurred_at >= since)
        and (until is None or e.occurred_at < until)
    ]


def _scope_status(events: Sequence[Event]) -> tuple[str, dict[str, list[str]]]:
    """Require one namespace/environment per scorecard cohort.

    A mixed export can otherwise make a healthy development cohort hide a
    production failure.  Callers can select a scope with the CLI filters.
    "unknown" is retained as a real value so incomplete exports do not get
    silently merged with a named environment.
    """
    scope = {
        "namespaces": sorted({event.namespace for event in events}),
        "environments": sorted({event.environment for event in events}),
        "server_environments": sorted({event.server_environment for event in events}),
        "builds": sorted({event.app_build for event in events}),
    }
    if len(scope["namespaces"]) > 1 or len(scope["environments"]) > 1:
        return "mixed_cohort_scope", scope
    return "ok", scope


def _wilson(numerator: int, denominator: int) -> tuple[float, float] | None:
    if denominator <= 0:
        return None
    p = numerator / denominator
    z = 1.96
    denominator_adj = 1 + z * z / denominator
    centre = (p + z * z / (2 * denominator)) / denominator_adj
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * denominator)) / denominator) / denominator_adj
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _ratio_metric(name: str, numerator: int, denominator: int, *, completeness: float = 1.0, **extra: Any) -> dict[str, Any]:
    if denominator <= 0:
        return {
            "name": name,
            "status": "insufficient_evidence",
            "value": None,
            "numerator": numerator,
            "denominator": denominator,
            "completeness": completeness,
            "uncertainty": None,
            **extra,
        }
    return {
        "name": name,
        "status": "ok",
        "value": numerator / denominator,
        "numerator": numerator,
        "denominator": denominator,
        "completeness": completeness,
        "uncertainty": {"method": "wilson_95", "interval": _wilson(numerator, denominator)},
        **extra,
    }


def _outcome_value(event: Event) -> str:
    return str(event.prop("outcome", "status", default="")).strip().lower()


def journey_metrics(events: Sequence[Event], *, as_of: datetime) -> dict[str, Any]:
    attempts: dict[str, dict[str, Any]] = {}
    orphan_first_results = 0
    orphan_outcomes = 0

    def _legacy_outcome(event: Event) -> Event:
        """Adapt legacy recording lifecycle data conservatively.

        ``Recording Completed`` means that the client closed its pipeline. It
        does not, by itself, prove a usable capture. Only an explicit outcome
        or bounded observed-audio/reason fields enter reliability.
        """
        properties = dict(event.properties)
        if _outcome_value(event) in TERMINAL_OUTCOMES:
            return event
        if event.name == "Recording Start Failed":
            properties["outcome"] = "failure"
        elif event.name == "Recording Completed":
            reason = str(event.prop("reason", default="")).strip().lower()
            audio_observed = _bool(event.prop("audio_observed"))
            coverage = str(event.prop("audio_observation_coverage", default="")).strip().lower()
            if reason == "pipeline_closed" or reason in {"device_disconnected", "mode_changed"}:
                properties["outcome"] = "cancelled"
            elif coverage == "native_batch_unavailable":
                # Native batch writes audio outside this Dart observer. Missing
                # observation is unknown, not evidence of an empty capture.
                properties["outcome"] = "unknown"
            elif audio_observed is False:
                properties["outcome"] = "empty"
            else:
                # Lifecycle close proves neither server persistence nor a
                # usable conversation. A Product Journey Outcome is required
                # for end-to-end success.
                properties["outcome"] = "unknown"
        return Event(
            event_id=event.event_id,
            name=event.name,
            user_id=event.user_id,
            occurred_at=event.occurred_at,
            ingested_at=event.ingested_at,
            namespace=event.namespace,
            environment=event.environment,
            server_environment=event.server_environment,
            app_build=event.app_build,
            properties=properties,
            raw=event.raw,
        )

    for event in events:
        if event.name in {"Product Journey Started", "Recording Started", "Phone Mic Recording Started"}:
            key = event.correlation_id or event.event_id or f"row:{id(event)}"
            attempts.setdefault(key, {"started": event, "first_result": None, "outcome": None})
    for event in events:
        if event.name in {"Product Journey First Result", "Transcribe Later Recording Processed"}:
            key = event.correlation_id or event.event_id or f"row:{id(event)}"
            if key in attempts:
                attempts[key]["first_result"] = event
            else:
                orphan_first_results += 1
        elif event.name in {"Product Journey Outcome", "Recording Completed", "Recording Start Failed"}:
            key = event.correlation_id or event.event_id or f"row:{id(event)}"
            if key in attempts:
                attempts[key]["outcome"] = _legacy_outcome(event) if event.name != "Product Journey Outcome" else event
            else:
                orphan_outcomes += 1
    terminal: defaultdict[str, int] = defaultdict(int)
    per_journey: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "pending": 0, "unknown": 0})
    pending = unknown = successes = 0
    result_latencies: list[float] = []
    for attempt in attempts.values():
        started: Event = attempt["started"]
        journey = str(started.prop("journey", default="capture" if "Recording" in started.name or "Mic" in started.name else "unknown"))
        per_journey[journey]["total"] += 1
        outcome: Event | None = attempt["outcome"]
        first: Event | None = attempt["first_result"]
        if first:
            result_latencies.append(max(0.0, (first.occurred_at - started.occurred_at).total_seconds() * 1000))
        if outcome:
            state = _outcome_value(outcome) or "unknown"
            if state not in TERMINAL_OUTCOMES:
                state = "unknown"
            terminal[state] += 1
            if state == "success":
                successes += 1
                per_journey[journey]["success"] += 1
            if state == "unobserved":
                unknown += 1
                per_journey[journey]["unknown"] += 1
            continue
        if as_of - started.occurred_at <= PENDING_AFTER:
            pending += 1
            per_journey[journey]["pending"] += 1
        else:
            unknown += 1
            per_journey[journey]["unknown"] += 1
    count = len(attempts)
    return {
        "journey_reliability": _ratio_metric(
            "journey_reliability",
            successes,
            count,
            terminal=dict(terminal),
            pending=pending,
            unknown=unknown,
            orphan_first_results=orphan_first_results,
            orphan_outcomes=orphan_outcomes,
            by_journey={
                name: {
                    **counts,
                    "reliability": counts["success"] / counts["total"] if counts["total"] else None,
                }
                for name, counts in per_journey.items()
            },
        ),
        "journey_pending_rate": _ratio_metric("journey_pending_rate", pending, count),
        "journey_unknown_rate": _ratio_metric("journey_unknown_rate", unknown, count),
        "time_to_first_result_ms": {
            "name": "time_to_first_result_ms",
            "status": "ok" if result_latencies else "insufficient_evidence",
            "value": (sum(result_latencies) / len(result_latencies)) if result_latencies else None,
            "count": len(result_latencies),
            "completeness": len(result_latencies) / count if count else 0.0,
            "uncertainty": None,
        },
    }


def activation_and_retention(events: Sequence[Event], *, as_of: datetime) -> dict[str, Any]:
    signup_names = {"Account Created", "User Signed Up", "Signup Completed", "signup"}
    value_names = {"Product Value", "Product Journey First Result"}
    signups: dict[str, datetime] = {}
    values: defaultdict[str, list[datetime]] = defaultdict(list)
    for event in events:
        if event.name in signup_names:
            signups[event.user_id] = min(signups.get(event.user_id, event.occurred_at), event.occurred_at)
        if event.name in value_names:
            values[event.user_id].append(event.occurred_at)
    activation_seconds = [
        (min(times) - start).total_seconds()
        for uid, start in signups.items()
        if (times := [t for t in values.get(uid, []) if t >= start])
    ]
    result: dict[str, Any] = {
        "activation_rate": _ratio_metric("activation_rate", len(activation_seconds), len(signups)),
        "time_to_value_seconds": {
            "name": "time_to_value_seconds",
            "status": "ok" if activation_seconds else "insufficient_evidence",
            "value": sum(activation_seconds) / len(activation_seconds) if activation_seconds else None,
            "count": len(activation_seconds),
            "completeness": len(activation_seconds) / len(signups) if signups else 0.0,
            "uncertainty": None,
        },
    }
    for days in (1, 7, 30):
        window_start = {uid: start + timedelta(days=days) for uid, start in signups.items()}
        window_end = {uid: start + timedelta(days=days + 1) for uid, start in signups.items()}
        # A Dn cohort is mature only once the complete [signup+n,
        # signup+n+1) window has elapsed. This prevents late events from
        # silently changing a still-open retention bucket.
        matured = [uid for uid in signups if as_of >= window_end[uid]]
        retained = sum(
            1
            for uid in matured
            if any(window_start[uid] <= t < window_end[uid] for t in values.get(uid, []))
        )
        result[f"retention_d{days}"] = _ratio_metric(
            f"retention_d{days}",
            retained,
            len(matured),
            matured_cohort=len(matured),
            window_start=f"signup+{days}d",
            window_end=f"signup+{days + 1}d",
            as_of=_json_time(as_of),
        )
    return result


def feedback_metrics(events: Sequence[Event]) -> dict[str, Any]:
    # The mobile prompt's authoritative exposure is the shared started event;
    # a Product Journey Outcome can be cancelled/failed and is not a response
    # ledger. Submission is counted only after the durable backend ledger write.
    exposed = {
        e.user_id
        for e in events
        if e.name == "Product Journey Started"
        and str(e.prop("journey", default="")) in {"summary_feedback", "recording_feedback"}
    }
    submitted: list[Event] = []
    # The backend ledger scopes feedback_id by authenticated user. Keep the
    # same scope here so two users choosing the same client id remain two
    # valid submissions rather than collapsing into one response.
    seen_feedback_ids: set[tuple[str, str]] = set()
    for event in events:
        if event.name != "Product Feedback Submitted":
            continue
        feedback_id = str(event.prop("feedback_id", default="")).strip()
        # The backend requires feedback_id for mobile submissions. Keep a
        # missing-id row visible for helpfulness diagnostics, but dedupe only
        # on the stable id so repeated delivery cannot inflate a response.
        feedback_key = (event.user_id, feedback_id)
        if feedback_id and feedback_key in seen_feedback_ids:
            continue
        if feedback_id:
            seen_feedback_ids.add(feedback_key)
        submitted.append(event)
    response_users = {e.user_id for e in submitted}
    helpful = sum(
        1
        for e in submitted
        if _bool(e.prop("helpful", "is_helpful")) is True
        or str(e.prop("value", "feedback_value", default="")).lower() in {"1", "helpful", "thumbs_up", "positive"}
    )
    return {
        "helpfulness_exposure_response_rate": _ratio_metric("helpfulness_exposure_response_rate", len(response_users & exposed), len(exposed)),
        "helpfulness_rate": _ratio_metric("helpfulness_rate", helpful, len(submitted), exposed_users=len(exposed)),
    }


def churn_and_errors(events: Sequence[Event], *, as_of: datetime) -> dict[str, Any]:
    # Billing lifecycle events are outcomes; they do not define the eligible
    # paid denominator. That denominator must come from an explicit owner-
    # authorized start-of-window snapshot.
    snapshots: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"at": None, "users": set()})
    for event in events:
        if event.name != "Billing Paid Population Snapshot" or event.prop("snapshot_role") != "start_of_window":
            continue
        snapshot_id = str(event.prop("snapshot_id", default="")).strip()
        if not snapshot_id:
            continue
        snapshot_at = _parse_time(event.prop("snapshot_at")) or event.occurred_at
        current = snapshots[snapshot_id]
        current["at"] = snapshot_at if current["at"] is None else min(current["at"], snapshot_at)
        current["users"].add(event.user_id)
    mature_snapshots = [
        (snapshot_id, data)
        for snapshot_id, data in snapshots.items()
        if data["at"] is not None and data["at"] <= as_of
    ]
    selected_snapshot_id, selected_snapshot = max(mature_snapshots, key=lambda item: item[1]["at"]) if mature_snapshots else (None, None)
    paid = selected_snapshot["users"] if selected_snapshot else set()
    churned = {
        e.user_id
        for e in events
        if e.name == "Billing Subscription Churned"
        and selected_snapshot
        and e.occurred_at >= selected_snapshot["at"]
        and e.occurred_at <= as_of
        # A deleted subscription can carry Stripe's
        # ``cancellation_requested`` reason after a voluntary period-end
        # cancellation actually ends. Scheduled intent is represented by a
        # separate lifecycle event and is therefore excluded by the event-name
        # predicate above; filtering the reason would erase real churn.
    }
    active_users = {e.user_id for e in events}
    error_users = {e.user_id for e in events if e.name in {"Product Error", "Error", "Client Error"}}
    return {
        "paid_churn_rate": _ratio_metric(
            "paid_churn_rate",
            len(churned & paid),
            len(paid),
            authoritative=True,
            snapshot_id=selected_snapshot_id,
            snapshot_required=True,
            snapshot_candidates=len(mature_snapshots),
        ),
        "error_affected_user_rate": _ratio_metric("error_affected_user_rate", len(error_users), len(active_users)),
        "errors_per_active_user": {
            "name": "errors_per_active_user",
            "status": "ok" if active_users else "insufficient_evidence",
            "value": sum(1 for e in events if e.name in {"Product Error", "Error", "Client Error"}) / len(active_users) if active_users else None,
            "numerator": sum(1 for e in events if e.name in {"Product Error", "Error", "Client Error"}),
            "denominator": len(active_users),
            "completeness": 1.0 if active_users else 0.0,
            "uncertainty": None,
        },
    }


def efficiency_metrics(events: Sequence[Event]) -> dict[str, Any]:
    expected = observed = cost = 0.0
    for event in events:
        expected += _number(event.prop("expected_duration_ms", "expected_audio_ms")) or 0.0
        observed += _number(event.prop("observed_duration_ms", "observed_audio_ms", "transcribed_duration_ms")) or 0.0
        cost += _number(event.prop("cost_usd", "cost")) or 0.0
    return {
        "capture_observed_expected_ratio": {
            "name": "capture_observed_expected_ratio",
            "status": "ok" if expected > 0 else "insufficient_evidence",
            "value": observed / expected if expected > 0 else None,
            "numerator": observed,
            "denominator": expected,
            "completeness": 1.0 if expected > 0 else 0.0,
            "uncertainty": None,
        },
        "cost_usd": {
            "name": "cost_usd",
            "status": "ok" if cost > 0 else "insufficient_evidence",
            "value": cost if cost > 0 else None,
            "completeness": 1.0 if cost > 0 else 0.0,
            "uncertainty": None,
        },
    }


def operational_observation_metrics(events: Sequence[Event]) -> dict[str, Any]:
    """Aggregate client delivery, render, and capture observations.

    These are health signals about what telemetry observed. They are kept
    separate from user outcomes and deliberately do not infer battery use,
    native hangs, or content usefulness.
    """
    health = [event for event in events if event.name == "Mobile Telemetry Health"]
    render = [event for event in events if event.name == "Mobile Render Observation"]
    starts = {
        str(event.prop("recording_id", "recording_session_id", default=""))
        for event in events
        if event.name in {"Recording Started", "Phone Mic Recording Started"}
        and str(event.prop("recording_id", "recording_session_id", default="")).strip()
    }
    audio = {
        str(event.prop("recording_id", "recording_session_id", default=""))
        for event in events
        if event.name == "Recording Observation"
        and event.prop("stage") == "audio"
        and str(event.prop("recording_id", "recording_session_id", default="")).strip()
    }
    transcript = {
        str(event.prop("recording_id", "recording_session_id", default=""))
        for event in events
        if event.name == "Recording Observation"
        and event.prop("stage") == "transcript"
        and str(event.prop("recording_id", "recording_session_id", default="")).strip()
    }
    frame_summaries = [event for event in render if event.prop("stage") == "frame_summary"]
    first_frames = [event for event in render if event.prop("stage") == "first_frame" and _number(event.prop("duration_ms")) is not None]
    total_frames = int(sum(_number(event.prop("frame_count")) or 0 for event in frame_summaries))
    slow_frames = int(sum(_number(event.prop("frames_over_32ms")) or 0 for event in frame_summaries))
    queue_dropped = sum(_number(event.prop("dropped_events")) or 0 for event in health)
    handoff_failures = sum(_number(event.prop("handoff_failures")) or 0 for event in health)
    return {
        "telemetry_health_observations": {
            "name": "telemetry_health_observations",
            "status": "ok" if health else "insufficient_evidence",
            "value": len(health) if health else None,
            "observation_count": len(health),
            "dropped_events_sum": int(queue_dropped),
            "handoff_failures_sum": int(handoff_failures),
            "completeness": 1.0 if health else 0.0,
            "uncertainty": None,
        },
        "render_slow_frame_rate": _ratio_metric(
            "render_slow_frame_rate", slow_frames, total_frames, threshold_ms=32, frame_summaries=len(frame_summaries)
        ),
        "render_first_frame_ms": {
            "name": "render_first_frame_ms",
            "status": "ok" if first_frames else "insufficient_evidence",
            "value": sum(_number(event.prop("duration_ms")) or 0 for event in first_frames) / len(first_frames) if first_frames else None,
            "count": len(first_frames),
            "completeness": 1.0 if first_frames else 0.0,
            "uncertainty": None,
        },
        "capture_audio_observation_rate": _ratio_metric("capture_audio_observation_rate", len(audio & starts), len(starts)),
        "capture_transcript_observation_rate": _ratio_metric("capture_transcript_observation_rate", len(transcript & starts), len(starts)),
    }


def recording_linkage_metrics(events: Sequence[Event]) -> dict[str, Any]:
    """Measure the authoritative recording-session to conversation join.

    A recording lifecycle event may arrive before a conversation exists.  The
    join therefore requires an explicit ``conversation_id`` or ``object_id``
    on a later event carrying the same recording id; a missing join is
    unknown, never inferred from timestamp proximity.
    """
    recording_names = {
        "Recording Started",
        "Recording Completed",
        "Recording Start Failed",
        "Phone Mic Recording Started",
        "Phone Mic Recording Stopped",
        "Transcribe Later Recording Processed",
    }
    recordings: set[str] = set()
    linked: set[str] = set()
    for event in events:
        recording_id = str(event.prop("recording_id", "recording_session_id", default="")).strip()
        if not recording_id and (event.name in recording_names or event.prop("journey", default="") == "capture"):
            recording_id = event.correlation_id
        if not recording_id:
            continue
        # A capture journey outcome alone is not an authoritative recording
        # session. It can contribute the join only after a lifecycle/observation
        # event has established the recording id.
        establishes_recording = event.name in recording_names or event.name == "Recording Observation"
        if establishes_recording:
            recordings.add(recording_id)
    for event in events:
        recording_id = str(event.prop("recording_id", "recording_session_id", default="")).strip()
        if not recording_id and (event.name in recording_names or event.prop("journey", default="") == "capture"):
            recording_id = event.correlation_id
        if not recording_id or recording_id not in recordings:
            continue
        conversation_id = event.prop("conversation_id", "object_id")
        if recording_id in recordings and isinstance(conversation_id, str) and conversation_id.strip():
            linked.add(recording_id)
    return {
        "recording_conversation_linkage": _ratio_metric(
            "recording_conversation_linkage",
            len(linked),
            len(recordings),
            linkage_policy="explicit_recording_id_to_conversation_id_or_object_id",
        )
    }


def scorecard(events: Sequence[Event], *, as_of: datetime | None = None) -> dict[str, Any]:
    if not events:
        return {
            "schema_version": SCHEMA_VERSION,
            "metric_definitions_version": definition_schema_version(),
            "status": "insufficient_evidence",
            "metrics": {},
            "events": {"valid": 0},
        }
    scope_status, scope = _scope_status(events)
    if scope_status != "ok":
        return {
            "schema_version": SCHEMA_VERSION,
            "metric_definitions_version": definition_schema_version(),
            "status": "insufficient_evidence",
            "reason": scope_status,
            "scope": scope,
            "metrics": {},
            "events": {"valid": len(events), "users": len({event.user_id for event in events})},
        }
    observed_as_of = as_of or max(event.occurred_at for event in events)
    metrics: dict[str, Any] = {}
    metrics.update(journey_metrics(events, as_of=observed_as_of))
    metrics.update(activation_and_retention(events, as_of=observed_as_of))
    metrics.update(feedback_metrics(events))
    metrics.update(churn_and_errors(events, as_of=observed_as_of))
    metrics.update(efficiency_metrics(events))
    metrics.update(operational_observation_metrics(events))
    metrics.update(recording_linkage_metrics(events))
    usable = sum(metric.get("status") == "ok" for metric in metrics.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "metric_definitions_version": definition_schema_version(),
        "status": "ok" if usable else "insufficient_evidence",
        "as_of": _json_time(observed_as_of),
        "scope": scope,
        "metrics": metrics,
        "events": {"valid": len(events), "users": len({event.user_id for event in events})},
    }


def _experiment_event_kind(event: Event) -> str:
    if event.name in {"Experiment Enrolled", "Experiment Assignment", "Experiment Assigned", "experiment_assigned"}:
        return "assignment"
    if event.name in {"Experiment Exposed", "Experiment Exposure", "experiment_exposed"}:
        return "exposure"
    if event.name in {"Experiment Outcome", "Experiment Metric Outcome", "experiment_outcome"}:
        return "outcome"
    return ""


def _feature_variant(event: Event, experiment_id: str) -> str | None:
    key = f"$feature/{experiment_id}"
    value = event.properties.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _experiment_success(event: Event) -> bool:
    raw = event.prop("success", "value", "outcome_value", "outcome", default=None)
    if _bool(raw) is True or _number(raw) == 1:
        return True
    return isinstance(raw, str) and raw.lower() in {"success", "succeeded", "true", "helpful"}


def _experiment_metric_hit(event: Event, metric: str) -> bool:
    """Evaluate one of the closed experiment metric filters."""
    if metric == "failure":
        raw = event.prop("outcome", "status", "failure", default=None)
        if isinstance(raw, str) and raw.strip().lower() in {"failure", "failed", "error"}:
            return True
        return _bool(event.prop("success", default=None)) is False
    if metric == "helpful":
        raw = event.prop("helpful", "is_helpful", "value", "outcome", default=None)
        if _bool(raw) is True or _number(raw) == 1:
            return True
        return isinstance(raw, str) and raw.strip().lower() in {"helpful", "positive", "thumbs_up"}
    return _experiment_success(event)


def experiment_comparison(
    events: Sequence[Event],
    *,
    experiment_id: str,
    metric: str = "success",
    as_of: datetime | None = None,
    maturity_days: int = 0,
    conversion_window_hours: int = 24,
    journey: str | None = None,
    registered_variants: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compare mature exposed users by the variant they actually saw.

    Assignment is retained for eligibility/allocation diagnostics. The
    analysis denominator is an unambiguous ``experiment_exposed`` event with
    one variant, and outcomes must be after exposure, before the configured
    conversion window, and before ``as_of``. Missing outcomes remain in the
    denominator and make the result insufficient rather than becoming zeros.
    """
    as_of = as_of or (max((event.occurred_at for event in events), default=datetime.now(timezone.utc)))
    metric = metric.strip().lower()
    if metric not in EXPERIMENT_METRICS:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "experiment_id": experiment_id,
            "reason": "unsupported_metric",
            "metric": metric,
        }
    scope_status, scope = _scope_status(events)
    if scope_status != "ok":
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "reason": scope_status,
            "experiment_id": experiment_id,
            "scope": scope,
        }

    assignments: defaultdict[str, list[tuple[str, datetime]]] = defaultdict(list)
    exposures: defaultdict[str, list[tuple[str, datetime]]] = defaultdict(list)
    candidate_outcomes: defaultdict[str, list[Event]] = defaultdict(list)
    allowed_variants = {str(value).strip() for value in (registered_variants or DEFAULT_EXPERIMENT_VARIANTS) if str(value).strip()}
    unknown_variants: set[str] = set()
    experiment_versions: set[int] = set()
    versioned_events = 0
    unversioned_events = 0

    def _record_experiment_version(event: Event) -> bool:
        nonlocal versioned_events, unversioned_events
        raw = event.prop("experiment_version", default=None)
        if raw is None:
            unversioned_events += 1
            return True
        try:
            version = int(raw)
        except (TypeError, ValueError):
            return False
        if version <= 0:
            return False
        versioned_events += 1
        experiment_versions.add(version)
        return True

    def _belongs(event: Event) -> tuple[str, str | None]:
        explicit_experiment = str(event.prop("experiment_id", "experiment", "experiment_key", default="")).strip()
        feature_variant = _feature_variant(event, experiment_id)
        # ProductTelemetry marks only its identity-fenced outcome/value path
        # verified. Native SDK feature properties and stale cached flags are
        # not enough to attribute a conversion.
        if event.name in {"Product Journey Outcome", "Product Value"}:
            if _bool(event.prop("experiment_context_verified", default=False)) is not True or feature_variant is None:
                return "", None
        if explicit_experiment != experiment_id and feature_variant is None:
            return "", None
        return explicit_experiment, feature_variant

    for event in events:
        if _bool(event.prop("experiment_qa", default=False)) is True:
            continue
        explicit_experiment, feature_variant = _belongs(event)
        if not explicit_experiment and feature_variant is None:
            continue
        kind = _experiment_event_kind(event)
        if kind == "assignment":
            variant = str(event.prop("variant", "arm", default="")).strip()
            if variant:
                if variant not in allowed_variants:
                    unknown_variants.add(variant)
                    continue
                if not _record_experiment_version(event):
                    return {
                        "schema_version": SCHEMA_VERSION,
                        "status": "insufficient_evidence",
                        "experiment_id": experiment_id,
                        "reason": "invalid_experiment_version",
                    }
                assignments[event.user_id].append((variant, event.occurred_at))
        elif kind == "exposure":
            variant = str(event.prop("variant", "arm", default="")).strip() or feature_variant
            if variant:
                if variant not in allowed_variants:
                    unknown_variants.add(variant)
                    continue
                if not _record_experiment_version(event):
                    return {
                        "schema_version": SCHEMA_VERSION,
                        "status": "insufficient_evidence",
                        "experiment_id": experiment_id,
                        "reason": "invalid_experiment_version",
                    }
                exposures[event.user_id].append((variant, event.occurred_at))
        elif kind == "outcome" or event.name in {"Product Journey Outcome", "Product Value"}:
            # Only the canonical experiment outcome events and the verified
            # Dart product-outcome path are eligible. A native `$identify`,
            # autocapture, or arbitrary event may carry cached `$feature/*`
            # properties but has no attribution contract.
            if kind != "outcome" and (
                event.name not in {"Product Journey Outcome", "Product Value"}
                or _bool(event.prop("experiment_context_verified", default=False)) is not True
                or feature_variant is None
            ):
                continue
            # Product outcomes are intentionally not a generic "success"
            # metric. Callers must bind them to the provisioned primary or
            # guardrail journey; otherwise a search/capture success can be
            # mistaken for a feedback conversion.
            if event.name in {"Product Journey Outcome", "Product Value"} and journey is None:
                continue
            if str(event.prop("metric", "metric_name", default=metric)) != metric:
                continue
            # A shared Product Journey Outcome receives experiment attribution
            # via $feature/<key>. Without it, a generic success from another
            # journey must not become this experiment's conversion.
            if event.name == "Product Journey Outcome" and feature_variant is None and not explicit_experiment:
                continue
            if journey is not None and str(event.prop("journey", default="")) != journey:
                continue
            if feature_variant is not None and feature_variant not in allowed_variants:
                unknown_variants.add(feature_variant)
                continue
            candidate_outcomes[event.user_id].append(event)

    # Exposure is authoritative. Drop users who changed arms, or whose
    # assignment and exposure disagree, instead of silently selecting the
    # first-seen arm.
    valid_exposures: dict[str, tuple[str, datetime]] = {}
    assignment_conflicts = 0
    exposure_conflicts = 0
    for uid, records in exposures.items():
        variants = {variant for variant, _ in records}
        if len(variants) != 1:
            exposure_conflicts += 1
            continue
        variant = next(iter(variants))
        assignment_variants = {assigned for assigned, _ in assignments.get(uid, [])}
        if len(assignment_variants) > 1 or (assignment_variants and variant not in assignment_variants):
            assignment_conflicts += 1
            continue
        valid_exposures[uid] = (variant, min(at for _, at in records))

    by_variant: defaultdict[str, list[str]] = defaultdict(list)
    for uid, (variant, _) in valid_exposures.items():
        by_variant[variant].append(uid)
    variants = set(by_variant)
    if unknown_variants:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "experiment_id": experiment_id,
            "reason": "unknown_variant",
            "unknown_variants": sorted(unknown_variants),
            "scope": scope,
        }
    if len(experiment_versions) > 1 or (versioned_events and unversioned_events):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "experiment_id": experiment_id,
            "reason": "experiment_version_conflict",
            "experiment_versions": sorted(experiment_versions),
            "versioned_events": versioned_events,
            "unversioned_events": unversioned_events,
            "scope": scope,
        }
    if len(variants) < 2:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "insufficient_evidence",
            "experiment_id": experiment_id,
            "reason": "two_variants_required",
            "scope": scope,
            "assignment_conflicts": assignment_conflicts,
            "exposure_conflicts": exposure_conflicts,
        }
    if "control" in variants:
        control = "control"
    elif "holdout" in variants:
        control = "holdout"
    else:
        control = sorted(variants)[0]
    preferred_candidates = [name for name in ("candidate", "treatment") if name in variants and name != control]
    candidate = preferred_candidates[0] if preferred_candidates else next(name for name in sorted(variants) if name != control)

    window = timedelta(hours=max(0, conversion_window_hours))
    arm_results: dict[str, Any] = {}
    for variant in sorted(variants, key=lambda name: (name != control, name != candidate, name)):
        uids = by_variant[variant]
        matured_uids = [
            uid
            for uid in uids
            if as_of >= valid_exposures[uid][1] + timedelta(days=max(0, maturity_days))
        ]
        observed_uids: list[str] = []
        successes = 0
        for uid in matured_uids:
            exposure_variant, exposed_at = valid_exposures[uid]
            eligible = []
            for outcome in candidate_outcomes.get(uid, []):
                if outcome.occurred_at <= exposed_at or outcome.occurred_at > as_of or outcome.occurred_at > exposed_at + window:
                    continue
                outcome_variant = _feature_variant(outcome, experiment_id)
                if outcome_variant is not None and outcome_variant != exposure_variant:
                    continue
                if outcome_variant is not None and outcome_variant not in allowed_variants:
                    unknown_variants.add(outcome_variant)
                    continue
                eligible.append(outcome)
            if eligible:
                observed_uids.append(uid)
                if any(_experiment_metric_hit(outcome, metric) for outcome in eligible):
                    successes += 1
        missing = len(matured_uids) - len(observed_uids)
        complete = len(matured_uids) > 0 and missing == 0
        arm_results[variant] = {
            "assigned": sum(1 for records in assignments.values() if records and records[0][0] == variant),
            "exposed": len(uids),
            "matured": len(matured_uids),
            "successes": successes,
            "observed_outcomes": len(observed_uids),
            "missing_outcomes": missing,
            "success_rate": successes / len(matured_uids) if complete else None,
            "success_rate_bounds": (
                [successes / len(matured_uids), (successes + missing) / len(matured_uids)]
                if matured_uids
                else None
            ),
            "completeness": len(observed_uids) / len(matured_uids) if matured_uids else 0.0,
            "uncertainty": {"method": "wilson_95", "interval": _wilson(successes, len(matured_uids))} if complete else None,
        }

    total = sum(len(uids) for uids in by_variant.values())
    control_share = len(by_variant[control]) / total if total else 0.0
    candidate_share = len(by_variant[candidate]) / total if total else 0.0
    imbalance = abs(control_share - candidate_share)
    control_rate = arm_results[control]["success_rate"]
    candidate_rate = arm_results[candidate]["success_rate"]
    complete = all(arm["matured"] > 0 and arm["missing_outcomes"] == 0 for arm in arm_results.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if complete else "insufficient_evidence",
        "experiment_id": experiment_id,
        "metric": metric,
        "journey": journey,
        "experiment_version": next(iter(experiment_versions), None),
        "registered_variants": sorted(allowed_variants),
        "analysis": "exposure_conditioned",
        "maturity_days": maturity_days,
        "conversion_window_hours": conversion_window_hours,
        "as_of": _json_time(as_of),
        "scope": scope,
        "variants": arm_results,
        "comparison": {
            "control": control,
            "candidate": candidate,
            "absolute_difference": (candidate_rate - control_rate) if control_rate is not None and candidate_rate is not None else None,
            "allocation_imbalance": imbalance,
            "allocation_within_heuristic": imbalance <= 0.10,
            "allocation_heuristic": "absolute exposed-arm share difference <= 0.10; descriptive only, not a statistical SRM test",
        },
        "guardrails": {
            "allocation_imbalance_max": 0.10,
            "maturity_required": maturity_days,
            "conversion_window_hours": conversion_window_hours,
            "assignment_conflicts_excluded": assignment_conflicts,
            "exposure_conflicts_excluded": exposure_conflicts,
        },
    }


def evidence_packet(
    events: Sequence[Event],
    *,
    baseline_build: str,
    candidate_build: str,
    threshold: float = 0.05,
    as_of: datetime | None = None,
    experiment_id: str | None = None,
    experiment_metric: str = "success",
    maturity_days: int = 0,
    conversion_window_hours: int = 24,
    journey: str | None = None,
    registered_variants: Sequence[str] | None = None,
) -> dict[str, Any]:
    baseline = scorecard([event for event in events if event.app_build == baseline_build], as_of=as_of)
    candidate = scorecard([event for event in events if event.app_build == candidate_build], as_of=as_of)
    base_metric = baseline["metrics"].get("journey_reliability", {})
    cand_metric = candidate["metrics"].get("journey_reliability", {})
    base_value = base_metric.get("value")
    cand_value = cand_metric.get("value")
    regression = base_value is not None and cand_value is not None and cand_value < base_value - threshold
    related = [event for event in events if event.app_build == candidate_build and (event.raw.get("trace_id") or event.prop("trace_id", "correlation_id"))]
    builds = sorted({event.app_build for event in events if event.app_build != "unknown"})
    prompts = sorted({str(event.prop("prompt_name", default="")) for event in related if event.prop("prompt_name")})
    prompt_commits = sorted({str(event.prop("prompt_commit", default="")) for event in related if event.prop("prompt_commit")})
    traces = sorted({str(event.raw.get("trace_id") or event.prop("trace_id")) for event in related if event.raw.get("trace_id") or event.prop("trace_id")})[:100]
    status = "regression_detected" if regression else ("ok" if base_value is not None and cand_value is not None else "insufficient_evidence")
    packet = {
        "schema_version": "product-evidence-packet.v1",
        "status": status,
        "generated_at": _json_time(datetime.now(timezone.utc)),
        "metric": "journey_reliability",
        "cohort": {"baseline_build": baseline_build, "candidate_build": candidate_build, "as_of": baseline.get("as_of") or candidate.get("as_of")},
        "comparison": {"baseline": base_metric, "candidate": cand_metric, "threshold": threshold},
        "attribution": {"builds": builds, "prompt_names": prompts, "prompt_commits": prompt_commits, "trace_ids": traces},
        "evidence": {"baseline_scorecard": baseline, "candidate_scorecard": candidate, "completeness": {"baseline": baseline.get("status"), "candidate": candidate.get("status")}},
        "proposed_action": {
            "type": "investigate_and_reproduce" if regression else "observe",
            "reason": "candidate reliability regressed beyond threshold" if regression else "no actionable regression proven",
            "rollback_condition": f"journey_reliability remains below {base_value - threshold:.4f}" if regression and base_value is not None else None,
        },
    }
    if experiment_id:
        packet["experiment"] = experiment_comparison(
            events,
            experiment_id=experiment_id,
            metric=experiment_metric,
            as_of=as_of,
            maturity_days=maturity_days,
            conversion_window_hours=conversion_window_hours,
            journey=journey,
            registered_variants=registered_variants,
        )
    return packet


def _load_events(args: argparse.Namespace) -> tuple[list[Event], LoadReport]:
    if args.input:
        return read_jsonl(Path(args.input))
    if args.posthog_hogql:
        if not args.since or not args.until:
            raise SystemExit("PostHog fetch requires --since and --until")
        events = fetch_posthog_events(
            Path(args.posthog_hogql).read_text(encoding="utf-8"), since=args.since, until=args.until
        )
        return events, LoadReport(len(events), len(events), 0, 0, 0, 0)
    raise SystemExit("one of --input or --posthog-hogql is required")


def _write_output(value: Mapping[str, Any], output: str | None) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True)
    if output:
        Path(output).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scorecard", "experiment", "workflow"))
    parser.add_argument("--input")
    parser.add_argument("--posthog-hogql", help="Explicit HogQL file; requires PostHog env configuration")
    parser.add_argument("--output")
    parser.add_argument("--as-of")
    parser.add_argument("--since", help="PostHog query window start (UTC ISO timestamp)")
    parser.add_argument("--until", help="PostHog query window end (UTC ISO timestamp)")
    parser.add_argument("--namespace")
    parser.add_argument("--environment")
    parser.add_argument("--build")
    parser.add_argument("--experiment-id")
    parser.add_argument("--metric", default="success")
    parser.add_argument("--maturity-days", type=int, default=0)
    parser.add_argument("--conversion-window-hours", type=int, default=24)
    parser.add_argument("--journey")
    parser.add_argument("--variants", help="comma-separated registered experiment variants")
    parser.add_argument("--baseline-build")
    parser.add_argument("--candidate-build")
    parser.add_argument("--threshold", type=float, default=0.05)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    events, load = _load_events(args)
    as_of = _parse_time(args.as_of) if args.as_of else None
    events = filtered(events, namespace=args.namespace, environment=args.environment, build=args.build)
    registered_variants = [value.strip() for value in args.variants.split(",") if value.strip()] if args.variants else None
    if args.command == "scorecard":
        result = scorecard(events, as_of=as_of)
        result["load"] = load.__dict__
    elif args.command == "experiment":
        if not args.experiment_id:
            raise SystemExit("--experiment-id is required for experiment")
        result = experiment_comparison(
            events,
            experiment_id=args.experiment_id,
            metric=args.metric,
            as_of=as_of,
            maturity_days=args.maturity_days,
            conversion_window_hours=args.conversion_window_hours,
            journey=args.journey,
            registered_variants=registered_variants,
        )
        result["load"] = load.__dict__
    else:
        if not args.baseline_build or not args.candidate_build:
            raise SystemExit("--baseline-build and --candidate-build are required for workflow")
        result = evidence_packet(
            events,
            baseline_build=args.baseline_build,
            candidate_build=args.candidate_build,
            threshold=args.threshold,
            as_of=as_of,
            experiment_id=args.experiment_id,
            experiment_metric=args.metric,
            maturity_days=args.maturity_days,
            conversion_window_hours=args.conversion_window_hours,
            journey=args.journey,
            registered_variants=registered_variants,
        )
        result["load"] = load.__dict__
    _write_output(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
