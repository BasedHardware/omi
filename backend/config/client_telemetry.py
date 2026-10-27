"""Frozen client-telemetry contract (v1).

Pure validation, canonical hashing, histogram conservation and aggregate
planning. Persistence lives in ``database.client_telemetry``. Enum literals
are taken from the frozen transport contract plus the existing emitters:

- screen task: ``TaskAssistant+ScreenTask.swift``, ``ScreenTaskTelemetry.swift``,
  ``ScreenTaskPipeline.swift``, ``ScreenTaskErrors.swift``
- voice route/reason: ``VoiceTurnCoordinator.routeLabel``, ``VoiceTurnTerminalReason``,
  ``DesktopDiagnosticsManager.voiceTurnOutcome``
- ingress aliases: ``OmiCaptureHealth.swift`` (``actionRequired``) and the
  contract's bounded phase/reason/recovery sets
- wedge trigger alias: Flutter ``rapid_reconnects`` → contract ``rapid_reconnect``
- fallback area/reason: ``utils.observability.fallback`` registered literals;
  unknown from/to/reason become ``unknown``; unknown areas become ``other``
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 128 * 1024
MAX_OBSERVATIONS = 100
MAX_OBSERVATION_BYTES = 4 * 1024
MAX_QUERY_ROWS = 50_000
RATE_LIMIT_BATCHES = 10
RATE_WINDOW_SECONDS = 60
DEDUP_RETENTION = timedelta(hours=48)
OBSERVATION_RETENTION = timedelta(days=30)
AGGREGATE_RETENTION = timedelta(days=90)
FUTURE_SKEW = timedelta(minutes=5)
MAX_EVENT_AGE = timedelta(hours=24)
STALE_AFTER = timedelta(minutes=15)
STANDARD_DURATION_MAX_MS = 86_400_000
SESSION_DURATION_MAX_MS = 604_800_000

HISTOGRAM_EDGES: tuple[str, ...] = (
    "0.05",
    "0.1",
    "0.25",
    "0.5",
    "1",
    "2",
    "5",
    "10",
    "30",
    "60",
    "120",
    "300",
    "900",
    "3600",
    "86400",
)
SESSION_EDGE = "604800"
INF_EDGE = "+Inf"

PLATFORMS = frozenset({"ios", "android", "macos"})
CHANNELS = frozenset({"production", "beta"})
QUERY_CHANNELS = frozenset({"production", "beta", "all"})
FAMILIES = frozenset(
    {
        "upload",
        "conversation_processing",
        "capture_ingress",
        "capture_wedge",
        "device_session",
        "screen_task",
        "voice_turn",
        "fallback",
    }
)

UPLOAD_PHASES = frozenset({"started", "accepted", "completed", "failed", "deferred"})
UPLOAD_SOURCES = frozenset({"pendant", "phone", "sdcard", "other", "unknown"})
FAILURE_CLASSES = frozenset(
    {"network", "timeout", "auth", "rate_limited", "client_error", "server_error", "cancelled", "unknown"}
)
CONVERSATION_OUTCOMES = frozenset({"completed", "failed", "cancelled"})
LATENCY_BASES = frozenset({"processing_observed", "request_started", "unknown"})
INGRESS_PHASES = frozenset(
    {
        "unknown",
        "inactive",
        "unverified",
        "subscribing",
        "awaiting_audio",
        "flowing",
        "quiet",
        "repairing",
        "recovering",
        "reconnecting",
        "action_required",
        "disconnected",
    }
)
INGRESS_PHASE_ALIASES = {"actionRequired": "action_required"}
INGRESS_REASONS = frozenset(
    {
        "none",
        "cccd_timeout_recovery",
        "subscription_timeout",
        "no_audio",
        "stale_audio",
        "disconnected",
        "unauthorized",
        "unknown",
    }
)
RECOVERY_OUTCOMES = frozenset({"none", "attempted", "recovered", "failed", "exhausted", "unknown"})
WEDGE_PHASES = frozenset({"detected", "resolved"})
WEDGE_TRIGGERS = frozenset(
    {
        "zero_bytes",
        "rapid_reconnect",
        "bytes_sent_no_transcript",
        "upload_silence",
        "ingress_recovery_failed",
        "other",
        "unknown",
    }
)
WEDGE_TRIGGER_ALIASES = {"rapid_reconnects": "rapid_reconnect"}
WEDGE_OUTCOMES = frozenset({"pending", "recovered", "failed", "exhausted", "unknown"})
DEVICE_VENDORS = frozenset({"omi", "limitless", "other", "unknown"})
DISCONNECT_CLASSES = frozenset({"intentional", "link_loss", "timeout", "adapter_off", "permission", "unknown"})
SCREEN_PIPELINES = frozenset({"screen_task_v2", "legacy", "unknown"})
SCREEN_EXTRACTORS = frozenset({"gemini_3_8", "legacy", "none", "unknown"})
SCREEN_GATE_OUTCOMES = frozenset({"passed", "rejected", "fail_open", "none", "unknown"})
SCREEN_OUTCOMES = frozenset(
    {"completed", "failed", "refused", "disabled", "dedupe_skipped", "gate_rejected", "unknown"}
)
SCREEN_ERROR_CLASSES = frozenset(
    {
        "none",
        "delivery_failure",
        "legacy_task_reservation_inactive",
        "timeout",
        "offline",
        "auth",
        "plan_or_quota",
        "gate_budget_cooldown",
        "backpressure",
        "admission_denied",
        "provider_5xx",
        "stopped",
        "owner_revoked",
        "privacy_revoked",
        "invalid_response",
        "provider_outage",
        "http_terminal",
        "cancelled",
        "local_failure",
        "unknown",
    }
)
SCREEN_FALLBACK_REASONS = frozenset(
    {
        "none",
        "ocr_unusable",
        "dispatch_disabled",
        "unknown",
        "gate_unavailable",
        "timeout",
        "provider_5xx",
        "provider_429",
        "enqueue_failed",
        "config_incomplete",
        "circuit_open",
        "last_resort",
        "connection_lost",
        "modulate_serve_error",
        "capability_mismatch",
        "auth",
        "quota",
        "local_heal",
        "policy",
        "byok",
        "malformed_doc",
        "capacity_full",
        "first_text_deadline",
        "empty_streak",
        "allocation_rejected",
        "private_tool_output_in_context",
        "not_authorized",
        "authorization_unavailable",
        "unmigrated_principal",
        "other",
        "initialization_failed",
        "send_failed",
        "socket_unavailable",
        "provider_budget_exhausted",
        "provider_auth_rejected",
        "provider_rate_limited",
        "soniox_idle_timeout",
        "soniox_request_timeout",
        "soniox_no_audio_teardown",
        "soniox_rotation",
        "no_text_rescue_complete",
        "soniox_invalid_hint",
        "vad_failed",
        "client_disconnect",
        "normal_close",
        "text",
        "no_text",
    }
)
SCREEN_COUNTERS = (
    "eligible_frames",
    "invalid_items",
    "gate_attempts",
    "extraction_attempts",
    "legacy_attempts",
    "policy_rejected",
    "outbox_saved",
    "coalesced",
    "pending_delivered",
    "failed",
)
SCREEN_DURATIONS = (
    "ocr_ms",
    "retrieval_ms",
    "gate_ms",
    "extraction_ms",
    "delivery_ms",
    "capture_to_terminal_ms",
)
VOICE_PHASES = frozenset({"started", "terminal"})
VOICE_POPULATIONS = frozenset({"physical_shortcut", "floating_voice"})
VOICE_INTENTS = frozenset({"hold", "locked", "legacy", "unknown"})
VOICE_OUTCOMES = frozenset({"success", "failure", "excluded", "unknown"})
VOICE_ROUTES = frozenset(
    {
        "undecided",
        "hub_warm_wait",
        "hub",
        "omni_stt",
        "deepgram_batch",
        "deepgram_live",
        "on_device_asr",
        "floating_voice",
        "none",
        "unknown",
    }
)
VOICE_REASONS = frozenset(
    {
        "success",
        "too_short",
        "silent_rejected",
        "cancelled",
        "owner_changed",
        "interrupted_by_barge_in",
        "permission_denied",
        "capture_failed",
        "capture_not_ready",
        "transcription_failed",
        "provider_failed",
        "no_network",
        "provider_no_response",
        "hub_warm_timeout",
        "deferred_commit_timeout",
        "barge_in_replacement_timeout",
        "tool_timeout",
        "playback_failed",
        "journal_failed",
        "explicit_interrupt",
        "cleanup",
        # contract §7: floating-voice failure/cancel reasons the macOS client
        # emits (ClientTelemetryShadow.floatingFailureReasons / floatingCancelReasons)
        "agent_error",
        "agent_runtime",
        "attachment_upload",
        "authentication",
        "bridge_start_failed",
        "bridge_unavailable",
        "browser_extension_missing",
        "concurrent_request",
        "encoding",
        "quota",
        "resource_exhausted",
        "session_setup",
        "superseded",
        "task_cancelled",
        "timeout",
        "tool_stall",
        "transient_network",
        "user_stop",
        "unknown",
    }
)
VOICE_EXCLUDED_REASONS = frozenset(
    {
        "too_short",
        "silent_rejected",
        "cancelled",
        "owner_changed",
        "interrupted_by_barge_in",
        "explicit_interrupt",
        "cleanup",
    }
)
FALLBACK_OUTCOMES = frozenset({"recovered", "degraded", "exhausted"})
# sol blocker: one aggregate document per UTC day grows without bound (2,008
# voice actors tripped the 900KB guard). Series/voice data is hash-sharded
# across DAY_SHARD_COUNT documents per day; the day *summary* document stays
# small (counters + shard manifest) and is the only document sealing touches.
DAY_SHARD_COUNT = 16


def day_shard_id(day: str, owner: str, series_key: str, salt: str = "") -> str:
    """Deterministic shard document id for one observation.

    The owner is part of the hash so different actors never share a shard
    assignment. `salt` adds per-turn uniqueness for voice observations: their
    shard must spread by turn (operation id), not by series key, or 2,000+
    same-owner voice actors would re-create the single-document capacity
    failure this sharding exists to prevent. Shards are merged additively, so
    the same series/voice key legitimately appearing in several shards sums.
    """
    digest = hashlib.sha256(f"{owner}\0{series_key}\0{salt}".encode("utf-8")).hexdigest()
    return f"{day}#s{int(digest[:8], 16) % DAY_SHARD_COUNT}"


FALLBACK_AREAS = frozenset({"realtime_hub", "ptt_cascade", "screen_task_gate", "screen_task_extraction", "other"})
# Registered allowlists for fallback `from`/`to` endpoints and `reason` values.
# Sources of truth: the client emitters bound these before send
# (DesktopDiagnosticsManager.shadowFallbackEndpoints / allowedFallbackReasons);
# this backend set must stay a superset. Non-members bucket to "unknown".
FALLBACK_ENDPOINTS = frozenset(
    {
        "openai",
        "gemini",
        "gemini_3_8",
        "gemini_2_5_flash",
        "gemini_2_5_flash_lite",
        "legacy",
        "jev",
        "claude",
        "local",
        "cloud",
        "primary",
        "secondary",
        "hub",
        "stt",
        "on_device",
        "deepgram",
        "disabled",
        "enabled",
        "floating_voice",
        "none",
        "unknown",
    }
)
FALLBACK_REASONS = frozenset(
    {
        "auth",
        "bind_failed",
        "ble_decode_failed",
        "byok",
        "capability_mismatch",
        "circuit_open",
        "config_incomplete",
        "contentless_projection",
        "db_backoff",
        "db_lock_contention",
        "dispatch_disabled",
        "engine_failed",
        "enqueue_failed",
        "gate_invalid_response",
        "gate_unavailable",
        "http_401",
        "local_heal",
        "mode_switch_timeout",
        "none",
        "ocr_unusable",
        "offline",
        "other",
        "out_of_memory",
        "policy",
        "process_exited",
        "provider_429",
        "provider_5xx",
        "quota",
        "stale_alive_latch",
        "state_divergence",
        "status_inferred",
        "timeout",
        "upload_failed",
        "wal_directory_unavailable",
        "wal_write_failed",
        "unknown",
    }
)
ENVELOPE_KEYS = frozenset({"schema_version", "batch_id", "observations"})
OBSERVATION_KEYS = frozenset({"event_id", "occurred_at", "platform", "channel", "family", "attributes"})

_FLAG_TRUE = frozenset({"1", "true", "on", "yes"})


class TelemetryContractError(Exception):
    """A batch or query outcome the router maps to HTTP."""

    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


def migration_flags(environ: dict[str, str] | None = None) -> dict[str, bool]:
    """Reader, transport-shadow and retirement flags. All default off."""
    env = os.environ if environ is None else environ

    def enabled(name: str) -> bool:
        return env.get(name, "off").strip().lower() in _FLAG_TRUE

    return {
        "transport_shadow": enabled("CLIENT_TELEMETRY_TRANSPORT"),
        "reader": enabled("CLIENT_TELEMETRY_READER"),
        "retirement": enabled("CLIENT_TELEMETRY_RETIREMENT"),
    }


def iso_z(value: datetime) -> str:
    text = value.astimezone(timezone.utc).isoformat()
    if text.endswith("+00:00"):
        return text[: -len("+00:00")] + "Z"
    return text


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(observation: dict[str, Any]) -> str:
    body = {
        "occurred_at": observation["occurred_at"],
        "platform": observation["platform"],
        "channel": observation["channel"],
        "family": observation["family"],
        "attributes": observation["attributes"],
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def series_key(platform: str, channel: str, family: str, dimensions: dict[str, str]) -> str:
    return canonical_json({"platform": platform, "channel": channel, "family": family, "dimensions": dimensions})


def empty_histogram(session: bool = False) -> dict[str, Any]:
    width = len(HISTOGRAM_EDGES) + (2 if session else 1)
    return {"count": 0, "sum_ms": 0, "buckets": [0] * width, "session": session}


def add_histogram(hist: dict[str, Any], duration_ms: int) -> None:
    seconds = Decimal(duration_ms) / Decimal(1000)
    edges = list(HISTOGRAM_EDGES)
    if hist.get("session"):
        edges.append(SESSION_EDGE)
    for index, edge in enumerate(edges):
        if seconds <= Decimal(edge):
            hist["buckets"][index] += 1
    hist["buckets"][-1] += 1
    hist["count"] += 1
    hist["sum_ms"] += duration_ms


def histogram_public(hist: dict[str, Any]) -> dict[str, Any]:
    edges = list(HISTOGRAM_EDGES)
    if hist.get("session"):
        edges.append(SESSION_EDGE)
    edges.append(INF_EDGE)
    buckets = []
    for edge, count in zip(edges, hist["buckets"]):
        le_seconds: str | float = edge if edge == INF_EDGE else float(edge)
        buckets.append({"le_seconds": le_seconds, "count": count})
    return {"count": hist["count"], "sum_ms": hist["sum_ms"], "buckets": buckets}


from typing import NoReturn


def _fail(message: str) -> NoReturn:
    raise TelemetryContractError(422, "telemetry_invalid", message)


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("%s must be an object" % label)
    return value


def _reject_unknown(payload: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        _fail("%s contains unknown keys: %s" % (label, ", ".join(extra)))


def _uuid(value: Any, label: str) -> str:
    if not isinstance(value, str):
        _fail("%s must be a UUID" % label)
    parsed: str | None
    try:
        parsed = str(UUID(value))
    except ValueError:
        parsed = None
    if parsed is None:
        _fail("%s must be a UUID" % label)
    assert parsed is not None
    return parsed


def _enum(value: Any, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail("%s is not an allowed value" % label)
    return value


def _bucket(value: Any, allowed: frozenset[str], aliases: dict[str, str] | None = None) -> str:
    if isinstance(value, str):
        mapped = aliases.get(value, value) if aliases else value
        if mapped in allowed:
            return mapped
    return "unknown"


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("%s must be a boolean" % label)
    return value


def _int(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("%s must be an integer" % label)
    if value < low or value > high:
        _fail("%s is out of range" % label)
    return value


def _timestamp(value: Any, now: datetime) -> datetime:
    if not isinstance(value, str):
        _fail("occurred_at must be a UTC timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed: datetime | None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        _fail("occurred_at must be a UTC timestamp")
    assert parsed is not None and parsed.tzinfo is not None
    parsed = parsed.astimezone(timezone.utc)
    if parsed - now > FUTURE_SKEW:
        _fail("occurred_at is too far in the future")
    if now - parsed > MAX_EVENT_AGE:
        _fail("occurred_at is older than 24 hours")
    return parsed


def _duration(value: Any, label: str, high: int = STANDARD_DURATION_MAX_MS) -> int:
    return _int(value, label, 0, high)


def _voice_outcome(reason: str, provided: str | None) -> str:
    if provided is not None:
        return provided
    if reason == "success":
        return "success"
    if reason in VOICE_EXCLUDED_REASONS:
        return "excluded"
    if reason == "unknown":
        return "unknown"
    return "failure"


def _dimensions(pairs: list[tuple[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in pairs:
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def _check_observation_size(raw: dict[str, Any]) -> None:
    encoded = canonical_json(raw).encode("utf-8")
    if len(encoded) > MAX_OBSERVATION_BYTES:
        _fail("observation exceeds 4 KiB")


def validate_batch(payload: Any, now: datetime) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(batch_id, normalized observations)`` or raise 422."""
    body = _require_object(payload, "batch")
    _reject_unknown(body, ENVELOPE_KEYS, "batch")
    if body.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version must be 1")
    batch_id = _uuid(body.get("batch_id"), "batch_id")
    observations = body.get("observations")
    if not isinstance(observations, list) or not observations:
        _fail("observations must be a non-empty list")
    observation_list: list[Any] = observations
    assert isinstance(observation_list, list)
    if len(observation_list) > MAX_OBSERVATIONS:
        _fail("observations exceeds 100")
    normalized = []
    seen: dict[str, str] = {}
    for index, raw in enumerate(observation_list):
        item = _require_object(raw, "observation %d" % index)
        _check_observation_size(item)
        normalized.append(_normalize_observation(item, now))
        event_id = normalized[-1]["event_id"]
        digest = normalized[-1]["content_hash"]
        previous = seen.get(event_id)
        if previous is not None and previous != digest:
            raise TelemetryContractError(
                409,
                "telemetry_conflict",
                "batch repeats event_id with a different payload",
            )
        seen[event_id] = digest
    return batch_id, normalized


def _normalize_observation(raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    _reject_unknown(raw, OBSERVATION_KEYS, "observation")
    occurred = _timestamp(raw.get("occurred_at"), now)
    platform = _enum(raw.get("platform"), PLATFORMS, "platform")
    channel = _enum(raw.get("channel"), CHANNELS, "channel")
    family = _enum(raw.get("family"), FAMILIES, "family")
    attributes = _require_object(raw.get("attributes"), "attributes")
    normalized_attributes, dimensions, durations, voice = _normalize_attributes(family, attributes)
    observation = {
        "event_id": _uuid(raw.get("event_id"), "event_id"),
        "occurred_at": iso_z(occurred),
        "day": occurred.astimezone(timezone.utc).date().isoformat(),
        "platform": platform,
        "channel": channel,
        "family": family,
        "attributes": normalized_attributes,
        "dimensions": dimensions,
        "durations": durations,
        "voice": voice,
    }
    observation["content_hash"] = content_hash(observation)
    observation["series_key"] = series_key(platform, channel, family, dimensions)
    return observation


def _normalize_attributes(
    family: str, attributes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], dict[str, int], dict[str, Any] | None]:
    if family == "upload":
        return _upload(attributes)
    if family == "conversation_processing":
        return _conversation(attributes)
    if family == "capture_ingress":
        return _ingress(attributes)
    if family == "capture_wedge":
        return _wedge(attributes)
    if family == "device_session":
        return _device(attributes)
    if family == "screen_task":
        return _screen(attributes)
    if family == "voice_turn":
        return _voice(attributes)
    return _fallback(attributes)


def _require_keys(attributes: dict[str, Any], required: frozenset[str], optional: frozenset[str]) -> None:
    _reject_unknown(attributes, required | optional, "attributes")
    missing = sorted(required - set(attributes))
    if missing:
        _fail("attributes missing %s" % ", ".join(missing))


def _upload(attributes: dict[str, Any]):
    required = frozenset({"attempt_id", "phase", "source"})
    optional = frozenset({"http_status", "failure_class", "latency_ms", "operation_id"})
    _require_keys(attributes, required, optional)
    phase = _enum(attributes["phase"], UPLOAD_PHASES, "phase")
    source = _enum(attributes["source"], UPLOAD_SOURCES, "source")
    failure = None
    if "failure_class" in attributes:
        failure = _enum(attributes["failure_class"], FAILURE_CLASSES, "failure_class")
    http_status = None
    if "http_status" in attributes:
        http_status = _int(attributes["http_status"], "http_status", 100, 599)
    latency = None
    if "latency_ms" in attributes:
        latency = _duration(attributes["latency_ms"], "latency_ms")
    operation_id = _uuid(attributes["operation_id"], "operation_id") if "operation_id" in attributes else None
    attempt_id = _uuid(attributes["attempt_id"], "attempt_id")
    stored: dict[str, Any] = {"attempt_id": attempt_id, "phase": phase, "source": source}
    if failure is not None:
        stored["failure_class"] = failure
    if http_status is not None:
        stored["http_status"] = http_status
    if latency is not None:
        stored["latency_ms"] = latency
    if operation_id is not None:
        stored["operation_id"] = operation_id
    durations = {} if latency is None else {"latency_ms": latency}
    return stored, _dimensions([("phase", phase), ("source", source), ("failure_class", failure)]), durations, None


def _conversation(attributes: dict[str, Any]):
    required = frozenset({"operation_id", "outcome"})
    optional = frozenset({"latency_ms", "latency_basis"})
    _require_keys(attributes, required, optional)
    outcome = _enum(attributes["outcome"], CONVERSATION_OUTCOMES, "outcome")
    basis = None
    if "latency_basis" in attributes:
        basis = _enum(attributes["latency_basis"], LATENCY_BASES, "latency_basis")
    latency = _duration(attributes["latency_ms"], "latency_ms") if "latency_ms" in attributes else None
    stored: dict[str, Any] = {"operation_id": _uuid(attributes["operation_id"], "operation_id"), "outcome": outcome}
    if basis is not None:
        stored["latency_basis"] = basis
    if latency is not None:
        stored["latency_ms"] = latency
    durations = {} if latency is None else {"latency_ms": latency}
    return stored, _dimensions([("outcome", outcome), ("latency_basis", basis)]), durations, None


def _ingress(attributes: dict[str, Any]):
    required = frozenset(
        {
            "operation_id",
            "phase",
            "reason",
            "subscription_confirmed",
            "recovery_outcome",
            "recovery_spent",
            "reconnect_spent",
        }
    )
    optional = frozenset({"unverified_duration_ms"})
    _require_keys(attributes, required, optional)
    phase = _bucket(attributes["phase"], INGRESS_PHASES, INGRESS_PHASE_ALIASES)
    reason = _bucket(attributes["reason"], INGRESS_REASONS)
    recovery = _bucket(attributes["recovery_outcome"], RECOVERY_OUTCOMES)
    confirmed = _bool(attributes["subscription_confirmed"], "subscription_confirmed")
    recovery_spent = _bool(attributes["recovery_spent"], "recovery_spent")
    reconnect_spent = _bool(attributes["reconnect_spent"], "reconnect_spent")
    unverified = None
    if "unverified_duration_ms" in attributes:
        unverified = _duration(attributes["unverified_duration_ms"], "unverified_duration_ms")
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "phase": phase,
        "reason": reason,
        "subscription_confirmed": confirmed,
        "recovery_outcome": recovery,
        "recovery_spent": recovery_spent,
        "reconnect_spent": reconnect_spent,
    }
    if unverified is not None:
        stored["unverified_duration_ms"] = unverified
    durations = {} if unverified is None else {"unverified_duration_ms": unverified}
    dimensions = _dimensions(
        [
            ("phase", phase),
            ("reason", reason),
            ("subscription_confirmed", confirmed),
            ("recovery_outcome", recovery),
            ("recovery_spent", recovery_spent),
            ("reconnect_spent", reconnect_spent),
        ]
    )
    return stored, dimensions, durations, None


def _wedge(attributes: dict[str, Any]):
    required = frozenset({"operation_id", "phase", "trigger", "outcome"})
    optional = frozenset({"latency_ms"})
    _require_keys(attributes, required, optional)
    phase = _enum(attributes["phase"], WEDGE_PHASES, "phase")
    trigger = _bucket(attributes["trigger"], WEDGE_TRIGGERS, WEDGE_TRIGGER_ALIASES)
    outcome = _bucket(attributes["outcome"], WEDGE_OUTCOMES)
    latency = _duration(attributes["latency_ms"], "latency_ms") if "latency_ms" in attributes else None
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "phase": phase,
        "trigger": trigger,
        "outcome": outcome,
    }
    if latency is not None:
        stored["latency_ms"] = latency
    durations = {} if latency is None else {"latency_ms": latency}
    return stored, _dimensions([("phase", phase), ("trigger", trigger), ("outcome", outcome)]), durations, None


def _device(attributes: dict[str, Any]):
    required = frozenset({"operation_id", "vendor", "disconnect_class", "recovery_outcome", "duration_ms"})
    optional = frozenset({"hci_reason_code", "intentional"})
    _require_keys(attributes, required, optional)
    vendor = _bucket(attributes["vendor"], DEVICE_VENDORS)
    disconnect = _bucket(attributes["disconnect_class"], DISCONNECT_CLASSES)
    recovery = _bucket(attributes["recovery_outcome"], RECOVERY_OUTCOMES)
    duration = _duration(attributes["duration_ms"], "duration_ms", SESSION_DURATION_MAX_MS)
    intentional = _bool(attributes["intentional"], "intentional") if "intentional" in attributes else None
    hci = _int(attributes["hci_reason_code"], "hci_reason_code", 0, 255) if "hci_reason_code" in attributes else None
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "vendor": vendor,
        "disconnect_class": disconnect,
        "recovery_outcome": recovery,
        "duration_ms": duration,
    }
    if intentional is not None:
        stored["intentional"] = intentional
    if hci is not None:
        stored["hci_reason_code"] = hci
    dimensions = _dimensions(
        [
            ("vendor", vendor),
            ("disconnect_class", disconnect),
            ("recovery_outcome", recovery),
            ("intentional", intentional),
        ]
    )
    return stored, dimensions, {"duration_ms": duration}, None


def _screen(attributes: dict[str, Any]):
    required = frozenset(
        {
            "operation_id",
            "schema_version",
            "pipeline",
            "gate_outcome",
            "audit_sample",
            "extractor",
            "outcome",
            "error_class",
            "fallback_reason",
            "eligible_frames",
            "feature_enabled_at_start",
            "client_bypass",
            "invalid_items",
            "gate_attempts",
            "extraction_attempts",
            "legacy_attempts",
            "policy_rejected",
            "outbox_saved",
            "coalesced",
            "pending_delivered",
            "failed",
        }
    )
    optional = frozenset(SCREEN_DURATIONS)
    _require_keys(attributes, required, optional)
    if attributes["schema_version"] != 2:
        _fail("screen_task schema_version must be 2")
    pipeline = _bucket(attributes["pipeline"], SCREEN_PIPELINES)
    gate = _bucket(attributes["gate_outcome"], SCREEN_GATE_OUTCOMES)
    extractor = _bucket(attributes["extractor"], SCREEN_EXTRACTORS)
    outcome = _bucket(attributes["outcome"], SCREEN_OUTCOMES)
    error_class = _bucket(attributes["error_class"], SCREEN_ERROR_CLASSES)
    fallback_reason = _bucket(attributes["fallback_reason"], SCREEN_FALLBACK_REASONS)
    eligible = _int(attributes["eligible_frames"], "eligible_frames", 0, 1)
    invalid_items = _int(attributes["invalid_items"], "invalid_items", 0, 8)
    counters = {
        "eligible_frames": eligible,
        "invalid_items": invalid_items,
        "gate_attempts": _int(attributes["gate_attempts"], "gate_attempts", 0, 1_000_000),
        "extraction_attempts": _int(attributes["extraction_attempts"], "extraction_attempts", 0, 1_000_000),
        "legacy_attempts": _int(attributes["legacy_attempts"], "legacy_attempts", 0, 1_000_000),
        "policy_rejected": _int(attributes["policy_rejected"], "policy_rejected", 0, 1_000_000),
        "outbox_saved": _int(attributes["outbox_saved"], "outbox_saved", 0, 1_000_000),
        "coalesced": _int(attributes["coalesced"], "coalesced", 0, 1_000_000),
        "pending_delivered": _int(attributes["pending_delivered"], "pending_delivered", 0, 1_000_000),
        "failed": _int(attributes["failed"], "failed", 0, 1_000_000),
    }
    audit = _bool(attributes["audit_sample"], "audit_sample")
    enabled = _bool(attributes["feature_enabled_at_start"], "feature_enabled_at_start")
    bypass = _bool(attributes["client_bypass"], "client_bypass")
    durations: dict[str, int] = {}
    for name in SCREEN_DURATIONS:
        if name in attributes:
            durations[name] = _duration(attributes[name], name)
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "schema_version": 2,
        "pipeline": pipeline,
        "gate_outcome": gate,
        "audit_sample": audit,
        "extractor": extractor,
        "outcome": outcome,
        "error_class": error_class,
        "fallback_reason": fallback_reason,
        "feature_enabled_at_start": enabled,
        "client_bypass": bypass,
    }
    stored.update(counters)
    stored.update(durations)
    dimensions = _dimensions(
        [
            ("pipeline", pipeline),
            ("gate_outcome", gate),
            ("audit_sample", audit),
            ("extractor", extractor),
            ("outcome", outcome),
            ("error_class", error_class),
            ("fallback_reason", fallback_reason),
            ("feature_enabled_at_start", enabled),
            ("client_bypass", bypass),
        ]
    )
    stored["_counters"] = counters
    return stored, dimensions, durations, None


def _voice(attributes: dict[str, Any]):
    required = frozenset({"operation_id", "phase", "population", "route", "intent"})
    optional = frozenset({"outcome", "reason", "latency_ms"})
    _require_keys(attributes, required, optional)
    phase = _enum(attributes["phase"], VOICE_PHASES, "phase")
    population = _enum(attributes["population"], VOICE_POPULATIONS, "population")
    intent = _enum(attributes["intent"], VOICE_INTENTS, "intent")
    route = _bucket(attributes["route"], VOICE_ROUTES)
    reason = (
        _bucket(attributes.get("reason", "unknown"), VOICE_REASONS)
        if "reason" in attributes or phase == "terminal"
        else None
    )
    if phase == "terminal" and reason is None:
        reason = "unknown"
    provided_outcome = None
    if "outcome" in attributes:
        provided_outcome = _enum(attributes["outcome"], VOICE_OUTCOMES, "outcome")
    outcome = (
        _voice_outcome(reason or "unknown", provided_outcome)
        if phase == "terminal"
        else (provided_outcome or "unknown")
    )
    latency = _duration(attributes["latency_ms"], "latency_ms") if "latency_ms" in attributes else None
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "phase": phase,
        "population": population,
        "route": route,
        "intent": intent,
        "outcome": outcome,
    }
    if reason is not None:
        stored["reason"] = reason
    if latency is not None:
        stored["latency_ms"] = latency
    durations: dict[str, int] = {}
    if phase == "terminal" and outcome == "success" and latency is not None:
        durations["latency_ms"] = latency
    voice = {
        "health_event": "voice_turn_started" if phase == "started" else "voice_turn_terminal",
        "outcome": outcome,
        "reason": reason or "unknown",
        "route": route,
        "intent": intent,
        "population": population,
        "duration_ms": durations.get("latency_ms", 0),
        # sol blocker: latency samples must be countable independently of success
        # count — absent latency contributes to `count` but never to `latency_count`
        # or the latency sum, so mixed known/unknown successes cannot bias the mean.
        "latency_present": "latency_ms" in durations,
    }
    dimensions = _dimensions(
        [
            ("phase", phase),
            ("population", population),
            ("route", route),
            ("intent", intent),
            ("outcome", outcome),
            ("reason", reason),
        ]
    )
    return stored, dimensions, durations, voice


def _fallback(attributes: dict[str, Any]):
    required = frozenset({"operation_id", "area", "from", "to", "reason", "outcome"})
    optional = frozenset({"latency_ms"})
    _require_keys(attributes, required, optional)
    area = (
        attributes["area"] if isinstance(attributes["area"], str) and attributes["area"] in FALLBACK_AREAS else "other"
    )
    outcome = _enum(attributes["outcome"], FALLBACK_OUTCOMES, "outcome")
    origin = _bucket(attributes["from"], FALLBACK_ENDPOINTS)
    dest = _bucket(attributes["to"], FALLBACK_ENDPOINTS)
    reason = _bucket(attributes["reason"], FALLBACK_REASONS)
    latency = _duration(attributes["latency_ms"], "latency_ms") if "latency_ms" in attributes else None
    stored: dict[str, Any] = {
        "operation_id": _uuid(attributes["operation_id"], "operation_id"),
        "area": area,
        "from": origin,
        "to": dest,
        "reason": reason,
        "outcome": outcome,
    }
    if latency is not None:
        stored["latency_ms"] = latency
    durations = {} if latency is None else {"latency_ms": latency}
    dimensions = _dimensions([("area", area), ("from", origin), ("to", dest), ("reason", reason), ("outcome", outcome)])
    return stored, dimensions, durations, None


def _blank_day(day: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "day": day,
        "rollup_sealed": False,
        "sealed_at": None,
        "accepted_observations": 0,
        "accepted_batches": 0,
        "last_accepted_at": None,
        "series": {},
        "voice": {},
    }


def _ensure_series(day_doc: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    key = observation["series_key"]
    series = day_doc["series"].get(key)
    if series is None:
        series = {
            "platform": observation["platform"],
            "channel": observation["channel"],
            "family": observation["family"],
            "dimensions": dict(observation["dimensions"]),
            "counters": {},
            "durations": {},
        }
        day_doc["series"][key] = series
    return series


def _add_counter(series: dict[str, Any], name: str, amount: int = 1) -> None:
    counter = name if name.endswith("_total") else name + "_total"
    series["counters"][counter] = series["counters"].get(counter, 0) + amount


def _add_durations(series: dict[str, Any], observation: dict[str, Any]) -> None:
    session = observation["family"] == "device_session"
    for name, duration_ms in observation["durations"].items():
        if observation["family"] == "screen_task" and duration_ms <= 0:
            continue
        hist = series["durations"].get(name)
        if hist is None:
            hist = empty_histogram(session=session and name == "duration_ms")
            series["durations"][name] = hist
        add_histogram(hist, duration_ms)


def _apply_screen_counters(series: dict[str, Any], attributes: dict[str, Any]) -> None:
    for name, amount in attributes.get("_counters", {}).items():
        _add_counter(series, name, amount)


def _public_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attributes.items() if key != "_counters"}


def _upload_conservation(
    series: dict[str, Any],
    observation: dict[str, Any],
    attempt: dict[str, Any],
    shards: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    phase = observation["attributes"]["phase"]
    _add_counter(series, phase)
    if phase == "started":
        return attempt
    if phase == "accepted" and not attempt.get("request_terminal"):
        attempt["request_terminal"] = "accepted"
        attempt["pending"] = True
        attempt["accepted_series_key"] = observation["series_key"]
        attempt["accepted_day"] = observation["day"]
        _add_counter(series, "pending_accepted")
        return attempt
    if phase in {"failed", "deferred"} and not attempt.get("request_terminal"):
        attempt["request_terminal"] = phase
        return attempt
    if phase != "completed":
        return attempt
    if attempt.get("pending") and not attempt.get("accepted_completed"):
        attempt["accepted_completed"] = True
        attempt["pending"] = False
        _add_counter(series, "accepted_completed")
        accepted_shard = shards.get(
            day_shard_id(
                attempt.get("accepted_day", observation["day"]),
                attempt.get("owner", ""),
                attempt.get("accepted_series_key", ""),
            )
        )
        accepted_series = (
            None if accepted_shard is None else accepted_shard["series"].get(attempt.get("accepted_series_key"))
        )
        if accepted_series is not None:
            pending = accepted_series["counters"].get("pending_accepted_total", 0)
            accepted_series["counters"]["pending_accepted_total"] = max(0, pending - 1)
        elif attempt.get("accepted_series_key") == observation["series_key"]:
            pending = series["counters"].get("pending_accepted_total", 0)
            series["counters"]["pending_accepted_total"] = max(0, pending - 1)
        return attempt
    if not attempt.get("request_terminal"):
        attempt["request_terminal"] = "completed"
        _add_counter(series, "request_completed")
    return attempt


def plan_batch(
    owner: str,
    observations: list[dict[str, Any]],
    now: datetime,
    rate: dict[str, Any] | None,
    dedup: dict[str, dict[str, Any]],
    attempts: dict[str, dict[str, Any]],
    days: dict[str, dict[str, Any]],
    shards: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan one atomic batch against already-read durable state.

    Conflict and rate-limit results contain no aggregate writes. Duplicate
    event ids do not increment counters. ``accepted_count + duplicate_count``
    equals the input length on success.
    """
    window = int(now.timestamp()) // RATE_WINDOW_SECONDS
    current = rate or {"window": window, "count": 0}
    if current.get("window") != window:
        current = {"window": window, "count": 0}
    if int(current.get("count", 0)) >= RATE_LIMIT_BATCHES:
        retry_after = RATE_WINDOW_SECONDS - (int(now.timestamp()) % RATE_WINDOW_SECONDS)
        raise TelemetryContractError(
            429,
            "telemetry_rate_limited",
            "per-owner batch rate limit exceeded",
            retry_after=max(1, retry_after),
        )
    next_rate = {"window": window, "count": int(current.get("count", 0)) + 1, "owner": owner}
    seen: dict[str, str] = {}
    for observation in observations:
        event_id = observation["event_id"]
        digest = observation["content_hash"]
        existing = dedup.get(event_id)
        if existing and _dedup_active(existing, now) and existing.get("content_hash") != digest:
            return _conflict(next_rate)
        prior = seen.get(event_id)
        if prior is not None and prior != digest:
            return _conflict(next_rate)
        seen[event_id] = digest

    next_days = {day: deepcopy(doc) for day, doc in days.items()}
    next_shards = {key: deepcopy(doc) for key, doc in (shards or {}).items()}
    next_attempts = {key: deepcopy(doc) for key, doc in attempts.items()}
    next_dedup: dict[str, dict[str, Any]] = {}
    observation_writes: dict[str, dict[str, Any]] = {}
    accepted = 0
    duplicates = 0
    seen = {}
    accepted_at = iso_z(now)
    expires = iso_z(now + DEDUP_RETENTION)

    for observation in observations:
        event_id = observation["event_id"]
        digest = observation["content_hash"]
        existing = dedup.get(event_id)
        prior = seen.get(event_id)
        if (existing and _dedup_active(existing, now) and existing.get("content_hash") == digest) or prior == digest:
            duplicates += 1
            seen[event_id] = digest
            continue
        seen[event_id] = digest
        _apply_one(owner, observation, next_days, next_attempts, next_shards)
        accepted += 1
        next_dedup[event_id] = {
            "owner": owner,
            "event_id": event_id,
            "content_hash": digest,
            "accepted_at": accepted_at,
            "expires_at": expires,
        }
        observation_writes[event_id] = {
            "owner": owner,
            "event_id": event_id,
            "accepted_at": accepted_at,
            "expires_at": iso_z(now + OBSERVATION_RETENTION),
            "occurred_at": observation["occurred_at"],
            "platform": observation["platform"],
            "channel": observation["channel"],
            "family": observation["family"],
            "attributes": _public_attributes(observation["attributes"]),
            "content_hash": digest,
        }

    if accepted:
        touched = {item["day"] for item in observations if item["event_id"] in next_dedup}
        for day in touched:
            doc = next_days[day]
            doc["last_accepted_at"] = accepted_at
            doc["accepted_batches"] = int(days.get(day, {}).get("accepted_batches", 0)) + 1

    return {
        "status": 200,
        "accepted_count": accepted,
        "duplicate_count": duplicates,
        "rate": next_rate,
        "dedup": next_dedup,
        "attempts": next_attempts,
        "days": next_days,
        "shards": next_shards,
        "observations": observation_writes,
    }


def _conflict(rate: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": 409,
        "code": "telemetry_conflict",
        "message": "event_id payload does not match the stored observation",
        "accepted_count": 0,
        "duplicate_count": 0,
        "rate": rate,
        "dedup": {},
        "attempts": {},
        "days": {},
        "shards": {},
        "observations": {},
    }


def _dedup_active(existing: dict[str, Any], now: datetime) -> bool:
    expires_at = existing.get("expires_at")
    if not isinstance(expires_at, str):
        return True
    text = expires_at[:-1] + "+00:00" if expires_at.endswith("Z") else expires_at
    try:
        expiry = datetime.fromisoformat(text)
    except ValueError:
        return True
    if expiry.tzinfo is None:
        return True
    return expiry.astimezone(timezone.utc) > now


def observation_shard_id(owner: str, observation: dict[str, Any]) -> str:
    """Single source of truth for an observation's shard id (read AND write)."""
    salt = observation["attributes"].get("operation_id", "") if observation["family"] == "voice_turn" else ""
    return day_shard_id(observation["day"], owner, observation["series_key"], salt)


def _apply_one(
    owner: str,
    observation: dict[str, Any],
    days: dict[str, dict[str, Any]],
    attempts: dict[str, dict[str, Any]],
    shards: dict[str, dict[str, Any]] | None = None,
) -> None:
    day = observation["day"]
    doc = days.get(day)
    if doc is None:
        doc = _blank_day(day)
        days[day] = doc
    # sol blocker: series/voice contributions live in per-day shard documents
    # keyed by day_shard_id(day, series_key); the day summary keeps only small
    # counters and the shard manifest, so no single document can fill up.
    shard_map: dict[str, dict[str, Any]] = shards if shards is not None else {}
    shard_id = observation_shard_id(owner, observation)
    blank_shard: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "day": day,
        "shard_id": shard_id,
        "series": {},
        "voice": {},
    }
    shard: dict[str, Any] = shard_map.get(shard_id, blank_shard)
    if shard_id not in shard_map:
        shard_map[shard_id] = shard
    manifest = doc.setdefault("shards", {})
    manifest[shard_id] = True
    target = _ensure_series(shard, observation)
    _add_counter(target, "observations")
    doc.setdefault("series_counts", {})
    doc["series_counts"][observation["series_key"]] = doc["series_counts"].get(observation["series_key"], 0) + 1
    if observation["family"] == "upload":
        attempt_id = observation["attributes"]["attempt_id"]
        attempt = attempts.get(attempt_id) or {"owner": owner, "attempt_id": attempt_id}
        attempts[attempt_id] = _upload_conservation(target, observation, attempt, shard_map)
    elif observation["family"] == "screen_task":
        _apply_screen_counters(target, observation["attributes"])
    else:
        phase = observation["attributes"].get("phase")
        if isinstance(phase, str):
            _add_counter(target, phase)
        outcome = observation["attributes"].get("outcome")
        if observation["family"] != "voice_turn" and isinstance(outcome, str):
            _add_counter(target, outcome)
    _add_durations(target, observation)
    voice = observation.get("voice")
    if voice is not None:
        assert isinstance(voice, dict), "voice payload must be a dict"
        voice_key = canonical_json(
            {
                "channel": observation["channel"],
                "actor_id": owner,
                "health_event": voice["health_event"],
                "outcome": voice["outcome"],
                "reason": voice["reason"],
                "route": voice["route"],
                "intent": voice["intent"],
                "population": voice["population"],
            }
        )
        row: dict[str, Any] | None = shard["voice"].get(voice_key)
        if row is None:
            row = {
                "day": day,
                "channel": observation["channel"],
                "actor_id": owner,
                "health_event": voice["health_event"],
                "outcome": voice["outcome"],
                "reason": voice["reason"],
                "route": voice["route"],
                "intent": voice["intent"],
                "population": voice["population"],
                "count": 0,
                "duration_ms": 0,
                "latency_count": 0,
            }
            shard["voice"][voice_key] = row
        voice_row: dict[str, Any] = row
        voice_row["count"] = int(voice_row.get("count", 0)) + 1
        voice_row["duration_ms"] = int(voice_row.get("duration_ms", 0)) + int(voice["duration_ms"])
        if voice.get("latency_present"):
            voice_row["latency_count"] = int(voice_row.get("latency_count", 0)) + 1
    doc["accepted_observations"] = int(doc.get("accepted_observations", 0)) + 1


def window_days(now: datetime, days: int) -> list[str]:
    if days < 1 or days > 90:
        _fail("days must be between 1 and 90")
    end = now.astimezone(timezone.utc).date()
    return [(end - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def aggregate_visible(day: str, now: datetime) -> bool:
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return False
    age = now.astimezone(timezone.utc).date() - parsed
    return timedelta(0) <= age <= AGGREGATE_RETENTION


def project_query(
    day_docs: dict[str, dict[str, Any] | None],
    now: datetime,
    days: int,
    channel: str,
    channel_by_actor: dict[str, str] | None,
) -> dict[str, Any]:
    """Build the aggregate response from day documents already loaded.

    Missing health receipts and unsealed days stay partial. Store failures are
    the caller's responsibility (503) and must not arrive here as empty docs
    that pretend the feed is healthy.
    """
    if channel not in QUERY_CHANNELS:
        _fail("channel must be production, beta, or all")
    selected = window_days(now, days)
    rows: list[dict[str, Any]] = []
    voice_rows: list[dict[str, Any]] = []
    sealed: list[str] = []
    classification_partial = False
    stale = False
    for day in selected:
        if not aggregate_visible(day, now):
            continue
        doc = day_docs.get(day)
        if not doc:
            continue
        if doc.get("rollup_sealed") is True:
            sealed.append(day)
        last_accepted = doc.get("last_accepted_at")
        if doc.get("rollup_sealed") is not True and isinstance(last_accepted, str):
            text = last_accepted[:-1] + "+00:00" if last_accepted.endswith("Z") else last_accepted
            try:
                accepted_at = datetime.fromisoformat(text)
            except ValueError:
                accepted_at = None
            if accepted_at is not None and now - accepted_at.astimezone(timezone.utc) > STALE_AFTER:
                stale = True
        for series in doc.get("series", {}).values():
            if channel != "all" and series.get("channel") != channel:
                continue
            rows.append(
                {
                    "day": day,
                    "platform": series["platform"],
                    "channel": series["channel"],
                    "family": series["family"],
                    "dimensions": dict(series.get("dimensions") or {}),
                    "counters": dict(series.get("counters") or {}),
                    "durations": {
                        name: histogram_public(hist) for name, hist in (series.get("durations") or {}).items()
                    },
                }
            )
        for voice in doc.get("voice", {}).values():
            if channel != "all" and voice.get("channel") != channel:
                continue
            actor_id = voice.get("actor_id")
            if channel_by_actor is None:
                if voice:
                    classification_partial = True
            else:
                classified = channel_by_actor.get(actor_id)
                if classified is None:
                    # sol blocker: once a roster exists, an unclassified actor
                    # must be excluded (not returned raw) and still mark the
                    # feed partial so consumers know classification was thin.
                    classification_partial = True
                    continue
                if classified != voice.get("channel"):
                    classification_partial = True
                    continue
            voice_rows.append(dict(voice))
    if len(rows) + len(voice_rows) > MAX_QUERY_ROWS:
        raise TelemetryContractError(503, "telemetry_query_truncated", "aggregate response exceeds 50000 rows")
    rows.sort(
        key=lambda row: (row["day"], row["platform"], row["channel"], row["family"], canonical_json(row["dimensions"]))
    )
    voice_rows.sort(
        key=lambda row: (
            row["day"],
            row["channel"],
            row["actor_id"],
            row["population"],
            row["health_event"],
            row["route"],
            row["intent"],
            row["outcome"],
            row["reason"],
        )
    )
    coverage_start = sealed[0] if sealed else None
    complete_through = None
    if sealed:
        sealed_set = set(sealed)
        cursor = datetime.strptime(sealed[0], "%Y-%m-%d").date()
        end = datetime.strptime(selected[-1], "%Y-%m-%d").date()
        while cursor.isoformat() in sealed_set and cursor <= end:
            complete_through = cursor.isoformat()
            cursor += timedelta(days=1)
    window_sealed = bool(sealed) and set(sealed) == set(selected)
    partial = (not window_sealed) or classification_partial or stale or coverage_start is None
    available = complete_through is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now),
        "coverage_start": coverage_start,
        "complete_through": complete_through,
        "partial": partial or not available,
        "available": available,
        "rows": rows,
        "voice_rows": voice_rows,
        "stale": stale,
    }


def finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return False
    return True
