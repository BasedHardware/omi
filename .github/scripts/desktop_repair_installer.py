#!/usr/bin/env python3
"""Build static metadata for a verified macOS stable repair installer."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

RELEASE_ID_RE = re.compile(r"^v\d+\.\d+(?:\.\d+)?\+\d+-macos$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _validate_bucket(bucket: str) -> str:
    if not bucket.startswith("gs://"):
        raise ValueError("bucket must use the gs://bucket-name form")
    name = bucket.removeprefix("gs://").strip().rstrip("/")
    if not name or "/" in name:
        raise ValueError("bucket must name exactly one GCS bucket")
    return name


def build_repair_bundle(manifest: dict[str, Any], bucket: str) -> dict[str, Any]:
    """Create immutable and latest-stable metadata from a validated manifest."""
    bucket_name = _validate_bucket(bucket)
    release_id = _required_string(manifest, "release_id")
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ValueError("release_id must be a macOS release tag")
    if _required_string(manifest, "platform") != "macos":
        raise ValueError("repair installers support only the macos platform")

    build_number = manifest.get("build_number")
    if not isinstance(build_number, int) or isinstance(build_number, bool) or build_number <= 0:
        raise ValueError("build_number must be a positive integer")

    source_sha = _required_string(manifest, "source_sha")
    if not SHA40_RE.fullmatch(source_sha):
        raise ValueError("source_sha has an invalid digest")
    dmg_sha256 = _required_string(manifest, "dmg_sha256")
    if not SHA256_RE.fullmatch(dmg_sha256):
        raise ValueError("dmg_sha256 has an invalid digest")

    release_path = quote(release_id, safe=".-_~+")
    public_base = f"https://storage.googleapis.com/{quote(bucket_name, safe='.-_~')}"
    artifact_object = f"stable/{release_id}/Omi.dmg"
    repair_object = f"stable/{release_id}/repair.json"
    installer_url = f"{public_base}/stable/{release_path}/Omi.dmg"
    repair_manifest_url = f"{public_base}/stable/{release_path}/repair.json"

    repair = {
        "schema_version": 1,
        "channel": "stable",
        "release_id": release_id,
        "version": _required_string(manifest, "version"),
        "build_number": build_number,
        "installer_url": installer_url,
        "installer_sha256": dmg_sha256.lower(),
        "source_sha": source_sha.lower(),
        "published_at": _required_string(manifest, "published_at"),
    }
    latest = {**repair, "repair_manifest_url": repair_manifest_url}
    version = html.escape(repair["version"])
    safe_installer_url = html.escape(installer_url, quote=True)
    landing_page = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Download Omi for macOS</title>
</head>
<body>
  <main>
    <h1>Download Omi for macOS</h1>
    <p>Stable version {version} is ready to install.</p>
    <p><a href=\"{safe_installer_url}\">Download the verified Omi installer</a></p>
    <ol>
      <li>Open the downloaded DMG.</li>
      <li>Move Omi to the <code>/Applications</code> folder.</li>
      <li>Open Omi from <code>/Applications</code> to finish the update.</li>
    </ol>
  </main>
</body>
</html>
"""
    return {
        "artifact_object": artifact_object,
        "repair_object": repair_object,
        "repair": repair,
        "latest": latest,
        "landing_page": landing_page,
    }


def write_repair_bundle(manifest: dict[str, Any], bucket: str, output_dir: Path) -> dict[str, Any]:
    bundle = build_repair_bundle(manifest, bucket)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "repair.json").write_text(json.dumps(bundle["repair"], indent=2) + "\n")
    (output_dir / "latest.json").write_text(json.dumps(bundle["latest"], indent=2) + "\n")
    (output_dir / "index.html").write_text(bundle["landing_page"])
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    bundle = write_repair_bundle(manifest, args.bucket, Path(args.output_dir))
    print(
        json.dumps({"installer_url": bundle["repair"]["installer_url"], "release_id": bundle["repair"]["release_id"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
