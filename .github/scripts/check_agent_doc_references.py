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

Second rule: a package-local doc that tells the reader to copy a template must
name a template that exists. This is the same failure class -- a pointer nobody
can follow -- in the forms the rules above cannot see: a `cp` inside a fenced
block, and the prose "Copy `x` to `y`". It is the first instruction a newcomer
runs, so a dead one stops them at step one.

Real instances this would have caught, all live on main when this landed --
fourteen, which the rule reports exactly, with nothing else:
  - README.md told every macOS reader to `cp ../../backend/.env.example
    ../../backend/.env`; the file has always been `backend/.env.template`.
  - Eight plugin setup docs said `cp .env.example .env` while shipping no such
    file: github (README and QUICKSTART), hive, linear, shopify, slack (README
    and SETUP), twitter.
  - Five more said it as prose rather than a command, which is why the prose
    form is scanned too: composio (`.env.template`), google-calendar, notion,
    twitter-chat-tools, whoop.

Scope is deliberately narrow. Only docs that sit in the directory they document
are scanned: a doc under `docs/` describes commands run somewhere else, and its
working directory lives in prose the checker cannot read. Only `.template` and
`.example` sources count. Unlike the reference rules above, this one does not
consult gitignore: a template is by definition committed, so a .gitignore that
hides one is the bug rather than the excuse -- a nested plugin .gitignore
re-ignoring `.env.*` would otherwise switch the rule off for that directory.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Docs whose references must resolve. Component AGENTS.md files are discovered.
EXTRA_DOCS = ("CLAUDE.md", "PRODUCT.md", "docs/agents", ".cursor/cloud-agent-environment.md")

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

# `cp <src> <dst>` inside a fenced block, and the `cd`s that move between them.
# Both are matched per command segment, so `cd x && cp a b` is seen as two.
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
CP_CMD = re.compile(r"^\s*(?:\$\s*)?cp\s+(?:-[\w-]+\s+)*(\S+)\s+\S+")
CD_CMD = re.compile(r"^\s*(?:\$\s*)?cd\s+(\S+)")
SEGMENT = re.compile(r"&&|\|\||;")

# The same instruction written as prose rather than as a command. Five of the
# fourteen dead pointers on main took this form -- disjoint from the nine
# written as `cp` -- so a fenced-only rule misses better than a third of them.
PROSE_COPY = re.compile(r"\b[Cc]opy\s+`([^`\n]+)`\s+to\s+`", re.M)

# A copied source that names a template rather than a real config file.
TEMPLATE_SRC = re.compile(r"\.(?:template|example)$")

# Directories whose markdown is vendored, generated, or agent-local.
UNSCANNED = {
    "node_modules", ".build", ".venv", "venv", "build", "dist", ".git",
    "Pods", "vendor", ".dart_tool", ".trellis", ".claude", "docs",
}


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


def collect_setup_docs(repo: Path) -> list[Path]:
    """Docs that sit in the directory whose setup they describe."""
    docs = []
    for suffix in ("*.md", "*.mdx"):
        for p in repo.rglob(suffix):
            if UNSCANNED & set(p.relative_to(repo).parts):
                continue
            docs.append(p)
    return sorted(docs)


def check_setup_doc(repo: Path, doc: Path) -> list[str]:
    """Every `cp <template> <dst>` must name a template that exists."""
    text = doc.read_text(encoding="utf-8")
    rel = doc.relative_to(repo)
    errors = []

    def flag(src: str, base: Path, form: str) -> None:
        if PLACEHOLDER.search(src) or not TEMPLATE_SRC.search(src):
            return
        stripped = re.sub(r"^(?:\.\.?/)+", "", src)
        # No `ignored()` hatch here: a template is by definition committed, so
        # a gitignore that hides one is the bug, not an excuse. A nested
        # plugin .gitignore re-ignoring `.env.*` otherwise disables this rule
        # for that directory.
        if any(c.exists() for c in (base / src, doc.parent / src, repo / stripped)):
            return
        errors.append(f"{rel}: {form} names a template that does not exist")

    for block in FENCE.findall(text):
        # Each `cd` moves the working directory for the commands that follow
        # it, not for the whole block, and always relative to the doc: reading
        # a bare `scripts` as the repo-root `scripts/` made the two spellings
        # of the same target disagree, and resolved nothing the doc-relative
        # reading does not. An absolute or `~` target would take the check off
        # the repo and make the verdict depend on the host, so it stops
        # tracking rather than guessing.
        base = doc.parent
        for line in block.splitlines():
            for segment in SEGMENT.split(line):
                cd = CD_CMD.match(segment)
                if cd:
                    target = cd.group(1).strip("'\"")
                    if PLACEHOLDER.search(target) or target.startswith(("/", "~")):
                        continue
                    base = base / target
                    continue
                cp = CP_CMD.match(segment)
                if cp:
                    src = cp.group(1).strip("'\"`")
                    flag(src, base, f"`cp {src} ...`")

    for match in PROSE_COPY.finditer(FENCE.sub("", text)):
        src = match.group(1).strip()
        flag(src, doc.parent, f"`Copy {src} to ...`")

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

        # -- cp <template> rule --------------------------------------------
        readme = repo / "backend" / "README.md"

        readme.write_text("```bash\ncp .env.template .env\n```\n")
        assert check_setup_doc(repo, readme), "missing template must fail"

        (repo / "backend" / ".env.template").write_text("")
        assert check_setup_doc(repo, readme) == [], "present template must pass"

        # Repo-root path reached by climbing out of a documented subdirectory.
        root_doc = repo / "README.md"
        root_doc.write_text("```bash\ncp ../../backend/.env.template ../../backend/.env\n```\n")
        assert check_setup_doc(repo, root_doc) == [], "../-prefixed repo path must resolve"

        root_doc.write_text("```bash\ncp ../../backend/.env.example ../../backend/.env\n```\n")
        assert check_setup_doc(repo, root_doc), "the real README defect must fail"

        # A `cd` inside the block moves the working directory.
        (repo / "app").mkdir()
        (repo / "app" / "creds.xcconfig.template").write_text("")
        root_doc.write_text("```bash\ncd app\ncp creds.xcconfig.template creds.xcconfig\n```\n")
        assert check_setup_doc(repo, root_doc) == [], "cd must set the working directory"

        # Copying a real config file is not a template pointer.
        root_doc.write_text("```bash\ncp deploy/live.yaml backup.yaml\n```\n")
        assert check_setup_doc(repo, root_doc) == [], "non-template cp must be ignored"

        # Two cds in one block: each moves the cwd only for what follows it.
        (repo / "app" / "sub").mkdir()
        (repo / "app" / "sub" / "b.template").write_text("")
        root_doc.write_text(
            "```bash\ncd app\ncp creds.xcconfig.template x\ncd sub\ncp b.template y\n```\n"
        )
        assert check_setup_doc(repo, root_doc) == [], "each cd moves the cwd for what follows"
        root_doc.write_text("```bash\ncd app\ncd sub\ncp creds.xcconfig.template x\n```\n")
        assert check_setup_doc(repo, root_doc), "a stale first cd must not mask a missing template"

        # `cd x && cp ...` on one line is two commands, not an unparsed blob.
        # The negative case is the discriminating one: without the segment
        # split the whole line matches CD_CMD, the cp is never examined, and
        # the result is [] for the wrong reason.
        root_doc.write_text("```bash\ncd app && cp creds.xcconfig.template x\n```\n")
        assert check_setup_doc(repo, root_doc) == [], "&& segments must be read as commands"
        root_doc.write_text("```bash\ncd app && cp gone.template x\n```\n")
        assert check_setup_doc(repo, root_doc), "a cp after && must still be checked"

        # The two spellings of one cd target must agree.
        root_doc.write_text("```bash\ncd app\ncp creds.xcconfig.template x\n```\n")
        with_slash = check_setup_doc(repo, root_doc)
        root_doc.write_text("```bash\ncd app/\ncp creds.xcconfig.template x\n```\n")
        assert check_setup_doc(repo, root_doc) == with_slash, "a trailing slash must not change the verdict"

        # An absolute cd would take the check off the repo; the verdict must
        # not depend on the host's filesystem.
        root_doc.write_text("```bash\ncd /nonexistent-host-path\ncp gone.template x\n```\n")
        assert check_setup_doc(repo, root_doc), "an absolute cd must not silence the rule"

        # A gitignored template is still a dead pointer, not an excuse.
        (repo / "app" / ".gitignore").write_text("*.template\n")
        root_doc.write_text("```bash\ncd app\ncp missing.template x\n```\n")
        assert check_setup_doc(repo, root_doc), "gitignore must not disable the rule"
        (repo / "app" / ".gitignore").unlink()

        # The same instruction as prose, outside any fenced block.
        root_doc.write_text("Copy `gone.template` to `gone.conf` first.\n")
        assert check_setup_doc(repo, root_doc), "prose-form copy must fail"
        root_doc.write_text("Copy `app/creds.xcconfig.template` to `x` first.\n")
        assert check_setup_doc(repo, root_doc) == [], "prose-form copy of a real template must pass"
        root_doc.write_text("```bash\ncp gone.template x\n```\nCopy `gone.template` to `y`.\n")
        assert len(check_setup_doc(repo, root_doc)) == 2, "both forms are reported"

        # Docs under docs/ describe commands run elsewhere; cwd is prose. The
        # temp repo needs a docs/ file, or this assertion cannot discriminate.
        (repo / "docs").mkdir()
        (repo / "docs" / "guide.md").write_text("```bash\ncp gone.template x\n```\n")
        assert not any(
            "docs" in d.relative_to(repo).parts for d in collect_setup_docs(repo)
        ), "docs/ must stay out of scope"


def main() -> int:
    self_test()
    repo = Path(__file__).resolve().parents[2]
    errors = [e for doc in collect_docs(repo) for e in check_doc(repo, doc)]
    errors += [
        e for doc in collect_setup_docs(repo) for e in check_setup_doc(repo, doc)
    ]
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
