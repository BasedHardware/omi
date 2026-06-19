from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database.v17_vector_repair_outbox_worker import (
    V17VectorRepairOutboxWorkerTickConfig,
    run_v17_vector_repair_outbox_worker_tick,
)

V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV = "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED"
V17_VECTOR_REPAIR_OUTBOX_UID_ENV = "V17_VECTOR_REPAIR_OUTBOX_UID"
V17_VECTOR_REPAIR_OUTBOX_WORKER_ID_ENV = "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID"
V17_VECTOR_REPAIR_OUTBOX_LIMIT_ENV = "V17_VECTOR_REPAIR_OUTBOX_LIMIT"
V17_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS_ENV = "V17_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS"
V17_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS_ENV = "V17_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS"


@dataclass(frozen=True)
class V17VectorRepairOutboxEntrypointConfig:
    enabled: bool
    uid: Optional[str]
    tick_config: Optional[V17VectorRepairOutboxWorkerTickConfig]


def run_v17_vector_repair_outbox_worker_entrypoint(
    *,
    env: Mapping[str, str],
    db_client: Any,
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]],
    vector_deleter: Callable[[Dict[str, Any]], Any],
    vector_repairer: Callable[[Dict[str, Any], Any], Any],
    tick_runner: Callable[..., Dict[str, Any]] = run_v17_vector_repair_outbox_worker_tick,
    print_json: Callable[[str], Any] = print,
) -> int:
    """Run the disabled-by-default Cloud Run/Tasks wrapper contract for one worker tick.

    This wrapper is deliberately small and fake-injectable. It reads only explicit
    server-owned env/config, refuses malformed or unbounded execution, invokes one
    bounded `run_v17_vector_repair_outbox_worker_tick(...)` when enabled, and
    prints exactly one deterministic JSON summary for Cloud Run/Tasks logs.
    """
    try:
        entrypoint_config = parse_v17_vector_repair_outbox_worker_entrypoint_config(env)
    except ValueError as exc:
        print_json(
            json.dumps(_entrypoint_summary(config_valid=False, errors=[_error("config", str(exc))]), sort_keys=True)
        )
        return 2

    if not entrypoint_config.enabled:
        print_json(json.dumps(_entrypoint_summary(config_valid=True), sort_keys=True))
        return 0

    if entrypoint_config.uid is None or entrypoint_config.tick_config is None:
        print_json(
            json.dumps(
                _entrypoint_summary(
                    config_valid=False, errors=[_error("config", "enabled worker config is incomplete")]
                ),
                sort_keys=True,
            )
        )
        return 2

    try:
        summary = tick_runner(
            db_client=db_client,
            uid=entrypoint_config.uid,
            config=entrypoint_config.tick_config,
            authoritative_item_loader=authoritative_item_loader,
            vector_deleter=vector_deleter,
            vector_repairer=vector_repairer,
        )
    except Exception as exc:
        summary = _entrypoint_summary(
            config_valid=True,
            enabled=True,
            uid=entrypoint_config.uid,
            worker_id=entrypoint_config.tick_config.worker_id,
            errors=[_error("tick", str(exc))],
        )

    output = dict(summary)
    output["config_valid"] = True
    print_json(json.dumps(output, sort_keys=True))
    return 1 if _summary_has_failures(output) else 0


def parse_v17_vector_repair_outbox_worker_entrypoint_config(
    env: Mapping[str, str],
) -> V17VectorRepairOutboxEntrypointConfig:
    enabled = _parse_enabled(env.get(V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV))
    if not enabled:
        return V17VectorRepairOutboxEntrypointConfig(enabled=False, uid=None, tick_config=None)

    uid = _required_env(env, V17_VECTOR_REPAIR_OUTBOX_UID_ENV)
    worker_id = _required_env(env, V17_VECTOR_REPAIR_OUTBOX_WORKER_ID_ENV)
    limit = _positive_int_env(env, V17_VECTOR_REPAIR_OUTBOX_LIMIT_ENV, 25)
    lease_seconds = _positive_int_env(env, V17_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS_ENV, 300)
    max_attempts = _positive_int_env(env, V17_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS_ENV, 3)
    return V17VectorRepairOutboxEntrypointConfig(
        enabled=True,
        uid=uid,
        tick_config=V17VectorRepairOutboxWorkerTickConfig(
            enabled=True,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        ),
    )


def main() -> int:
    """CLI hook for disabled-by-default Cloud Run/Tasks images.

    The checked-in CLI is a contract harness only: disabled/default config prints
    a no-op summary. Enabled production execution still requires explicit service
    wiring to pass the Firestore client, authoritative loader, and Pinecone-shaped
    adapters into `run_v17_vector_repair_outbox_worker_entrypoint(...)`.
    """
    return run_v17_vector_repair_outbox_worker_entrypoint(
        env=os.environ,
        db_client=None,
        authoritative_item_loader=_missing_production_dependency,
        vector_deleter=_missing_production_dependency,
        vector_repairer=_missing_production_repair_dependency,
    )


def _parse_enabled(raw: Optional[str]) -> bool:
    if raw is None or raw == "" or raw.lower() == "false":
        return False
    if raw.lower() == "true":
        return True
    raise ValueError(f"{V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV} must be 'true' or 'false'")


def _required_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required when enabled")
    return value.strip()


def _positive_int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _entrypoint_summary(
    *,
    config_valid: bool,
    enabled: bool = False,
    uid: Optional[str] = None,
    worker_id: Optional[str] = None,
    errors: Optional[list] = None,
) -> Dict[str, Any]:
    return {
        "enabled": enabled,
        "config_valid": config_valid,
        "uid": uid,
        "worker_id": worker_id,
        "leased_count": 0,
        "processed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": errors or [],
    }


def _error(stage: str, error: str) -> Dict[str, str]:
    return {"stage": stage, "error": error}


def _summary_has_failures(summary: Dict[str, Any]) -> bool:
    return bool(summary.get("errors")) or any(
        int(summary.get(key, 0) or 0) > 0 for key in ("failed_count", "ack_failed_count")
    )


def _missing_production_dependency(record: Dict[str, Any]) -> None:
    raise RuntimeError("production vector repair worker dependencies are not wired in this wrapper contract")


def _missing_production_repair_dependency(record: Dict[str, Any], item: Any) -> None:
    raise RuntimeError("production vector repair worker dependencies are not wired in this wrapper contract")


if __name__ == "__main__":
    sys.exit(main())
