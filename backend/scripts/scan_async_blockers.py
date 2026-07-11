#!/usr/bin/env python3
"""
FastAPI async blocker scanner for backend/.

Detects dangerous patterns in async def endpoints and helpers:
  1. async def with zero await (should be plain def)
  2. async def mixing await + sync DB calls (needs run_in_executor)
  3. Blocking file I/O (open, shutil) in async def
  4. Blocking network I/O (GCS uploads, google auth refresh) in async def
  5. time.sleep on event loop
  6. The same blocking calls hidden behind module-local sync helpers
  7. asyncio.to_thread(), which bypasses the repository's owned executor pools

Skips blocking calls already wrapped in asyncio.to_thread() or run_in_executor()
(i.e. calls inside lambda bodies or nested def functions that are passed
as arguments to these wrappers), while separately reporting asyncio.to_thread()
itself as an unmanaged offload.

Usage:
  python3 scan_async_blockers.py [--dirs backend/routers backend/utils backend/agent-proxy backend/dependencies.py] [--json]
  python3 scan_async_blockers.py --diff-base origin/main --fail-on high_network_io,mixed_await_sync_db

Exit codes:
  0 = clean for the selected fail-on policy
  1 = selected fail-on findings present
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union, cast

DEFAULT_FAIL_ON = ("high_network_io",)
DEFAULT_SCAN_DIRS = ("backend/routers", "backend/utils", "backend/agent-proxy", "backend/dependencies.py")
LOCAL_SCAN_DIRS = ("routers", "utils", "agent-proxy", "dependencies.py")
FAIL_ON_CATEGORIES = (
    "high_network_io",
    "async_helpers_with_blocking",
    "time_sleep",
    "mixed_await_sync_db",
    "no_await_should_be_def",
    "medium_file_io",
    "unmanaged_thread_offload",
)

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]
BlockingEffectKey = Tuple[str, int, str]
LocalHelperPath = Tuple[Tuple[str, int], ...]
LocalHelperEffects = Dict[str, Dict[BlockingEffectKey, LocalHelperPath]]
BLOCKING_EFFECT_FIELDS = ("db_calls", "file_io", "network_io", "sleeps")
STORAGE_NETWORK_CALL_MARKERS = (
    "upload",
    "delete",
    "deletion",
    "download",
    "signed_url",
    "signed_uri",
    "cleanup",
)


def _node_lineno(node: ast.AST) -> int:
    """Best-effort line number for an arbitrary AST node."""
    return cast(int, getattr(node, "lineno", 0))


def get_db_imports(source: str) -> Tuple[Set[str], Set[str]]:
    db_names: Set[str] = set()
    db_module_aliases: Set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and 'database' in node.module:
            if node.module == 'database':
                for alias in node.names:
                    db_module_aliases.add(alias.asname or alias.name)
            else:
                for alias in node.names:
                    db_names.add(alias.asname or alias.name)
        if isinstance(node, ast.ImportFrom) and node.module == 'firebase_admin':
            for alias in node.names:
                if alias.name == 'firestore':
                    db_module_aliases.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'database' in alias.name:
                    db_module_aliases.add(alias.asname or alias.name.split('.')[-1])
    return db_names, db_module_aliases


def get_storage_imports(source: str) -> Set[str]:
    names: Set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and 'storage' in node.module:
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def get_prerecorded_stt_imports(source: str) -> Set[str]:
    """Return imported synchronous prerecorded-STT callables.

    The public ``prerecorded*`` entry points perform synchronous provider HTTP
    calls. Keep the match import-aware so unrelated local helpers with similar
    names do not become false positives.
    """
    names: Set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module != "utils.stt.pre_recorded":
            continue
        for alias in node.names:
            if alias.name.startswith("prerecorded"):
                names.add(alias.asname or alias.name)
    return names


def _walk_body(node: FunctionNode) -> Iterator[ast.AST]:
    for stmt in node.body:
        yield from ast.walk(stmt)


def has_await(node: ast.AsyncFunctionDef) -> bool:
    for child in _walk_body(node):
        if isinstance(child, ast.Await):
            return True
    return False


def get_route_info(decorators: Sequence[ast.AST]) -> Tuple[str, Any]:
    for dec in decorators:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            method = dec.func.attr.upper()
            if dec.args and isinstance(dec.args[0], ast.Constant):
                return method, dec.args[0].value
    return "?", "?"


def _get_offloaded_lines(node: FunctionNode) -> Set[int]:
    """Find line numbers of calls inside recognized executor wrappers.

    These are lambda bodies and nested def functions passed as arguments to
    asyncio.to_thread(), loop.run_in_executor(), or the repository's
    utils.executors.run_blocking(). Calls inside those are already offloaded and
    should not be flagged.
    """
    offloaded: Set[int] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        is_to_thread = isinstance(child.func, ast.Attribute) and child.func.attr == 'to_thread'
        is_run_in_executor = isinstance(child.func, ast.Attribute) and child.func.attr == 'run_in_executor'
        is_run_blocking = isinstance(child.func, ast.Name) and child.func.id == 'run_blocking'
        if not is_to_thread and not is_run_in_executor and not is_run_blocking:
            continue
        for arg in child.args + [kw.value for kw in child.keywords]:
            if isinstance(arg, ast.Lambda):
                for n in ast.walk(arg.body):
                    offloaded.add(_node_lineno(n))
            elif isinstance(arg, ast.Name):
                offloaded.add(arg.lineno)
    return offloaded


def _collect_nested_func_lines(node: FunctionNode) -> Set[int]:
    """Collect line numbers inside nested def/lambda within an async function.

    Calls inside nested sync functions are not directly on the event loop,
    even if those functions are defined inside if/for/try blocks.
    """
    nested: Set[int] = set()
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for n in ast.walk(child):
                nested.add(_node_lineno(n))
    return nested


def _unmanaged_to_thread_calls(node: ast.AsyncFunctionDef) -> List[Dict[str, Any]]:
    """Return bare asyncio.to_thread calls outside nested function scopes."""
    nested = _collect_nested_func_lines(node)
    calls: List[Dict[str, Any]] = []
    for child in _walk_body(node):
        if not isinstance(child, ast.Call) or child.lineno in nested:
            continue
        if (
            isinstance(child.func, ast.Attribute)
            and child.func.attr == 'to_thread'
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == 'asyncio'
        ):
            calls.append({"line": child.lineno, "call": "asyncio.to_thread() [unmanaged executor]"})
    return calls


def _scan_function_body(
    node: FunctionNode,
    db_names: Set[str],
    db_module_aliases: Set[str],
    storage_names: Set[str],
    prerecorded_stt_names: Set[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Set[int]]:
    """Return direct blocking calls in a function body, excluding nested scopes."""
    db_calls: List[Dict[str, Any]] = []
    file_io: List[Dict[str, Any]] = []
    network_io: List[Dict[str, Any]] = []
    sleeps: List[Dict[str, Any]] = []
    body_call_lines: Set[int] = set()

    offloaded = _get_offloaded_lines(node)
    nested = _collect_nested_func_lines(node)

    for child in _walk_body(node):
        if not isinstance(child, ast.Call):
            continue
        line = child.lineno
        if line in offloaded or line in nested:
            continue
        body_call_lines.add(line)
        if isinstance(child.func, ast.Name):
            if child.func.id in db_names:
                db_calls.append({"line": line, "call": child.func.id})
            if child.func.id in storage_names:
                call_name = child.func.id
                if any(marker in call_name.lower() for marker in STORAGE_NETWORK_CALL_MARKERS):
                    network_io.append({"line": line, "call": call_name})
            if child.func.id in prerecorded_stt_names:
                network_io.append({"line": line, "call": f"{child.func.id}() [sync STT]"})
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
            if child.func.attr == 'verify_id_token':
                network_io.append({"line": line, "call": "verify_id_token() [sync HTTP]"})

    return db_calls, file_io, network_io, sleeps, body_call_lines


def _module_sync_helpers(tree: ast.Module) -> Dict[str, ast.FunctionDef]:
    """Return unambiguous module-level sync helpers.

    Resolution is deliberately narrow: only a direct ``helper()`` call can
    resolve to one top-level ``def helper`` in the same module. Imported calls,
    attributes, callbacks, conditionally defined functions, and async helpers
    remain outside this analysis so the scanner does not guess at runtime
    dispatch.
    """
    candidates: Dict[str, List[ast.FunctionDef]] = {}
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef):
            candidates.setdefault(statement.name, []).append(statement)
    return {name: nodes[0] for name, nodes in candidates.items() if len(nodes) == 1}


def _local_helper_calls(node: FunctionNode, helper_names: Set[str]) -> List[Tuple[str, int]]:
    """Return direct calls to resolvable local sync helpers in this function."""
    calls: List[Tuple[str, int]] = []
    offloaded = _get_offloaded_lines(node)
    nested = _collect_nested_func_lines(node)
    for child in _walk_body(node):
        if not isinstance(child, ast.Call):
            continue
        line = child.lineno
        if line in offloaded or line in nested:
            continue
        if isinstance(child.func, ast.Name) and child.func.id in helper_names:
            calls.append((child.func.id, line))
    return sorted(calls, key=lambda item: (item[1], item[0]))


def analyze_local_sync_helpers(
    tree: ast.Module,
    db_names: Set[str],
    db_module_aliases: Set[str],
    storage_names: Set[str],
    prerecorded_stt_names: Set[str],
) -> LocalHelperEffects:
    """Compute the shortest blocking path reachable from each local sync helper.

    A fixed-point calculation makes recursion and mutually recursive helper
    cycles safe. Each blocking sink is retained once per helper with its
    shortest call path; cycles therefore cannot grow paths forever.
    """
    helpers = _module_sync_helpers(tree)
    helper_names = set(helpers)
    effects: LocalHelperEffects = {name: {} for name in helpers}
    edges: Dict[str, List[Tuple[str, int]]] = {}

    for name, node in helpers.items():
        db_calls, file_io, network_io, sleeps, _ = _scan_function_body(
            node,
            db_names,
            db_module_aliases,
            storage_names,
            prerecorded_stt_names,
        )
        direct_by_field = {
            "db_calls": db_calls,
            "file_io": file_io,
            "network_io": network_io,
            "sleeps": sleeps,
        }
        for field, calls in direct_by_field.items():
            for call in calls:
                effects[name][(field, call["line"], call["call"])] = ()
        edges[name] = _local_helper_calls(node, helper_names)

    changed = True
    while changed:
        changed = False
        for caller in sorted(helpers):
            for callee, edge_line in edges[caller]:
                for effect, callee_path in sorted(effects[callee].items()):
                    candidate = ((callee, edge_line),) + callee_path
                    current = effects[caller].get(effect)
                    if current is None or len(candidate) < len(current):
                        effects[caller][effect] = candidate
                        changed = True

    return effects


def _propagated_helper_calls(
    node: ast.AsyncFunctionDef,
    local_helper_effects: LocalHelperEffects,
) -> Dict[str, List[Dict[str, Any]]]:
    """Materialize blocking helper paths at their async call sites."""
    propagated: Dict[str, List[Dict[str, Any]]] = {field: [] for field in BLOCKING_EFFECT_FIELDS}
    helper_names = set(local_helper_effects)
    for helper, call_line in _local_helper_calls(node, helper_names):
        for (field, sink_line, sink_call), helper_path in sorted(local_helper_effects[helper].items()):
            via = [helper, *(callee for callee, _ in helper_path)]
            chain_lines = [call_line, *(line for _, line in helper_path), sink_line]
            chain = " -> ".join([*(f"{name}()" for name in via), sink_call])
            propagated[field].append(
                {
                    "line": call_line,
                    "call": chain,
                    "via": via,
                    "chain_lines": chain_lines,
                    "sink_line": sink_line,
                }
            )
    return propagated


def scan_async_function(
    node: ast.AsyncFunctionDef,
    db_names: Set[str],
    db_module_aliases: Set[str],
    storage_names: Set[str],
    local_helper_effects: Optional[LocalHelperEffects] = None,
    prerecorded_stt_names: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Set[int]]:
    """Scan direct and module-local transitive blocking calls on the event loop."""
    db_calls, file_io, network_io, sleeps, body_call_lines = _scan_function_body(
        node,
        db_names,
        db_module_aliases,
        storage_names,
        prerecorded_stt_names or set(),
    )
    if local_helper_effects:
        propagated = _propagated_helper_calls(node, local_helper_effects)
        db_calls.extend(propagated["db_calls"])
        file_io.extend(propagated["file_io"])
        network_io.extend(propagated["network_io"])
        sleeps.extend(propagated["sleeps"])
    return db_calls, file_io, network_io, sleeps, body_call_lines


def collect_py_files(dirs: Sequence[str]) -> List[str]:
    files: List[str] = []
    for d in dirs:
        if os.path.isfile(d):
            if d.endswith('.py') and os.path.basename(d) != '__init__.py':
                files.append(d)
            continue
        for root, _, fnames in os.walk(d):
            for fname in sorted(fnames):
                if fname.endswith('.py') and fname != '__init__.py':
                    files.append(os.path.join(root, fname))
    return sorted(files)


def _line_span(node: ast.AsyncFunctionDef) -> Tuple[int, int]:
    start_line = node.lineno
    if node.decorator_list:
        start_line = min(dec.lineno for dec in node.decorator_list)
    end_line = cast(int, getattr(node, "end_lineno", node.lineno))
    return start_line, end_line


def scan_dirs(dirs: Sequence[str]) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "high_network_io": [],
        "medium_file_io": [],
        "no_await_should_be_def": [],
        "mixed_await_sync_db": [],
        "time_sleep": [],
        "async_helpers_with_blocking": [],
        "unmanaged_thread_offload": [],
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
        prerecorded_stt_names = get_prerecorded_stt_imports(source)
        local_helper_effects = analyze_local_sync_helpers(
            tree,
            db_names,
            db_module_aliases,
            storage_names,
            prerecorded_stt_names,
        )
        module_level_nodes = set(tree.body)
        is_dependency_module = os.path.basename(fpath) == 'dependencies.py'

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_endpoint = any('router' in ast.dump(d).lower() for d in node.decorator_list) or (
                    is_dependency_module and isinstance(node, ast.AsyncFunctionDef) and node in module_level_nodes
                )
                if is_endpoint:
                    if isinstance(node, ast.AsyncFunctionDef):
                        total_async += 1
                    else:
                        total_def += 1

            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            is_endpoint = any('router' in ast.dump(d).lower() for d in node.decorator_list) or (
                is_dependency_module and node in module_level_nodes
            )
            db_calls, file_io, network_io, sleeps, body_call_lines = scan_async_function(
                node,
                db_names,
                db_module_aliases,
                storage_names,
                local_helper_effects=local_helper_effects,
                prerecorded_stt_names=prerecorded_stt_names,
            )
            unmanaged_offloads = _unmanaged_to_thread_calls(node)
            endpoint_has_await = has_await(node)
            start_line, end_line = _line_span(node)
            blocking_call_lines = {
                call["line"] for call in db_calls + file_io + network_io + sleeps + unmanaged_offloads
            }
            all_calls_are_blocking = bool(body_call_lines) and body_call_lines <= blocking_call_lines

            if is_endpoint:
                method, path = get_route_info(node.decorator_list)
                entry: Dict[str, Any] = {
                    "file": fpath,
                    "line": start_line,
                    "end_line": end_line,
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
                if unmanaged_offloads:
                    results["unmanaged_thread_offload"].append({**entry, "calls": unmanaged_offloads})
                if not endpoint_has_await:
                    results["no_await_should_be_def"].append(
                        {
                            **entry,
                            "db_calls": db_calls,
                            "all_blocking": db_calls + file_io + network_io + sleeps + unmanaged_offloads,
                            "all_calls_are_blocking": all_calls_are_blocking,
                        }
                    )
                elif db_calls:
                    results["mixed_await_sync_db"].append({**entry, "db_calls": db_calls})
            else:
                if unmanaged_offloads:
                    results["unmanaged_thread_offload"].append(
                        {
                            "file": fpath,
                            "line": start_line,
                            "end_line": end_line,
                            "function": node.name,
                            "calls": unmanaged_offloads,
                        }
                    )
                if network_io or file_io or sleeps or db_calls:
                    results["async_helpers_with_blocking"].append(
                        {
                            "file": fpath,
                            "line": start_line,
                            "end_line": end_line,
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
        "unmanaged_thread_offload": len(results["unmanaged_thread_offload"]),
    }
    return results


def _normalize_path(path: str) -> str:
    return path.replace(os.sep, "/")


def _diff_paths(dirs: Sequence[str]) -> List[str]:
    return [_normalize_path(d.rstrip("/")) for d in dirs]


def changed_scope(diff_base: str, dirs: Sequence[str]) -> Dict[str, Any]:
    """Return changed line ranges and import-changed files for diff-scoped failures."""
    cmd: List[str] = [
        "git",
        "diff",
        "--unified=0",
        "--no-renames",
        "--diff-filter=ACMRTD",
        f"{diff_base}...HEAD",
        "--",
        *_diff_paths(dirs),
    ]
    proc = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE)
    ranges_by_file: Dict[str, List[Tuple[int, int]]] = {}
    import_changed_files: Set[str] = set()
    current_file: Optional[str] = None
    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    stdout_text = proc.stdout or ""
    for line in stdout_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            ranges_by_file.setdefault(current_file, [])
            continue
        if current_file is None:
            continue
        if line.startswith("@@"):
            match = hunk_re.match(line)
            if not match:
                continue
            start_str = match.group(1)
            count_str = match.group(2)
            if start_str is None:
                continue
            start = int(start_str)
            count = int(count_str or "1")
            if count == 0:
                # Deletion-only hunks have an empty new-side range (for example
                # ``+42,0``). Keep the adjacent post-delete line in scope so
                # diff-scoped fail-on checks still catch regressions caused by
                # removing an await/offload inside an otherwise unchanged async
                # function.
                start = max(start, 1)
                ranges_by_file[current_file].append((start, start))
                continue
            ranges_by_file[current_file].append((start, start + count - 1))
            continue
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        changed_source = line[1:].strip()
        if changed_source.startswith(("import ", "from ")):
            # Import-only changes in very large legacy async modules should not
            # pull every pre-existing blocking call in the file into fail-on
            # scope. The changed hunks themselves remain checked via ranges.
            if "# async-blockers: no-import-scope" not in changed_source:
                import_changed_files.add(current_file)

    import_changed_files = {
        file_path
        for file_path in import_changed_files
        if "async-blockers: no-import-scope" not in _read_source_for_scope(file_path)
    }
    return {"ranges": ranges_by_file, "import_changed_files": import_changed_files}


def _read_source_for_scope(file_path: str) -> str:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def finding_in_changed_scope(finding: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    file_path = _normalize_path(finding["file"])
    if file_path in scope["import_changed_files"]:
        return True

    file_ranges = scope["ranges"].get(file_path, [])
    if not file_ranges:
        return False
    source_text = _read_source_for_scope(file_path)
    if "async-blockers: no-changed-range-scope" in source_text:
        return False
    start = finding["line"]
    end = finding.get("end_line", start)
    if any(start <= changed_end and end >= changed_start for changed_start, changed_end in file_ranges):
        return True

    # A diff can add the blocking sink (or a transitive helper edge) while the
    # async caller itself remains unchanged. Keep every resolved call-graph
    # line in scope so helper extraction cannot evade the diff gate.
    related_lines: Set[int] = set()
    for call in _finding_calls(finding):
        related_lines.add(call.get("sink_line", call.get("line", 0)))
        related_lines.update(call.get("chain_lines", []))
    return any(
        changed_start <= line <= changed_end for line in related_lines for changed_start, changed_end in file_ranges
    )


def _finding_qualifies(category: str, finding: Dict[str, Any]) -> bool:
    return True


def normalize_fail_on(values: Sequence[str]) -> Tuple[str, ...]:
    categories: List[str] = []
    for value in values:
        for category in value.split(","):
            category = category.strip()
            if category:
                categories.append(category)
    unknown = sorted(set(categories) - set(FAIL_ON_CATEGORIES))
    if unknown:
        print(f"Error: unknown --fail-on categories: {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid categories: {', '.join(FAIL_ON_CATEGORIES)}", file=sys.stderr)
        sys.exit(2)
    return tuple(dict.fromkeys(categories))


def selected_failures(
    results: Dict[str, Any],
    fail_on: Tuple[str, ...],
    scope: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, Dict[str, Any]]]:
    failures: List[Tuple[str, Dict[str, Any]]] = []
    for category in fail_on:
        for finding in results.get(category, []):
            if not _finding_qualifies(category, finding):
                continue
            if scope is not None and not finding_in_changed_scope(finding, scope):
                continue
            failures.append((category, finding))
    return failures


def print_report(results: Dict[str, Any]) -> None:
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
    print(f"  unmanaged asyncio.to_thread:         {s['unmanaged_thread_offload']}")
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

    if results["unmanaged_thread_offload"]:
        print("--- Unmanaged thread offloads ---")
        for e in results["unmanaged_thread_offload"]:
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in e["calls"])
            label = e.get("endpoint") or e.get("function") or "async def"
            print(f"  {e['file']}:{e['line']} | {label} | {calls}")
        print()

    if results["medium_file_io"]:
        print("--- MEDIUM: Blocking file I/O in endpoints ---")
        for e in results["medium_file_io"]:
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in e["calls"])
            print(f"  {e['file']}:{e['line']} | {e['method']} {e['path']} | {e['endpoint']} | {calls}")
        print()

    if results["no_await_should_be_def"]:
        print(f"--- STRUCTURAL: async def with 0 await (should be def) ---")
        by_file: Dict[str, List[Dict[str, Any]]] = {}
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


def _finding_calls(finding: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "calls" in finding:
        return finding["calls"]
    return (
        finding.get("network_io", [])
        + finding.get("file_io", [])
        + finding.get("sleeps", [])
        + finding.get("db_calls", [])
        + finding.get("all_blocking", [])
    )


def print_selected_report(
    results: Dict[str, Any],
    failures: List[Tuple[str, Dict[str, Any]]],
    fail_on: Sequence[str],
    diff_base: str,
    full_report: bool,
) -> None:
    s: Dict[str, Any] = results["summary"]
    scope_label = (
        f"changed function/decorator ranges and import-changed files since {diff_base}"
        if diff_base
        else "all scanned functions"
    )

    print("=== FastAPI Async Blocker Gate ===")
    print(f"Endpoints scanned: {s['total_def_endpoints']} def + {s['total_async_endpoints']} async def")
    print(f"Fail-on policy: {', '.join(fail_on) if fail_on else '(none)'}")
    print(f"Fail-on scope: {scope_label}")
    print(f"Selected blocking findings: {len(failures)}")

    if failures:
        print()
        print("--- Blocking findings selected for this push ---")
        for category, finding in failures:
            label = finding.get("endpoint") or finding.get("function") or "async def"
            calls = ", ".join(f"{c['call']}:{c['line']}" for c in _finding_calls(finding))
            detail = f" | {calls}" if calls else ""
            print(f"  {category}: {finding['file']}:{finding['line']} | {label}{detail}")
    elif not full_report:
        total_known = sum(s[category] for category in FAIL_ON_CATEGORIES if category in s)
        print(f"Known findings outside this push's fail scope: {total_known}")
        print("Full audit suppressed; rerun with --full-report or PRE_PUSH_VERBOSE=1 for legacy findings.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan FastAPI routers for async blocking patterns")
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=list(DEFAULT_SCAN_DIRS),
        help=f"Directories to scan (default: {' '.join(DEFAULT_SCAN_DIRS)})",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument(
        "--fail-on",
        action="append",
        default=None,
        metavar="CATEGORY[,CATEGORY...]",
        help=(
            "Finding categories that should make the scanner exit 1. "
            f"Valid categories: {', '.join(FAIL_ON_CATEGORIES)}. "
            f"Default: {','.join(DEFAULT_FAIL_ON)}"
        ),
    )
    parser.add_argument(
        "--diff-base",
        help=(
            "Only fail findings whose function/decorator line range intersects lines changed since this git ref, "
            "or findings in files with changed imports."
        ),
    )
    parser.add_argument(
        "--full-report",
        action="store_true",
        help="Print every finding from the full async audit, including legacy findings outside the fail scope.",
    )
    args = parser.parse_args()
    if tuple(args.dirs) == DEFAULT_SCAN_DIRS and not os.path.isdir(DEFAULT_SCAN_DIRS[0]):
        args.dirs = list(LOCAL_SCAN_DIRS)
    fail_on = normalize_fail_on(args.fail_on or [",".join(DEFAULT_FAIL_ON)])

    for d in args.dirs:
        if not os.path.exists(d):
            print(f"Error: {d} not found", file=sys.stderr)
            sys.exit(2)

    results = scan_dirs(args.dirs)
    scope = changed_scope(args.diff_base, args.dirs) if args.diff_base else None
    failures = selected_failures(results, fail_on, scope)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        print_selected_report(results, failures, fail_on, args.diff_base, args.full_report)
        if args.full_report:
            print()
            print_report(results)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
