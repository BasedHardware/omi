#!/usr/bin/env python3
"""Reconcile the bounded Firestore schema required by the isolated JIT QA path.

The checked-in manifest is the source of truth, but the QA database is a
separate development database that must not receive the full production
manifest merely to exercise JIT history and entity-timeline reads.  This
operator validates the complete generated manifest, selects a bounded set of named query
requirements from it, and delegates inventory/provisioning/waiting to the
shared Firestore reconciler.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from database.firestore_index_registry import (
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY,
    ENTITY_TIMELINE_CONVERSATIONS_QUERY,
    FINALIZATION_OLDEST_NONTERMINAL_QUERY,
    UNIVERSAL_CANONICAL_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY,
    UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY,
)
from scripts import reconcile_firestore_indexes as reconciler

PROJECT = "based-hardware-dev"
DATABASE = "jit-qa"
APPLY_CONFIRMATION = "APPLY_JIT_QA_INDEXES"
ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "firestore.indexes.json"
_FIRESTORE_ADMIN_API = "https://firestore.googleapis.com/v1"


@dataclass(frozen=True)
class FieldIndexTarget:
    """One single-field index that cannot be represented by ``indexes`` JSON.

    Firestore's collection-group single-field config is distinct from the
    repository's composite-index manifest.  Keep it explicit here so the QA
    operator cannot accidentally apply the production manifest wholesale.
    """

    identifier: str
    collection_group: str
    field_path: str
    query_scope: str
    order: str

    def to_receipt(self, state: str) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "collection_group": self.collection_group,
            "field_path": self.field_path,
            "query_scope": self.query_scope,
            "order": self.order,
            "state": state,
        }


TARGET_REQUIREMENTS = (
    UNIVERSAL_CANONICAL_LIST_SCAN_QUERY.index_requirement,
    ENTITY_TIMELINE_CONVERSATIONS_QUERY.index_requirement,
    UNIVERSAL_HISTORICAL_UPDATED_LIST_SCAN_QUERY.index_requirement,
    UNIVERSAL_HISTORICAL_CREATED_LIST_SCAN_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY.index_requirement,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY.index_requirement,
    # The backend startup health gauge runs this query even when QA leaves
    # Cloud Tasks finalization dispatch in its safe inline default.
    # Keep the existing production registry requirement in the bounded QA set.
    FINALIZATION_OLDEST_NONTERMINAL_QUERY.index_requirement,
)

# Firestore returns COLLECTION_GROUP_ASC for this query as a single-field
# collection-group configuration.  It must not be represented as a one-field
# composite (Firestore rejects that as redundant), nor as a production
# fieldOverride: this target is intentionally QA-only.
TARGET_FIELD_INDEXES = (
    FieldIndexTarget(
        identifier="conversations_status_collection_group_ascending",
        collection_group="conversations",
        field_path="status",
        query_scope="COLLECTION_GROUP",
        order="ASCENDING",
    ),
)


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


def _field_resource_name(*, project: str, database: str, target: FieldIndexTarget) -> str:
    return (
        f"projects/{project}/databases/{database}/collectionGroups/"
        f"{target.collection_group}/fields/{target.field_path}"
    )


def _field_resource_url(*, project: str, database: str, target: FieldIndexTarget) -> str:
    return f"{_FIRESTORE_ADMIN_API}/{_field_resource_name(project=project, database=database, target=target)}"


def _gcloud_access_token() -> str:
    """Read the already-authorized gcloud token without exposing it in output."""

    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise IndexOperatorError("gcloud access-token lookup failed for Firestore field configuration")
    return token


def _field_api_request(method: str, url: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Make one bounded Firestore Admin API request using the active gcloud identity."""

    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {_gcloud_access_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise IndexOperatorError(f"Firestore field API {method} failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise IndexOperatorError(f"Firestore field API {method} was unavailable") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndexOperatorError(f"Firestore field API {method} returned invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise IndexOperatorError(f"Firestore field API {method} returned a non-object")
    return parsed


def _field_indexes_from_payload(
    payload: Mapping[str, Any],
    *,
    target: FieldIndexTarget,
    fetch: Any,
    visited: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Resolve inherited field config before adding the QA-only index.

    A patch against a field with ``usesAncestorConfig`` would otherwise wipe
    the inherited collection-scope defaults.  Follow the explicit ancestor
    chain and fail closed if the API does not expose the effective defaults.
    """

    config = payload.get("indexConfig")
    if not isinstance(config, Mapping):
        raise IndexOperatorError("Firestore field config omitted indexConfig; refusing to overwrite inherited defaults")
    raw_indexes = config.get("indexes")
    uses_ancestor = config.get("usesAncestorConfig") is True
    if uses_ancestor:
        ancestor = config.get("ancestorField")
        if not isinstance(ancestor, str) or not ancestor:
            raise IndexOperatorError("Firestore field config omitted ancestorField; refusing to overwrite defaults")
        if ancestor in visited:
            raise IndexOperatorError("Firestore field config ancestor chain is cyclic")
        ancestor_payload = fetch("GET", f"{_FIRESTORE_ADMIN_API}/{ancestor.lstrip('/')}", None)
        return _field_indexes_from_payload(
            ancestor_payload,
            target=target,
            fetch=fetch,
            visited=visited | {ancestor},
        )
    if not isinstance(raw_indexes, list):
        raise IndexOperatorError("Firestore field config omitted explicit indexes; refusing to overwrite defaults")
    if not all(isinstance(index, Mapping) for index in raw_indexes):
        raise IndexOperatorError("Firestore field config contains a malformed index")
    normalized = []
    for index in raw_indexes:
        _validate_field_api_scope(index)
        fields = index.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(field, Mapping) for field in fields):
            raise IndexOperatorError("Firestore field config contains an index with malformed fields")
        normalized_fields = []
        for field in fields:
            normalized_field = dict(field)
            if normalized_field.get("fieldPath") == "*":
                normalized_field["fieldPath"] = target.field_path
            normalized_fields.append(normalized_field)
        normalized_index = dict(index)
        normalized_index["fields"] = normalized_fields
        normalized.append(normalized_index)
    return normalized


def _validate_field_api_scope(index: Mapping[str, Any]) -> None:
    """Require Firestore-native field indexes, treating omission as ANY_API."""

    if "apiScope" not in index:
        return
    api_scope = index["apiScope"]
    if api_scope != "ANY_API":
        raise IndexOperatorError("Firestore field index apiScope must be ANY_API or omitted")


def _field_index_matches(index: Mapping[str, Any], target: FieldIndexTarget) -> bool:
    _validate_field_api_scope(index)
    fields = index.get("fields")
    if not isinstance(fields, list) or len(fields) != 1 or not isinstance(fields[0], Mapping):
        return False
    return (
        str(index.get("queryScope", "")).upper() == target.query_scope
        and fields[0].get("fieldPath") == target.field_path
        and str(fields[0].get("order", "")).upper() == target.order
    )


def _patchable_field_index(index: Mapping[str, Any]) -> dict[str, Any]:
    """Strip server output fields while retaining every semantic index option."""

    _validate_field_api_scope(index)
    query_scope = index.get("queryScope")
    fields = index.get("fields")
    if not isinstance(query_scope, str) or not query_scope:
        raise IndexOperatorError("Firestore field config index omitted queryScope")
    if not isinstance(fields, list) or not fields or not all(isinstance(field, Mapping) for field in fields):
        raise IndexOperatorError("Firestore field config index omitted fields")
    patch = {"queryScope": query_scope}
    for key in ("apiScope",):
        if key in index:
            patch[key] = index[key]
    patch["fields"] = []
    for field in fields:
        field_patch = {}
        for key in ("fieldPath", "order", "arrayConfig", "vectorConfig"):
            if key in field:
                field_patch[key] = field[key]
        if "fieldPath" not in field_patch:
            raise IndexOperatorError("Firestore field config index field omitted fieldPath")
        patch["fields"].append(field_patch)
    return patch


def _field_target_state(
    *,
    project: str,
    database: str,
    target: FieldIndexTarget,
    field_api_request: Any,
) -> tuple[str, dict[str, Any] | None]:
    resource_url = _field_resource_url(project=project, database=database, target=target)
    payload = field_api_request("GET", resource_url, None)
    indexes = _field_indexes_from_payload(payload, target=target, fetch=field_api_request)
    target_states: list[str] = []
    for index in indexes:
        state = index.get("state")
        if not isinstance(state, str) or not state:
            raise IndexOperatorError(f"Firestore field index state is missing: {target.identifier}")
        normalized_state = state.upper()
        if normalized_state not in {"CREATING", "READY", "NEEDS_REPAIR"}:
            raise IndexOperatorError(f"Firestore field index has unsupported state: {target.identifier}")
        if _field_index_matches(index, target):
            target_states.append(normalized_state)
        elif normalized_state == "CREATING":
            # Do not patch over a preserved index that is still building.
            return "CREATING", None
        elif normalized_state == "NEEDS_REPAIR":
            raise IndexOperatorError(f"Firestore field index needs repair: {target.identifier}")
    if "NEEDS_REPAIR" in target_states:
        raise IndexOperatorError(f"Firestore field index needs repair: {target.identifier}")
    if "CREATING" in target_states:
        return "CREATING", None
    if target_states:
        return "READY", None
    updated_indexes = [
        *(_patchable_field_index(index) for index in indexes),
        {
            "queryScope": target.query_scope,
            "fields": [{"fieldPath": target.field_path, "order": target.order}],
        },
    ]
    return "MISSING", {
        "name": _field_resource_name(project=project, database=database, target=target),
        "indexConfig": {"indexes": updated_indexes},
    }


def _wait_field_target(
    *,
    project: str,
    database: str,
    target: FieldIndexTarget,
    field_api_request: Any,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Any,
    monotonic: Any,
) -> None:
    deadline = monotonic() + max(0.0, timeout_seconds)
    while True:
        state, _ = _field_target_state(
            project=project,
            database=database,
            target=target,
            field_api_request=field_api_request,
        )
        if state == "READY":
            return
        if state != "CREATING":
            raise IndexOperatorError(f"Firestore field index did not become ready: {target.identifier}")
        if monotonic() >= deadline:
            raise IndexOperatorError(f"Firestore field index timed out: {target.identifier}")
        sleep(min(max(0.1, poll_interval_seconds), max(0.1, deadline - monotonic())))


def _wait_field_operation(
    operation_name: str,
    *,
    field_api_request: Any,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Any,
    monotonic: Any,
) -> None:
    deadline = monotonic() + max(0.0, timeout_seconds)
    url = f"{_FIRESTORE_ADMIN_API}/{operation_name.lstrip('/')}"
    while True:
        operation = field_api_request("GET", url, None)
        if operation.get("done") is True:
            error = operation.get("error")
            if error:
                raise IndexOperatorError("Firestore field index operation failed")
            return
        if monotonic() >= deadline:
            raise IndexOperatorError("Firestore field index operation timed out")
        sleep(min(max(0.1, poll_interval_seconds), max(0.1, deadline - monotonic())))


def _apply_field_target(
    *,
    project: str,
    database: str,
    target: FieldIndexTarget,
    field_api_request: Any,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Any,
    monotonic: Any,
) -> bool:
    state, patch = _field_target_state(
        project=project,
        database=database,
        target=target,
        field_api_request=field_api_request,
    )
    if state == "READY":
        return False
    if state == "CREATING":
        _wait_field_target(
            project=project,
            database=database,
            target=target,
            field_api_request=field_api_request,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
        return False
    if state != "MISSING" or patch is None:
        raise IndexOperatorError(f"Firestore field index is not provisionable: {target.identifier}")
    resource_url = _field_resource_url(project=project, database=database, target=target)
    operation = field_api_request("PATCH", f"{resource_url}?updateMask=indexConfig", patch)
    operation_name = operation.get("name")
    if not isinstance(operation_name, str) or not operation_name:
        raise IndexOperatorError("Firestore field index update returned no operation")
    _wait_field_operation(
        operation_name,
        field_api_request=field_api_request,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )
    _wait_field_target(
        project=project,
        database=database,
        target=target,
        field_api_request=field_api_request,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )
    return True


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
        field_api_request = _field_api_request
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
    for target in TARGET_FIELD_INDEXES:
        state, _ = _field_target_state(
            project=project,
            database=database,
            target=target,
            field_api_request=field_api_request,
        )
        field_requirements.append(target.to_receipt(state))
    return {
        "schema_version": "omi.jit.qa.firestore-index-plan.v1",
        "project": project,
        "database": database,
        "manifest_validated": True,
        "selected_index_count": len(manifest["indexes"]),
        "indexes": requirements,
        "selected_field_index_count": len(TARGET_FIELD_INDEXES),
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
        field_api_request = _field_api_request
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
        created_field_index_count = sum(
            _apply_field_target(
                project=project,
                database=database,
                target=target,
                field_api_request=field_api_request,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
            for target in TARGET_FIELD_INDEXES
        )
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
