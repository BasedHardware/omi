#!/usr/bin/env python3
"""Every repo path an agent doc points at must exist.

Agent docs are read by agents that cannot tell a stale pointer from a live one.
A rename that orphans a reference is silent until an agent follows it, wastes a
turn, and then improvises -- which is exactly the failure mode guidance is
supposed to prevent.

Real instances this would have caught, all live on main when this landed:
  - CLAUDE.md pointed at `desktop/CLAUDE.md` and `desktop/e2e/SKILL.md`; both
    moved under `desktop/macos/` long before.
  - desktop/macos/AGENTS.md pointed at `.claude/skills/firebase/SKILL.md` and
    `.claude/skills/sentry-release/SKILL.md`, which are agent-local and have
    never existed in this repo.
  - desktop/macos/AGENTS.md told agents to launch via `./reset-and-run.sh`,
    which does not exist.

What counts as a reference: a markdown link to a relative path, and a backticked
token that looks like a repo path (contains `/` and a known source extension, or
starts with a top-level repo directory). Bare filenames like `auth.py` are
shorthand, not pointers, and are ignored -- resolving those would need judgment,
and a check that needs judgment is a check that gets an allowlist.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Docs whose references must resolve. Component AGENTS.md files are discovered.
EXTRA_DOCS = ("CLAUDE.md", "PRODUCT.md", "docs/agents")

SOURCE_SUFFIXES = {
    ".md", ".py", ".sh", ".yaml", ".yml", ".json", ".dart", ".swift",
    ".ts", ".tsx", ".rs", ".mdx", ".toml", ".kt", ".java", ".h", ".c",
}

# Top-level directories that make a backticked token unambiguously a repo path.
REPO_ROOTS = (
    ".github/", ".cursor/", "app/", "backend/", "desktop/", "docs/",
    "infrastructure/", "omi/", "scripts/", "web/",
)

MD_LINK = re.compile(r"\[[^\]]*\]\(\s*(?!https?:|mailto:|#)([^)\s#]+)")
BACKTICK = re.compile(r"`([^`\n]+)`")

# Placeholder segments: a path that is illustrative, not a real file.
PLACEHOLDER = re.compile(r"[<>{}*]|\.\.\.|\bYYYY\b|\bXXXX\b|20260628-short-description")


def is_repo_path(token: str) -> bool:
    """True when a backticked token is a pointer rather than shorthand."""
    if PLACEHOLDER.search(token) or " " in token:
        return False
    if token.startswith(REPO_ROOTS):
        return True
    # A relative path with a directory part and a known extension, e.g.
    # `scripts/foo.sh` inside a component guide.
    return "/" in token and Path(token).suffix in SOURCE_SUFFIXES


def ignored(repo: Path, candidates: list[Path]) -> bool:
    """True when git deliberately ignores the path.

    Build outputs, virtualenvs, .env files, and generated sources are absent in a
    clean checkout by design. Pointing at them is correct documentation, not a
    stale reference, so gitignore is the repo's own answer to 'is this expected
    to be missing?' -- no hand-maintained allowlist required.
    """
    rels = []
    for c in candidates:
        try:
            rels.append(str(c.relative_to(repo)))
        except ValueError:
            continue
    if not rels:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", "--stdin"],
        cwd=repo,
        input="\n".join(rels),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def resolve(repo: Path, doc: Path, ref: str) -> bool:
    """A reference resolves if it exists relative to the doc or the repo root."""
    ref = ref.rstrip("/")
    if not ref:
        return True
    candidates = [doc.parent / ref, repo / ref]
    if any(c.exists() for c in candidates):
        return True
    return ignored(repo, candidates)


def collect_docs(repo: Path) -> list[Path]:
    docs = sorted(
        p for p in repo.rglob("AGENTS.md")
        if "node_modules" not in p.parts and ".build" not in p.parts
    )
    for extra in EXTRA_DOCS:
        target = repo / extra
        if target.is_dir():
            docs.extend(sorted(target.rglob("*.md")))
        elif target.exists():
            docs.append(target)
    return docs


def check_doc(repo: Path, doc: Path) -> list[str]:
    text = doc.read_text(encoding="utf-8")
    rel = doc.relative_to(repo)
    errors = []
    seen: set[str] = set()

    for ref in MD_LINK.findall(text):
        if ref in seen or PLACEHOLDER.search(ref):
            continue
        seen.add(ref)
        if not resolve(repo, doc, ref):
            errors.append(f"{rel}: markdown link -> '{ref}' does not exist")

    for token in BACKTICK.findall(text):
        token = token.strip()
        if token in seen or not is_repo_path(token):
            continue
        seen.add(token)
        if not resolve(repo, doc, token):
            errors.append(f"{rel}: reference `{token}` does not exist")

    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "backend").mkdir()
        (repo / "backend" / "real.py").write_text("")
        doc = repo / "AGENTS.md"

        doc.write_text("see `backend/real.py` and [ok](backend/real.py)\n")
        assert check_doc(repo, doc) == [], "existing references must pass"

        doc.write_text("see `backend/gone.py`\n")
        assert check_doc(repo, doc), "missing backticked repo path must fail"

        doc.write_text("see [x](backend/gone.py)\n")
        assert check_doc(repo, doc), "missing markdown link must fail"

        doc.write_text("run `auth.py` and `make setup` and `pip install -e .`\n")
        assert check_doc(repo, doc) == [], "bare shorthand must be ignored"

        doc.write_text("see `docs/<component>/guide.md` and `changelog/YYYY-x.json`\n")
        assert check_doc(repo, doc) == [], "placeholders must be ignored"

        # A component guide resolving a path relative to its own directory.
        (repo / "backend" / "AGENTS.md").write_text("run `scripts/x.sh`\n")
        (repo / "backend" / "scripts").mkdir()
        (repo / "backend" / "scripts" / "x.sh").write_text("")
        assert check_doc(repo, repo / "backend" / "AGENTS.md") == [], (
            "component-relative reference must resolve"
        )


def main() -> int:
    self_test()
    repo = Path(__file__).resolve().parents[2]
    errors = [e for doc in collect_docs(repo) for e in check_doc(repo, doc)]
    if errors:
        print("Agent docs reference paths that do not exist:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(
            "\nFix the path, or delete the pointer if the target is gone.\n"
            "Agents cannot tell a stale pointer from a live one.",
            file=sys.stderr,
        )
        return 1
    print("agent doc references OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
