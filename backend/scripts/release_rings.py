#!/usr/bin/env python3
"""Create and validate immutable inputs for stateless release-ring deployments.

This module deliberately owns data shapes only. GCS provides immutable object
storage/CAS and GitHub Actions provides per-ring serialization; this code must
not grow into a release coordinator or reconciliation service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
RINGS = frozenset({"beta", "prod"})
# These are the images the release builder creates.  Config-only resources are
# deliberately separate so a record can deploy the ConfigMap and ExternalSecret
# that the stateless workloads consume, without inventing a fake image for them.
COMPONENTS = ("backend", "backend-listen", "pusher", "llm-gateway", "agent-proxy")
CONFIG_COMPONENTS = COMPONENTS + ("backend-config", "backend-secrets")
CLOUD_RUN_SERVICES = ("backend", "backend-sync", "backend-sync-backfill", "backend-integration")
RECEIPT_STATES = frozenset({"started", "verified", "restored", "partial_mutation"})
_DIGEST_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SECRET_VERSION_RE = re.compile(r"^projects/[^/]+/secrets/[^/]+/versions/[1-9][0-9]*$")
_OBJECT_RE = re.compile(r"^gs://[^/]+/.+#sha256:[0-9a-f]{64}$")
_RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_assignments(values: Iterable[str], *, label: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        name, separator, item = value.partition("=")
        if not separator or not name or not item:
            raise ValueError(f"{label} must use NAME=VALUE: {value!r}")
        if name in parsed:
            raise ValueError(f"{label} repeats {name!r}")
        parsed[name] = item
    return parsed


def build_record(
    *,
    release_id: str,
    git_sha: str,
    eligibility_run_id: str,
    images: Mapping[str, str],
    rendered_config: Mapping[str, str],
    secret_versions: Mapping[str, str],
    topology: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "git_sha": git_sha,
        "eligibility_run_id": eligibility_run_id,
        "images": dict(sorted(images.items())),
        "rendered_config": dict(sorted(rendered_config.items())),
        "secret_versions": dict(sorted(secret_versions.items())),
        "topology": topology,
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }
    errors = validate_record(record)
    if errors:
        raise ValueError("invalid release record: " + "; ".join(errors))
    return record


def validate_record(record: object) -> list[str]:
    if not isinstance(record, Mapping):
        return ["record must be an object"]
    errors: list[str] = []
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    release_id = record.get("release_id")
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        errors.append("release_id must be a durable identifier")
    git_sha = record.get("git_sha")
    if not isinstance(git_sha, str) or not _SHA_RE.fullmatch(git_sha):
        errors.append("git_sha must be a lowercase full commit SHA")
    run_id = record.get("eligibility_run_id")
    if not isinstance(run_id, str) or not run_id.isdecimal() or int(run_id) <= 0:
        errors.append("eligibility_run_id must be a positive decimal GitHub run ID")

    images = record.get("images")
    if not isinstance(images, Mapping):
        errors.append("images must be an object")
    else:
        for component in COMPONENTS:
            image = images.get(component)
            if not isinstance(image, str) or not _DIGEST_RE.fullmatch(image):
                errors.append(f"images.{component} must be an immutable OCI digest")
        unexpected = sorted(str(name) for name in images if name not in COMPONENTS)
        if unexpected:
            errors.append(f"images contains unsupported components: {', '.join(unexpected)}")

    config = record.get("rendered_config")
    required_config = {f"{ring}/{component}" for ring in RINGS for component in CONFIG_COMPONENTS}
    if not isinstance(config, Mapping):
        errors.append("rendered_config must be an object")
    else:
        missing = sorted(required_config - set(config))
        if missing:
            errors.append(f"rendered_config is missing: {', '.join(missing)}")
        extra = sorted(str(name) for name in config if name not in required_config)
        if extra:
            errors.append(f"rendered_config has unsupported entries: {', '.join(extra)}")
        for name, reference in config.items():
            if not isinstance(reference, str) or not _OBJECT_RE.fullmatch(reference):
                errors.append(f"rendered_config.{name} must be an immutable GCS object reference")

    secrets = record.get("secret_versions")
    if not isinstance(secrets, Mapping) or not secrets:
        errors.append("secret_versions must be a non-empty object")
    else:
        for name, reference in secrets.items():
            if not isinstance(name, str) or not name:
                errors.append("secret_versions contains an empty name")
            if not isinstance(reference, str) or not _SECRET_VERSION_RE.fullmatch(reference):
                errors.append(f"secret_versions.{name} must pin a numeric Secret Manager version")

    topology = record.get("topology")
    if not isinstance(topology, Mapping):
        errors.append("topology must be an object")
    else:
        prod_topology = topology.get("prod")
        prod_services = prod_topology.get("cloud_run_services") if isinstance(prod_topology, Mapping) else None
        for ring in RINGS:
            ring_topology = topology.get(ring)
            if not isinstance(ring_topology, Mapping):
                errors.append(f"topology.{ring} must be an object")
                continue
            namespace = ring_topology.get("namespace")
            if not isinstance(namespace, str) or namespace != f"{ring}-omi-backend":
                errors.append(f"topology.{ring}.namespace must be {ring}-omi-backend")
            services = ring_topology.get("cloud_run_services")
            if not isinstance(services, Mapping):
                errors.append(f"topology.{ring}.cloud_run_services must be an object")
                continue
            for service in CLOUD_RUN_SERVICES:
                name = services.get(service)
                if not isinstance(name, str) or not name:
                    errors.append(f"topology.{ring}.cloud_run_services.{service} must be a non-empty name")
            if ring == "beta" and services == prod_services:
                errors.append("topology.beta.cloud_run_services must not reuse prod service identities")

    if _contains_mutable_reference(record):
        errors.append("release records must not contain mutable 'latest' references")
    return errors


def _contains_mutable_reference(value: object) -> bool:
    if isinstance(value, str):
        return value.lower() == "latest" or ":latest" in value.lower() or "/versions/latest" in value.lower()
    if isinstance(value, Mapping):
        return any(_contains_mutable_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_mutable_reference(item) for item in value)
    return False


def build_active_pointer(
    *,
    ring: str,
    release_id: str,
    existing: Mapping[str, Any] | None,
    hold: bool = False,
    updated_at: str | None = None,
) -> dict[str, Any]:
    if ring not in RINGS:
        raise ValueError(f"unknown ring {ring!r}")
    if not _RELEASE_ID_RE.fullmatch(release_id):
        raise ValueError("release_id must be a durable identifier")
    current = existing.get("current_release_id") if isinstance(existing, Mapping) else None
    held = set(existing.get("held_release_ids", []) if isinstance(existing, Mapping) else [])
    if hold:
        held.add(release_id)
        next_current = current if isinstance(current, str) else None
        previous = existing.get("previous_verified_release_id") if isinstance(existing, Mapping) else None
    else:
        if release_id in held:
            raise ValueError(f"held release {release_id!r} cannot be promoted")
        next_current = release_id
        previous = current if isinstance(current, str) and current != release_id else None
    return {
        "schema_version": SCHEMA_VERSION,
        "ring": ring,
        "current_release_id": next_current,
        "previous_verified_release_id": previous,
        "held_release_ids": sorted(held),
        "updated_at": updated_at or datetime.now(UTC).isoformat(),
    }


def build_receipt(
    *,
    ring: str,
    release_id: str,
    run_id: str,
    state: str,
    snapshot_reference: str,
    components: Mapping[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    if ring not in RINGS:
        raise ValueError(f"unknown ring {ring!r}")
    if state not in RECEIPT_STATES:
        raise ValueError(f"unsupported receipt state {state!r}")
    if not run_id.isdecimal() or int(run_id) <= 0:
        raise ValueError("run_id must be a positive decimal GitHub run ID")
    if not _OBJECT_RE.fullmatch(snapshot_reference):
        raise ValueError("snapshot_reference must be an immutable GCS object reference")
    if not components or any(not name or not value for name, value in components.items()):
        raise ValueError("components must contain non-empty observed deployment details")
    return {
        "schema_version": SCHEMA_VERSION,
        "ring": ring,
        "release_id": release_id,
        "run_id": run_id,
        "state": state,
        "snapshot_reference": snapshot_reference,
        "components": dict(sorted(components.items())),
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }


def resolve_secret_versions(*, manifests: Iterable[Path], project: str) -> dict[str, str]:
    """Resolve every manifest Secret Manager reference to an immutable version.

    PyYAML is intentionally imported only for this release-build command. The
    normal record validation path remains stdlib-only for CI and incident use.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised in Actions
        raise ValueError("resolve-secrets requires PyYAML") from exc
    names: set[str] = set()
    for manifest in manifests:
        loaded = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        names.update(_secret_names(loaded))
    resolved: dict[str, str] = {}
    for name in names:
        command = [
            "gcloud",
            "secrets",
            "versions",
            "describe",
            "latest",
            f"--secret={name}",
            f"--project={project}",
            "--format=value(name)",
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        reference = completed.stdout.strip()
        if not _SECRET_VERSION_RE.fullmatch(reference):
            raise ValueError(f"{name}: gcloud did not resolve a numeric secret version")
        resolved[name] = reference
    return resolved


def materialize_secret_versions(*, manifest: Path, secret_versions: Mapping[str, str]) -> dict[str, Any]:
    """Replace every mutable manifest binding with the record's numeric version."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised in Actions
        raise ValueError("materialize-secrets requires PyYAML") from exc
    loaded = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("runtime manifest must be a YAML object")

    def rewrite(value: object) -> object:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, Mapping):
            return value
        result = {str(name): rewrite(item) for name, item in value.items()}
        secret = result.get("secret") or result.get("remoteKey")
        version = result.get("version")
        if isinstance(secret, str) and (version is None or version == "latest"):
            reference = secret_versions.get(secret)
            if not isinstance(reference, str) or not _SECRET_VERSION_RE.fullmatch(reference):
                raise ValueError(f"{secret}: record does not contain a numeric secret version")
            result["version"] = reference.rsplit("/", 1)[1]
        return result

    materialized = rewrite(loaded)
    if not isinstance(materialized, dict):  # defensive narrowing for type checkers
        raise ValueError("runtime manifest did not materialize to an object")
    return materialized


def _secret_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        secret = value.get("secret") or value.get("remoteKey")
        if isinstance(secret, str):
            names.add(secret)
        for item in value.values():
            names.update(_secret_names(item))
    elif isinstance(value, list):
        for item in value:
            names.update(_secret_names(item))
    return names


def materialize_runtime_config(
    *, manifest: Path, secret_versions: Mapping[str, str], public_values: Mapping[str, str]
) -> dict[str, Any]:
    """Produce a deployable runtime manifest with neither `latest` nor `env_var`.

    Public values are captured from the serving ConfigMap (plus the two VPC
    settings) while building the record.  A deploy or rollback never consults
    mutable GitHub variables again.
    """
    materialized = materialize_secret_versions(manifest=manifest, secret_versions=secret_versions)

    def rewrite(value: object) -> object:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, Mapping):
            return value
        result = {str(name): rewrite(item) for name, item in value.items()}
        env_var = result.get("env_var")
        if isinstance(env_var, str):
            replacement = public_values.get(env_var)
            if replacement is None:
                replacement = result.get("default")
            if replacement is None:
                raise ValueError(f"{env_var}: release record has no public value")
            result.pop("env_var", None)
            result.pop("default", None)
            result["value"] = str(replacement)
        return result

    rewritten = rewrite(materialized)
    if not isinstance(rewritten, dict):  # pragma: no cover - defended above
        raise ValueError("runtime manifest did not materialize to an object")
    return rewritten


def _read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _write_json(path: Path | None, value: Mapping[str, Any]) -> None:
    rendered = canonical_json(value)
    if path is None:
        print(rendered, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-record", help="create a deployable immutable release record")
    create.add_argument("--release-id", required=True)
    create.add_argument("--git-sha", required=True)
    create.add_argument("--eligibility-run-id", required=True)
    create.add_argument("--image", action="append", default=[])
    create.add_argument("--rendered-config", action="append", default=[])
    create.add_argument("--secret-versions-file", type=Path, required=True)
    create.add_argument("--topology-file", type=Path, required=True)
    create.add_argument("--created-at")
    create.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser("validate-record", help="fail closed on an invalid release record")
    validate.add_argument("--record", type=Path, required=True)

    pointer = commands.add_parser("active-pointer", help="build a CAS-ready ring active pointer")
    pointer.add_argument("--ring", choices=sorted(RINGS), required=True)
    pointer.add_argument("--release-id", required=True)
    pointer.add_argument("--existing", type=Path)
    pointer.add_argument("--hold", action="store_true")
    pointer.add_argument("--output", type=Path, required=True)

    receipt = commands.add_parser("receipt", help="build an append-only ring deployment receipt")
    receipt.add_argument("--ring", choices=sorted(RINGS), required=True)
    receipt.add_argument("--release-id", required=True)
    receipt.add_argument("--run-id", required=True)
    receipt.add_argument("--state", choices=sorted(RECEIPT_STATES), required=True)
    receipt.add_argument("--snapshot-reference", required=True)
    receipt.add_argument("--component", action="append", default=[])
    receipt.add_argument("--output", type=Path, required=True)

    secrets = commands.add_parser("resolve-secrets", help="resolve manifest secret names to numeric versions")
    secrets.add_argument("--manifest", type=Path, action="append", required=True)
    secrets.add_argument("--project", required=True)
    secrets.add_argument("--output", type=Path, required=True)

    materialize = commands.add_parser(
        "materialize-secrets", help="write a runtime manifest with record-pinned versions"
    )
    materialize.add_argument("--manifest", type=Path, required=True)
    materialize.add_argument("--secret-versions-file", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)

    runtime = commands.add_parser("materialize-runtime", help="write a fully pinned Cloud Run runtime manifest")
    runtime.add_argument("--manifest", type=Path, required=True)
    runtime.add_argument("--secret-versions-file", type=Path, required=True)
    runtime.add_argument("--public-values-file", type=Path, required=True)
    runtime.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "create-record":
            secret_versions = _read_json(args.secret_versions_file)
            _write_json(
                args.output,
                build_record(
                    release_id=args.release_id,
                    git_sha=args.git_sha,
                    eligibility_run_id=args.eligibility_run_id,
                    images=parse_assignments(args.image, label="--image"),
                    rendered_config=parse_assignments(args.rendered_config, label="--rendered-config"),
                    secret_versions={str(name): str(value) for name, value in secret_versions.items()},
                    topology=_read_json(args.topology_file),
                    created_at=args.created_at,
                ),
            )
        elif args.command == "validate-record":
            errors = validate_record(_read_json(args.record))
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print("release record is valid")
        elif args.command == "active-pointer":
            _write_json(
                args.output,
                build_active_pointer(
                    ring=args.ring,
                    release_id=args.release_id,
                    existing=_read_json(args.existing) if args.existing else None,
                    hold=args.hold,
                ),
            )
        elif args.command == "receipt":
            _write_json(
                args.output,
                build_receipt(
                    ring=args.ring,
                    release_id=args.release_id,
                    run_id=args.run_id,
                    state=args.state,
                    snapshot_reference=args.snapshot_reference,
                    components=parse_assignments(args.component, label="--component"),
                ),
            )
        elif args.command == "resolve-secrets":
            _write_json(args.output, resolve_secret_versions(manifests=args.manifest, project=args.project))
        elif args.command == "materialize-secrets":
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - exercised in Actions
                raise ValueError("materialize-secrets requires PyYAML") from exc
            materialized = materialize_secret_versions(
                manifest=args.manifest,
                secret_versions=_read_json(args.secret_versions_file),
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(yaml.safe_dump(materialized, sort_keys=False), encoding="utf-8")
        else:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - exercised in Actions
                raise ValueError("materialize-runtime requires PyYAML") from exc
            public_values = _read_json(args.public_values_file)
            if not all(isinstance(name, str) and isinstance(value, str) for name, value in public_values.items()):
                raise ValueError("public values must be a string-to-string JSON object")
            materialized = materialize_runtime_config(
                manifest=args.manifest,
                secret_versions=_read_json(args.secret_versions_file),
                public_values={str(name): str(value) for name, value in public_values.items()},
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(yaml.safe_dump(materialized, sort_keys=False), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
