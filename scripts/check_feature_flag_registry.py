#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

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

# Existing duplicate declarations are assigned to workstream B, which is
# consolidating runtime_env and Helm values to one source per service. This
# reviewed 2026-10-20 allowlist expires 2026-11-20; newly introduced duplicates
# fail immediately and entries must be removed when their source overlap ends.
DUPLICATE_DECLARATION_ALLOWLIST_EXPIRES = date(2026, 11, 20)
DUPLICATE_DECLARATION_ALLOWLIST = {
    "AUDIO_ARCHIVE_PERCENT",
    "AUDIO_ARCHIVE_REGIONAL_CACHE_PERCENT",
    "AUDIO_ARCHIVE_STOP_PCM_PERCENT",
    "AUDIO_ARCHIVE_UID_ALLOWLIST",
    "BATCH_LIVE_STT_RETIRE_PERCENT",
    "BATCH_PIPELINE_PERCENT",
    "BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST",
    "BATCH_PIPELINE_UID_ALLOWLIST",
    "CONVERSATION_RELEVANCE_JEV_PERCENT",
    "DEMAND_PROCESSING_PERCENT",
    "DEMAND_PROCESSING_UID_ALLOWLIST",
    "DREAM_AGENT_UID_ALLOWLIST",
    "FIRST_SUMMARY_DEADLINE_PERCENT",
    "MOBILE_STANDARD_BATCH_PERCENT",
    "PARAKEET_STREAM_ALLOCATION_PERCENT",
    "PARAKEET_WINDOW_ALLOCATION_PERCENT",
    "SPEAKER_GROUPING_SHADOW_PERCENT",
    "SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST",
    "STT_LIVE_DEMAND_PERCENT",
    "STT_LIVE_DEMAND_UID_ALLOWLIST",
    "STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT",
    "STT_ROUTING_ON_PERCENT",
    "SYNC_LEGACY_FRESH_PERCENT",
    "SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST",
    "TRANSCRIPTION_FINAL_PASS_PERCENT",
    "TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST",
    "TRANSCRIPTION_SHADOW_PERCENT",
    "TRANSCRIPTION_SHADOW_UID_ALLOWLIST",
}
# Empty on 2026-10-20: no row is beyond its seven-day grace. Add only an
# already-overdue row with an expiry and reason; the checker prints it as a
# blocker for David until the row is reviewed or the exception expires.
REVIEW_OVERDUE: dict[str, dict[str, str]] = {}


def check(root: Path, *, check_render: bool = True, as_of: date | None = None) -> tuple[list[str], list[str]]:
    current_date = as_of or date.today()
    registry_path = root / "config/feature-flags.yaml"
    registry = load_registry(registry_path)
    errors = validate_registry(registry, root=root)
    if errors:
        return errors, []
    warnings: list[str] = []
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
    for key, sources in duplicate_sources.items():
        source_list = ", ".join(sources)
        if key not in DUPLICATE_DECLARATION_ALLOWLIST:
            errors.append(f"duplicate ramp/allowlist declaration: {key} appears in {source_list}")
        elif current_date > DUPLICATE_DECLARATION_ALLOWLIST_EXPIRES:
            errors.append(
                f"duplicate declaration exception expired {DUPLICATE_DECLARATION_ALLOWLIST_EXPIRES}: "
                f"{key} still appears in {source_list}"
            )
        else:
            warnings.append(
                f"WARNING: duplicate declaration allowlisted until {DUPLICATE_DECLARATION_ALLOWLIST_EXPIRES}: "
                f"{key} appears in {source_list} (workstream B source consolidation)"
            )
    if root.resolve() == ROOT.resolve():
        stale_allowlist = sorted(DUPLICATE_DECLARATION_ALLOWLIST - set(duplicate_sources))
        if stale_allowlist:
            errors.append("remove stale duplicate declaration allowlist entries: " + ", ".join(stale_allowlist))

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
    for key in sorted(beyond_grace):
        exception = REVIEW_OVERDUE.get(key)
        if exception is None:
            errors.append(
                f"review overdue beyond the {REVIEW_GRACE_DAYS}-day grace: {key} "
                f"(review_by {flags[key]['review_by']})"
            )
            continue
        try:
            expires = date.fromisoformat(exception["expires"])
            reason = exception["reason"].strip()
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append(f"review_overdue[{key}] requires an ISO expires date and nonempty reason")
            continue
        if not reason:
            errors.append(f"review_overdue[{key}] requires an ISO expires date and nonempty reason")
        elif current_date > expires:
            errors.append(f"review_overdue exception expired {expires}: {key} (review_by {flags[key]['review_by']})")
        else:
            active_review_exceptions.add(key)
            warnings.append(
                f"BLOCKER for David: review_overdue exception {key} (review_by {flags[key]['review_by']}) "
                f"expires {expires}: {reason}"
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
    args = parser.parse_args()
    try:
        errors, warnings = check(args.root.resolve(), check_render=not args.skip_render)
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
