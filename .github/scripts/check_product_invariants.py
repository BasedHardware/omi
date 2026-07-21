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
import sys
from pathlib import Path

INVARIANT_DIR = Path("docs/product/invariants")
ID_RE = re.compile(r"^#\s+(INV-[A-Z0-9]+(?:-\*|(?:-\d+)+))", re.MULTILINE)
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\w+)", re.MULTILINE | re.IGNORECASE)
GLOB_LINE_RE = re.compile(r"^-\s+`([^`]+)`\s*$", re.MULTILINE)
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
    in_globs = False
    for line in text.splitlines():
        if line.strip().lower().startswith("## path globs"):
            in_globs = True
            continue
        if in_globs and line.startswith("## "):
            break
        if in_globs:
            m = GLOB_LINE_RE.match(line.strip())
            if m:
                globs.append(m.group(1))
    return {
        "id": id_match.group(1),
        "status": status,
        "globs": globs,
        "require_naming": not bool(SKIP_NAMING_RE.search(text)),
        "path": str(path),
    }


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
        matching = [p for p in changed if any(path_matches(p, g) for g in inv["globs"])]
        if matching:
            hits.append({**inv, "matched_files": matching})
    return hits


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
    invariants = load_locked_invariants(root)
    hits = matched_invariants(changed, invariants)
    pr_body = load_pr_body(args)

    if args.suggest:
        print(format_suggest_block(hits), end="")
        return 0

    if args.print_only:
        if not hits:
            print("No locked invariants matched changed files.")
            return 0
        for hit in hits:
            print(f"{hit['id']}: {len(hit['matched_files'])} file(s) ({hit['path']})")
            for f in hit["matched_files"][:20]:
                print(f"  - {f}")
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
        print(f"\n  Missing: {hit['id']} (from {hit['path']})")
        print("  Matched files:")
        for f in hit["matched_files"][:15]:
            print(f"    - {f}")
        if len(hit["matched_files"]) > 15:
            print(f"    … and {len(hit['matched_files']) - 15} more")
    print("\nPaste this into the PR body (or a draft for --pr-body-file / OMI_PR_BODY_FILE):")
    print()
    print(format_suggest_block(hits), end="")
    print("Then re-run: scripts/pr-preflight --pr-body-file <draft.md>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
