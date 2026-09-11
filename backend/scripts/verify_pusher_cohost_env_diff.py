#!/usr/bin/env python3
"""Fail closed when pusher and backend-listen charts diverge without explanation.

Decision 4 of pusher-production-hardening: a shared-config / shared-code-path
host must be verified against its co-hosts, not against its own history. The
2026-08-30 finalization outage shipped ``process_conversation`` onto pusher
while ``MEMORY_ENABLED`` (and the conversation-notes rollout flags) existed
only on backend-listen.

This gate compares explicit ``env:`` key names in the Helm values files — the
keys that actually ship. Shared ``envFrom`` ConfigMap names must also match.
It never reads ConfigMap or Secret values.

Unexplained listen-only or pusher-only keys fail. The current residuals are
an explicit allowlist so a *new* flag cannot repeat the outage class. Growing
the allowlist is a reviewed decision; shrinking it is required when a key
lands on both hosts. Required-identical literals (the shared finalizer
rollout flags) must exist on both hosts with the same value.

Stdlib-only. Runs in pre-push/CI and in the pusher deploy workflows::

  python3 backend/scripts/verify_pusher_cohost_env_diff.py
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ("dev", "prod")

REQUIRED_IDENTICAL_LITERALS = (
    "MEMORY_ENABLED",
    "CONVERSATION_NOTES_V2_ENABLED",
    "CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED",
    "CONVERSATION_OCR_CONTEXT_ENABLED",
)

# Explained listen-only residuals. New listen-only keys fail until added here
# *or* declared on pusher. Do not copy secret refs onto pusher from this list
# without an ExternalSecret inventory (#12298).
LISTEN_ONLY_ALLOWED: dict[str, frozenset[str]] = {
    "dev": frozenset(
        {
            "ACCOUNT_CUTOVER_ENFORCEMENT",
            "DEEPGRAM_API_KEY",
            "DEEPGRAM_SELF_HOSTED_ENABLED",
            "DESKTOP_UPDATE_POINTERS_MODE",
            "DESKTOP_UPDATE_RECONCILE_SAMPLE_RATE",
            "FAIR_USE_3DAY_SPEECH_MS",
            "FAIR_USE_BUCKET_SECONDS",
            "FAIR_USE_CHECK_INTERVAL_SECONDS",
            "FAIR_USE_CLASSIFIER_ABUSE_SCORE_THRESHOLD",
            "FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS",
            "FAIR_USE_CLASSIFIER_LOOKBACK_DAYS",
            "FAIR_USE_CLASSIFIER_MODEL",
            "FAIR_USE_DAILY_SPEECH_MS",
            "FAIR_USE_ENABLED",
            "FAIR_USE_EXEMPT_UIDS",
            "FAIR_USE_KILL_SWITCH",
            "FAIR_USE_REDIS_RETENTION_SECONDS",
            "FAIR_USE_RESTRICT_DAILY_DG_MS",
            "FAIR_USE_WEEKLY_SPEECH_MS",
            "GCP_LOCATION",
            "GEMINI_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_CALENDAR_AUTO_LINK_ENABLED",
            "GROQ_API_KEY",
            "HOSTED_PUSHER_API_URL",
            "HOSTED_TRANSLATION_API_URL",
            "HOSTED_VAD_API_URL",
            "LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED",
            "LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS",
            "LLM_GATEWAY_ACCOUNTING_ENABLED",
            "MCP_OAUTH_CHATGPT_CLIENT_SECRET",
            "MEETING_RECEIPT_RECONCILER_ENABLED",
            "MEMORY_CANONICAL_MAINTENANCE_ENABLED",
            "MEMORY_TYPESENSE_COLLECTION",
            "OMI_FIRESTORE_DATA_PLANE_PROJECT",
            "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED",
            "OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE",
            "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED",
            "OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE",
            "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED",
            "OMI_LLM_GATEWAY_DEV_SHADOW_ALL_SAMPLE_RATE",
            "OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED",
            "OMI_PARITY_PACK_ALLOWED_PRINCIPALS",
            "OMI_PARITY_PACK_CAPTURE",
            "OMI_PARITY_PACK_EXPORT_INTERVAL_SECONDS",
            "OMI_PARITY_PACK_GCS_URI",
            "OMI_PARITY_PACK_ROOT",
            "OPENROUTER_API_KEY",
            "POSTHOG_PROJECT_API_KEY",
            "PUBLIC_SHARED_CONVERSATION_CHAT_MODE",
            "RAPID_API_KEY",
            "REFERRAL_PUBLIC_BASE_URL",
            "SONIOX_API_KEY",
            "TRANSLATION_SERVICE_MODELS",
            "TWILIO_API_KEY_SECRET",
            "TWILIO_AUTH_TOKEN",
            "USE_VERTEX_AI",
            "VAD_GATE_MODE",
            "WAKE_WORD_ADJUDICATION_ENABLED",
            "X_OAUTH_CLIENT_SECRET",
        }
    ),
    "prod": frozenset(
        {
            "ACCOUNT_CUTOVER_ENFORCEMENT",
            "ACCOUNT_DELETION_DISPATCH_MODE",
            "ACCOUNT_DELETION_TASKS_QUEUE",
            "BETA_PROMOTION_TOKEN",
            "DESKTOP_UPDATE_POINTERS_MODE",
            "DESKTOP_UPDATE_RECONCILE_SAMPLE_RATE",
            "FAIR_USE_3DAY_SPEECH_MS",
            "FAIR_USE_BUCKET_SECONDS",
            "FAIR_USE_CHECK_INTERVAL_SECONDS",
            "FAIR_USE_CLASSIFIER_ABUSE_SCORE_THRESHOLD",
            "FAIR_USE_CLASSIFIER_COOLDOWN_SECONDS",
            "FAIR_USE_CLASSIFIER_LOOKBACK_DAYS",
            "FAIR_USE_CLASSIFIER_MODEL",
            "FAIR_USE_DAILY_SPEECH_MS",
            "FAIR_USE_ENABLED",
            "FAIR_USE_EXEMPT_UIDS",
            "FAIR_USE_KILL_SWITCH",
            "FAIR_USE_REDIS_RETENTION_SECONDS",
            "FAIR_USE_RESTRICT_DAILY_DG_MS",
            "FAIR_USE_WEEKLY_SPEECH_MS",
            "GCP_LOCATION",
            "GEMINI_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "HOSTED_PUSHER_API_URL",
            "HOSTED_TRANSLATION_API_URL",
            "HOSTED_VAD_API_URL",
            "LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED",
            "LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS",
            "LLM_GATEWAY_ACCOUNTING_ENABLED",
            "MCP_OAUTH_CHATGPT_CLIENT_SECRET",
            "MCP_OAUTH_CLIENTS_JSON",
            "MEETING_RECEIPT_RECONCILER_ENABLED",
            "MEMORY_BELIEF_MODEL_ENABLED",
            "MEMORY_CANONICAL_MAINTENANCE_ENABLED",
            "MEMORY_TYPESENSE_COLLECTION",
            "MEMORY_V3_CURSOR_SECRET",
            "OMI_FIRESTORE_DATA_PLANE_PROJECT",
            "OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED",
            "POSTHOG_PROJECT_API_KEY",
            "PUBLIC_SHARED_CONVERSATION_CHAT_MODE",
            "REFERRAL_PUBLIC_BASE_URL",
            "SONIOX_API_KEY",
            "SYNC_TASKS_LOCATION",
            "SYNC_TASKS_PROJECT",
            "TRANSLATION_SERVICE_MODELS",
            "TWILIO_API_KEY_SECRET",
            "TWILIO_AUTH_TOKEN",
            "USE_VERTEX_AI",
            "VAD_GATE_MODE",
            "WAKE_WORD_ADJUDICATION_ENABLED",
            "X_OAUTH_CLIENT_SECRET",
        }
    ),
}

PUSHER_ONLY_ALLOWED: dict[str, frozenset[str]] = {
    "dev": frozenset({"GOOGLE_CLIENT_ID", "REDIS_DB_HOST", "TYPESENSE_HOST"}),
    "prod": frozenset({"DEEPGRAM_SELF_HOSTED_URL", "REDIS_DB_HOST", "TYPESENSE_HOST"}),
}

# Shared keys whose *literal* values are allowed to differ. Name-only diffs
# belong in the only-allowed sets above, not here.
SHARED_VALUE_DIFF_ALLOWED: dict[str, frozenset[str]] = {
    "dev": frozenset({"DD_SERVICE", "STRIPE_ARCHITECT_MONTHLY_PRICE_ID"}),
    "prod": frozenset({"BUCKET_SPEECH_PROFILES", "DD_SERVICE", "DEEPGRAM_SELF_HOSTED_ENABLED"}),
}


class DiffError(ValueError):
    """Raised when chart inputs cannot be parsed for a co-host comparison."""


@dataclass(frozen=True)
class EnvEntry:
    name: str
    value: str | None
    secret_key: str | None
    config_map_key: str | None


def _values_path(root: Path, service: str, env: str) -> Path:
    if service == "pusher":
        return root / "backend" / "charts" / "pusher" / f"{env}_omi_pusher_values.yaml"
    if service == "listen":
        return root / "backend" / "charts" / "backend-listen" / f"{env}_omi_backend_listen_values.yaml"
    raise DiffError(f"unknown service {service!r}")


def _env_block_lines(text: str) -> list[str]:
    lines = text.splitlines()
    started = False
    block: list[str] = []
    for line in lines:
        if not started:
            if re.match(r"^env:\s*$", line):
                started = True
            continue
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        block.append(line)
    if not started:
        raise DiffError("values file has no top-level env: list")
    return block


def parse_env_entries(text: str) -> dict[str, EnvEntry]:
    """Parse explicit ``env:`` entries from a chart values file (stdlib)."""

    entries: dict[str, EnvEntry] = {}
    current: str | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal current, body
        if current is None:
            return
        blob = "\n".join(body)
        value_match = re.search(r"^\s+value:\s*(.*)$", blob, re.MULTILINE)
        value = value_match.group(1).strip().strip("\"'") if value_match else None
        secret_match = re.search(
            r"secretKeyRef:\s*\n\s*name:\s*(\S+)\s*\n\s*key:\s*(\S+)",
            blob,
        )
        config_match = re.search(
            r"configMapKeyRef:\s*\n\s*name:\s*(\S+)\s*\n\s*key:\s*(\S+)",
            blob,
        )
        entries[current] = EnvEntry(
            name=current,
            value=value,
            secret_key=secret_match.group(2) if secret_match else None,
            config_map_key=config_match.group(2) if config_match else None,
        )
        current = None
        body = []

    for line in _env_block_lines(text):
        match = re.match(r"^  - name:\s+(\S+)\s*$", line)
        if match:
            flush()
            current = match.group(1)
            body = []
            continue
        if current is not None:
            body.append(line)
    flush()
    if not entries:
        raise DiffError("values file env: list declared no names")
    return entries


def parse_envfrom_configmaps(text: str) -> set[str]:
    return set(re.findall(r"configMapRef:\s*\n\s*name:\s*(\S+)", text))


def _read_values(root: Path, service: str, env: str) -> tuple[dict[str, EnvEntry], set[str]]:
    path = _values_path(root, service, env)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffError(f"could not read {path}: {exc}") from exc
    return parse_env_entries(text), parse_envfrom_configmaps(text)


def validate_preflight(root: Path = ROOT) -> list[str]:
    """Return every unexplained pusher ↔ backend-listen env divergence."""

    errors: list[str] = []
    for env in ENVIRONMENTS:
        try:
            pusher_env, pusher_from = _read_values(root, "pusher", env)
            listen_env, listen_from = _read_values(root, "listen", env)
        except DiffError as exc:
            errors.append(f"[{env}] {exc}")
            continue

        if pusher_from != listen_from:
            errors.append(
                f"[{env}] envFrom ConfigMap set differs: pusher={sorted(pusher_from)} "
                f"listen={sorted(listen_from)} — co-hosts must share the same bulk source"
            )

        for flag in REQUIRED_IDENTICAL_LITERALS:
            pusher_entry = pusher_env.get(flag)
            listen_entry = listen_env.get(flag)
            if pusher_entry is None or listen_entry is None:
                missing = "pusher" if pusher_entry is None else "backend-listen"
                errors.append(
                    f"[{env}] required identical flag {flag} is missing on {missing} "
                    "(shared process_conversation host)"
                )
                continue
            if pusher_entry.value is None or listen_entry.value is None:
                errors.append(f"[{env}] required identical flag {flag} must be a literal on both hosts")
                continue
            if pusher_entry.value != listen_entry.value:
                errors.append(
                    f"[{env}] required identical flag {flag} disagrees: "
                    f"pusher={pusher_entry.value!r} listen={listen_entry.value!r}"
                )

        listen_only = set(listen_env) - set(pusher_env)
        pusher_only = set(pusher_env) - set(listen_env)
        allowed_listen = LISTEN_ONLY_ALLOWED[env]
        allowed_pusher = PUSHER_ONLY_ALLOWED[env]
        unexplained_listen = sorted(listen_only - allowed_listen)
        unexplained_pusher = sorted(pusher_only - allowed_pusher)
        stale_listen = sorted(allowed_listen - listen_only)
        stale_pusher = sorted(allowed_pusher - pusher_only)

        for name in unexplained_listen:
            errors.append(
                f"[{env}] unexplained listen-only env {name} — add it to pusher "
                "or to LISTEN_ONLY_ALLOWED with a reason"
            )
        for name in unexplained_pusher:
            errors.append(
                f"[{env}] unexplained pusher-only env {name} — add it to backend-listen "
                "or to PUSHER_ONLY_ALLOWED with a reason"
            )
        for name in stale_listen:
            errors.append(f"[{env}] LISTEN_ONLY_ALLOWED entry {name} is no longer listen-only; remove it")
        for name in stale_pusher:
            errors.append(f"[{env}] PUSHER_ONLY_ALLOWED entry {name} is no longer pusher-only; remove it")

        allowed_value_diff = SHARED_VALUE_DIFF_ALLOWED[env]
        shared = set(pusher_env) & set(listen_env)
        for name in sorted(shared):
            pusher_value = pusher_env[name].value
            listen_value = listen_env[name].value
            if pusher_value is None or listen_value is None:
                continue
            if pusher_value == listen_value:
                if name in allowed_value_diff:
                    errors.append(f"[{env}] SHARED_VALUE_DIFF_ALLOWED entry {name} now matches; remove it")
                continue
            if name in REQUIRED_IDENTICAL_LITERALS:
                continue
            if name not in allowed_value_diff:
                errors.append(
                    f"[{env}] unexplained literal value diff for shared env {name}: "
                    f"pusher={pusher_value!r} listen={listen_value!r}"
                )
        for name in sorted(allowed_value_diff - shared):
            errors.append(f"[{env}] SHARED_VALUE_DIFF_ALLOWED entry {name} is not shared; remove it")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (for hermetic fixture tests).",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors = validate_preflight(root)
    if errors:
        print("FAIL: pusher co-host env-diff gate", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("OK: pusher co-host env-diff gate passed.")
    for env in ENVIRONMENTS:
        try:
            pusher_env, _ = _read_values(root, "pusher", env)
            listen_env, _ = _read_values(root, "listen", env)
        except DiffError:
            continue
        print(
            f"- {env}: pusher={len(pusher_env)} listen={len(listen_env)} "
            f"listen-only-allowed={len(LISTEN_ONLY_ALLOWED[env])} "
            f"required-identical={len(REQUIRED_IDENTICAL_LITERALS)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
