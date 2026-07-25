#!/usr/bin/env python3
"""Collect sanitized release state and generate an advisory evidence report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from desktop_release_doctor_report import (
    METRIC_CONTRACTS,
    REPORT_TYPE,
    SCHEMA_VERSION,
    TAG_RE,
    _optional_string,
    _unavailable,
    evaluate_snapshot,
    format_summary,
)

REPOSITORY = "BasedHardware/omi"
PRIVATE_KEY_VALUE_BLOCK_RE = re.compile(r"<!--\s*KEY_VALUE_START.*?KEY_VALUE_END\s*-->", re.DOTALL)
STALE_STABLE_PROSE_RE = re.compile(r"stable\s+(?:remains\s+)?blocked", re.IGNORECASE)
SPARKLE_NAMESPACE = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def _metadata_from_release_body(body: object) -> tuple[dict[str, str], bool]:
    """Keep only release-control keys; never copy prose into the snapshot."""
    if not isinstance(body, str):
        return {}, False

    metadata: dict[str, str] = {}
    in_block = False
    for line in body.splitlines():
        stripped = line.strip().removeprefix("<!--").removesuffix("-->").strip()
        if stripped == "KEY_VALUE_START":
            in_block = True
            continue
        if stripped == "KEY_VALUE_END":
            break
        if not in_block or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

    safe_keys = (
        "channel",
        "isLive",
        "qualifiedBeta",
        "qualifiedBetaSha",
        "qualifiedBetaTier",
        "qualifiedBetaEvidence",
    )
    public_metadata = {key: metadata[key] for key in safe_keys if key in metadata}
    human_prose = PRIVATE_KEY_VALUE_BLOCK_RE.sub("", body)
    return public_metadata, bool(STALE_STABLE_PROSE_RE.search(human_prose))


def _firestore_value(value: object) -> object:
    if not isinstance(value, dict):
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        try:
            return int(value["integerValue"])
        except (TypeError, ValueError):
            return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "timestampValue" in value:
        return value["timestampValue"]
    if "mapValue" in value:
        fields = value["mapValue"].get("fields", {})
        return {key: _firestore_value(item) for key, item in fields.items()}
    if "arrayValue" in value:
        return [_firestore_value(item) for item in value["arrayValue"].get("values", [])]
    return None


def _firestore_fields(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        return {}
    fields = document.get("fields", {})
    if not isinstance(fields, dict):
        return {}
    return {key: _firestore_value(value) for key, value in fields.items()}


def _http_json(url: str, *, token: str | None = None) -> object:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(
        request, timeout=30
    ) as response:  # nosec B310: URLs are fixed release-control endpoints.
        return json.loads(response.read().decode("utf-8"))


def _http_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": "application/xml,application/json,text/plain"})
    with urllib.request.urlopen(
        request, timeout=30
    ) as response:  # nosec B310: URLs are fixed release-control endpoints.
        return response.read().decode("utf-8")


def _release_id_from_url(url: object) -> str:
    if not isinstance(url, str):
        return ""
    prefix = "/BasedHardware/omi/releases/download/"
    path = urllib.parse.urlparse(url).path
    if prefix not in path:
        return ""
    suffix = path.split(prefix, 1)[1]
    try:
        release_id, _asset = suffix.rsplit("/", 1)
    except ValueError:
        return ""
    return urllib.parse.unquote(release_id)


def _appcast_items(xml: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    items: dict[str, str] = {}
    for item in root.findall("./channel/item"):
        channel = item.findtext(f"{SPARKLE_NAMESPACE}channel") or "stable"
        enclosure = item.find("enclosure")
        release_id = _release_id_from_url(enclosure.get("url") if enclosure is not None else "")
        if release_id:
            items.setdefault(channel, release_id)
    return items


def _safe_firestore_document(
    project_id: str, collection: str, document_id: str, token: str, *, allowed_fields: tuple[str, ...]
) -> dict[str, object]:
    encoded_id = urllib.parse.quote(document_id, safe="")
    url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/"
        f"{collection}/{encoded_id}"
    )
    try:
        fields = _firestore_fields(_http_json(url, token=token))
        return {field: fields[field] for field in allowed_fields if field in fields}
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return _unavailable("document is absent")
        return _unavailable(f"Firestore returned HTTP {error.code}")
    except (OSError, ValueError) as error:
        return _unavailable(f"Firestore read failed: {type(error).__name__}")


def _project_release_summary(release: object) -> dict[str, object]:
    if not isinstance(release, dict):
        return _unavailable("GitHub release response was not an object")
    metadata, stale_human_prose = _metadata_from_release_body(release.get("body"))
    assets = release.get("assets", [])
    asset_names = [
        asset.get("name") for asset in assets if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    ]
    return {
        "tag_name": _optional_string(release.get("tagName")),
        "is_draft": release.get("isDraft") is True,
        "is_prerelease": release.get("isPrerelease") is True,
        "metadata": metadata,
        "asset_names": asset_names,
        "stale_human_prose": stale_human_prose,
    }


def _safe_static_json(bucket: str, name: str) -> dict[str, object]:
    object_path = f"{bucket.rstrip('/')}/{name}"
    result = subprocess.run(
        ("gcloud", "storage", "cat", object_path),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return _unavailable(f"static object unavailable: {name}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _unavailable(f"static object was not JSON: {name}")
    if not isinstance(data, dict):
        return _unavailable(f"static object was not an object: {name}")
    allowed = ("channel", "release_id", "tag", "version", "build_number")
    return {key: data[key] for key in allowed if key in data}


def _safe_health(service_url: str) -> dict[str, object]:
    if not service_url:
        return _unavailable("desktop-backend service URL was unavailable")
    try:
        payload = _http_json(f"{service_url.rstrip('/')}/health")
    except (OSError, ValueError, urllib.error.HTTPError) as error:
        return _unavailable(f"backend health read failed: {type(error).__name__}")
    if not isinstance(payload, dict):
        return _unavailable("backend health response was not an object")
    allowed = ("release_tag", "release_sha", "release_channel", "revision")
    return {key: payload[key] for key in allowed if key in payload}


def _safe_appcast(url: str) -> dict[str, object]:
    try:
        items = _appcast_items(_http_text(url))
    except (OSError, urllib.error.HTTPError) as error:
        return _unavailable(f"appcast read failed: {type(error).__name__}")
    return {"channels": items}


def collect_snapshot(
    *, release_tag: str, project_id: str, repository: str, bucket: str, service: str, region: str
) -> dict[str, object]:
    """Collect every currently accessible surface without persisting secrets or prose."""
    if not TAG_RE.fullmatch(release_tag):
        raise ValueError("release_tag must use v<version>+<build>-macos form")
    _run("git", "fetch", "--force", "origin", f"+refs/tags/{release_tag}:refs/tags/{release_tag}")
    tag_sha = _run("git", "rev-list", "-n1", release_tag).strip()
    release_raw = json.loads(
        _run(
            "gh",
            "release",
            "view",
            release_tag,
            "--repo",
            repository,
            "--json",
            "tagName,body,isDraft,isPrerelease,assets",
        )
    )
    access_token = _run("gcloud", "auth", "print-access-token").strip()
    service_url = _run(
        "gcloud",
        "run",
        "services",
        "describe",
        service,
        "--region",
        region,
        "--project",
        project_id,
        "--format=value(status.url)",
        check=False,
    ).strip()
    match = TAG_RE.fullmatch(release_tag)
    assert match is not None
    legacy_id = f"v{match.group('version')}+{match.group('build')}"
    tracking_sha = _run("git", "rev-list", "-n1", "desktop-backend-prod-deployed", check=False).strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_tag,
        "tag_sha": tag_sha,
        "collected_at": _utc_now(),
        "github_release": _project_release_summary(release_raw),
        "manifest": _safe_firestore_document(
            project_id,
            "desktop_release_manifests",
            release_tag,
            access_token,
            allowed_fields=(
                "release_id",
                "platform",
                "version",
                "build_number",
                "app_source_sha",
                "zip_sha256",
                "dmg_sha256",
                "qualification_evidence_asset",
                "qualification_evidence_sha256",
            ),
        ),
        "pointers": {
            "beta": _safe_firestore_document(
                project_id,
                "desktop_update_channels",
                "macos-beta",
                access_token,
                allowed_fields=(
                    "platform",
                    "channel",
                    "release_id",
                    "version",
                    "build_number",
                    "generation",
                    "updated_at",
                ),
            ),
            "stable": _safe_firestore_document(
                project_id,
                "desktop_update_channels",
                "macos-stable",
                access_token,
                allowed_fields=(
                    "platform",
                    "channel",
                    "release_id",
                    "version",
                    "build_number",
                    "generation",
                    "updated_at",
                ),
            ),
        },
        "legacy_release": _safe_firestore_document(
            project_id,
            "desktop_releases",
            legacy_id,
            access_token,
            allowed_fields=("version", "build_number", "channel", "is_live"),
        ),
        "appcasts": {
            "python": _safe_appcast("https://api.omi.me/v2/desktop/appcast.xml?platform=macos"),
            "rust": _safe_appcast(f"{service_url.rstrip('/')}/appcast.xml?platform=macos"),
        },
        "static": {
            "beta": _safe_static_json(bucket, "beta/redirect.json"),
            "stable": _safe_static_json(bucket, "stable/latest.json"),
        },
        "backend": _safe_health(service_url),
        "tracking": (
            {"desktop_backend_prod_deployed_sha": tracking_sha}
            if tracking_sha
            else _unavailable("tracking tag is absent")
        ),
        "codemagic": _unavailable("Codemagic API is not yet a release-control dependency"),
        "metrics": {
            name: _unavailable("metric collection is advisory work not yet wired") for name in METRIC_CONTRACTS
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="evaluate an existing sanitized snapshot")
    report.add_argument("--snapshot", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--summary", type=Path)
    doctor = commands.add_parser("doctor", help="collect all release surfaces and write advisory evidence")
    doctor.add_argument("--release-tag", required=True)
    doctor.add_argument("--project-id", required=True)
    doctor.add_argument("--repository", default=REPOSITORY)
    doctor.add_argument("--gcs-bucket", required=True)
    doctor.add_argument("--service", default="desktop-backend")
    doctor.add_argument("--region", default="us-central1")
    doctor.add_argument("--output", type=Path, required=True)
    doctor.add_argument("--summary", type=Path)
    doctor.add_argument("--snapshot-output", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise SystemExit("snapshot must be a JSON object")
    else:
        try:
            snapshot = collect_snapshot(
                release_tag=args.release_tag,
                project_id=args.project_id,
                repository=args.repository,
                bucket=args.gcs_bucket,
                service=args.service,
                region=args.region,
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            raise SystemExit(f"FAIL: could not collect desktop release snapshot: {error}") from error
        if args.snapshot_output:
            _write_json(args.snapshot_output, snapshot)
    try:
        evidence = evaluate_snapshot(snapshot)
    except ValueError as error:
        raise SystemExit(f"FAIL: invalid desktop release snapshot: {error}") from error
    _write_json(args.output, evidence)
    summary = format_summary(evidence)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
