#!/usr/bin/env python3
"""Deterministic docs-site gate for docs/ (Mintlify at docs.omi.me).

Validates docs.json against the files on disk:
  1. every navigation entry resolves to an .mdx/.md file (or declared asset);
  2. every .mdx/.md page under docs/ is reachable from the navigation (orphans);
  3. internal links (/...) in pages resolve to a page, an asset, or a redirect target;
  4. image references resolve to files on disk;
  5. redirects: a source must not exist as a page (else it shadows the file),
     internal targets must resolve, external targets must be absolute URLs.

No network, stdlib only. Exit 1 with one line per problem.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs"

# Files that live under docs/ but are deliberately not pages (meta, config, assets).
NON_PAGE_FILES = {
    "AGENTS",
    "docs.json",
    "favicon.ico",
}
NON_PAGE_DIRS = {"images", "assets", "logo"}

LINK_ATTR = re.compile(r'href="(/[^"#?]*)')
IMG_ATTR = re.compile(r'src="(/[^"?#]*)')
IMG_MD = re.compile(r'!\[[^\]]*\]\((/[^)\s]+)\)')
LINK_MD = re.compile(r'\]\((/[^)\s#]+)\)')


def load_nav_and_redirects() -> tuple[set[str], dict[str, str], list[str]]:
    config = json.loads((DOCS / "docs.json").read_text())
    nav: set[str] = set()
    redirects: dict[str, str] = {}

    def walk(node) -> None:
        if isinstance(node, str):
            nav.add(node)
        elif isinstance(node, dict):
            if "openapi" in node and isinstance(node["openapi"], str):
                spec = DOCS / node["openapi"]
                if not spec.exists():
                    problems.append(f"openapi spec missing: {node['openapi']}")
            for page in node.get("pages", []):
                walk(page)

    problems: list[str] = []
    for tab in config.get("navigation", {}).get("tabs", []):
        for group in tab.get("groups", []):
            walk(group)
    for entry in config.get("redirects", []):
        if "source" not in entry or "destination" not in entry:
            problems.append("redirect entry missing source/destination keys")
            continue
        source = entry["source"].rstrip("/")
        target = entry["destination"]
        if source in redirects:
            problems.append(f"duplicate redirect source: {source}")
        redirects[source] = target
    return nav, redirects, problems


def page_exists(page: str) -> bool:
    for ext in (".mdx", ".md", ""):
        candidate = DOCS / (page + ext)
        if ext == "" and candidate.suffix:
            continue
        if candidate.is_file():
            return True
    return False


def asset_exists(path: str) -> bool:
    return (DOCS / path.lstrip("/")).is_file()


def all_pages() -> set[str]:
    pages = set()
    for path in DOCS.rglob("*"):
        if not path.is_file() or path.suffix not in (".mdx", ".md"):
            continue
        rel = path.relative_to(DOCS).with_suffix("")
        rel_str = rel.as_posix()
        if rel_str in NON_PAGE_FILES or rel.parts[0] in NON_PAGE_DIRS:
            continue
        if rel.name == "README" and len(rel.parts) == 1:
            continue
        pages.add(rel_str)
    return pages


def main() -> int:
    global problems, DOCS
    if len(sys.argv) > 2 and sys.argv[1] == "--docs":
        DOCS = pathlib.Path(sys.argv[2]).resolve()
    nav, redirects, problems = load_nav_and_redirects()

    # 1. nav entries exist
    for page in sorted(nav):
        if not page_exists(page):
            problems.append(f"nav entry points to missing file: {page}")

    # 2. orphans (pages not in nav)
    nav_with_dupes = nav
    for page in sorted(all_pages() - nav_with_dupes):
        problems.append(f"page not in navigation and not excluded (orphan): {page}")

    # 5. redirects
    for source, target in sorted(redirects.items()):
        if page_exists(source.lstrip("/")):
            problems.append(f"redirect source exists as a file (shadows page): {source}")
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target_page = target.lstrip("/")
        if not page_exists(target_page) and not asset_exists(target):
            problems.append(f"redirect target does not resolve: {source} -> {target}")

    # 3./4. links and images in pages
    for page in sorted(all_pages() | nav):
        for ext in (".mdx", ".md"):
            path = DOCS / (page + ext)
            if not path.is_file():
                continue
            text = path.read_text()
            for match in LINK_ATTR.findall(text) + LINK_MD.findall(text):
                target = match.rstrip("/")
                if target.startswith("/images") or any(target.startswith(f"/{d}") for d in NON_PAGE_DIRS):
                    if not asset_exists(target):
                        problems.append(f"{page}: broken asset link {match}")
                    continue
                if page_exists(target.lstrip("/")):
                    continue
                if target in redirects:
                    problems.append(f"{page}: links to a redirect source instead of its target {match}")
                    continue
                problems.append(f"{page}: broken internal link {match}")
            for match in IMG_ATTR.findall(text) + IMG_MD.findall(text):
                if not asset_exists(match):
                    problems.append(f"{page}: broken image reference {match}")
            break

    if problems:
        print(f"docs site check: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("docs site check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
