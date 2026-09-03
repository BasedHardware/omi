#!/usr/bin/env python3
"""Fail on duplicate route registrations across backend routers.

Incident class FC-shadowed-route-handler: DELETE /v1/conversations/{id}/action-items
was registered in two routers; main.py mounted conversations first, so FastAPI's
first-match silently shadowed the richer action_items handler (and its vector
cleanup) while that handler's own tests stayed green.

Deterministic and hermetic: parses @<router>.<method>("path") decorators and
APIRouter(prefix=...) definitions in backend/routers/, resolves mounts from the
three service entrypoints (backend/main.py, backend/desktop_backend.py,
backend/pusher/main.py), and fails if any (app, method, path) is registered more
than once. KNOWN_DUPLICATES exempts duplicates whose shadowing semantics are
load-bearing for shipped clients; each entry is an explicit mount-order decision
with a named migration follow-up. stdlib-only.
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
HTTP_METHODS = {"get", "post", "patch", "put", "delete", "websocket", "api_route"}

# Duplicates whose shadowing semantics are load-bearing today. An entry is an
# explicit mount-order decision backed by evidence, not a silent pass; keep this
# set minimal and remove an entry once its client migration lands.
# ("main", "delete", "/v1/conversations/{conversation_id}/action-items"): shipped
#   Flutter clients send the description-body DELETE to the first-mounted
#   conversations handler (app/lib/backend/http/api/conversations.dart sends
#   {'completed', 'description'} and expects 204), so serving the path from the
#   second-mounted action_items handler would turn a single-item swipe-delete
#   into delete-all-items-for-conversation on already-shipped builds. Follow-up:
#   migrate those callers to the per-item DELETE /v1/action-items/{id}, then
#   dedupe this registration. Evidence:
#   omi-knowledge-base/projects/monorepo-cleanup/evidence/
#   2026-09-03-pr12697-highrisk-audit.md (FINDING B).
KNOWN_DUPLICATES = {
    ("main", "delete", "/v1/conversations/{conversation_id}/action-items"),
}

ROUTER_DEF = re.compile(r"(\w+)\s*=\s*APIRouter\(([^)]*)\)", re.S)
PREFIX_KW = re.compile(r"prefix\s*=\s*['\"]([^'\"]+)['\"]")
DECORATOR = re.compile(
    r"@(\w+)\.(get|post|patch|put|delete|websocket|api_route)\(\s*['\"]([^'\"]+)['\"]", re.S)
INCLUDE = re.compile(r"include_router\(\s*(\w+)\.router\b")
IMPORT_AS = re.compile(r"from\s+(?:backend\.)?routers\.(\w+)\s+import\s+(?:.*)?\b(\w+)\s+as\s+\w+|"
                       r"from\s+(?:backend\.)?routers\.(\w+)\s+import\s+router", re.S)
PLAIN_IMPORT = re.compile(r"import\s+routers\.(\w+)\b")


def parse_router_module(path: Path):
    """Return {router_var: prefix} and [(method, path), ...] for one module."""
    text = path.read_text(encoding="utf-8", errors="replace")
    prefixes = {}
    for var, args in ROUTER_DEF.findall(text):
        m = PREFIX_KW.search(args)
        prefixes[var] = m.group(1) if m else ""
    routes = []
    for var, method, route_path in DECORATOR.findall(text):
        if var in prefixes or var.endswith("_router"):
            prefix = prefixes.get(var, "")
            if method == "api_route":
                # methods= kwarg decides; conservatively treat as all methods
                for m in ("get", "post", "patch", "put", "delete"):
                    routes.append((m, prefix + route_path))
            else:
                routes.append((method, prefix + route_path))
    router_vars = {v for v in prefixes if v == "router"} or {v for v in prefixes}
    return prefixes, routes, router_vars


def mounted_apps():
    """Return {app_name: [routers_module_names]} for each service entrypoint."""
    apps = {}
    for app, entry in ENTRYPOINTS.items():
        mods = []
        if entry.exists():
            text = entry.read_text(encoding="utf-8", errors="replace")
            for var in INCLUDE.findall(text):
                # include_router(chat.router) -> find the routers module that
                # exposes `router` imported under name `var`
                mods.append(var)
        apps[app] = mods
    return apps


def import_aliases(entry_text: str):
    """Map local var name -> routers module name from an entrypoint's imports."""
    aliases = {}
    for m in re.finditer(r"from\s+\.?routers\.(\w+)\s+import\s+(\w+)", entry_text):
        module, name = m.group(1), m.group(2)
        aliases.setdefault(name, module)
        aliases.setdefault(f"{name}.router", module)
    for m in re.finditer(r"from\s+\.?routers\s+import\s+([\w, ]+)", entry_text):
        for name in m.group(1).split(","):
            name = name.strip()
            if name:
                aliases.setdefault(name, name)
    return aliases


def main() -> int:
    module_routes = {}
    for py in sorted(ROUTERS_DIR.rglob("*.py")):
        if py.name == "__init__.py" and py.parent != ROUTERS_DIR:
            continue
        rel = py.relative_to(ROUTERS_DIR).with_suffix("").as_posix()
        if "/" in rel:
            continue  # support packages are shared modules, not routers
        _, routes, _ = parse_router_module(py)
        if routes:
            module_routes[rel] = routes

    registered = defaultdict(list)  # (app, method, path) -> [module, ...]
    for app, entry in ENTRYPOINTS.items():
        if not entry.exists():
            continue
        text = entry.read_text(encoding="utf-8", errors="replace")
        aliases = import_aliases(text)
        for var in INCLUDE.findall(text):
            module = aliases.get(var, var)
            for method, path in module_routes.get(module, []):
                registered[(app, method, path)].append(module)

    duplicates = {
        k: v for k, v in registered.items() if len(set(v)) > 1 and k not in KNOWN_DUPLICATES
    }
    exempted = sorted(k for k in registered if len(set(registered[k])) > 1 and k in KNOWN_DUPLICATES)
    if exempted:
        print("known duplicates exempted (load-bearing shadowing; see KNOWN_DUPLICATES):")
        for app, method, path in exempted:
            print(f"  [{app}] {method.upper()} {path}")
    if duplicates:
        print("FAIL: duplicate route registrations (first-mounted handler silently wins):")
        for (app, method, path), mods in sorted(duplicates.items()):
            print(f"  [{app}] {method.upper()} {path}  registered by: {', '.join(sorted(set(mods)))}")
        print("Dedupe to one registration, or make the mount-order decision explicit in the PR.")
        return 1
    total = len(registered)
    print(f"ok: no duplicate route registrations across {total} mounted (app, method, path) combinations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
