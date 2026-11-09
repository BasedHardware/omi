#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from feature_flag_parser_defaults import parser_defaults
from feature_flag_registry import (
    REVIEW_GRACE_DAYS,
    RAMP_REQUIRED_FROM,
    ROOT,
    _ramp_applies_to,
    duplicate_declaration_sources,
    extract_action_declarations,
    extract_code_reads,
    extract_deploy_declarations,
    load_registry,
    overdue,
    overdue_beyond_grace,
    validate_registry,
)

AS_OF = re.compile(r"<!-- feature-flag-registry as-of: (\d{4}-\d{2}-\d{2}) -->")

# Rows already past review_by may carry a dated exception (expiry + reason); it is
# printed on every run and turns back into an error when it expires. Entries for
# rows not yet past review_by are stale and fail.
# 2026-11-08: the ad1268 ramp-or-retire sweep (auditfix) covers every row that
# would pass its grace before 2026-11-14; the registry v2 checker replaces these
# with per-row extension fields before they expire.
_AD1268_SWEEP = {"expires": "2026-11-15", "reason": "ad1268 ramp-or-retire sweep in progress (auditfix)"}
REVIEW_OVERDUE: dict[str, dict[str, str]] = {
    "ACTION_ITEM_REFRESH_PRESERVE_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_HEAD_PRIORITY_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_LIVE_ADMISSION_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_PERCENT": _AD1268_SWEEP,
    "BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_PROJECTION_TIMING_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_RECOVERY_ALL_ADMITTED": _AD1268_SWEEP,
    "BATCH_PIPELINE_RECOVERY_MODE": _AD1268_SWEEP,
    "BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST": _AD1268_SWEEP,
    "BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_SERVING_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_SHADOW_PERCENT": _AD1268_SWEEP,
    "BATCH_PIPELINE_SHARED_LIVE_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED": _AD1268_SWEEP,
    "BATCH_PIPELINE_UID_ALLOWLIST": _AD1268_SWEEP,
    "BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED": _AD1268_SWEEP,
    "CAPTURE_GROUP_CONTAINMENT_MODE": _AD1268_SWEEP,
    "CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED": _AD1268_SWEEP,
    "DREAM_AGENT_PAID_PERCENT": _AD1268_SWEEP,
    "DREAM_HISTORY_COMPACT_MODE": _AD1268_SWEEP,
    "DREAM_HISTORY_COMPACT_MODE_SERVE_PERCENT": _AD1268_SWEEP,
    "DREAM_IDLE_SKIP_MODE": _AD1268_SWEEP,
    "DREAM_IDLE_SKIP_MODE_SERVE_PERCENT": _AD1268_SWEEP,
    "DREAM_MATERIAL_BUDGET_MODE": _AD1268_SWEEP,
    "DREAM_MATERIAL_BUDGET_MODE_SERVE_PERCENT": _AD1268_SWEEP,
    "DREAM_PAYOFF_ORDER_MODE": _AD1268_SWEEP,
    "EPISODES_CLIENT_CHANNELS": _AD1268_SWEEP,
    "EPISODES_PERCENT": _AD1268_SWEEP,
    "FIRST_SUMMARY_DEADLINE_ENABLED": _AD1268_SWEEP,
    "FIRST_SUMMARY_DEADLINE_PERCENT": _AD1268_SWEEP,
    "FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED": _AD1268_SWEEP,
    "FIRST_SUMMARY_UID_ALLOWLIST": _AD1268_SWEEP,
    "LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION": _AD1268_SWEEP,
    "LIVE_CAPTURE_WINDOW_MERGE_UNION": _AD1268_SWEEP,
    "LIVE_CAPTURE_WINDOW_RETENTION": _AD1268_SWEEP,
    "LIVE_CAPTURE_WINDOW_STRICT_PROJECTION": _AD1268_SWEEP,
    "LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_C6_TIMEOUT_SECONDS": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_CLAIMS_ENABLED": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_TIERED_ENABLED": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_TIER_MIN_SOURCE_KINDS": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_TIER_MIN_WORDS": _AD1268_SWEEP,
    "MEETING_NOTES_EPISODE_WRITER_TIMEOUT_SECONDS": _AD1268_SWEEP,
    "OMI_SHAPED_AGENT_MODE": _AD1268_SWEEP,
    "PARAKEET_EXPLICIT_CUDA_GRAPHS": _AD1268_SWEEP,
    "PARAKEET_PACKING_ENABLED": _AD1268_SWEEP,
    "PARAKEET_WINDOW_DIARIZATION": _AD1268_SWEEP,
    "SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT": _AD1268_SWEEP,
    "SONIOX_CAPTURE_AXIS_DIAGNOSTICS": _AD1268_SWEEP,
    "SONIOX_ELAPSED_AXIS": _AD1268_SWEEP,
    "SONIOX_ORDERED_FINALIZE": _AD1268_SWEEP,
    "SONIOX_WIRE_LEDGER": _AD1268_SWEEP,
    "SPEAKER_MATCH_SCORES_ENABLED": _AD1268_SWEEP,
    "STT_CAP_RECOVERY_COHORT": _AD1268_SWEEP,
    "STT_FAILOVER_RECOVERY_ENABLED": _AD1268_SWEEP,
    "STT_LEARNED_LANGUAGE_PROFILE": _AD1268_SWEEP,
    "STT_MULTI_LANGUAGE_HINTS": _AD1268_SWEEP,
    "STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT": _AD1268_SWEEP,
    "STT_PAID_SPILLOVER_BUDGET_ENABLED": _AD1268_SWEEP,
    "STT_RESILIENT_RECONNECT": _AD1268_SWEEP,
    "STT_ROUTING_MODE": _AD1268_SWEEP,
    "STT_ROUTING_ON_PERCENT": _AD1268_SWEEP,
    "SUMMARY_DEBT_REPAIR_ENABLED": _AD1268_SWEEP,
    "SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED": _AD1268_SWEEP,
    "SYNC_BACKFILL_ORDER": _AD1268_SWEEP,
    "SYNC_BACKFILL_ORDER_PERCENT": _AD1268_SWEEP,
    "SYNC_BACKFILL_ORDER_UID_ALLOWLIST": _AD1268_SWEEP,
    "SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM": _AD1268_SWEEP,
    "SYNC_DURABLE_REDRIVE_GUARD": _AD1268_SWEEP,
    "SYNC_LEGACY_COMPLETION_CONVERGENCE": _AD1268_SWEEP,
    "SYNC_LINEAGE_LIVE_DEDUPE_ENABLED": _AD1268_SWEEP,
    "SYNC_LINEAGE_RESOLVE_ENABLED": _AD1268_SWEEP,
    "SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST": _AD1268_SWEEP,
    "SYNC_POLL_BACKOFF_ENABLED": _AD1268_SWEEP,
    "TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE": _AD1268_SWEEP,
    "TRANSCRIPTION_FINAL_PASS_PERCENT": _AD1268_SWEEP,
    "TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED": _AD1268_SWEEP,
    "TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST": _AD1268_SWEEP,
    "TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED": _AD1268_SWEEP,
    "TRANSCRIPTION_SHADOW_ENABLED": _AD1268_SWEEP,
    "TRANSCRIPTION_SHADOW_PERCENT": _AD1268_SWEEP,
    "TRANSCRIPTION_SHADOW_UID_ALLOWLIST": _AD1268_SWEEP,
    "onboarding-setup-rating-prompt": _AD1268_SWEEP,
    "proactivity_v2": _AD1268_SWEEP,
    "screen_activity_lossless_sync": _AD1268_SWEEP,
    "screen_activity_lossless_sync_kill": _AD1268_SWEEP,
    "summary-generation-v2": _AD1268_SWEEP,
}
# Only new rollout rows are gated; existing rows still contribute to the count.
MAX_UNRAMPED_PER_OWNER = 5
# Keys use normalize_owner(); exceptions require an ISO expires date and reason.
OWNER_BACKLOG_EXCEPTIONS: dict[str, dict[str, str]] = {
    # 167 legacy rows name the account, not a lane; the retro N3 batch ruling ramps or retires them.
    # New rows should name the owning lane. Expiry turns this back into an error.
    "dazheng": {"expires": "2026-11-15", "reason": "retro N3 ramp-or-retire batch pending"},
}


def normalize_owner(owner: str) -> str:
    """Ignore parenthetical annotations, case and whitespace runs."""
    while re.search(r"\([^()]*\)", owner):
        owner = re.sub(r"\([^()]*\)", " ", owner)
    return " ".join(owner.lower().split())


def owner_backlog(registry: dict[str, Any]) -> Counter[str]:
    return Counter(
        normalize_owner(entry["owner"])
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") == "rollout"
        and entry.get("decision") in {"pending", "undecided"}
        and isinstance(entry.get("owner"), str)
    )


def load_base_registry(root: Path) -> dict[str, Any]:
    # Hooks can export a different repository selection to child Git commands.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    base = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    content = subprocess.run(
        ["git", "show", f"{base}:config/feature-flags.yaml"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="omi-flag-base-") as directory:
        path = Path(directory) / "feature-flags.yaml"
        path.write_text(content, encoding="utf-8")
        return load_registry(path)


def check_owner_backlog(
    root: Path, registry: dict[str, Any], current_date: date, errors: list[str], warnings: list[str]
) -> None:
    try:
        base = load_base_registry(root)
        base_keys = {entry["key"] for entry in base["flags"]}
        counts = owner_backlog(base)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        warnings.append(
            f"WARNING: owner backlog gate skipped: cannot load registry at merge-base with origin/main: {error}"
        )
        return
    for entry in registry["flags"]:
        owner = normalize_owner(entry["owner"])
        if entry["key"] in base_keys or entry["lifecycle"] != "rollout" or counts[owner] < MAX_UNRAMPED_PER_OWNER:
            continue
        message = (
            f"{entry['key']}: owner={owner} had {counts[owner]} unramped flags at merge-base "
            f"(cap {MAX_UNRAMPED_PER_OWNER}); ramp or retire before adding"
        )
        exception = OWNER_BACKLOG_EXCEPTIONS.get(owner)
        if exception is None:
            errors.append(message)
            continue
        try:
            expires = date.fromisoformat(exception["expires"])
            reason = exception["reason"].strip()
            if not reason:
                raise ValueError("empty reason")
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append(f"owner_backlog_exceptions[{owner}] requires an ISO expires date and nonempty reason")
            continue
        if current_date > expires:
            errors.append(f"owner backlog exception expired {expires}: {message}")
        else:
            warnings.append(f"WARNING: owner backlog exception expires {expires}: {message} ({reason})")


def check(root: Path, *, check_render: bool = True, as_of: date | None = None) -> tuple[list[str], list[str]]:
    # UTC, so a pre-push hook on a host ahead of UTC agrees with CI.
    current_date = as_of or datetime.now(timezone.utc).date()
    registry_path = root / "config/feature-flags.yaml"
    registry = load_registry(registry_path)
    errors = validate_registry(registry, root=root)
    for owner, count in sorted(owner_backlog(registry).items()):
        print(f"FLAG_OWNER_BACKLOG owner={owner} unramped={count}")
    if errors:
        return errors, []
    warnings: list[str] = []
    check_owner_backlog(root, registry, current_date, errors, warnings)
    flags = {entry["key"]: entry for entry in registry["flags"]}
    for key, expected in parser_defaults(root).items():
        if key in flags and flags[key]["fail"] != expected:
            errors.append(f"{key}: fail must be {expected} for the shared boolean parser; regenerate the registry")
    grandfathered = sum(
        1
        for entry in registry["flags"]
        if _ramp_applies_to(entry) and date.fromisoformat(entry["created"]) < RAMP_REQUIRED_FROM and "ramp" not in entry
    )
    if grandfathered:
        warnings.append(
            f"WARNING: {grandfathered} grandfathered pending/undecided rollout rows lack ramp "
            f"(created before {RAMP_REQUIRED_FROM.isoformat()})"
        )
    else:
        warnings.append(f"Grandfathered pending/undecided rollout rows without ramp: 0 (cutoff {RAMP_REQUIRED_FROM})")
    alias_to_key = {alias: entry["key"] for entry in registry["flags"] for alias in entry.get("aliases", [])}
    ignored = {entry["key"] for entry in registry["ignore"]}
    retired = {entry["key"] for entry in registry["retired"]}
    known = set(flags) | set(alias_to_key) | ignored | retired
    reads = extract_code_reads(root, known)
    present = {read.key for read in reads}
    for read in reads:
        if read.key in retired:
            errors.append(f"{read.path}:{read.line}: retired name reintroduced: {read.key}")
        elif read.key not in known:
            errors.append(f"{read.path}:{read.line}: unregistered feature flag: {read.key}")
    for key in sorted(set(flags) | set(alias_to_key)):
        if key not in present:
            errors.append(f"stale registry entry: delete it or restore the read: {key}")
    declarations = extract_deploy_declarations(root) + extract_action_declarations(root)
    for declared in declarations:
        if declared.key not in known:
            errors.append(f"{declared.path}:{declared.line}: undeclared registry flag: {declared.key}")
        elif declared.key in retired:
            errors.append(f"{declared.path}:{declared.line}: retired name redeclared: {declared.key}")

    duplicate_sources = duplicate_declaration_sources(declarations)
    for (key, _platform, workload, environment), sources in duplicate_sources.items():
        errors.append(
            f"duplicate declaration: {key} for {workload}/{environment} appears in {', '.join(sources)}: keep one source, "
            "or declare it in the manifest gke section that validates this chart"
        )

    doc = root / "backend/docs/feature-flag-registry.md"
    if check_render:
        old = doc.read_text(encoding="utf-8") if doc.is_file() else ""
        match = AS_OF.search(old)
        if match is None:
            errors.append(
                f"{doc.relative_to(root)}: missing committed as-of header; regenerate with python3 scripts/render_feature_flag_registry.py --as-of 2026-09-24"
            )
        else:
            as_of = date.fromisoformat(match[1])
            from render_feature_flag_registry import render

            fresh = render(root, registry, as_of)
            if old != fresh:
                errors.append(
                    f"{doc.relative_to(root)}: rendered doc drift; regenerate with python3 scripts/render_feature_flag_registry.py --as-of {as_of.isoformat()}"
                )
    past_due = overdue(registry, current_date)
    beyond_grace = set(overdue_beyond_grace(registry, current_date))
    in_grace = sorted(set(past_due) - beyond_grace)
    if in_grace:
        details = ", ".join(f"{key} (review_by {flags[key]['review_by']})" for key in in_grace)
        warnings.append(f"WARNING: review_by passed but remains within the {REVIEW_GRACE_DAYS}-day grace: {details}")

    active_review_exceptions: set[str] = set()
    for key in sorted(beyond_grace - set(REVIEW_OVERDUE)):
        errors.append(
            f"review overdue beyond the {REVIEW_GRACE_DAYS}-day grace: {key} "
            f"(review_by {flags[key]['review_by']})"
        )
    for key in sorted(set(REVIEW_OVERDUE) & set(past_due)):
        exception = REVIEW_OVERDUE[key]
        try:
            expires = date.fromisoformat(exception["expires"])
            reason = exception["reason"].strip()
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append(f"review_overdue[{key}] requires an ISO expires date and nonempty reason")
            continue
        if not reason:
            errors.append(f"review_overdue[{key}] requires an ISO expires date and nonempty reason")
        elif current_date > expires:
            active_review_exceptions.add(key)
            if key in beyond_grace:
                errors.append(f"review_overdue exception expired {expires}: {key} (review_by {flags[key]['review_by']})")
        else:
            active_review_exceptions.add(key)
            warnings.append(
                f"review_overdue exception {key} (review_by {flags[key]['review_by']}) expires {expires}: {reason}"
            )
    if root.resolve() == ROOT.resolve():
        stale_review_exceptions = sorted(set(REVIEW_OVERDUE) - active_review_exceptions)
        if stale_review_exceptions:
            errors.append("remove stale review_overdue entries: " + ", ".join(stale_review_exceptions))
    return sorted(set(errors)), warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, help="evaluate review dates as of YYYY-MM-DD (UTC)")
    args = parser.parse_args()
    try:
        errors, warnings = check(args.root.resolve(), check_render=not args.skip_render, as_of=args.as_of)
    except (OSError, ValueError, SyntaxError) as error:
        print(f"feature-flag registry: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(warning, file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("feature-flag registry: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
