#!/usr/bin/env python3
"""Dead-code ratchet: reject NEW unreachable/zero-importer files in four areas.

Areas and methods (ported from the validated 2026-09-03 prototype, see
omi-knowledge-base projects/monorepo-cleanup evidence 2026-09-03-deadcode-detector-benchmark.md):

- flutter: import-graph reachability from app/lib/main.dart (routing is
  widget-direct, so the import graph *is* reachability). gen/, l10n/,
  *.g.dart, *.gen.dart are intentional codegen surfaces and are excluded.
- backend: inbound-import buckets over backend/{utils,models,database,services,jobs}
  with four demotion passes before any dead claim: __init__-marker exemption
  while siblings live, __main__-guard entrypoint exemption, script-only
  bucketing (scripts/, migrations/ importers), and a name-mention verification
  pass (a dotted-path or file-path mention anywhere in non-test code demotes
  to manual review, never auto-dead).
- agent: TS graph from desktop/macos/agent/src/index.ts.
- windows: TS graph from the vite/electron entry set (main, kgWorker, preload,
  renderer html entries) with the @renderer alias resolved. Dynamic import(),
  new URL(), and string-spawned .js/.mjs siblings are edges. *.test.*/*.spec.*,
  .d.ts, and tests/ dirs are excluded (test-infra that still flags gets the
  allowlist, not an exclusion).

Trap catalogue encoded (each produced a false result until encoded):
  - `from pkg import mod` edges to pkg/mod.py, not just pkg/__init__.py.
  - relative imports inside __init__.py resolve against the containing package.
  - `from x import y as z` strips the alias or the edge is lost.
  - dotted-attribute / string-mention usage demotes to manual review.
  - dynamic `import('./x')` is an edge.
  - string-spawned siblings (`join(__dirname, "x.js")`, worker entries) are
    edges without imports.
  - `new URL('./x.ts', import.meta.url)` worklet/aux entries are edges.
  - bundler aliases must resolve or whole renderer trees orphan.
  - sources are read with errors="replace": non-ASCII must never silently
    truncate a scan.

Ratchet contract (monorepo rules: deterministic, hermetic, actionable):
- `--check` (default) fails only on files that are newly dead relative to the
  area baseline + allowlist, and tells the developer the exact fix: delete the
  file, or add it to the area allowlist with a reason.
- `--update-baseline` rewrites the baseline from the current state (deletions
  shrink it; the allowlist is never touched or auto-pruned).
- No network, no git history: pure filesystem analysis of the checkout. Files
  git ignores are not part of that checkout — CI never sees them — so they are
  excluded before reachability runs (see `_git_ignored_paths`).
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR_REL = ".github/scripts/dead_code"
AREAS = ("flutter", "backend", "agent", "windows")

FIX_HINT = "delete it, or add it to {allowlist} with a reason"


@dataclass(frozen=True)
class AreaScan:
    """Result of scanning one area. Paths are repo-relative POSIX."""

    area: str
    dead: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    error: str | None = None


# ---------------------------------------------------------------------------
# gitignore
# ---------------------------------------------------------------------------

def _git_ignored_paths(root: Path) -> set[Path]:
    """Absolute paths git ignores under `root`.

    The scan walks the working tree, but the contract is about the tree CI
    checks out. A developer machine also carries gitignored siblings — generated
    config like `app/lib/firebase_options_dev.dart`, build output, `.claude/`
    worktrees — none of which exist in CI. Reporting them as newly dead fails
    the gate only locally, which reads as the checker being broken.

    Mirrors `_git_ignored_paths` in backend/scripts/generate_plan_catalog.py,
    added for the same reason in #12476.

    Returns an empty set when git cannot answer, leaving the pure-filesystem
    behaviour unchanged.
    """
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--directory",
                "-z",
            ],
            capture_output=True,
            text=True,
            # A filename whose bytes are invalid for the locale must degrade to the
            # filesystem fallback, not raise out of a checker that has to keep running.
            errors="surrogateescape",
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return set()
    return {(root / entry).resolve() for entry in completed.stdout.split("\0") if entry}


def _ignore_predicate(root: Path):
    """Return `is_ignored(path)`; git is consulted once per scan."""
    ignored = _git_ignored_paths(root)
    if not ignored:
        return lambda path: False
    resolved_root = root.resolve()

    def is_ignored(path: Path) -> bool:
        # `--directory` collapses an ignored directory to one entry, so a file
        # inside it matches through an ancestor rather than directly.
        current = path.resolve()
        while True:
            if current in ignored:
                return True
            if current == resolved_root:
                return False
            parent = current.parent
            if parent == current:
                return False
            current = parent

    return is_ignored


# ---------------------------------------------------------------------------
# flutter
# ---------------------------------------------------------------------------

FLUTTER_LIB_REL = "app/lib"
FLUTTER_ENTRY = "main.dart"
FLUTTER_SKIP = re.compile(r"(?:^|/)(gen|l10n)(?:/|$)|\.g\.dart$|\.gen\.dart$")
DART_STMT = re.compile(r"""^[ \t]*(?:import|export|part)[ \t]+['"]([^'"]+)['"]""", re.M)
DART_COND = re.compile(r"""\bif\s*\([^)]*\)\s*['"]([^'"]+)['"]""")
DART_PACKAGE_PREFIX = "package:omi/"


def scan_flutter(root: Path) -> AreaScan:
    lib = root / FLUTTER_LIB_REL
    entry = lib / FLUTTER_ENTRY
    if not entry.is_file():
        return AreaScan("flutter", error=f"flutter entry {FLUTTER_LIB_REL}/{FLUTTER_ENTRY} is missing; nothing to anchor reachability")
    is_ignored = _ignore_predicate(root)
    if is_ignored(entry):
        # Reachability is seeded from this entry below. Excluding it from `files`
        # while still walking from it would strand every other file and report
        # the whole area dead, so fail closed the way a missing entry does.
        return AreaScan("flutter", error=f"flutter entry {FLUTTER_LIB_REL}/{FLUTTER_ENTRY} is gitignored; nothing to anchor reachability")
    files: dict[str, Path] = {}
    for path in lib.rglob("*.dart"):
        rel = path.relative_to(lib).as_posix()
        if not FLUTTER_SKIP.search(rel) and not is_ignored(path):
            files[rel] = path
    edges: dict[str, set[str]] = {}
    for rel, path in files.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        targets: set[str] = set()
        for spec in DART_STMT.findall(text) + DART_COND.findall(text):
            target = None
            if spec.startswith(DART_PACKAGE_PREFIX):
                target = spec[len(DART_PACKAGE_PREFIX):]
            elif not spec.startswith(("dart:", "package:")):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
            if target and target in files:
                targets.add(target)
        edges[rel] = targets
    seen, stack = {FLUTTER_ENTRY}, [FLUTTER_ENTRY]
    while stack:
        for target in edges.get(stack.pop(), ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    dead = sorted(f"{FLUTTER_LIB_REL}/{rel}" for rel in set(files) - seen)
    return AreaScan("flutter", dead=tuple(dead))


# ---------------------------------------------------------------------------
# backend
# ---------------------------------------------------------------------------

BACKEND_REL = "backend"
BACKEND_LIB_PREFIXES = ("utils/", "models/", "database/", "services/", "jobs/")
BACKEND_SCRIPT_PREFIXES = ("scripts/", "migrations/")
BACKEND_TEST_PREFIXES = ("tests/", "testing/")
PY_STMT = re.compile(
    r"^[ \t]*(?:from[ \t]+([\.\w]+)[ \t]+import[ \t]+\(?\s*([\w*, \t\r\n]+?)\s*\)?[ \t]*(?:#.*)?$"
    r"|import[ \t]+([\w., \t]+?)[ \t]*(?:#.*)?$)",
    re.M,
)


def scan_backend(root: Path) -> AreaScan:
    backend = root / BACKEND_REL
    if not backend.is_dir():
        return AreaScan("backend", error="backend/ is missing; nothing to scan")
    is_ignored = _ignore_predicate(root)
    files: dict[str, Path] = {}
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if "__pycache__" in rel or rel.startswith(BACKEND_TEST_PREFIXES):
            continue
        if is_ignored(path):
            continue
        files[rel] = path
    modmap: dict[str, str] = {}
    for rel in files:
        parts = rel[:-3].split("/")
        dotted = ".".join(parts[:-1]) if parts[-1] == "__init__" else ".".join(parts)
        modmap[dotted] = rel
    texts = {rel: path.read_text(encoding="utf-8", errors="replace") for rel, path in files.items()}
    inbound: dict[str, set[str]] = defaultdict(set)
    script_inbound: dict[str, set[str]] = defaultdict(set)

    def resolve(base: str, names: list[str], rel: str) -> set[str]:
        if base.startswith("."):
            level = len(base) - len(base.lstrip("."))
            leaf = base.lstrip(".")
            pkg = rel[:-3].split("/")
            # Containing package = dirname in both cases ('__init__.py' is the package itself).
            ctx = pkg[:-1]
            ctx = ctx[: len(ctx) - (level - 1)] if level > 1 else ctx
            base_abs = ".".join([*ctx, *leaf.split(".")]) if leaf else ".".join(ctx)
        else:
            base_abs = base
        out: set[str] = set()
        for candidate in [base_abs] + [f"{base_abs}.{n.split(' as ')[0].strip()}" for n in names
                                       if n.strip() and n.strip() != "*"]:
            if candidate in modmap:
                out.add(modmap[candidate])
        return out

    for rel, text in texts.items():
        is_script = rel.startswith(BACKEND_SCRIPT_PREFIXES)
        for match in PY_STMT.finditer(text):
            if match.group(1):
                mods = resolve(
                    match.group(1),
                    match.group(2).replace("(", "").replace(")", "").split(","),
                    rel,
                )
            else:
                mods = {candidate.strip().split(" as ")[0] for candidate in match.group(3).split(",")}
                mods = {modmap[c] for c in mods if c in modmap}
            for target in mods:
                (script_inbound if is_script else inbound)[target].add(rel)

    candidates = [
        rel
        for rel in files
        if rel.startswith(BACKEND_LIB_PREFIXES) and not inbound.get(rel) and not script_inbound.get(rel)
    ]
    script_only = [
        rel for rel in files
        if rel.startswith(BACKEND_LIB_PREFIXES) and not inbound.get(rel) and script_inbound.get(rel)
    ]

    entrypoints = [
        rel for rel in candidates
        if "__name__ == '__main__'" in texts[rel] or '__name__ == "__main__"' in texts[rel]
    ]
    candidates = [rel for rel in candidates if rel not in entrypoints]

    def sibling_alive(rel: str) -> bool:
        parent = posixpath.dirname(rel)
        return any(
            inbound.get(sibling) or script_inbound.get(sibling)
            for sibling in files
            if posixpath.dirname(sibling) == parent and sibling != rel
        )

    init_markers = [rel for rel in candidates if rel.endswith("__init__.py") and sibling_alive(rel)]
    candidates = [rel for rel in candidates if rel not in init_markers]

    dead, mentioned = [], []
    for rel in candidates:
        dotted = rel[:-len("__init__.py")].replace("/", ".").rstrip(".") if rel.endswith("__init__.py") \
            else rel[:-3].replace("/", ".")
        pattern = re.compile(r"\b" + re.escape(dotted) + r"\b|" + re.escape(rel))
        hit = any(
            pattern.search(texts[other])
            for other in texts
            if other != rel and not other.startswith(BACKEND_TEST_PREFIXES)
        )
        (mentioned if hit else dead).append(rel)

    dead_repo = sorted(f"{BACKEND_REL}/{rel}" for rel in dead)
    notes = (
        f"demoted to manual-review buckets, not auto-dead: mentioned-only={len(mentioned)} "
        f"script-only={len(script_only)} entrypoint-class={len(entrypoints)} init-markers={len(init_markers)}",
    )
    return AreaScan("backend", dead=tuple(dead_repo), notes=notes)


# ---------------------------------------------------------------------------
# shared TS graph (agent + windows)
# ---------------------------------------------------------------------------

TS_SUFFIXES = (".ts", ".tsx", ".mjs")
# public/ holds runtime-URL assets (e.g. postinstall-copied VAD wasm bundles that
# are gitignored on dev machines); they are loaded by URL, never imported.
TS_SKIP = re.compile(r"(?:^|/)(tests|test|public|assets)(?:/|$)|\.d\.ts$|\.(?:test|spec)\.[cm]?[jt]sx?$")
TS_ASSET_SUFFIXES = (".css", ".png", ".svg", ".html")
JS_SIBLING_REF = re.compile(r"""['"]([\w./-]+)\.(?:js|mjs)['"]""")
NEW_URL_REF = re.compile(r"""new URL\(\s*['"]([^'"]+)['"]""")


def _import_patterns(aliases: dict[str, str]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Import/dynamic-import regexes matching relative and alias-prefixed specs.

    The prototype only matched "."-prefixed specs, so its alias resolution was
    effectively unreachable code; here alias prefixes are surfaced explicitly so
    `@renderer/x` edges resolve (today usage is zero, so the dead set is
    unchanged — this is future-proofing, and bare package specifiers are still
    ignored).
    """
    spec_alt = r"\.[^'\"]+"
    if aliases:
        spec_alt += "|" + "|".join(re.escape(alias) + r"(?:/[^'\"]*)?" for alias in aliases)
    static = re.compile(f"""(?:from|import)\\s*['"]({spec_alt})['"]""")
    dynamic = re.compile(f"""import\\(\\s*['"]({spec_alt})['"]""")
    return static, dynamic


def scan_ts(root: Path, area: str, area_root_rel: str, entry_specs: list[str],
            aliases: dict[str, str] | None = None) -> AreaScan:
    aliases = aliases or {}
    base = root / area_root_rel / "src"
    if not base.is_dir():
        return AreaScan(area, error=f"{area_root_rel}/src is missing; nothing to scan")
    is_ignored = _ignore_predicate(root)
    files: dict[str, Path] = {}
    for path in base.rglob("*"):
        if path.suffix in TS_SUFFIXES and path.is_file():
            rel = path.relative_to(base).as_posix()
            if not TS_SKIP.search(rel) and not is_ignored(path):
                files[rel] = path
    static_imp, dynamic_imp = _import_patterns(aliases)
    # Deterministic winner: rglob order is filesystem-dependent, so with bare-stem
    # collisions ("index" for main/index.ts, preload/index.ts,
    # main/codingAgent/pi-mono-extension/index.ts, ...) this last-writer-wins map
    # used to flip which file a sibling ref resolves to between machines — silently
    # flipping reachability verdicts (first seen as a CI-only windows-area failure).
    # Sorted input makes the lexicographically-last rel the stable winner.
    stems = {posixpath.splitext(rel)[0].rsplit("/", 1)[-1]: rel for rel in sorted(files)}
    edges: dict[str, set[str]] = defaultdict(set)

    def resolve(spec: str, importer: str) -> str | None:
        base_dir = posixpath.dirname(importer)
        for prefix, mapped in aliases.items():
            if spec == prefix or spec.startswith(prefix + "/"):
                # Alias-mapped paths are already src-relative; TS imports omit
                # extensions, so the extension candidates below still apply.
                spec = posixpath.normpath(posixpath.join(mapped, spec[len(prefix):].lstrip("/")))
                base_dir = ""
                break
        for candidate in (
            spec,
            spec + ".ts",
            spec + ".tsx",
            spec + ".mjs",
            posixpath.join(spec, "index.ts"),
            posixpath.join(spec, "index.tsx"),
        ):
            target = posixpath.normpath(posixpath.join(base_dir, candidate))
            if target in files:
                return target
        return None

    for rel, path in files.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        for spec in static_imp.findall(text) + dynamic_imp.findall(text) + NEW_URL_REF.findall(text):
            spec = spec.split("?")[0]
            if spec.endswith(TS_ASSET_SUFFIXES):
                continue
            target = resolve(spec, rel)
            if target:
                edges[rel].add(target)
        for ref in JS_SIBLING_REF.findall(text):
            target = stems.get(posixpath.splitext(posixpath.basename(ref))[0])
            if target and target != rel:
                edges[rel].add(target)

    entry_set = {spec for spec in entry_specs if spec in files}
    missing = [spec for spec in entry_specs if spec not in files]
    if not entry_set:
        return AreaScan(area, error=(
            f"none of the {area} entry files exist under {area_root_rel}/src "
            f"({', '.join(sorted(missing))}); refusing to flag everything as unreachable"
        ))
    warnings = tuple(f"{area} entry {area_root_rel}/src/{spec} is missing" for spec in sorted(missing))
    seen, stack = set(entry_set), list(entry_set)
    while stack:
        for target in edges.get(stack.pop(), ()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    dead = sorted(f"{area_root_rel}/src/{rel}" for rel in set(files) - seen)
    return AreaScan(area, dead=tuple(dead), warnings=warnings)


def scan_agent(root: Path) -> AreaScan:
    return scan_ts(root, "agent", "desktop/macos/agent", ["index.ts"])


def windows_entry_specs(root: Path) -> list[str]:
    specs = ["main/index.ts", "main/ipc/kgWorker.ts"]
    preload = root / "desktop/windows/src/preload"
    if preload.is_dir():
        for path in sorted(preload.glob("*.ts")):
            if not path.name.endswith(".d.ts"):
                specs.append(f"preload/{path.name}")
    for stem in ("main", "captureEntry", "glow", "insightToast"):
        for suffix in (".tsx", ".ts"):
            if (root / f"desktop/windows/src/renderer/src/{stem}{suffix}").is_file():
                specs.append(f"renderer/src/{stem}{suffix}")
                break
    return specs


def scan_windows(root: Path) -> AreaScan:
    return scan_ts(
        root,
        "windows",
        "desktop/windows",
        windows_entry_specs(root),
        aliases={"@renderer": "renderer/src"},
    )


SCANNERS = {
    "flutter": scan_flutter,
    "backend": scan_backend,
    "agent": scan_agent,
    "windows": scan_windows,
}


# ---------------------------------------------------------------------------
# baseline + allowlist
# ---------------------------------------------------------------------------

def baseline_path(root: Path, area: str) -> Path:
    return root / DATA_DIR_REL / f"{area}.baseline.json"


def allowlist_path(root: Path, area: str) -> Path:
    return root / DATA_DIR_REL / f"{area}.allowlist.json"


def load_baseline(root: Path, area: str) -> tuple[set[str], tuple[str, ...]]:
    path = baseline_path(root, area)
    if not path.is_file():
        return set(), (f"no baseline at {DATA_DIR_REL}/{area}.baseline.json; "
                       f"run --update-baseline --area {area} to seed the ratchet floor",)
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("unreachable")
    if not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries):
        raise SystemExit(f"error: {path} must be an object with an 'unreachable' list of path strings")
    return set(entries), ()


def load_allowlist(root: Path, area: str) -> tuple[set[str], list[str]]:
    """Return (allowed paths, schema errors). Entries require path AND reason."""
    path = allowlist_path(root, area)
    if not path.is_file():
        return set(), []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return set(), [f"{path} is not valid JSON: {exc}"]
    entries = data.get("entries")
    if not isinstance(entries, list):
        return set(), [f"{path} must be an object with an 'entries' list"]
    allowed: set[str] = set()
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{path}: entries[{index}] must be an object with 'path' and 'reason'")
            continue
        allow_path = entry.get("path")
        reason = entry.get("reason")
        if not allow_path or not isinstance(allow_path, str):
            errors.append(f"{path}: entries[{index}] is missing a non-empty 'path'")
        if not reason or not isinstance(reason, str):
            errors.append(f"{path}: entry '{allow_path}' is missing a non-empty 'reason'; "
                          "state why the file is intentionally kept")
        if isinstance(allow_path, str) and allow_path in allowed:
            errors.append(f"{path}: duplicate entry '{allow_path}'")
        if isinstance(allow_path, str):
            allowed.add(allow_path)
    return allowed, errors


def write_baseline(root: Path, area: str, dead: set[str]) -> None:
    path = baseline_path(root, area)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "area": area,
        "comment": (
            "Ratchet floor of unreachable/zero-importer files tolerated at seed time. "
            "Shrink by deleting files and re-running "
            f"check_dead_code.py --update-baseline --area {area}; new entries fail CI."
        ),
        "unreachable": sorted(dead),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------

def scan_area(root: Path, area: str) -> AreaScan:
    return SCANNERS[area](root)


def check_area(root: Path, area: str) -> tuple[list[str], list[str], AreaScan]:
    """Return (failures, warnings, scan) for one area in check mode."""
    scan = scan_area(root, area)
    warnings = list(scan.warnings)
    if scan.error:
        return [scan.error], warnings, scan
    floor, floor_warnings = load_baseline(root, area)
    warnings.extend(floor_warnings)
    allowed, allow_errors = load_allowlist(root, area)
    allowed_stale = sorted(allowed - set(scan.dead))
    if allowed_stale:
        warnings.append(
            f"{area}: allowlist entries no longer dead (remove them or leave for review): "
            + ", ".join(allowed_stale)
        )
    failures = list(allow_errors)
    if failures:
        return failures, warnings, scan
    new_dead = sorted(set(scan.dead) - floor - allowed)
    for path in new_dead:
        hint = FIX_HINT.format(allowlist=posixpath.join(DATA_DIR_REL, f"{area}.allowlist.json"))
        failures.append(f"{path}\n      fix: {hint}")
    prunable = sorted(floor - set(scan.dead))
    if prunable:
        warnings.append(
            f"{area}: {len(prunable)} baseline entr{'y is' if len(prunable) == 1 else 'ies are'} "
            f"no longer dead (deleted or re-imported); shrink the floor with "
            f"--update-baseline --area {area}"
        )
    return failures, warnings, scan


def update_baseline_area(root: Path, area: str) -> tuple[list[str], list[str], AreaScan]:
    scan = scan_area(root, area)
    warnings = list(scan.warnings)
    if scan.error:
        return [scan.error], warnings, scan
    allowed, allow_errors = load_allowlist(root, area)
    if allow_errors:
        # The allowlist is never auto-edited: a broken entry must be fixed by hand.
        return allow_errors, warnings, scan
    previous, _ = load_baseline(root, area)
    floor = set(scan.dead) - allowed
    write_baseline(root, area, floor)
    pruned = len(previous - floor)
    kept = len(previous & floor)
    warnings.append(
        f"{area}: baseline now {len(floor)} file(s) ({kept} carried over, {pruned} pruned, "
        f"{len(set(scan.dead) & allowed)} covered by the allowlist, which is never auto-pruned)"
    )
    return [], warnings, scan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--area", choices=AREAS, help="scan one area instead of all four")
    parser.add_argument("--update-baseline", action="store_true",
                        help="rewrite the baseline floor(s) from the current state; "
                             "allowlist files are validated but never modified")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="repository root to scan (default: this checkout; for hermetic tests)")
    args = parser.parse_args()

    root = args.root.resolve()
    areas = (args.area,) if args.area else AREAS
    exit_code = 0
    for area in areas:
        if args.update_baseline:
            failures, warnings, scan = update_baseline_area(root, area)
        else:
            failures, warnings, scan = check_area(root, area)
        for warning in warnings:
            print(f"dead-code[{area}]: note: {warning}")
        for note in scan.notes:
            print(f"dead-code[{area}]: {note}")
        if failures:
            exit_code = 1
            print(f"dead-code[{area}]: FAILED, {len(failures)} problem(s):")
            for failure in failures:
                print(f"  - {failure}")
        elif not args.update_baseline:
            print(f"dead-code[{area}]: ok ({len(scan.dead)} unreachable file(s) at the baseline/allowlist floor)")
    if exit_code:
        print("dead-code check failed; new dead code must be deleted or explicitly allowlisted "
              "with a reason (see .github/scripts/dead_code/)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
