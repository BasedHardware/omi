from __future__ import annotations

import copy
import importlib.util
import json
import sys
from typing import Any

from scripts.readiness._paths import BACKEND_DIR, GATES_DIR, MANIFEST_PATH, REGISTRIES_DIR, HANDLERS_DIR

_MANIFEST: dict[str, Any] | None = None
_HANDLER_MODULES: dict[str, Any] = {}


def _load_manifest() -> dict[str, Any]:
    global _MANIFEST
    if _MANIFEST is None:
        _MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return _MANIFEST


def list_gate_ids() -> list[str]:
    return [entry["gate_id"] for entry in _load_manifest()["gates"]]


def _resolve_refs(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            ref = value["$ref"]
            registry_path = REGISTRIES_DIR / f"{ref}.json"
            if not registry_path.exists():
                raise KeyError(f"missing readiness registry {ref}")
            return json.loads(registry_path.read_text(encoding="utf-8"))
        return {key: _resolve_refs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(item) for item in value]
    return value


def _load_gate_payload(gate_id: str, *, execute: bool) -> dict[str, Any]:
    suffix = ".execute.json" if execute else ".json"
    gate_path = GATES_DIR / f"{gate_id}{suffix}"
    if execute and not gate_path.exists():
        gate_path = GATES_DIR / f"{gate_id}.json"
    if not gate_path.exists():
        raise KeyError(f"missing readiness gate payload {gate_id}")
    payload = json.loads(gate_path.read_text(encoding="utf-8"))
    return _resolve_refs(payload)


def _load_handler_module(gate_id: str):
    if gate_id in _HANDLER_MODULES:
        return _HANDLER_MODULES[gate_id]
    handler_path = HANDLERS_DIR / f"{gate_id}.py"
    if not handler_path.exists():
        raise KeyError(f"missing readiness handler {gate_id}")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location(f"readiness_handler_{gate_id}", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load readiness handler {handler_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _HANDLER_MODULES[gate_id] = module
    return module


def build_report(gate_id: str, *, execute: bool = False) -> dict[str, Any]:
    """Build a readiness report for ``gate_id`` (data-backed or handler-backed)."""
    manifest = _load_manifest()
    handler_ids = set(manifest.get("handler_gates", []))
    if gate_id in handler_ids:
        module = _load_handler_module(gate_id)
        if gate_id == "p1_3_v3_control_reader_emulator_readiness":
            return module.build_report(execute=execute, env={})
        if gate_id == "p1_3_v3_fastapi_route_contract":
            return module.build_report(execute)
        return module.build_report(execute=execute)

    report = copy.deepcopy(_load_gate_payload(gate_id, execute=execute))
    if "execute" in report:
        report["execute"] = execute
    if "execute_requested" in report:
        report["execute_requested"] = execute
    return report
