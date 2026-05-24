#!/usr/bin/env python3
"""
FastAPI async blocker scanner for backend/.

Detects dangerous patterns in async def endpoints and helpers:
  1. async def with zero await (should be plain def)
  2. async def mixing await + sync DB calls (needs run_in_executor)
  3. Blocking file I/O (open, shutil) in async def
  4. Blocking network I/O (GCS uploads, google auth refresh) in async def
  5. time.sleep on event loop

Skips calls already wrapped in asyncio.to_thread() or run_in_executor()
(i.e. calls inside lambda bodies or nested def functions that are passed
as arguments to these wrappers).

Usage:
  python3 scan_async_blockers.py [--dirs backend/routers backend/utils] [--json]

Exit codes:
  0 = clean (no HIGH findings)
  1 = HIGH findings present
"""

import ast, os, sys, json, argparse


def get_db_imports(source):
    db_names = set()
    db_module_aliases = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and 'database' in node.module:
            if node.module == 'database':
                for alias in node.names:
                    db_module_aliases.add(alias.asname or alias.name)
            else:
                for alias in node.names:
                    db_names.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'database' in alias.name:
                    db_module_aliases.add(alias.asname or alias.name.split('.')[-1])
    return db_names, db_module_aliases


def get_storage_imports(source):
    names = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and 'storage' in node.module:
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def has_await(node):
    for child in ast.walk(node):
        if isinstance(child, ast.Await):
            return True
    return False


def get_route_info(decorators):
    for dec in decorators:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            method = dec.func.attr.upper()
            if dec.args and isinstance(dec.args[0], ast.Constant):
                return method, dec.args[0].value
    return "?", "?"


def _get_offloaded_lines(node):
    """Find line numbers of calls inside asyncio.to_thread/run_in_executor wrappers.

    These are lambda bodies and nested def functions passed as arguments to
    asyncio.to_thread() or loop.run_in_executor(). Calls inside those are
    already offloaded and should not be flagged.
    """
    offloaded = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        is_to_thread = isinstance(child.func, ast.Attribute) and child.func.attr == 'to_thread'
        is_run_in_executor = isinstance(child.func, ast.Attribute) and child.func.attr == 'run_in_executor'
        if not is_to_thread and not is_run_in_executor:
            continue
        for arg in child.args + [kw.value for kw in child.keywords]:
            if isinstance(arg, ast.Lambda):
                for n in ast.walk(arg.body):
                    offloaded.add(n.lineno if hasattr(n, 'lineno') else 0)
            elif isinstance(arg, ast.Name):
                offloaded.add(arg.lineno)
    return offloaded


def _collect_nested_func_lines(node):
    """Collect line numbers inside nested def/lambda within an async function.

    Calls inside nested sync functions are not directly on the event loop,
    even if those functions are defined inside if/for/try blocks.
    """
    nested = set()
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.Lambda)):
            for n in ast.walk(child):
                if hasattr(n, 'lineno'):
                    nested.add(n.lineno)
    return nested


def scan_async_function(node, db_names, db_module_aliases, storage_names):
    """Scan an async function body for blocking calls on the event loop."""
    db_calls = []
    file_io = []
    network_io = []
    sleeps = []

    offloaded = _get_offloaded_lines(node)
    nested = _collect_nested_func_lines(node)

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        line = child.lineno
        if line in offloaded or line in nested:
            continue
        if isinstance(child.func, ast.Name):
            if child.func.id in db_names:
                db_calls.append({"line": line, "call": child.func.id})
            if child.func.id in storage_names:
                call_name = child.func.id
                if any(kw in call_name.lower() for kw in ["upload", "delete", "download"]):
                    network_io.append({"line": line, "call": call_name})
            if child.func.id == 'open':
                file_io.append({"line": line, "call": "open()"})
        if isinstance(child.func, ast.Attribute):
            if isinstance(child.func.value, ast.Name):
                if child.func.value.id in db_module_aliases:
                    db_calls.append({"line": line, "call": f"{child.func.value.id}.{child.func.attr}"})
                if child.func.value.id == 'time' and child.func.attr == 'sleep':
                    sleeps.append({"line": line, "call": "time.sleep()"})
                if child.func.value.id == 'requests':
                    network_io.append({"line": line, "call": f"requests.{child.func.attr}()"})
                if child.func.value.id == 'shutil':
                    file_io.append({"line": line, "call": f"shutil.{child.func.attr}()"})
            if (
                child.func.attr == 'refresh'
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == 'creds'
            ):
                network_io.append({"line": line, "call": "creds.refresh() [sync HTTP]"})

    return db_calls, file_io, network_io, sleeps


def collect_py_files(dirs):
    files = []
    for d in dirs:
        for root, _, fnames in os.walk(d):
            for fname in sorted(fnames):
                if fname.endswith('.py') and fname != '__init__.py':
                    files.append(os.path.join(root, fname))
    return sorted(files)


def scan_dirs(dirs):
    results = {
        "high_network_io": [],
        "medium_file_io": [],
        "no_await_should_be_def": [],
        "mixed_await_sync_db": [],
        "time_sleep": [],
        "async_helpers_with_blocking": [],
    }
    total_def = 0
    total_async = 0
    files_scanned = 0

    for fpath in collect_py_files(dirs):
        with open(fpath) as f:
            source = f.read()
        try:
            tree = ast.parse(source, filename=fpath)
        except Exception:
            continue
        files_scanned += 1

        db_names, db_module_aliases = get_db_imports(source)
        storage_names = get_storage_imports(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_endpoint = any('router' in ast.dump(d).lower() for d in node.decorator_list)
                if is_endpoint:
                    if isinstance(node, ast.AsyncFunctionDef):
                        total_async += 1
                    else:
                        total_def += 1

            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            is_endpoint = any('router' in ast.dump(d).lower() for d in node.decorator_list)
            db_calls, file_io, network_io, sleeps = scan_async_function(
                node, db_names, db_module_aliases, storage_names
            )
            endpoint_has_await = has_await(node)

            if is_endpoint:
                method, path = get_route_info(node.decorator_list)
                entry = {
                    "file": fpath,
                    "line": node.lineno,
                    "endpoint": node.name,
                    "method": method,
                    "path": path,
                    "has_await": endpoint_has_await,
                }

                if network_io:
                    results["high_network_io"].append({**entry, "calls": network_io})
                if file_io:
                    results["medium_file_io"].append({**entry, "calls": file_io})
                if sleeps:
                    results["time_sleep"].append({**entry, "calls": sleeps})
                if not endpoint_has_await:
                    results["no_await_should_be_def"].append(
                        {**entry, "db_calls": db_calls, "all_blocking": db_calls + file_io + network_io}
                    )
                elif db_calls:
                    results["mixed_await_sync_db"].append({**entry, "db_calls": db_calls})
            else:
                if network_io or file_io or sleeps or db_calls:
                    results["async_helpers_with_blocking"].append(
                        {
                            "file": fpath,
                            "line": node.lineno,
                            "function": node.name,
                            "network_io": network_io,
                            "file_io": file_io,
                            "sleeps": sleeps,
                            "db_calls": db_calls,
                        }
                    )

    results["summary"] = {
        "files_scanned": files_scanned,
        "total_def_endpoints": total_def,
        "total_async_endpoints": total_async,
        "high_network_io": len(results["high_network_io"]),
        "medium_file_io": len(results["medium_file_io"]),
        "no_await_should_be_def": len(results["no_await_should_be_def"]),
        "mixed_await_sync_db": len(results["mixed_await_sync_db"]),
        "time_sleep_on_loop": len(results["time_sleep"]),
        "async_helpers_with_blocking": len(results["async_helpers_with_blocking"]),
    }
    return results


def print_report(results):
    s = results["summary"]
    print(f"=== FastAPI Async Blocker Audit ===")
    print(f"Endpoints scanned: {s['total_def_endpoints']} def + {s['total_async_endpoints']} async def")
    print(f"")
    print(f"  HIGH  (network I/O on loop):        {s['high_network_io']}")
    print(f"  HIGH  (async helpers with blocking): {s['async_helpers_with_blocking']}")
    print(f"  MEDIUM (file I/O on loop):           {s['medium_file_io']}")
    print(f"  STRUCTURAL (async def, 0 await):     {s['no_await_should_be_def']}")
    print(f"  STRUCTURAL (mixed await+sync DB):    {s['mixed_await_sync_db']}")
    print(f"  time.sleep on loop:                  {s['time_sleep_on_loop']}")
    print()

    if results["high_network_io"]:
        print("--- HIGH: Blocking network I/O in endpoints ---")
        for e in results["high_network_io"]:
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in e["calls"])
            print(f"  {e['file']}:{e['line']} | {e['method']} {e['path']} | {e['endpoint']} | {calls}")
        print()

    if results["async_helpers_with_blocking"]:
        print("--- Async helper functions with blocking calls ---")
        for e in results["async_helpers_with_blocking"]:
            items = e.get("network_io", []) + e.get("file_io", []) + e.get("sleeps", []) + e.get("db_calls", [])
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in items)
            print(f"  {e['file']}:{e['line']} | {e['function']} | {calls}")
        print()

    if results["medium_file_io"]:
        print("--- MEDIUM: Blocking file I/O in endpoints ---")
        for e in results["medium_file_io"]:
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in e["calls"])
            print(f"  {e['file']}:{e['line']} | {e['method']} {e['path']} | {e['endpoint']} | {calls}")
        print()

    if results["no_await_should_be_def"]:
        print(f"--- STRUCTURAL: async def with 0 await (should be def) ---")
        by_file = {}
        for e in results["no_await_should_be_def"]:
            f = e['file'].split('/')[-1]
            by_file.setdefault(f, []).append(e)
        for f, eps in sorted(by_file.items()):
            print(f"  {f}: {len(eps)} endpoints")
            for e in eps:
                blocking = e.get("all_blocking", [])
                extra = f" | blocking: {', '.join(c['call']+':'+str(c['line']) for c in blocking)}" if blocking else ""
                print(f"    :{e['line']} {e['endpoint']}{extra}")
        print()

    if results["mixed_await_sync_db"]:
        print(f"--- STRUCTURAL: Mixed await + sync DB calls ---")
        for e in results["mixed_await_sync_db"]:
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in e["db_calls"])
            print(f"  {e['file']}:{e['line']} | {e['endpoint']} | {calls}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Scan FastAPI routers for async blocking patterns")
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=["backend/routers", "backend/utils"],
        help="Directories to scan (default: backend/routers backend/utils)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    for d in args.dirs:
        if not os.path.isdir(d):
            print(f"Error: {d} not found", file=sys.stderr)
            sys.exit(2)

    results = scan_dirs(args.dirs)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        print_report(results)

    has_high = results["summary"]["high_network_io"] > 0
    sys.exit(1 if has_high else 0)


if __name__ == "__main__":
    main()
