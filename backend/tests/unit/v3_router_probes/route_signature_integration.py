#!/usr/bin/env python3
"""Pure/static Oracle P1-3 `/v3` route-signature integration proof.

This runner statically inspects `backend/routers/memories.py` with Python AST and
source text only. It intentionally does not import FastAPI, router modules,
Firestore/Pinecone/cloud/provider clients, or application startup code. It makes
no runtime cutover claim; current `/v3` behavior remains legacy-wired and
BLOCKED/NO-GO for memory rollout.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

TARGET_ROUTES = {
    ('GET', '/v3/memories'),
    ('POST', '/v3/memories'),
    ('DELETE', '/v3/memories/{memory_id}'),
}

CURRENT_RUNTIME_SUMMARY = (
    "GET /v3/memories now has a hard default-off memory dependency branch: production/default and "
    "non-enrolled legacy-primary reads preserve legacy memories_db semantics, while TestClient-only "
    "memory read-mode overrides can call the composed service without legacy fallback. POST/DELETE remain legacy mutation paths."
)

FUTURE_WIRING_SEAM = [
    "GET route query params -> adapt_v3_request_parameters(...) without FastAPI-specific coupling",
    "adapted request + server-owned control/grant/projection/write evidence -> plan_v3_memory_route(...) pure planner",
    "planner read envelope -> adapt_v3_memory_response(...) List[MemoryDB] body plus additive headers",
]

RUNTIME_BLOCKERS = [
    "Do not wire while GET still lacks route-local server-owned memory control/grant/projection evidence inputs.",
    "Do not wire while POST/DELETE still execute direct legacy DB/vector mutation paths for enrolled memory accounts.",
    "Do not wire until FastAPI dependency/response-model behavior is proven with controlled stubs or production deps.",
]

GET_PARAM_CONTRACT_MAPPING = [
    {
        "route_param": "limit",
        "current_route_param_present": True,
        "request_adapter_field": "limit",
        "safe_to_map": True,
        "future_only": False,
        "memory_constraint": "bounded memory limit; never expanded to 5000 in memory cursor mode",
        "blocked_reason": None,
    },
    {
        "route_param": "offset",
        "current_route_param_present": True,
        "request_adapter_field": "offset",
        "safe_to_map": False,
        "future_only": False,
        "memory_constraint": "legacy-primary compatibility only",
        "blocked_reason": "offset is legacy-primary only; memory cohort requires signed cursor mode",
    },
    {
        "route_param": "cursor",
        "current_route_param_present": True,
        "request_adapter_field": "cursor",
        "safe_to_map": True,
        "future_only": False,
        "memory_constraint": "additive opaque HMAC keyset cursor bound to uid/account/projection/filter/source/read-mode",
        "blocked_reason": None,
    },
    {
        "route_param": "category",
        "current_route_param_present": False,
        "request_adapter_field": "filters.category",
        "safe_to_map": True,
        "future_only": True,
        "memory_constraint": "filter hash must be cursor-bound; no silent legacy fallback for unsupported filters",
        "blocked_reason": None,
    },
    {
        "route_param": "include_archive",
        "current_route_param_present": False,
        "request_adapter_field": "include_archive",
        "safe_to_map": False,
        "future_only": True,
        "memory_constraint": "Archive default-unavailable unless a separate explicit persisted capability is launched",
        "blocked_reason": "Archive default-unavailable for /v3 default reads",
    },
]

ROUTE_SIGNATURE_INTEGRATION_PROOF = {
    "service": "backend/scripts/p1_3_v3_route_signature_integration.py",
    "test": "backend/tests/unit/test_p1_3_v3_route_signature_integration.py",
    "runtime_wired": True,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "static_ast_source_inspection_of_memories_router_no_fastapi_import",
        "pins_get_post_delete_v3_route_signatures_and_body_models",
        "pins_current_legacy_get_post_delete_db_vector_paths_no_cutover_claim",
        "maps_get_limit_offset_to_request_adapter_contract_with_offset_memory_blocked",
        "identifies_future_query_to_request_adapter_to_route_planner_to_response_adapter_seam",
        "archive_default_unavailable_no_stale_short_term_default_visible",
    ],
}


def _repo_backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _annotation(arg: ast.arg) -> str | None:
    return ast.unparse(arg.annotation) if arg.annotation is not None else None


def _default_for(index: int, args: ast.arguments) -> ast.expr | None:
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    return defaults[index]


def _dependency(default: ast.expr | None) -> str | None:
    if not isinstance(default, ast.Call):
        return None
    if ast.unparse(default.func) != 'Depends' or not default.args:
        return None
    return ast.unparse(default.args[0])


def _param_kind(name: str, route_path: str, method: str, dependency: str | None, body_model: str | None) -> str:
    if dependency is not None:
        return 'dependency'
    if '{' + name + '}' in route_path:
        return 'path'
    if method == 'POST' and body_model == name:
        return 'body'
    return 'query'


def _decorated_route(decorator: ast.expr) -> tuple[str, str, str | None] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = ast.unparse(decorator.func)
    if not func.startswith('router.') or not decorator.args:
        return None
    method = func.split('.', 1)[1].upper()
    path_node = decorator.args[0]
    if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
        return None
    response_model = None
    for keyword in decorator.keywords:
        if keyword.arg == 'response_model':
            response_model = ast.unparse(keyword.value)
    return method, path_node.value, response_model


FRAMEWORK_INJECTED_PARAM_TYPES = frozenset({'Request', 'Response', 'BackgroundTasks', 'WebSocket'})


def _body_model(function: ast.FunctionDef | ast.AsyncFunctionDef, method: str, route_path: str) -> str | None:
    if method not in {'POST', 'PATCH', 'PUT'}:
        return None
    for index, arg in enumerate(function.args.args):
        default = _default_for(index, function.args)
        dep = _dependency(default)
        annotation = _annotation(arg)
        if dep is None and annotation is not None and '{' + arg.arg + '}' not in route_path:
            base_type = annotation.split('[')[0].strip()
            if base_type in FRAMEWORK_INJECTED_PARAM_TYPES:
                continue
            return annotation
    return None


def _params(
    function: ast.FunctionDef | ast.AsyncFunctionDef, method: str, route_path: str, body_model: str | None
) -> list[dict[str, Any]]:
    params = []
    for index, arg in enumerate(function.args.args):
        default = _default_for(index, function.args)
        default_text = ast.unparse(default) if default is not None else None
        dep = _dependency(default)
        kind_body_model = arg.arg if body_model is not None and _annotation(arg) == body_model else None
        params.append(
            {
                "name": arg.arg,
                "annotation": _annotation(arg),
                "default": default_text,
                "dependency": dep,
                "kind": _param_kind(arg.arg, route_path, method, dep, kind_body_model),
            }
        )
    return params


def _legacy_runtime_calls(route: str, source_segment: str) -> list[str]:
    if route == 'GET /v3/memories':
        required = [
            ("_legacy_get_memories(uid, limit, offset)", "if offset == 0: limit = 5000"),
            ("_legacy_get_memories(uid, limit, offset)", "memories_db.get_memories(uid, limit, offset)"),
        ]
    elif route == 'POST /v3/memories':
        required = [
            (
                "MemoryDB.from_memory(memory, uid, None, manually_added)",
                "MemoryDB.from_memory(memory, uid, None, manually_added)",
            ),
            ("memories_db.create_memory", "memories_db.create_memory(uid, payload)"),
            (
                "upsert_memory_vector",
                "upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value, memory_db.subject_entity_id)",
            ),
        ]
    elif route == 'DELETE /v3/memories/{memory_id}':
        required = [
            ("_validate_memory(uid, memory_id)", "_validate_memory(uid, memory_id)"),
            ("memories_db.delete_memory(uid, memory_id)", "memories_db.delete_memory(uid, memory_id)"),
            ("delete_memory_vector(uid, memory_id)", "delete_memory_vector(uid, memory_id)"),
        ]
    else:
        required = []
    return [label for needle, label in required if needle in source_segment]


def inspect_route_signatures(router_source_path: Path | None = None) -> list[dict[str, Any]]:
    source_path = router_source_path or (_repo_backend_root() / 'routers' / 'memories.py')
    source = source_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    routes: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            decorated = _decorated_route(decorator)
            if decorated is None:
                continue
            method, route_path, response_model = decorated
            if (method, route_path) not in TARGET_ROUTES:
                continue
            route = f'{method} {route_path}'
            body_model = _body_model(node, method, route_path)
            source_segment = ast.get_source_segment(source, node) or ''
            routes.append(
                {
                    "route": route,
                    "method": method,
                    "path": route_path,
                    "handler": node.name,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "response_model": response_model,
                    "body_model": body_model,
                    "params": _params(node, method, route_path, body_model),
                    "legacy_runtime_calls": _legacy_runtime_calls(route, source_segment),
                    "source_file": "backend/routers/memories.py",
                    "static_source_inspection": True,
                    "runtime_wired_to_memory": route == 'GET /v3/memories',
                }
            )
    return sorted(routes, key=lambda item: (item['method'], item['path']))


def build_report(*, execute: bool = False) -> dict[str, Any]:
    route_signatures = inspect_route_signatures()
    return {
        "artifact": "p1_3_v3_route_signature_integration",
        "status": "BLOCKED",
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "app_startup_executed": False,
        "router_imported": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "pinecone_calls_executed": False,
        "benchmark_evidence_collected": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "runtime_cutover_claimed": False,
        "route_signatures": route_signatures,
        "get_param_contract_mapping": GET_PARAM_CONTRACT_MAPPING,
        "future_wiring_seam": FUTURE_WIRING_SEAM,
        "runtime_blockers": RUNTIME_BLOCKERS,
        "current_runtime_summary": CURRENT_RUNTIME_SUMMARY,
        "route_signature_integration_proof": ROUTE_SIGNATURE_INTEGRATION_PROOF,
        "non_claims": [
            "No FastAPI/router module import or app startup executed.",
            "No runtime /v3 route behavior changed.",
            "No production traffic, Firestore, Pinecone, cloud, provider, or network calls executed.",
            "No Firestore reads or writes executed.",
            "No benchmark evidence or rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "route_signature_count": len(route_signatures),
            "mapped_get_param_count": len(GET_PARAM_CONTRACT_MAPPING),
            "read_only": True,
            "mutation_allowed": False,
            "router_imported": False,
            "runtime_cutover_claimed": False,
            "approval_claimed": False,
        },
    }


def test_build_report_static_probe_is_read_only_and_blocked():
    report = build_report()
    assert report["summary"]["status"] == "BLOCKED"
    assert report["summary"]["read_only"] is True
    assert report["summary"]["router_imported"] is False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit the same safe static report with execute=true")
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
