#!/usr/bin/env python3
"""Demote stable desktop releases that are not the rollback target.

During a forced rollback (``force=true`` with an older ``release_tag``),
any release currently on the ``stable`` channel that is NOT the rollback
target must be demoted to ``beta``. Otherwise both appcast paths continue
to serve the newer stable release while the backend runs the older one:

* Python appcast (``backend/routers/updates.py``) sorts by ``published_at``
  descending and the GitHub Release body metadata determines the channel.
* Rust appcast (``desktop/macos/Backend-Rust``) sorts by ``build_number``
  descending and the Firestore ``desktop_releases`` document determines
  the channel.

This script handles both surfaces:

1.  **GitHub Releases** — parses the ``KEY_VALUE_START`` metadata block,
    rewrites ``channel: stable`` to ``channel: beta``, and edits the
    release via ``gh release edit``.
2.  **Firestore** — lists ``desktop_releases`` documents, finds any with
    ``channel == stable`` that are not the target, and PATCHes them to
    ``beta``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")


# ---------------------------------------------------------------------------
# Metadata helpers (mirrors check-desktop-release-promotion.py)
# ---------------------------------------------------------------------------

def normalize_metadata_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("<!--"):
        stripped = stripped[4:].strip()
    if stripped.endswith("-->"):
        stripped = stripped[:-3].strip()
    return stripped


def parse_metadata(body: str) -> dict[str, str]:
    in_block = False
    metadata: dict[str, str] = {}
    for line in body.splitlines():
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            continue
        if stripped == "KEY_VALUE_END":
            return metadata
        if not in_block or not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def rewrite_channel_stable_to_beta(body: str) -> tuple[str, bool]:
    """Rewrite ``channel: stable`` → ``channel: beta`` inside the KV block.

    Returns ``(new_body, changed)``.
    """
    lines = body.splitlines()
    output: list[str] = []
    in_block = False
    changed = False
    for line in lines:
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            output.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            in_block = False
            output.append(line)
            continue
        if in_block and stripped.startswith("channel:") and "stable" in stripped.lower():
            output.append(line.replace("stable", "beta"))
            changed = True
            continue
        output.append(line)
    trailing = "\n" if body.endswith("\n") else ""
    return "\n".join(output) + trailing, changed


# ---------------------------------------------------------------------------
# GitHub Releases
# ---------------------------------------------------------------------------

def demote_github_releases(target_tag: str, repo: str) -> list[str]:
    """Demote non-target GitHub Releases from stable to beta."""
    demoted: list[str] = []

    # Use the REST API so we get the full body in one paginated call.
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{repo}/releases",
            "--paginate",
            "--jq",
            '[.[] | select(.draft == false) | select(.tag_name | endswith("-macos")) '
            "| {tag_name, body}]",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    releases = json.loads(result.stdout) if result.stdout.strip() else []

    for release in releases:
        tag = release.get("tag_name", "")
        if tag == target_tag or not tag.endswith("-macos"):
            continue
        body = release.get("body", "") or ""
        metadata = parse_metadata(body)
        if metadata.get("channel", "").lower() != "stable":
            continue

        new_body, changed = rewrite_channel_stable_to_beta(body)
        if not changed:
            continue

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(new_body)
            notes_path = f.name

        try:
            subprocess.run(
                [
                    "gh", "release", "edit", tag,
                    "--repo", repo,
                    "--notes-file", notes_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            demoted.append(f"GitHub Release {tag}: stable -> beta")
        finally:
            os.unlink(notes_path)

    return demoted


# ---------------------------------------------------------------------------
# Firestore
# ---------------------------------------------------------------------------

def _gcloud_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _firestore_request(url: str, token: str, method: str = "GET", data: bytes | None = None):
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def demote_firestore_releases(target_tag: str, project_id: str) -> list[str]:
    """Demote non-target Firestore desktop_releases docs from stable to beta."""
    demoted: list[str] = []

    target_match = TAG_RE.match(target_tag)
    if target_match:
        target_doc_id = f"v{target_match.group('version')}+{target_match.group('build')}"
    else:
        target_doc_id = ""

    token = _gcloud_token()
    base = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/desktop_releases"

    try:
        data = _firestore_request(base, token)
    except urllib.error.HTTPError as e:
        print(f"Warning: could not list Firestore desktop_releases: {e}", file=sys.stderr)
        return demoted
    except Exception as e:
        print(f"Warning: could not list Firestore desktop_releases: {e}", file=sys.stderr)
        return demoted

    for doc in data.get("documents", []):
        name = doc.get("name", "")
        doc_id = name.rsplit("/", 1)[-1]
        if doc_id == target_doc_id:
            continue

        fields = doc.get("fields", {})
        channel = fields.get("channel", {}).get("stringValue", "")
        if channel != "stable":
            continue

        patch_url = f"{base}/{doc_id}?updateMask.fieldPaths=channel"
        patch_data = json.dumps(
            {"fields": {"channel": {"stringValue": "beta"}}}
        ).encode()

        try:
            _firestore_request(patch_url, token, method="PATCH", data=patch_data)
            demoted.append(f"Firestore desktop_releases/{doc_id}: stable -> beta")
        except Exception as e:
            print(f"Warning: could not demote Firestore doc {doc_id}: {e}", file=sys.stderr)

    return demoted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-tag", required=True, help="Rollback target release tag")
    parser.add_argument("--repo", required=True, help="GitHub owner/repo")
    parser.add_argument("--project-id", default="", help="GCP project ID for Firestore")
    args = parser.parse_args()

    demoted: list[str] = []

    print("Demoting GitHub Releases on stable channel (excluding target)...")
    demoted.extend(demote_github_releases(args.target_tag, args.repo))

    if args.project_id:
        print("Demoting Firestore desktop_releases on stable channel (excluding target)...")
        demoted.extend(demote_firestore_releases(args.target_tag, args.project_id))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if demoted:
        for d in demoted:
            print(f"  {d}")
        if summary_path:
            with open(summary_path, "a") as f:
                f.write("### Demoted newer stable releases (rollback)\n\n")
                for d in demoted:
                    f.write(f"- {d}\n")
    else:
        print("No newer stable releases to demote.")
        if summary_path:
            with open(summary_path, "a") as f:
                f.write("_No newer stable releases needed demotion._\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
