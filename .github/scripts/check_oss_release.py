#!/usr/bin/env python3
"""ADR-0054: the images WE build carry the release, and the release has exactly one source.

`deploy/onprem/omi.oss.release.env` holds OMI_OSS_RELEASE. Compose reads it through the long form of
`include:` (next to the third-party pins, ADR-0055) and every image we build is tagged with it, so a
rebuild produces a NEW reference and `helm upgrade` / `docker compose up` can no longer serve stale code
from a cache under an unchanged `:latest`.

Invariants enforced here (the chart-side ones — appVersion, chart tags, no `:latest` in the prod/k0s
overlays — land with the chart conversion):

  1. the release file exists, parses, and carries a SemVer OMI_OSS_RELEASE;
  2. the release file is TRACKED by git — it is source, and the repo-wide `*.env` rule would otherwise
     swallow it, making the release silently local to one machine;
  3. every `omi-oss-*` image in the compose files is tagged with the release, never a literal tag.

Stdlib only, like the other guards.

Run:  python3 .github/scripts/check_oss_release.py   # exit 0 = consistent
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_ENV = ROOT / "deploy/onprem/omi.oss.release.env"
GITIGNORE = ROOT / "deploy/onprem/.gitignore"
COMPOSE = [ROOT / "deploy/onprem/compose.base.yaml", ROOT / "deploy/onprem/compose.selfhost.yaml"]

VAR = "OMI_OSS_RELEASE"
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_IMAGE_RE = re.compile(r'^\s*\w*[iI]mage:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
# `omi-oss-<name>:${OMI_OSS_RELEASE...}` — the only shape allowed for an image we build.
_OURS_RELEASE_RE = re.compile(r"^omi-oss-[a-z0-9-]+:\$\{" + VAR + r"(:[?-][^}]*)?\}$")
_OURS_ANY_RE = re.compile(r"^omi-oss-[a-z0-9-]+:")


def release_of(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{VAR}="):
            return line.split("=", 1)[1].strip()
    return None


def _images(text: str) -> list[str]:
    return [raw if raw.startswith("${") else raw.split("#", 1)[0].strip() for raw in _IMAGE_RE.findall(text)]


def check(release_text: str, compose_texts: dict[str, str], gitignore_text: str) -> list[str]:
    """The whole rule over source strings, so it is testable without a repo on disk."""
    problems: list[str] = []

    release = release_of(release_text)
    if release is None:
        problems.append(f"{RELEASE_ENV.name}: no {VAR}= line")
    elif not _SEMVER_RE.match(release):
        problems.append(f"{RELEASE_ENV.name}: {VAR}={release!r} is not SemVer (ADR-0054)")

    # The release file is source: the repo-wide `*.env` rule must be negated for it, or it silently
    # stops being versioned and every machine builds its own idea of the release.
    if not re.search(r"^!omi\.oss\.release\.env\s*$", gitignore_text, re.MULTILINE):
        problems.append(
            "deploy/onprem/.gitignore: missing `!omi.oss.release.env` — the repo-wide *.env rule would "
            "untrack the release file"
        )

    for fname, text in compose_texts.items():
        for img in _images(text):
            if _OURS_ANY_RE.match(img) and not _OURS_RELEASE_RE.match(img):
                problems.append(
                    f"{fname}: {img!r} is an image we build but is not tagged with the release — use "
                    f"omi-oss-<name>:${{{VAR}:?...}} (:latest is a dev alias produced by build.tags)"
                )
    return problems


def _tracked_by_git() -> str | None:
    """None when tracked (or when git cannot answer); an error string when git says it is not."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(RELEASE_ENV.relative_to(ROOT))],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return None  # no git available (e.g. a source tarball) — the .gitignore check still applies
    if proc.returncode != 0:
        return (
            f"{RELEASE_ENV.name}: not tracked by git — it is source, not operator config; "
            f"`git add {RELEASE_ENV.relative_to(ROOT)}`"
        )
    return None


def main() -> int:
    if not RELEASE_ENV.exists():
        print(f"Release check FAILED: {RELEASE_ENV} is missing")
        return 1

    problems = check(
        RELEASE_ENV.read_text(encoding="utf-8"),
        {f.name: f.read_text(encoding="utf-8") for f in COMPOSE},
        GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else "",
    )
    untracked = _tracked_by_git()
    if untracked:
        problems.append(untracked)

    if problems:
        print("Release check FAILED:\n  " + "\n  ".join(problems))
        return 1

    print(f"Release OK — {VAR}={release_of(RELEASE_ENV.read_text(encoding='utf-8'))}, "
          f"tracked, and every image we build in compose carries it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
