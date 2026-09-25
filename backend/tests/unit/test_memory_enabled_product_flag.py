"""One product flag: MEMORY_ENABLED=on|off.

Keeps this file import-light so the fast-unit duration guard stays honest.
MemoryService intake/list behavior is covered in test_universal_memory_service
and test_memories_pagination_clamp.
"""

from __future__ import annotations

from pathlib import Path

from config.memory_rollout import (
    memory_enabled_env_value,
    rollout_mode_env_value,
)

BACKEND = Path(__file__).resolve().parents[2]


def test_memory_enabled_on_maps_to_write_not_gate3_read():
    env = {"MEMORY_ENABLED": "on"}
    assert memory_enabled_env_value(env) is True
    assert rollout_mode_env_value(env) == "write"


def test_memory_enabled_off_pauses_writes_and_fail_closed_unset():
    assert memory_enabled_env_value({"MEMORY_ENABLED": "off"}) is False
    assert rollout_mode_env_value({"MEMORY_ENABLED": "off"}) == "off"
    assert memory_enabled_env_value({}) is False
    assert rollout_mode_env_value({}) == "off"


def test_retired_aliases_do_not_enable_memory():
    env = {"MEMORY_MODE": "write", "MEMORY_V3_GET_ENABLED": "true"}
    assert memory_enabled_env_value(env) is False
    assert rollout_mode_env_value(env) == "off"


def test_dev_and_prod_overlays_pin_memory_enabled_on():
    import yaml

    composed = yaml.safe_load((BACKEND / "deploy/runtime_env.yaml").read_text(encoding="utf-8"))
    dev = composed["environments"]["dev"]
    prod = composed["environments"]["prod"]

    def _value(env_map, key):
        entry = env_map.get(key) or {}
        return (entry.get("value") or "").strip().lower()

    for scope, env_map in (
        ("dev/gke/backend-listen", dev["gke"]["backend-listen"]["env"]),
        ("dev/cloud_run/backend", dev["cloud_run"]["services"]["backend"]["env"]),
    ):
        assert "MEMORY_MODE" not in env_map and "MEMORY_V3_GET_ENABLED" not in env_map, scope
        assert _value(env_map, "MEMORY_ENABLED") == "on", scope
        assert _value(env_map, "MEMORY_CANONICAL_MAINTENANCE_ENABLED") in {"", "false"}

    dev_job = dev["cloud_run"]["jobs"]["memory-maintenance-job"]["env"]
    assert "MEMORY_MODE" not in dev_job and "MEMORY_V3_GET_ENABLED" not in dev_job
    assert _value(dev_job, "MEMORY_ENABLED") == "on"
    assert _value(dev_job, "MEMORY_CANONICAL_MAINTENANCE_ENABLED") == "true"
    assert _value(dev_job, "MEMORY_CANONICAL_MAINTENANCE_FLEX") == "true"

    for scope, env_map in (
        ("prod/gke/backend-listen", prod["gke"]["backend-listen"]["env"]),
        ("prod/cloud_run/backend", prod["cloud_run"]["services"]["backend"]["env"]),
    ):
        # Prod GO was 2026-08-15: request-path prod pins MEMORY_ENABLED=on so the
        # next deploy cannot silently pause fleet memory writes again.
        assert "MEMORY_MODE" not in env_map and "MEMORY_V3_GET_ENABLED" not in env_map, scope
        assert _value(env_map, "MEMORY_ENABLED") == "on", scope
        assert _value(env_map, "MEMORY_CANONICAL_MAINTENANCE_ENABLED") in {"", "false"}

    prod_job = prod["cloud_run"]["jobs"]["memory-maintenance-job"]["env"]
    assert "MEMORY_MODE" not in prod_job and "MEMORY_V3_GET_ENABLED" not in prod_job
    assert _value(prod_job, "MEMORY_ENABLED") == "on"
    assert _value(prod_job, "MEMORY_CANONICAL_MAINTENANCE_ENABLED") == "true"
    assert _value(prod_job, "MEMORY_CANONICAL_MAINTENANCE_FLEX") == "true"


def test_memory_enabled_on_does_not_require_maintenance():
    from scripts.runtime_env_validation import manifest as validator

    errors = validator._validate_memory_maintenance_job_contract(
        "dev",
        validator._load_yaml(validator.DEFAULT_MANIFEST)["environments"]["dev"],
    )
    assert errors == []
