#!/usr/bin/env python3
"""Fail on duplicate route registrations across backend routers.

Incident class FC-shadowed-route-handler: DELETE /v1/conversations/{id}/action-items
was registered in two routers; main.py mounted conversations first, so FastAPI's
first-match silently shadowed the richer action_items handler (and its vector
cleanup) while that handler's own tests stayed green.

Deterministic and hermetic: parses @<router>.<method>("path") decorators and
APIRouter(prefix=...) definitions in backend/routers/ — including decorators
whose path is a module-level string constant and the legacy
`router.add_api_route(path, handler, methods=[...])` table form — resolves
mounts from the three service entrypoints (backend/main.py,
backend/desktop_backend.py, backend/pusher/main.py), and fails if any
(app, method, normalized-path) is registered more than once. Path normalization
collapses {param} placeholders to {} so `/t/{a}` and `/t/{b}` compare equal
(FastAPI matches them identically). KNOWN_DUPLICATES exempts duplicates whose
shadowing semantics are load-bearing for shipped clients; each entry is an
explicit mount-order decision with a named migration follow-up. stdlib-only.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = ROOT / "backend" / "routers"
ENTRYPOINTS = {
    "main": ROOT / "backend" / "main.py",
    "desktop_backend": ROOT / "backend" / "desktop_backend.py",
    "pusher": ROOT / "backend" / "pusher" / "main.py",
}

# Duplicates whose shadowing semantics are load-bearing today. An entry is an
# explicit mount-order decision backed by evidence, not a silent pass; keep this
# set minimal and remove an entry once its client migration lands.
# ("main", "delete", "/v1/conversations/{}/action-items"): shipped Flutter
#   clients send the description-body DELETE to the first-mounted conversations
#   handler (app/lib/backend/http/api/conversations.dart sends
#   {'completed', 'description'} and expects 204), so serving the path from the
#   second-mounted action_items handler would turn a single-item swipe-delete
#   into delete-all-items-for-conversation on already-shipped builds. Follow-up:
#   migrate those callers to the per-item DELETE /v1/action-items/{id}, then
#   dedupe this registration. Evidence:
#   omi-knowledge-base/projects/monorepo-cleanup/evidence/
#   2026-09-03-pr12697-highrisk-audit.md (FINDING B).
KNOWN_DUPLICATES = {
    ("main", "delete", "/v1/conversations/{}/action-items"),
}

ROUTER_DEF = re.compile(r"(\w+)\s*=\s*APIRouter\(([^)]*)\)", re.S)
PREFIX_KW = re.compile(r"prefix\s*=\s*['\"]([^'\"]+)['\"]")
DECORATOR = re.compile(
    r"@(\w+)\.(get|post|patch|put|delete|websocket|api_route)\(\s*['\"]([^'\"]+)['\"]",
    re.S,
)
CONST_ASSIGN = re.compile(r"^(_?[A-Z][A-Z0-9_]*)\s*=\s*['\"]([^'\"]+)['\"]", re.M)
DECORATOR_CONST = re.compile(
    r"@(\w+)\.(get|post|patch|put|delete|websocket|api_route)\(\s*([A-Za-z_]\w*)\b",
    re.S,
)
API_ROUTE_METHODS = re.compile(r"methods\s*=\s*\[([^\]]*)\]", re.S)
ADD_API_ROUTE = re.compile(
    r"\b(\w+)\.add_api_route\(\s*['\"]([^'\"]+)['\"]\s*,\s*\w+\s*,\s*methods\s*=\s*(?:list\()?\[([^\]]*)\]",
    re.S,
)
# Legacy dynamic table: `for path_var, methods_var in TABLE.items():` with
# `router.add_api_route(path_var, handler, methods=list(methods_var))` in the
# loop body (desktop_deprecated pattern); TABLE is a literal dict of
# "path": ("GET", "PATCH") entries.
ROUTE_TABLE_LOOP = re.compile(
    r"for\s+(\w+)\s*,\s*(\w+)\s+in\s+(_?[A-Z][A-Z0-9_]*)\.items\(\):(.*?)(?=\ndef |\n\n\n|\Z)",
    re.S,
)
DICT_ENTRY = re.compile(r"['\"]([^'\"]+)['\"]\s*:\s*\(([^)]*)\)")
# include_router(<anything>) — captures the full dotted attribute expression
# (e.g. `conv.router`, `api_key_management.mcp_router`, `imported_alias`).
INCLUDE_ANY = re.compile(r"include_router\(\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")


def _split_methods(raw: str):
    """['GET', 'POST'] -> {'get', 'post'} (lowercased)."""
    return {m.strip().strip("'\"").lower() for m in raw.split(",") if m.strip()}


def normalize_path(path: str) -> str:
    """Collapse {param} placeholders so /t/{a} and /t/{b} compare equal."""
    return re.sub(r"\{[^/}]+\}", "{}", path)


def parse_router_module(path: Path):
    """Return {router_var: [(method, normalized_path), ...]} for one module."""
    text = path.read_text(encoding="utf-8", errors="replace")
    prefixes = {}
    for var, args in ROUTER_DEF.findall(text):
        m = PREFIX_KW.search(args)
        prefixes[var] = m.group(1) if m else ""
    # Module-level string constants usable as decorator paths (jit_* pattern).
    constants = dict(CONST_ASSIGN.findall(text))

    router_routes = defaultdict(list)

    def add(router_var: str, method: str, route_path: str):
        prefix = prefixes.get(router_var, "")
        router_routes[router_var].append((method, normalize_path(prefix + route_path)))

    for var, method, route_path in DECORATOR.findall(text):
        if var in prefixes or var.endswith("_router"):
            if method == "api_route":
                # methods= kwarg decides; fall back to GET (FastAPI's default).
                m = API_ROUTE_METHODS.search(text)
                methods = _split_methods(m.group(1)) if m else {"get"}
                for meth in methods:
                    add(var, meth, route_path)
            else:
                add(var, method, route_path)

    # Decorators whose path is a module-level constant (e.g. @router.get(_SNAPSHOT_PATH)).
    for var, method, name in DECORATOR_CONST.findall(text):
        if name not in constants or name == "router":
            continue
        if var in prefixes or var.endswith("_router"):
            if method == "api_route":
                m = API_ROUTE_METHODS.search(text)
                methods = _split_methods(m.group(1)) if m else {"get"}
                for meth in methods:
                    add(var, meth, constants[name])
            else:
                add(var, method, constants[name])

    # Legacy dynamic table 1: router.add_api_route("path", handler, methods=[...]).
    for var, route_path, raw_methods in ADD_API_ROUTE.findall(text):
        for meth in _split_methods(raw_methods):
            add(var, meth, route_path)

    # Legacy dynamic table 2: `for path_var, methods_var in TABLE.items():` with
    # `router.add_api_route(path_var, handler, methods=list(methods_var))` in the
    # loop body; TABLE is a literal dict of "path": ("GET", ...) entries.
    for path_var, methods_var, table_name, body in ROUTE_TABLE_LOOP.findall(text):
        table_match = re.search(table_name + r"\s*=\s*\{(.*?)\n\}", text, re.S)
        if not table_match:
            continue
        if not re.search(r"add_api_route\(\s*" + path_var, body):
            continue
        if not re.search(r"methods\s*=\s*(?:list\()?\[?\s*" + methods_var, body):
            continue
        for route_path, raw_methods in DICT_ENTRY.findall(table_match.group(1)):
            for meth in _split_methods(raw_methods):
                add("router", meth, route_path)

    return dict(router_routes)


def mounted_routers(entry_text: str, aliases: dict):
    """Return [(routers_module_name, router_var), ...] mounted by one entrypoint.

    Matches every include_router(<attr>) form: `conv.router` (module attr),
    `api_key_management.mcp_router` (named routers from one module), a bare
    alias-imported router (`from routers.x import mcp_router`), or a bare
    module reference (conventionally exposing `.router`).
    """
    mounted = []
    for attr in INCLUDE_ANY.findall(entry_text):
        head = attr.split(".")[0]
        module = aliases.get(head, head)
        if "." in attr:
            var = attr.split(".")[-1]
        elif head in aliases:
            var = head  # alias-imported router object
        else:
            var = "router"  # bare module reference; routers expose `router`
        mounted.append((module, var))
    return mounted


def import_aliases(entry_text: str):
    """Map local var name -> routers module name from an entrypoint's imports."""
    aliases = {}
    # from routers.api_key_management import mcp_router, developer_router
    for m in re.finditer(r"from\s+\.?routers\.(\w+)\s+import\s+([\w, ]+)", entry_text):
        module, names = m.group(1), m.group(2)
        for name in names.split(","):
            name = name.strip()
            if name and name != "router":
                aliases.setdefault(name, module)
    # from .routers import conv, items
    for m in re.finditer(r"from\s+\.?routers\s+import\s+([\w, ]+)", entry_text):
        for name in m.group(1).split(","):
            name = name.strip()
            if name:
                aliases.setdefault(name, name)
    return aliases


def main() -> int:
    module_routers = {}
    for py in sorted(ROUTERS_DIR.rglob("*.py")):
        if py.name == "__init__.py" and py.parent != ROUTERS_DIR:
            continue
        rel = py.relative_to(ROUTERS_DIR).with_suffix("").as_posix()
        if "/" in rel:
            continue  # support packages are shared modules, not routers
        router_routes = parse_router_module(py)
        if router_routes:
            module_routers[rel] = router_routes

    registered = defaultdict(list)  # (app, method, normalized_path) -> [module, ...]
    for app, entry in ENTRYPOINTS.items():
        if not entry.exists():
            continue
        text = entry.read_text(encoding="utf-8", errors="replace")
        aliases = import_aliases(text)
        for module, var in mounted_routers(text, aliases):
            for method, path in module_routers.get(module, {}).get(var, []):
                registered[(app, method, path)].append(module)

    duplicates = {
        k: v for k, v in registered.items() if len(v) > 1 and k not in KNOWN_DUPLICATES
    }
    exempted = sorted(
        k for k in registered if len(registered[k]) > 1 and k in KNOWN_DUPLICATES
    )
    if exempted:
        print(
            "known duplicates exempted (load-bearing shadowing; see KNOWN_DUPLICATES):"
        )
        for app, method, path in exempted:
            print(f"  [{app}] {method.upper()} {path}")
    if duplicates:
        print(
            "FAIL: duplicate route registrations (first-mounted handler silently wins):"
        )
        for (app, method, path), mods in sorted(duplicates.items()):
            print(
                f"  [{app}] {method.upper()} {path}  registered by: {', '.join(sorted(set(mods)))}"
            )
        print(
            "Dedupe to one registration, or make the mount-order decision explicit in the PR."
        )
        return 1
    total = len(registered)
    print(
        f"ok: no duplicate route registrations across {total} mounted (app, method, path) combinations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
