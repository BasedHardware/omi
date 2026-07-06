from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, cast

try:
    from fastapi import FastAPI  # pyright: ignore[reportAssignmentType]
except (ModuleNotFoundError, ImportError):

    class FastAPI:
        # Minimal duck-typed stand-in used only when fastapi is unavailable.
        routes_by_path: dict[str, Callable[..., Any]]

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes_by_path = {}

        def post(
            self, path: str, include_in_schema: bool = False
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                self.routes_by_path[path] = func
                return func

            return decorator


_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database.memory_collections import MemoryCollections
from database.memory_vector_repair_outbox_worker import (
    VectorRepairOutboxWorkerTickConfig,
    run_vector_repair_outbox_worker_tick,
)
from database.memory_vector_repair_pinecone_adapter import (
    VECTOR_REPAIR_PINECONE_NAMESPACE,
    make_pinecone_vector_deleter,
    make_pinecone_vector_repairer,
)
from models.product_memory import MemoryItem

MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED"
MEMORY_VECTOR_REPAIR_OUTBOX_UID_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_UID"
MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID"
MEMORY_VECTOR_REPAIR_OUTBOX_LIMIT_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_LIMIT"
MEMORY_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS"
MEMORY_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS"
PINECONE_API_KEY_ENV = "PINECONE_API_KEY"
PINECONE_INDEX_NAME_ENV = "PINECONE_INDEX_NAME"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"


@dataclass(frozen=True)
class VectorRepairOutboxEntrypointConfig:
    enabled: bool
    uid: Optional[str]
    tick_config: Optional[VectorRepairOutboxWorkerTickConfig]


@dataclass(frozen=True)
class VectorRepairOutboxProductionDependencies:
    db_client: Any
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]]
    vector_deleter: Callable[[Dict[str, Any]], Any]
    vector_repairer: Callable[[Dict[str, Any], Any], Any]


def run_vector_repair_outbox_worker_entrypoint(
    *,
    env: Mapping[str, str],
    db_client: Any,
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]],
    vector_deleter: Callable[[Dict[str, Any]], Any],
    vector_repairer: Callable[[Dict[str, Any], Any], Any],
    tick_runner: Callable[..., Dict[str, Any]] = run_vector_repair_outbox_worker_tick,
    print_json: Callable[[str], Any] = print,
) -> int:
    """Run the disabled-by-default Cloud Run/Tasks wrapper contract for one worker tick.

    This wrapper is deliberately small and fake-injectable. It reads only explicit
    server-owned env/config, refuses malformed or unbounded execution, invokes one
    bounded `run_vector_repair_outbox_worker_tick(...)` when enabled, and
    prints exactly one deterministic JSON summary for Cloud Run/Tasks logs.
    """
    try:
        entrypoint_config = parse_vector_repair_outbox_worker_entrypoint_config(env)
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


def parse_vector_repair_outbox_worker_entrypoint_config(
    env: Mapping[str, str],
) -> VectorRepairOutboxEntrypointConfig:
    enabled = _parse_enabled(env.get(MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV))
    if not enabled:
        return VectorRepairOutboxEntrypointConfig(enabled=False, uid=None, tick_config=None)

    uid = _required_env(env, MEMORY_VECTOR_REPAIR_OUTBOX_UID_ENV)
    worker_id = _required_env(env, MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID_ENV)
    limit = _positive_int_env(env, MEMORY_VECTOR_REPAIR_OUTBOX_LIMIT_ENV, 25)
    lease_seconds = _positive_int_env(env, MEMORY_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS_ENV, 300)
    max_attempts = _positive_int_env(env, MEMORY_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS_ENV, 3)
    return VectorRepairOutboxEntrypointConfig(
        enabled=True,
        uid=uid,
        tick_config=VectorRepairOutboxWorkerTickConfig(
            enabled=True,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        ),
    )


def build_vector_repair_outbox_production_dependencies(
    env: Mapping[str, str],
    *,
    module_loader: Callable[[str], Any] = importlib.import_module,
) -> VectorRepairOutboxProductionDependencies:
    """Build production dependencies for an explicitly enabled worker invocation.

    This resolver is deliberately called only after wrapper config has enabled the
    worker. Disabled/default CLI smoke therefore avoids importing or initializing
    Pinecone, embedding, or Firestore client singletons. Required secret/config
    env is validated before importing network clients so enabled misconfiguration
    fails deterministically before leasing any outbox record.
    """
    pinecone_api_key = _required_dependency_env(env, PINECONE_API_KEY_ENV)
    pinecone_index_name = _required_dependency_env(env, PINECONE_INDEX_NAME_ENV)
    _required_dependency_env(env, OPENAI_API_KEY_ENV)

    pinecone_module = module_loader("pinecone")
    firestore_client_module = module_loader("database._client")
    llm_clients_module = module_loader("utils.llm.clients")

    pinecone_client = pinecone_module.Pinecone(api_key=pinecone_api_key)
    pinecone_index = pinecone_client.Index(pinecone_index_name)
    db_client = firestore_client_module.db
    embeddings = llm_clients_module.embeddings

    return VectorRepairOutboxProductionDependencies(
        db_client=db_client,
        authoritative_item_loader=make_authoritative_item_loader(db_client=db_client),
        vector_deleter=make_pinecone_vector_deleter(
            delete_vectors=pinecone_index.delete,
            namespace=VECTOR_REPAIR_PINECONE_NAMESPACE,
        ),
        vector_repairer=make_pinecone_vector_repairer(
            embed_text=embeddings.embed_query,
            upsert_vectors=pinecone_index.upsert,
            namespace=VECTOR_REPAIR_PINECONE_NAMESPACE,
        ),
    )


def make_authoritative_item_loader(*, db_client: Any) -> Callable[[Dict[str, Any]], Optional[MemoryItem]]:
    """Return a worker-compatible loader for authoritative `memory_items` docs."""

    def load_authoritative_item(record: Dict[str, Any]) -> Optional[MemoryItem]:
        uid = _required_record_str(record, "uid")
        memory_id = _required_record_str(record, "memory_id")
        snapshot = db_client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
        if not getattr(snapshot, "exists", False):
            return None
        data = cast(Dict[str, Any], snapshot.to_dict() or {})
        return MemoryItem(**data)

    return load_authoritative_item


def run_vector_repair_outbox_worker_http_tick(
    *,
    env: Mapping[str, str],
    dependency_builder: Callable[[Mapping[str, str]], VectorRepairOutboxProductionDependencies],
    tick_runner: Callable[..., Dict[str, Any]] = run_vector_repair_outbox_worker_tick,
) -> Dict[str, Any]:
    """Cloud Run/Tasks HTTP shim for one disabled-by-default worker tick.

    Authentication is intentionally delegated to Cloud Run IAM (roles/run.invoker)
    with Cloud Scheduler/Tasks OIDC tokens and an exact audience, as documented
    in the deployment contract. This endpoint does not invent an app-level bearer
    token scheme. If it is exposed without Cloud Run/IAP IAM, the worker must
    still remain disabled by env and fail closed before dependencies are built.
    The uid/shard and worker id come only from server-owned environment config,
    never from a client request body.
    """
    try:
        entrypoint_config = parse_vector_repair_outbox_worker_entrypoint_config(env)
    except ValueError as exc:
        return _entrypoint_summary(config_valid=False, errors=[_error("config", str(exc))])

    if not entrypoint_config.enabled:
        return _entrypoint_summary(config_valid=True)

    if entrypoint_config.uid is None or entrypoint_config.tick_config is None:
        return _entrypoint_summary(
            config_valid=False,
            errors=[_error("config", "enabled worker config is incomplete")],
        )

    try:
        dependencies = dependency_builder(env)
    except ValueError as exc:
        return _entrypoint_summary(config_valid=False, errors=[_error("dependencies", str(exc))])

    try:
        summary = tick_runner(
            db_client=dependencies.db_client,
            uid=entrypoint_config.uid,
            config=entrypoint_config.tick_config,
            authoritative_item_loader=dependencies.authoritative_item_loader,
            vector_deleter=dependencies.vector_deleter,
            vector_repairer=dependencies.vector_repairer,
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
    return output


def create_vector_repair_outbox_worker_app(
    *,
    env: Optional[Mapping[str, str]] = None,
    dependency_builder: Callable[
        [Mapping[str, str]], VectorRepairOutboxProductionDependencies
    ] = build_vector_repair_outbox_production_dependencies,
    tick_runner: Callable[..., Dict[str, Any]] = run_vector_repair_outbox_worker_tick,
) -> FastAPI:
    """Create the minimal ASGI surface used by Cloud Run service deployments.

    The route is sync on purpose: production Firestore/Pinecone/embedding clients
    are synchronous, and FastAPI runs sync handlers in a threadpool.
    """
    effective_env = os.environ if env is None else env
    worker_app = FastAPI(title="memory-vector-repair-outbox-worker", docs_url=None, redoc_url=None, openapi_url=None)
    routes_by_path = {}

    @worker_app.post("/memory-vector-repair-outbox-worker/tick", include_in_schema=False)
    def vector_repair_outbox_worker_tick_http() -> Dict[str, Any]:
        return run_vector_repair_outbox_worker_http_tick(
            env=effective_env,
            dependency_builder=dependency_builder,
            tick_runner=tick_runner,
        )

    routes_by_path["/memory-vector-repair-outbox-worker/tick"] = vector_repair_outbox_worker_tick_http
    worker_app.routes_by_path = routes_by_path
    return worker_app


def main(
    *,
    env: Optional[Mapping[str, str]] = None,
    tick_runner: Callable[..., Dict[str, Any]] = run_vector_repair_outbox_worker_tick,
    print_json: Callable[[str], Any] = print,
) -> int:
    """CLI hook for disabled-by-default Cloud Run/Tasks images."""
    effective_env = os.environ if env is None else env
    try:
        entrypoint_config = parse_vector_repair_outbox_worker_entrypoint_config(effective_env)
    except ValueError as exc:
        print_json(
            json.dumps(_entrypoint_summary(config_valid=False, errors=[_error("config", str(exc))]), sort_keys=True)
        )
        return 2

    if not entrypoint_config.enabled:
        print_json(json.dumps(_entrypoint_summary(config_valid=True), sort_keys=True))
        return 0

    try:
        dependencies = build_vector_repair_outbox_production_dependencies(effective_env)
    except ValueError as exc:
        print_json(
            json.dumps(
                _entrypoint_summary(config_valid=False, errors=[_error("dependencies", str(exc))]), sort_keys=True
            )
        )
        return 2

    return run_vector_repair_outbox_worker_entrypoint(
        env=effective_env,
        db_client=dependencies.db_client,
        authoritative_item_loader=dependencies.authoritative_item_loader,
        vector_deleter=dependencies.vector_deleter,
        vector_repairer=dependencies.vector_repairer,
        tick_runner=tick_runner,
        print_json=print_json,
    )


def _parse_enabled(raw: Optional[str]) -> bool:
    if raw is None or raw == "" or raw.lower() == "false":
        return False
    if raw.lower() == "true":
        return True
    raise ValueError(f"{MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED_ENV} must be 'true' or 'false'")


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


def _required_dependency_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required when memory vector repair worker is enabled")
    return value.strip()


def _required_record_str(record: Dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"record {key} is required")
    return value.strip()


def _entrypoint_summary(
    *,
    config_valid: bool,
    enabled: bool = False,
    uid: Optional[str] = None,
    worker_id: Optional[str] = None,
    errors: Optional[list[Dict[str, str]]] = None,
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


app = create_vector_repair_outbox_worker_app()


if __name__ == "__main__":
    sys.exit(main())
