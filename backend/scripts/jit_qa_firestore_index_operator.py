#!/usr/bin/env python3
"""Reconcile the Firestore composite schema required by the isolated JIT QA path.

The checked-in manifest is the source of truth.  The QA database is a separate
development database, and the named QA app now runs the full shared desktop
path against it for real working days, so every composite the registry
declares must be servable there: each registry entry was added because a
production query needs it, and a fresh database provisioned from a subset
returns ``FailedPrecondition`` on the first read that reaches an unselected
query (measured 2026-09-10 on ``action_items`` and 2026-09-11 on
``chat_first_deferrals`` while the bounded plan reported "none missing").
This operator validates the complete generated manifest, selects every
registry composite and additive single-field requirement from it, and
delegates inventory/provisioning/waiting to the shared Firestore
reconciler.  Project, database, and confirmation stay fixed.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Mapping

from database.firestore_index_registry import FIELD_INDEX_REQUIREMENTS, INDEX_REQUIREMENTS
from scripts import firestore_field_indexes as field_indexes
from scripts import reconcile_firestore_indexes as reconciler

PROJECT = "based-hardware-dev"
DATABASE = "jit-qa"
APPLY_CONFIRMATION = "APPLY_JIT_QA_INDEXES"
ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "firestore.indexes.json"


# Every registry composite and additive field requirement.  The registry is
# exactly the set production is reconciled against, so selecting all of it
# makes the isolated QA database serve whatever shared query the QA app
# reaches next instead of failing one path per working day.
TARGET_REQUIREMENTS = INDEX_REQUIREMENTS
TARGET_FIELD_REQUIREMENTS = FIELD_INDEX_REQUIREMENTS


class IndexOperatorError(ValueError):
    """Raised when a bounded QA schema operation crosses its fixed contract."""


def _entry_signature(index: Mapping[str, Any]) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    collection_group = index.get("collectionGroup")
    query_scope = index.get("queryScope")
    fields = index.get("fields")
    if not isinstance(collection_group, str) or not isinstance(query_scope, str) or not isinstance(fields, list):
        raise IndexOperatorError("generated Firestore manifest entry is malformed")
    normalized: list[tuple[str, str]] = []
    for field in fields:
        if not isinstance(field, Mapping) or not isinstance(field.get("fieldPath"), str):
            raise IndexOperatorError("generated Firestore manifest field is malformed")
        direction = field.get("order") or field.get("arrayConfig")
        if not isinstance(direction, str):
            raise IndexOperatorError("generated Firestore manifest field has no direction")
        normalized.append((field["fieldPath"], direction))
    return collection_group, query_scope, tuple(normalized)


def _require_target(project: str, database: str) -> None:
    if project != PROJECT:
        raise IndexOperatorError(f"project is fixed to {PROJECT}")
    if database != DATABASE:
        raise IndexOperatorError(f"database is fixed to {DATABASE}")


def _target_signatures() -> set[reconciler.IndexSignature]:
    return {requirement.signature for requirement in TARGET_REQUIREMENTS}


def selected_manifest(*, manifest_path: Path = MANIFEST_PATH) -> tuple[dict[str, Any], set[reconciler.IndexSignature]]:
    """Validate the canonical manifest and return only the bounded QA entries."""

    generated = reconciler.verify_manifest_source(manifest_path)
    targets = _target_signatures()
    selected = [
        entry for entry in generated["indexes"] if isinstance(entry, Mapping) and _entry_signature(entry) in targets
    ]
    if {_entry_signature(entry) for entry in selected} != targets:
        raise IndexOperatorError("canonical manifest is missing a required JIT QA index")
    if len(selected) != len(targets):
        raise IndexOperatorError("canonical manifest contains duplicate JIT QA index signatures")
    return {"indexes": selected}, targets


def _display_requirement(signature: reconciler.IndexSignature, state: str) -> dict[str, Any]:
    collection_group, query_scope, fields = signature
    requirement = next(item for item in TARGET_REQUIREMENTS if item.signature == signature)
    return {
        "identifier": requirement.identifier,
        "collection_group": collection_group,
        "query_scope": query_scope,
        "fields": [{"field_path": path, "direction": direction} for path, direction in fields],
        "state": state,
    }


def _field_requirement_receipt(requirement, state: str) -> dict[str, Any]:
    return {
        "identifier": requirement.identifier,
        "collection_group": requirement.collection_group,
        "field_path": requirement.field_path,
        "collection_group_modes": list(requirement.collection_group_modes),
        "state": state,
    }


def _field_requirement_state(
    *,
    project: str,
    database: str,
    requirement,
    field_api_request: Any,
) -> tuple[str, dict[str, Any] | None]:
    try:
        return field_indexes.field_requirement_state(
            project=project,
            database=database,
            requirement=requirement,
            request=field_api_request,
        )
    except field_indexes.FieldIndexError as exc:
        raise IndexOperatorError(str(exc)) from exc


def _apply_field_requirement(
    *,
    project: str,
    database: str,
    requirement,
    field_api_request: Any,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Any,
    monotonic: Any,
) -> bool:
    try:
        return field_indexes.apply_field_requirement(
            project=project,
            database=database,
            requirement=requirement,
            request=field_api_request,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
    except field_indexes.FieldIndexError as exc:
        raise IndexOperatorError(str(exc)) from exc


def build_plan(
    *,
    project: str,
    database: str,
    manifest_path: Path = MANIFEST_PATH,
    runner: reconciler.CommandRunner = reconciler.subprocess.run,
    field_api_request: Any | None = None,
) -> dict[str, Any]:
    """Read the named database and report only the bounded QA requirements."""

    _require_target(project, database)
    if field_api_request is None:
        field_api_request = field_indexes.field_api_request
    manifest, expected = selected_manifest(manifest_path=manifest_path)
    live = reconciler.list_live_indexes(project=project, database=database, runner=runner)
    states = reconciler.expected_index_states(
        expected=expected,
        live_indexes=live,
        project=project,
        database=database,
    )
    requirements = [_display_requirement(signature, states[signature]) for signature in sorted(expected)]
    field_requirements = []
    for requirement in TARGET_FIELD_REQUIREMENTS:
        state, _ = _field_requirement_state(
            project=project,
            database=database,
            requirement=requirement,
            field_api_request=field_api_request,
        )
        field_requirements.append(_field_requirement_receipt(requirement, state))
    return {
        "schema_version": "omi.jit.qa.firestore-index-plan.v1",
        "project": project,
        "database": database,
        "manifest_validated": True,
        "selected_index_count": len(manifest["indexes"]),
        "indexes": requirements,
        "selected_field_index_count": len(TARGET_FIELD_REQUIREMENTS),
        "field_indexes": field_requirements,
        "missing_count": sum(state != "READY" for state in states.values())
        + sum(item["state"] != "READY" for item in field_requirements),
    }


def apply_plan(
    *,
    project: str,
    database: str,
    manifest_path: Path = MANIFEST_PATH,
    confirmation: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    runner: reconciler.CommandRunner = reconciler.subprocess.run,
    sleep: Any = reconciler.time.sleep,
    monotonic: Any = reconciler.time.monotonic,
    field_api_request: Any | None = None,
) -> dict[str, Any]:
    """Create/wait only for the bounded requirements after explicit confirmation."""

    _require_target(project, database)
    if confirmation != APPLY_CONFIRMATION:
        raise IndexOperatorError(f"apply requires {APPLY_CONFIRMATION}")
    if field_api_request is None:
        field_api_request = field_indexes.field_api_request
    _, expected = selected_manifest(manifest_path=manifest_path)
    # The operator's stdout is a machine-readable receipt. Shared reconciler
    # progress belongs on stderr, including its successful READY message.
    with redirect_stdout(sys.stderr):
        created = reconciler.provision_missing_indexes(
            expected=expected, project=project, database=database, runner=runner
        )
        reconciler.wait_for_indexes(
            expected=expected,
            project=project,
            database=database,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            runner=runner,
            sleep=sleep,
            monotonic=monotonic,
        )
        try:
            patched_fields = field_indexes.provision_field_requirements(
                requirements=tuple(TARGET_FIELD_REQUIREMENTS),
                project=project,
                database=database,
                request=field_api_request,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
        except field_indexes.FieldIndexError as exc:
            raise IndexOperatorError(str(exc)) from exc
        created_field_index_count = len(patched_fields)
    plan = build_plan(
        project=project,
        database=database,
        manifest_path=manifest_path,
        runner=runner,
        field_api_request=field_api_request,
    )
    plan["schema_version"] = "omi.jit.qa.firestore-index-apply.v1"
    plan["confirmation"] = APPLY_CONFIRMATION
    plan["created_index_count"] = len(created)
    plan["created_field_index_count"] = created_field_index_count
    return plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=10.0)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("plan", help="read the named database and print the bounded QA index plan")
    apply = sub.add_parser("apply", help="create/wait for the bounded QA indexes after explicit confirmation")
    apply.add_argument("--confirmation", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.operation == "plan":
            result = build_plan(
                project=args.project,
                database=args.database,
                manifest_path=args.manifest.resolve(),
            )
        else:
            result = apply_plan(
                project=args.project,
                database=args.database,
                manifest_path=args.manifest.resolve(),
                confirmation=args.confirmation,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
