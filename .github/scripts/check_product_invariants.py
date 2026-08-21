#!/usr/bin/env python3
"""Require PRs that touch locked product-invariant paths to name the invariant ID.

Parses docs/product/invariants/*.md (except README). For each locked invariant
with path globs, if any changed file matches a glob and the invariant's PR rule
requires naming the ID, the PR body must contain that ID (e.g. INV-CHAT-1).

Stdlib-only. Wired from .github/workflows/repo-checks.yml on pull_request.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

INVARIANT_DIR = Path("docs/product/invariants")
ID_RE = re.compile(r"^#\s+(INV-[A-Z0-9]+(?:-\*|(?:-\d+)+))", re.MULTILINE)
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\w+)", re.MULTILINE | re.IGNORECASE)
# A glob may carry a trailing note, e.g. ``path/**`` (retired: ...).
GLOB_LINE_RE = re.compile(r"^-\s+`([^`]+)`(?:\s+\S.*)?$", re.MULTILINE)
SKIP_NAMING_RE = re.compile(
    r"Do\s+\*\*not\*\*\s+require\s+naming|do\s+not\s+require\s+naming",
    re.IGNORECASE,
)
# Match an invariant ID as a distinct token so INV-CHAT-1 does not satisfy
# a check for INV-CHAT-10 (or vice-versa). Word boundaries via lookarounds
# because `-` is not a word char, so \b does not anchor the trailing digits.
ID_TOKEN_RE_TMPL = r"(?<![A-Z0-9-]){id}(?![A-Z0-9-])"
# HTML comments in the PR template contain example IDs like INV-CHAT-1;
# strip them before matching so untouched template text does not auto-pass.
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Any bullet under "## Path globs". A glob that is not backtick-wrapped is
# silently ignored by GLOB_LINE_RE, which quietly narrows enforcement, so the
# audit treats a non-parsing bullet as an error rather than a comment.
GLOB_BULLET_RE = re.compile(r"^-\s+(.*)$")
# Guard-test entries name repo paths, either as `path` or [`path`](relative).
GUARD_PATH_RE = re.compile(r"`([^`]+)`")
CHECK_SCRIPT_RE = re.compile(r"^\.github/scripts/[\w.-]+\.py$")
README_ROW_RE = re.compile(r"^\|\s*(INV-[A-Z0-9*-]+)\s*\|.*\|\s*\[([^\]]+)\]", re.MULTILINE)
# A glob rooted at one of these covers a whole application tree. Citation on
# such a glob taxes every PR in that tree, which is how a citation becomes
# ritual; those invariants must let their guard carry the floor instead
# (the INV-UI-1 pattern: enforce statically, opt out of naming).
APP_ROOTS = frozenset(
    {
        "backend",
        "app",
        "app/lib",
        "desktop",
        "desktop/macos",
        "desktop/macos/Desktop",
        "desktop/macos/Desktop/Sources",
        "desktop/windows",
        "desktop/windows/src",
        "web",
        ".github",
        ".github/workflows",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-files",
        required=True,
        help="Path to a file listing changed paths (one per line).",
    )
    parser.add_argument(
        "--pr-body",
        default="",
        help="PR body text (or path via --pr-body-file).",
    )
    parser.add_argument(
        "--pr-body-file",
        default=None,
        help="Optional file containing the PR body.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (default: cwd).",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print matched invariants and exit 0.",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Print a paste-ready 'Product invariants affected' markdown block and exit 0.",
    )
    return parser.parse_args()


def format_suggest_block(hits: list[dict]) -> str:
    """Return a paste-ready PR-body section for the required invariant IDs."""
    lines = ["## Product invariants affected", ""]
    if not hits:
        lines.append("none")
    else:
        for hit in hits:
            lines.append(f"- {hit['id']}")
    lines.append("")
    return "\n".join(lines)


def format_invariant_briefing(hits: list[dict]) -> str:
    """Print what each matched invariant actually requires.

    The citation itself is cheap to satisfy — paste the ID and the check goes
    green. Its durable value is routing the rule into the context of whoever
    (or whatever) is editing these files, so the rule travels with the failure
    rather than sitting in a doc nobody opened.
    """
    blocks: list[str] = []
    for hit in hits:
        lines = [f"{hit['id']}  ({hit['path']})"]
        if hit.get("statement"):
            lines.append(f"  Statement: {hit['statement']}")
        must_not = hit.get("must_not", [])
        if must_not:
            lines.append(f"  MUST NOT ({len(must_not)}):")
            for bullet in must_not:
                lines.append(f"    - {bullet}")
        by_glob = hit.get("matched_by_glob") or {}
        if by_glob:
            lines.append("  Why it applies:")
            for glob in sorted(by_glob):
                files = by_glob[glob]
                lines.append(f"    `{glob}` matched {len(files)} changed file(s):")
                for path in files[:10]:
                    lines.append(f"      - {path}")
                if len(files) > 10:
                    lines.append(f"      … and {len(files) - 10} more")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def load_pr_body(args: argparse.Namespace) -> str:
    if args.pr_body_file:
        return Path(args.pr_body_file).read_text(encoding="utf-8")
    return args.pr_body or ""


def pr_body_cites_id(inv_id: str, pr_body: str) -> bool:
    """True if the PR body names inv_id as a distinct token.

    Strips HTML comments first so the PR template's example IDs do not
    auto-satisfy the check. Uses lookaround boundaries because ``-`` is not
    a word character, so ``\\b`` would not anchor the trailing digits.
    """
    cleaned = HTML_COMMENT_RE.sub("", pr_body)
    token_re = re.compile(ID_TOKEN_RE_TMPL.format(id=re.escape(inv_id)))
    return token_re.search(cleaned) is not None


def parse_invariant(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    id_match = ID_RE.search(text)
    if not id_match:
        return None
    status_match = STATUS_RE.search(text)
    status = (status_match.group(1).lower() if status_match else "proposed")
    # Path globs section only
    globs: list[str] = []
    unparsed_globs: list[str] = []
    in_globs = False
    for line in text.splitlines():
        if line.strip().lower().startswith("## path globs"):
            in_globs = True
            continue
        if in_globs and line.startswith("## "):
            break
        if in_globs:
            stripped = line.strip()
            m = GLOB_LINE_RE.match(stripped)
            if m:
                globs.append(m.group(1))
            elif GLOB_BULLET_RE.match(stripped):
                unparsed_globs.append(stripped)
    return {
        "id": id_match.group(1),
        "status": status,
        "globs": globs,
        "unparsed_globs": unparsed_globs,
        "guard_paths": section_backtick_paths(text, "guard tests"),
        "statement": extract_statement(text),
        "must_not": extract_section_bullets(text, "must not"),
        "require_naming": not bool(SKIP_NAMING_RE.search(text)),
        "path": str(path),
    }


def _section(text: str, heading: str) -> list[str]:
    """Return the lines of a '## <heading>' section, case-insensitively."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip().lower().startswith(f"## {heading}"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            lines.append(line)
    return lines


def section_backtick_paths(text: str, heading: str) -> list[str]:
    """Repo paths named in a section, whether bare `path` or [`path`](link)."""
    paths: list[str] = []
    for line in _section(text, heading):
        for token in GUARD_PATH_RE.findall(line):
            if "/" in token and "." in token.rsplit("/", 1)[-1]:
                paths.append(token)
    return paths


def extract_statement(text: str) -> str:
    match = re.search(r"^\*\*Statement:\*\*\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_section_bullets(text: str, heading: str) -> list[str]:
    bullets: list[str] = []
    for line in _section(text, heading):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        elif bullets and stripped:
            bullets[-1] = f"{bullets[-1]} {stripped}"
    return bullets


def load_locked_invariants(root: Path) -> list[dict]:
    directory = root / INVARIANT_DIR
    if not directory.is_dir():
        raise SystemExit(f"FAIL: missing invariant registry at {directory}")
    invariants: list[dict] = []
    for path in sorted(directory.glob("*.md")):
        if path.name.upper() == "README.MD":
            continue
        parsed = parse_invariant(path)
        if not parsed:
            # Fail-closed: a malformed invariant doc should not silently
            # disable enforcement. Surface it so formatting drift is caught.
            raise SystemExit(
                f"FAIL: could not parse invariant ID from {path.name}.\n"
                f"Expected a '# INV-XXX-N: Title' header. Fix the doc so "
                f"enforcement is not silently skipped."
            )
        if parsed["status"] != "locked":
            continue
        if not parsed["globs"]:
            continue
        invariants.append(parsed)
    return invariants


def parse_all_invariants(root: Path) -> list[dict]:
    directory = root / INVARIANT_DIR
    if not directory.is_dir():
        raise SystemExit(f"FAIL: missing invariant registry at {directory}")
    parsed: list[dict] = []
    for path in sorted(directory.glob("*.md")):
        if path.name.upper() == "README.MD":
            continue
        entry = parse_invariant(path)
        if not entry:
            raise SystemExit(
                f"FAIL: could not parse invariant ID from {path.name}.\n"
                f"Expected a '# INV-XXX-N: Title' header. Fix the doc so "
                f"enforcement is not silently skipped."
            )
        parsed.append(entry)
    return parsed


def manifest_referenced_scripts(root: Path) -> set[str]:
    """Every path mentioned in the checks manifest, read as text.

    Deliberately not a YAML parse: a script is 'wired' if the manifest names it
    at all, whether as a command or a trigger, and this file must keep working
    without PyYAML.
    """
    manifest = root / ".github/checks-manifest.yaml"
    if not manifest.is_file():
        return set()
    text = manifest.read_text(encoding="utf-8")
    return {match for match in re.findall(r"[\w./-]+\.py", text)}


def whole_tree_globs(globs: list[str]) -> list[str]:
    hits = []
    for glob in globs:
        if glob.endswith("/**") and glob[: -len("/**")] in APP_ROOTS:
            hits.append(glob)
    return hits


def audit_registry(root: Path) -> list[str]:
    """Standing checks on the registry itself.

    Every claim a doc makes is verified continuously, rather than once at
    promotion time. A guard test deleted next month fails here the same day.
    """
    problems: list[str] = []
    invariants = parse_all_invariants(root)
    scripts = manifest_referenced_scripts(root)

    readme = root / INVARIANT_DIR / "README.md"
    indexed = dict(README_ROW_RE.findall(readme.read_text(encoding="utf-8"))) if readme.is_file() else {}

    for inv in invariants:
        name = Path(inv["path"]).name
        for bullet in inv["unparsed_globs"]:
            problems.append(
                f"{name}: path-glob bullet is not backtick-wrapped so it is silently ignored: {bullet}"
            )
        if inv["id"] not in indexed:
            problems.append(f"{name}: {inv['id']} is missing from the README index table")
        elif not (root / INVARIANT_DIR / indexed[inv["id"]]).is_file():
            problems.append(f"README index row for {inv['id']} points at a missing doc: {indexed[inv['id']]}")

        if inv["status"] != "locked":
            continue

        for guard in inv["guard_paths"]:
            # A guard may be named as a pytest node id (file.py::TestCase).
            guard_file = guard.split("::", 1)[0]
            if not (root / guard_file).exists():
                problems.append(f"{name}: {inv['id']} is locked but names a guard that does not exist: {guard_file}")
            elif CHECK_SCRIPT_RE.match(guard_file) and guard_file not in scripts:
                problems.append(
                    f"{name}: {inv['id']} names guard script {guard_file}, which no checks-manifest entry runs"
                )
        if inv["require_naming"]:
            for glob in whole_tree_globs(inv["globs"]):
                problems.append(
                    f"{name}: {inv['id']} requires citation on the whole-tree glob `{glob}`, which taxes every PR "
                    f"in that tree. Let the guard carry the floor and opt out of naming (the INV-UI-1 pattern)."
                )

    for inv_id, doc in indexed.items():
        if not any(entry["id"] == inv_id for entry in invariants):
            problems.append(f"README index lists {inv_id} ({doc}) with no matching doc in the registry")

    return problems


def path_matches(path: str, pattern: str) -> bool:
    """Match registry globs. `**` matches zero or more path segments (gitignore-like)."""
    normalized = pattern.rstrip("/")
    if normalized.endswith("/**") and "*" not in normalized[: -len("/**")]:
        prefix = normalized[: -len("/**")]
        return path == prefix or path.startswith(prefix + "/")

    if "**" in pattern:
        # Translate gitignore-like ** : `**/` matches zero or more segments.
        escaped = re.escape(pattern)
        escaped = escaped.replace(r"\*\*/", "\0DOUBLESTARSLASH\0")
        escaped = escaped.replace(r"\*\*", "\0DOUBLESTAR\0")
        escaped = escaped.replace(r"\*", "[^/]*")
        escaped = escaped.replace("\0DOUBLESTARSLASH\0", "(?:.*/)?")
        escaped = escaped.replace("\0DOUBLESTAR\0", ".*")
        return re.fullmatch(escaped, path) is not None

    if "*" in pattern or "?" in pattern or "[" in pattern:
        return fnmatch.fnmatch(path, pattern)
    return path == pattern or path.startswith(pattern.rstrip("/") + "/")


def matched_invariants(changed: list[str], invariants: list[dict]) -> list[dict]:
    hits: list[dict] = []
    for inv in invariants:
        if not inv["require_naming"]:
            continue
        by_glob: dict[str, list[str]] = {}
        matching: list[str] = []
        for path in changed:
            # Attribute to every glob that caught it: when a file matches two
            # globs, which one is "responsible" is not a question with an answer,
            # and reporting only the first hides why a rule applies.
            caught = [g for g in inv["globs"] if path_matches(path, g)]
            if not caught:
                continue
            matching.append(path)
            for glob in caught:
                by_glob.setdefault(glob, []).append(path)
        if matching:
            hits.append({**inv, "matched_files": matching, "matched_by_glob": by_glob})
    return hits


def glob_breadth(root: Path, globs: list[str]) -> dict[str, int]:
    """How many tracked files each glob covers — i.e. how often it will fire.

    Reported rather than enforced: breadth changes as the tree grows, and a
    threshold that fails a PR because an unrelated directory got bigger is the
    kind of wall-clock-shaped gate this registry is trying to get away from.
    """
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {}
    return {glob: sum(1 for f in tracked if path_matches(f, glob)) for glob in globs}


def missing_invariant_hits(hits: list[dict], pr_body: str) -> list[dict]:
    still_missing: list[dict] = []
    for hit in hits:
        inv_id = hit["id"]
        if pr_body_cites_id(inv_id, pr_body):
            continue
        # INV-AGENT-* : accept INV-AGENT-* literally, INV-AGENT, or control-plane doc ref
        if inv_id.endswith("-*"):
            prefix = inv_id[:-2]  # INV-AGENT
            if pr_body_cites_id(prefix, pr_body) or pr_body_cites_id(inv_id, pr_body):
                continue
            if "agent-control-plane" in pr_body.lower():
                continue
        still_missing.append(hit)
    return still_missing


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    changed_path = Path(args.changed_files)
    changed = [line.strip() for line in changed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    audit_problems = audit_registry(root)
    invariants = load_locked_invariants(root)
    hits = matched_invariants(changed, invariants)
    pr_body = load_pr_body(args)

    if audit_problems and not (args.suggest or args.print_only):
        print("FAIL: the invariant registry does not hold up its own claims.")
        print("Every locked invariant must name guards that exist and are wired; the index must match the directory.")
        for problem in audit_problems:
            print(f"  - {problem}")
        return 1

    if args.suggest:
        print(format_suggest_block(hits), end="")
        return 0

    if args.print_only:
        if not hits:
            print("No locked invariants matched changed files.")
            return 0
        for hit in hits:
            print(f"{hit['id']}: {len(hit['matched_files'])} changed file(s) ({hit['path']})")
            breadth = glob_breadth(root, list((hit.get("matched_by_glob") or {}).keys()))
            for glob, files in sorted((hit.get("matched_by_glob") or {}).items()):
                covers = breadth.get(glob)
                scope = f", covers {covers} tracked file(s)" if covers is not None else ""
                print(f"  `{glob}` → {len(files)} changed{scope}")
                for path in files[:20]:
                    print(f"      - {path}")
        return 0

    still_missing = missing_invariant_hits(hits, pr_body)

    if not still_missing:
        if hits:
            print(f"OK: PR body names required invariant(s): {', '.join(h['id'] for h in hits)}")
        else:
            print("OK: no locked invariants require naming for these changes.")
        return 0

    print("FAIL: PR touches locked product invariant paths but does not name the invariant ID(s).")
    print("Add them under 'Product invariants affected' in the PR body.")
    print("Registry: docs/product/invariants/")
    for hit in still_missing:
        print(f"  Missing: {hit['id']} — {len(hit['matched_files'])} changed file(s) under {len(hit.get('matched_by_glob') or {})} glob(s)")
    print("\nWhat these invariants require, and why each applies:")
    print()
    print(format_invariant_briefing(still_missing))
    print("\nPaste this into the PR body (or a draft for --pr-body-file / OMI_PR_BODY_FILE):")
    print()
    print(format_suggest_block(hits), end="")
    print("Then re-run: scripts/pr-preflight --pr-body-file <draft.md>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
