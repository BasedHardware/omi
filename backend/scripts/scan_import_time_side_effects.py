#!/usr/bin/env python3
"""Tier-1 guard: ban import-time side effects in backend production code.

WHY: the root cause of the backend unit suite's inability to run in a single pytest
process is production modules performing side effects at import time (constructing
credentialled clients, downloading artifacts, reading env that can raise). Tests then
mutate ``sys.modules`` to paper over it. This scanner enforces *import purity* at the
source so the disease is not regenerated. See ``backend/docs/test_isolation.md`` and
``.coordination/test-isolation/PLAN.md`` (Tier 1, conviction P2).

WHAT IT DETECTS (at module scope only — inside functions/classes is allowed):
  - Calls to a curated list of side-effecting constructors, e.g.:
      OpenAI / AsyncOpenAI / Anthropic / AsyncAnthropic
      DeepgramClient
      Pinecone
      firebase_admin.initialize_app
      tiktoken.encoding_for_model / tiktoken.get_encoding
      typesense.Client / pusher.Client
      requests.Session / httpx.Client / httpx.AsyncClient
      firestore.Client / firestore.Firestore / redis.Redis
    (The list is maintained in ``SIDE_EFFECT_CTORS``; adding constructors is
    *tightening*, never debt.)
  - ``os.environ["X"]`` subscript at module scope (raises if missing → brittle import).
    ``os.getenv(...)`` / ``os.environ.get(...)`` are allowed.
  - Top-level network calls: ``requests.get/post/...``, ``httpx.get/post/...``,
    ``urllib.request.urlopen``.
  - Top-level ``open(...)`` calls (file IO at import time).

SCOPE: ``backend/**/*.py`` excluding ``backend/tests/`` and ``backend/testing/``.
(migrations/ and scripts/ are included; existing violations are grandfathered into
the legacy allowlist, new ones must justify via pragma or fix.)

ESCAPE VALVE: a deprecated legacy allowlist
(``backend/tests/.import_time_side_effects_legacy``) plus a per-line pragma
``# noqa: import-side-effect: <reason>`` with a REQUIRED reason string. The pragma
makes escapes visible, auditable, and grep-able. Tier-1 has a pragma; Tier-2
(``check_module_stub_pollution.py``) does not — the sanctioned seam exists, so there
is no excuse for new ``sys.modules`` writes.

USAGE:
  python backend/scripts/scan_import_time_side_effects.py
  python backend/scripts/scan_import_time_side_effects.py --files <file-list>
  python backend/scripts/scan_import_time_side_effects.py --check-allowlist-monotonic main

Exit 1 on any unallowlisted/pragma-less offender or any allowlist growth.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_ALLOWLIST = BACKEND_DIR / "tests" / ".import_time_side_effects_legacy"

# (module_prefix, attr_name) tuples; a call matches if its dotted chain starts with
# module_prefix and ends with attr_name. Curated = low false-positive.
SIDE_EFFECT_CTORS: list[tuple[str, str]] = [
    ("openai", "OpenAI"),
    ("openai", "AsyncOpenAI"),
    ("langchain_openai", "ChatOpenAI"),
    ("langchain_openai", "OpenAIEmbeddings"),
    ("anthropic", "Anthropic"),
    ("anthropic", "AsyncAnthropic"),
    ("deepgram", "DeepgramClient"),
    ("pinecone", "Pinecone"),
    ("firebase_admin", "initialize_app"),
    ("tiktoken", "encoding_for_model"),
    ("tiktoken", "get_encoding"),
    ("typesense", "Client"),
    ("pusher", "Client"),
    ("requests", "Session"),
    ("httpx", "Client"),
    ("httpx", "AsyncClient"),
    ("firestore", "Client"),
    ("firestore", "Firestore"),
    ("redis", "Redis"),
]

NETWORK_MODULES = {"requests", "httpx"}
NETWORK_VERBS = {"get", "post", "put", "patch", "delete", "head", "request"}
PRAGMA_RE = re.compile(r"#\s*noqa:\s*import-side-effect(?:\s*:\s*(.+))?", re.IGNORECASE)


def _attr_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    parts.reverse()
    return parts


def _collect_import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map locally-bound names to their fully-qualified dotted source.

    Tracks ``import a.b.c as x`` and ``from a.b import c as d`` so that an
    unqualified call like ``OpenAI()`` (from ``from openai import OpenAI``) is
    recognised as a side-effecting constructor.
    """
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or (alias.name.split(".")[0] if alias.name else alias.name)
                full = alias.name
                if bound and full:
                    aliases[bound] = full
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                full = f"{module}.{alias.name}" if module else alias.name
                aliases[bound] = full
    return aliases


def _has_future_annotations(tree: ast.Module) -> bool:
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(a.name == "annotations" for a in node.names)
        ):
            return True
    return False


def _resolve_chain(chain: list[str], aliases: dict[str, str]) -> list[str]:
    """Resolve the head of a dotted chain through import aliases."""
    if not chain:
        return chain
    head = chain[0]
    if head in aliases:
        return aliases[head].split(".") + chain[1:]
    return chain


def _ctor_matches(chain: list[str]) -> bool:
    if not chain:
        return False
    for prefix, attr in SIDE_EFFECT_CTORS:
        if chain[-1] != attr:
            continue
        pref_parts = prefix.split(".")
        if len(chain) >= len(pref_parts) + 1 and chain[: len(pref_parts)] == pref_parts:
            return True
        # bare name matching a known constructor attr called unqualified
        if len(chain) == 1 and prefix == attr:
            return True
    return False


def _is_os_environ_subscript(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
    )


def _is_network_call(chain: list[str]) -> bool:
    """True if ``chain`` is a top-level network call (module or alias-resolved).

    Accepts the (already alias-resolved) dotted chain so ``from requests import get;
    get(url)`` — where ``get`` resolves to ``requests.get`` — is also caught.
    """
    if len(chain) >= 2 and chain[0] in NETWORK_MODULES and chain[-1] in NETWORK_VERBS:
        return True
    # urllib.request.urlopen(...)
    if len(chain) >= 2 and chain[:2] == ["urllib", "request"] and chain[-1] == "urlopen":
        return True
    return False


def _record_offenders_in_expr(node: ast.AST, aliases: dict[str, str], out: list[tuple[int, str]]) -> None:
    """Walk an expression subtree, appending (lineno, reason) for any offender."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            chain = _attr_chain(sub.func)
            resolved = _resolve_chain(chain, aliases)
            if _ctor_matches(resolved):
                out.append((sub.lineno, f"import-time constructor: {'.'.join(chain)}"))
                continue
            if _is_network_call(resolved):
                out.append((sub.lineno, f"top-level network call: {'.'.join(resolved)}"))
                continue
            if isinstance(sub.func, ast.Name) and sub.func.id == "open":
                out.append((sub.lineno, "top-level open() call"))
                continue
        if isinstance(sub, ast.Subscript) and _is_os_environ_subscript(sub):
            out.append((sub.lineno, "os.environ[] subscript at module scope"))


def _function_annotation_exprs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    exprs: list[ast.AST] = []
    if node.returns is not None:
        exprs.append(node.returns)
    a = node.args
    for arg in list(getattr(a, "posonlyargs", [])) + list(a.args) + list(a.kwonlyargs):
        if arg.annotation is not None:
            exprs.append(arg.annotation)
    for arg in (a.vararg, a.kwarg):
        if arg is not None and arg.annotation is not None:
            exprs.append(arg.annotation)
    return exprs


def _record_import_scope_stmt(
    node: ast.stmt,
    aliases: dict[str, str],
    eval_annotations: bool,
    out: list[tuple[int, str]],
) -> None:
    """Scan one statement that executes during module import.

    Function bodies do not execute at import time, but their decorators/defaults (and
    annotations unless postponed) do. Class bodies *do* execute at import time, so
    recurse into them while still treating methods like functions.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for expr in node.decorator_list:
            _record_offenders_in_expr(expr, aliases, out)
        a = node.args
        default_exprs = list(a.defaults) + [d for d in (a.kw_defaults or []) if d is not None]
        for expr in default_exprs:
            _record_offenders_in_expr(expr, aliases, out)
        if eval_annotations:
            for expr in _function_annotation_exprs(node):
                _record_offenders_in_expr(expr, aliases, out)
        return

    if isinstance(node, ast.ClassDef):
        for expr in node.decorator_list:
            _record_offenders_in_expr(expr, aliases, out)
        for expr in node.bases:
            _record_offenders_in_expr(expr, aliases, out)
        for kw in node.keywords:
            _record_offenders_in_expr(kw.value, aliases, out)
        for stmt in node.body:
            _record_import_scope_stmt(stmt, aliases, eval_annotations, out)
        return

    if isinstance(node, ast.AnnAssign):
        # The assigned value executes at import/class-body time. The annotation
        # expression only executes when postponed annotations are not enabled.
        if node.value is not None:
            _record_offenders_in_expr(node.value, aliases, out)
        if eval_annotations:
            _record_offenders_in_expr(node.annotation, aliases, out)
        return

    _record_offenders_in_expr(node, aliases, out)


def _module_level_offenders(tree: ast.Module, source_lines: list[str]) -> list[tuple[int, str]]:
    """Return (lineno, reason) for module-scope import-time side effects.

    Decorator lists, default values, class bases/keywords and (when PEP 563 is not
    active) annotations all evaluate at import time, so they are scanned too.
    Class *bodies* also execute at import time (the class statement runs them when
    it defines the class), so class-level assignments/expressions are scanned as
    well — only function/method bodies are skipped (they run at call time).
    """
    out: list[tuple[int, str]] = []
    aliases = _collect_import_aliases(tree)
    eval_annotations = not _has_future_annotations(tree)

    for node in tree.body:
        _record_import_scope_stmt(node, aliases, eval_annotations, out)

    # Deduplicate by (lineno, reason); collapse multiple hits on same line.
    seen: set[tuple[int, str]] = set()
    deduped: list[tuple[int, str]] = []
    for ln, reason in out:
        key = (ln, reason)
        if key not in seen:
            seen.add(key)
            deduped.append((ln, reason))
    return deduped


def _has_pragma_with_reason(source_lines: list[str], lineno: int) -> bool:
    """A qualifying pragma must be on the offending line or the line above."""
    for cand in (lineno, lineno - 1):
        if 1 <= cand <= len(source_lines):
            m = PRAGMA_RE.search(source_lines[cand - 1])
            if m and (m.group(1) or "").strip():
                return True
    return False


def _load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return entries


# Directory names that must never be scanned: virtualenvs, vendored/built
# third-party code, caches, and dot-directories. The scanner polices backend
# production code only; site-packages (e.g. a local .openapi-venv) are full of
# import-time side effects that are irrelevant here and would drown the signal.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "site-packages",
        ".openapi-venv",
        "node_modules",
        "build",
        "dist",
    }
)


def _is_under_excluded_dir(rel: str) -> bool:
    parts = rel.split("/")
    for part in parts:
        if part in _EXCLUDED_DIR_NAMES or part.startswith("."):
            return True
    return False


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if rel.startswith("tests/") or rel.startswith("testing/"):
            continue
        if _is_under_excluded_dir(rel):
            continue
        files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(BACKEND_DIR))
    parser.add_argument("--files", help="path to a file listing repo-relative paths (changed-files mode)")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST))
    parser.add_argument("--check-allowlist-monotonic", metavar="BASE_REF")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    allowlist_path = Path(args.allowlist).resolve()
    allowlist = _load_allowlist(allowlist_path)

    if args.check_allowlist_monotonic:
        rc = _check_monotonic(allowlist_path, args.check_allowlist_monotonic)
        if rc != 0:
            return rc

    if args.files:
        files: list[Path] = []
        for raw in Path(args.files).read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            p = REPO_ROOT / raw
            if p.suffix == ".py" and p.exists():
                files.append(p)
    else:
        files = _candidate_files(root)

    violations: list[str] = []
    checked = 0
    for path in files:
        try:
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        if not rel.startswith("backend/"):
            continue
        if rel.startswith("backend/tests/") or rel.startswith("backend/testing/"):
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{rel}: SYNTAX ERROR {exc}")
            continue
        lines = text.splitlines()
        offenders = _module_level_offenders(tree, lines)
        if not offenders:
            checked += 1
            continue
        # Apply pragma suppression per offending line.
        unsuppressed = [(ln, reason) for (ln, reason) in offenders if not _has_pragma_with_reason(lines, ln)]
        if unsuppressed and rel not in allowlist:
            joined = "; ".join(f"L{ln} {reason}" for ln, reason in unsuppressed)
            violations.append(f"{rel}: {joined}")
        checked += 1

    if not args.quiet:
        print(f"Checked {checked} backend production file(s); {len(violations)} violation(s).")

    if violations:
        print("\nImport-time side effects are banned in backend production code.", file=sys.stderr)
        print("Defer resource construction into a lazy getter or app startup.", file=sys.stderr)
        print("See backend/docs/test_isolation.md (Tier 1) and PLAN.md P2.\n", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    return 0


def _check_monotonic(allowlist_path: Path, base_ref: str) -> int:
    """Fail if the allowlist grew relative to BASE_REF. Creation (absent at base) is allowed."""
    import subprocess

    rel = allowlist_path.relative_to(REPO_ROOT).as_posix()
    exists_at_base = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{base_ref}:{rel}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    if not exists_at_base:
        return 0

    out = subprocess.run(
        ["git", "show", f"{base_ref}:{rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    base_entries = {
        line.strip() for line in out.stdout.splitlines() if line.strip() and not line.strip().startswith("#")
    }
    current = _load_allowlist(allowlist_path)
    added = current - base_entries
    if added:
        print(f"FAIL: import-time-side-effect legacy allowlist grew relative to {base_ref}:", file=sys.stderr)
        for e in sorted(added):
            print(f"  + {e}", file=sys.stderr)
        print("The allowlist may only shrink. See .coordination/test-isolation/PLAN.md (P4).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
