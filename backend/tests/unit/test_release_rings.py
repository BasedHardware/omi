from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "release_rings.py"
SPEC = importlib.util.spec_from_file_location("release_rings", MODULE_PATH)
assert SPEC and SPEC.loader
release_rings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_rings)


def _record() -> dict[str, object]:
    digest = "a" * 64
    config_digest = "b" * 64
    return release_rings.build_record(
        release_id="2026-07-20.42",
        git_sha="c" * 40,
        eligibility_run_id="42",
        images={component: f"gcr.io/example/{component}@sha256:{digest}" for component in release_rings.COMPONENTS},
        rendered_config={
            f"{ring}/{component}": f"gs://release-records/config/2026-07-20.42/{ring}/{component}.json#sha256:{config_digest}"
            for ring in release_rings.RINGS
            for component in release_rings.CONFIG_COMPONENTS
        },
        secret_versions={"OPENAI_API_KEY": "projects/example/secrets/OPENAI_API_KEY/versions/7"},
        topology={
            "prod": {
                "namespace": "prod-omi-backend",
                "cloud_run_services": {
                    "backend": "backend",
                    "backend-sync": "backend-sync",
                    "backend-sync-backfill": "backend-sync-backfill",
                    "backend-integration": "backend-integration",
                },
            },
        },
        created_at="2026-07-20T00:00:00+00:00",
    )


def test_release_record_requires_all_deployable_inputs() -> None:
    record = _record()

    assert release_rings.validate_record(record) == []
    assert record["images"]["backend-listen"].endswith("@sha256:" + "a" * 64)


@pytest.mark.parametrize(
    ("section", "key", "value", "expected"),
    [
        ("images", "backend", "gcr.io/example/backend:latest", "immutable OCI digest"),
        (
            "secret_versions",
            "OPENAI_API_KEY",
            "projects/example/secrets/key/versions/latest",
            "numeric Secret Manager version",
        ),
        ("rendered_config", "prod/backend", "gs://release-records/config.json", "immutable GCS object reference"),
    ],
)
def test_release_record_rejects_mutable_or_unrestorable_inputs(
    section: str, key: str, value: str, expected: str
) -> None:
    record = _record()
    record[section][key] = value

    assert any(expected in error for error in release_rings.validate_record(record))


def test_active_pointer_promote_and_hold_are_monotonic() -> None:
    existing = {
        "current_release_id": "2026-07-19.1",
        "previous_verified_release_id": "2026-07-18.1",
        "held_release_ids": [],
    }

    promoted = release_rings.build_active_pointer(
        ring="prod", release_id="2026-07-20.1", existing=existing, updated_at="2026-07-20T00:00:00+00:00"
    )
    assert promoted["previous_verified_release_id"] == "2026-07-19.1"

    held = release_rings.build_active_pointer(
        ring="prod", release_id="2026-07-20.2", existing=promoted, hold=True, updated_at="2026-07-20T00:01:00+00:00"
    )
    assert held["current_release_id"] == "2026-07-20.1"
    assert held["held_release_ids"] == ["2026-07-20.2"]
    with pytest.raises(ValueError, match="held release"):
        release_rings.build_active_pointer(ring="prod", release_id="2026-07-20.2", existing=held)


def test_recovery_pointer_uses_pre_mutation_state_after_a_late_failure() -> None:
    before = {
        "current_release_id": "2026-07-19.1",
        "previous_verified_release_id": "2026-07-18.1",
        "held_release_ids": [],
    }
    promoted = release_rings.build_active_pointer(
        ring="prod", release_id="2026-07-20.1", existing=before, updated_at="2026-07-20T00:00:00+00:00"
    )
    assert promoted["current_release_id"] == "2026-07-20.1"

    recovered = release_rings.build_active_pointer(
        ring="prod",
        release_id="2026-07-20.1",
        existing=before,
        hold=True,
        updated_at="2026-07-20T00:01:00+00:00",
    )

    assert recovered["current_release_id"] == "2026-07-19.1"
    assert recovered["previous_verified_release_id"] == "2026-07-18.1"
    assert recovered["held_release_ids"] == ["2026-07-20.1"]


def test_receipt_keeps_partial_mutation_distinct_from_restoration() -> None:
    receipt = release_rings.build_receipt(
        ring="prod",
        release_id="2026-07-20.1",
        run_id="99",
        state="partial_mutation",
        snapshot_reference="gs://release-records/receipts/prod/snapshot.json#sha256:" + "d" * 64,
        components={"cloud-run/backend": "restored", "gke/pusher": "restore_failed"},
        created_at="2026-07-20T00:00:00+00:00",
    )

    assert receipt["state"] == "partial_mutation"


def test_materialize_secret_versions_removes_latest_from_runtime_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "runtime.yaml"
    manifest.write_text(
        "services:\n  backend:\n    secrets:\n      API_KEY:\n        secret: API_KEY\n        version: latest\n",
        encoding="utf-8",
    )

    materialized = release_rings.materialize_secret_versions(
        manifest=manifest,
        secret_versions={"API_KEY": "projects/example/secrets/API_KEY/versions/12"},
    )

    assert materialized["services"]["backend"]["secrets"]["API_KEY"]["version"] == "12"


def test_materialize_runtime_config_captures_public_values_and_remote_secret_versions(tmp_path: Path) -> None:
    manifest = tmp_path / "runtime.yaml"
    manifest.write_text(
        "network:\n  subnet:\n    env_var: CLOUD_RUN_VPC_SUBNET\nservices:\n  backend:\n    env:\n      URL:\n        env_var: API_URL\n"
        "    secrets:\n      API_KEY:\n        secret: API_KEY\n        version: latest\n  eso:\n    remoteKey: OTHER_KEY\n",
        encoding="utf-8",
    )

    materialized = release_rings.materialize_runtime_config(
        manifest=manifest,
        secret_versions={
            "API_KEY": "projects/example/secrets/API_KEY/versions/12",
            "OTHER_KEY": "projects/example/secrets/OTHER_KEY/versions/13",
        },
        public_values={"CLOUD_RUN_VPC_SUBNET": "subnet-a", "API_URL": "https://api.omi.me"},
    )

    assert materialized["network"]["subnet"] == {"value": "subnet-a"}
    assert materialized["services"]["backend"]["env"]["URL"] == {"value": "https://api.omi.me"}
    assert materialized["services"]["backend"]["secrets"]["API_KEY"]["version"] == "12"
    assert materialized["services"]["eso"]["version"] == "13"


def test_release_record_rejects_retired_backend_ring() -> None:
    record = _record()
    record["topology"]["beta"] = {}

    assert any("unsupported rings" in error for error in release_rings.validate_record(record))


def test_active_pointer_rejects_retired_backend_ring() -> None:
    with pytest.raises(ValueError, match="unknown ring"):
        release_rings.build_active_pointer(ring="beta", release_id="2026-07-20.2", existing=None)
