"""Validate the checked-in Cloud Storage lifecycle contract for private-cloud-sync.

Offline validator, in the shape of ``validate_frame_request_bucket_contract.py``:
it reads a checked-in desired document and, optionally, a
``gcloud storage buckets describe --format=json`` fixture. It never creates or
mutates a bucket.

The load-bearing facts this guards:

* ``gcloud storage buckets update --lifecycle-file`` **replaces** the whole
  lifecycle config, so a desired file that forgets a live rule silently deletes
  that rule. Without ``--allow-rule-removal`` this validator refuses any desired
  file that drops a rule present in the live describe. Rollback is narrower:
  ``--allow-rule-removal-of <apply document>`` permits dropping only rules that
  the apply variant declared (the Coldline rule); any other live rule still
  blocks. ``--allow-rule-removal`` remains as an explicit operator override.
* No ``Delete`` action may ever reach ``chunks/``. An unscoped Delete rule counts
  as reaching it.
* Every ``SetStorageClass`` rule must be prefix-scoped to exactly ``chunks/``.
* Noncurrent-version rules (``isLive: false`` and friends) are forbidden: a
  bucket-wide noncurrent rule would move ``playback/`` noncurrent versions to
  Coldline, which the 30-day Delete rule then early-deletes.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CHUNKS_PREFIX = "chunks/"
ALLOWED_ACTIONS = {"Delete", "SetStorageClass"}
ALLOWED_SOURCE_CLASSES = {"STANDARD", "MULTI_REGIONAL"}
NONCURRENT_CONDITION_KEYS = ("daysSinceNoncurrentTime", "noncurrentTimeBefore", "numNewerVersions")

PROD_BUCKET = "omi-private-cloud-sync"
LEGACY_DELETE_RULES: tuple[dict[str, Any], ...] = (
    {"action": {"type": "Delete"}, "condition": {"age": 3, "matchesPrefix": ["merged/"]}},
    {"action": {"type": "Delete"}, "condition": {"age": 30, "matchesPrefix": ["playback/"]}},
)


def _rules(document: Mapping[str, Any] | None) -> list[Any]:
    if not isinstance(document, Mapping):
        return []
    lifecycle = document.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        return []
    rules = lifecycle.get("rule")
    return list(rules) if isinstance(rules, list) else []


def _prefix_touches_chunks(prefix: str) -> bool:
    """True when a lifecycle prefix can select an object under ``chunks/``."""
    return prefix.startswith(CHUNKS_PREFIX) or CHUNKS_PREFIX.startswith(prefix)


def validate_desired_document(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    bucket = str(document.get("bucket") or "").strip()
    project = str(document.get("project") or "").strip()
    if not bucket:
        errors.append("desired document must name a bucket")
    if not project:
        errors.append("desired document must name a project")
    lifecycle = document.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or not isinstance(lifecycle.get("rule"), list):
        errors.append("desired document must contain lifecycle.rule as a list")
        return errors

    set_class_rules = 0
    for index, rule in enumerate(lifecycle["rule"]):
        if not isinstance(rule, Mapping):
            errors.append(f"desired rule {index} is not an object")
            continue
        action = rule.get("action") if isinstance(rule.get("action"), Mapping) else {}
        condition = rule.get("condition") if isinstance(rule.get("condition"), Mapping) else {}
        action_type = action.get("type")
        if not isinstance(action_type, str) or action_type not in ALLOWED_ACTIONS:
            errors.append(f"desired rule {index} has unsupported action {action_type!r}")
            continue
        if condition.get("isLive") is False or any(key in condition for key in NONCURRENT_CONDITION_KEYS):
            errors.append(
                f"desired rule {index} targets noncurrent versions; noncurrent-version rules are forbidden "
                "(they would Coldline playback/ noncurrent versions that the 30-day Delete rule early-deletes)"
            )
        prefixes = condition.get("matchesPrefix")
        if prefixes is not None and (
            not isinstance(prefixes, Sequence)
            or isinstance(prefixes, (str, bytes))
            or not all(isinstance(p, str) for p in prefixes)
        ):
            errors.append(f"desired rule {index} matchesPrefix must be a list of strings")
            continue

        if action_type == "Delete":
            if not prefixes:
                errors.append(
                    f"desired rule {index} is an unscoped Delete; a Delete rule must never be able to match {CHUNKS_PREFIX!r}"
                )
            else:
                for prefix in prefixes:
                    if _prefix_touches_chunks(prefix):
                        errors.append(
                            f"desired rule {index} is a Delete rule whose prefix {prefix!r} can match {CHUNKS_PREFIX!r}"
                        )
        else:  # SetStorageClass
            set_class_rules += 1
            if action.get("storageClass") != "COLDLINE":
                errors.append(
                    f"desired rule {index} must set storageClass COLDLINE, got {action.get('storageClass')!r}"
                )
            age = condition.get("age")
            if not isinstance(age, int) or isinstance(age, bool) or age < 30:
                errors.append(f"desired rule {index} must carry an integer age >= 30, got {age!r}")
            if list(prefixes or []) != [CHUNKS_PREFIX]:
                errors.append(
                    f"desired rule {index} SetStorageClass must be prefix-scoped to exactly ['{CHUNKS_PREFIX}'], "
                    f"got {prefixes!r}"
                )
            source_classes = condition.get("matchesStorageClass")
            classes_ok = (
                isinstance(source_classes, list)
                and all(isinstance(c, str) for c in source_classes)
                and sorted(source_classes) == sorted(ALLOWED_SOURCE_CLASSES)
            )
            if not classes_ok:
                errors.append(
                    f"desired rule {index} matchesStorageClass must be exactly "
                    f"{sorted(ALLOWED_SOURCE_CLASSES)}, got {source_classes!r}"
                )

    if set_class_rules > 1:
        errors.append(f"desired document declares {set_class_rules} SetStorageClass rules; exactly one is expected")
    if bucket == PROD_BUCKET:
        for legacy in LEGACY_DELETE_RULES:
            if legacy not in lifecycle["rule"]:
                errors.append(f"desired document is missing the legacy prod rule {json.dumps(legacy, sort_keys=True)}")
    return errors


def validate_against_live(
    desired: Mapping[str, Any],
    live: Mapping[str, Any],
    allow_rule_removal: bool = False,
    expect_applied: bool = False,
    allow_rule_removal_of: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    live_name = str(live.get("name") or "").strip()
    bucket = str(desired.get("bucket") or "").strip()
    if live_name and bucket and live_name != bucket:
        errors.append(f"live bucket name {live_name!r} does not match desired bucket {bucket!r}")
    versioning = live.get("versioning")
    enabled = versioning.get("enabled") if isinstance(versioning, Mapping) else None
    if enabled is not True:
        errors.append("live bucket versioning must be enabled; it is the only undo for a mass-delete bug")

    desired_rules = _rules(desired)
    live_rules = _rules(live)
    if not allow_rule_removal:
        # Scoped removal (rollback): only rules the apply variant declared may
        # be dropped; a later live rule the apply never contained still blocks.
        droppable: Sequence[Any] = (
            desired_rules if allow_rule_removal_of is None else desired_rules + list(allow_rule_removal_of)
        )
        for rule in live_rules:
            if rule in droppable:
                continue
            hint = (
                "Re-declare it or pass --allow-rule-removal."
                if allow_rule_removal_of is None
                else "Re-declare it, or restrict removal to rules the apply variant declared."
            )
            errors.append(
                "desired document drops a rule that is live on the bucket "
                f"({json.dumps(rule, sort_keys=True)}); --lifecycle-file replaces the whole config, "
                f"so this would delete it. {hint}"
            )
    if expect_applied:
        missing = [r for r in desired_rules if r not in live_rules]
        extra = [r for r in live_rules if r not in desired_rules]
        if missing or extra:
            errors.append(
                "applied lifecycle does not equal the desired lifecycle; "
                f"missing={json.dumps(missing, sort_keys=True)} unexpected={json.dumps(extra, sort_keys=True)}"
            )
    return errors


def validate_notifications(notifications: Any) -> list[str]:
    if isinstance(notifications, list) and not notifications:
        return []
    return [
        "bucket has notification configs; lifecycle transitions would fan out metadata events — review first "
        f"({json.dumps(notifications, sort_keys=True)})"
    ]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desired", type=Path, required=True)
    parser.add_argument("--live", type=Path, default=None, help="gcloud storage buckets describe --format=json")
    parser.add_argument("--notifications", type=Path, default=None)
    parser.add_argument("--expect-applied", action="store_true")
    parser.add_argument("--allow-rule-removal", action="store_true")
    parser.add_argument(
        "--allow-rule-removal-of",
        type=Path,
        default=None,
        help="Scoped removal (rollback): allow dropping only rules declared in this apply document",
    )
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    if args.allow_rule_removal and args.allow_rule_removal_of is not None:
        errors.append("--allow-rule-removal and --allow-rule-removal-of are mutually exclusive")
    try:
        desired = _read_json(args.desired)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read desired lifecycle document: {exc}")
        return 1
    if not isinstance(desired, Mapping):
        print("ERROR: desired lifecycle document must be a JSON object")
        return 1
    errors.extend(validate_desired_document(desired))

    if args.source_only:
        if (
            args.live
            or args.notifications
            or args.expect_applied
            or args.allow_rule_removal
            or args.allow_rule_removal_of is not None
        ):
            errors.append("--source-only cannot claim live bucket validation")
    else:
        allow_rule_removal_of: Sequence[Mapping[str, Any]] | None = None
        if args.allow_rule_removal_of is not None:
            try:
                apply_document = _read_json(args.allow_rule_removal_of)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"could not read allow-rule-removal-of document: {exc}")
            else:
                if isinstance(apply_document, Mapping):
                    allow_rule_removal_of = _rules(apply_document)
                else:
                    errors.append("allow-rule-removal-of document must be a JSON object")
        if args.live is None:
            errors.append("a live describe document is required outside --source-only mode")
        else:
            try:
                live = _read_json(args.live)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"could not read live describe document: {exc}")
            else:
                if isinstance(live, Mapping):
                    errors.extend(
                        validate_against_live(
                            desired,
                            live,
                            allow_rule_removal=args.allow_rule_removal,
                            expect_applied=args.expect_applied,
                            allow_rule_removal_of=allow_rule_removal_of,
                        )
                    )
                else:
                    errors.append("live describe document must be a JSON object")
        if args.notifications is not None:
            try:
                notifications = _read_json(args.notifications)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"could not read notifications document: {exc}")
            else:
                errors.extend(validate_notifications(notifications))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"storage lifecycle contract passed for {desired.get('bucket')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
