#!/usr/bin/env python3
"""Generate a sanitized, advisory desktop-release evidence report.

The ``doctor`` command is intentionally read-only.  It fetches the release
surfaces that are authoritative today, normalizes them into a snapshot with no
secrets or release prose, and emits a versioned evidence artifact.  Promotion
workflows can upload that artifact before any future enforcement is enabled.
"""

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


SCHEMA_VERSION = 1
REPORT_TYPE = "desktop-release-evidence"
REPOSITORY = "BasedHardware/omi"
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")
PRIVATE_KEY_VALUE_BLOCK_RE = re.compile(r"<!--\s*KEY_VALUE_START.*?KEY_VALUE_END\s*-->", re.DOTALL)
STALE_STABLE_PROSE_RE = re.compile(r"stable\s+(?:remains\s+)?blocked", re.IGNORECASE)
SPARKLE_NAMESPACE = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"

METRIC_CONTRACTS = (
    "beta_soak_duration",
    "updater_delivery",
    "eligible_beta_cohort",
    "crash_free_sessions",
    "feature_path_success",
    "backend_error_rate",
    "fallback_outcomes",
    "provider_runtime",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def _unavailable(reason: str) -> dict[str, str]:
    return {"availability": "unavailable", "reason": reason}


def _is_unavailable(value: object) -> bool:
    return isinstance(value, dict) and value.get("availability") == "unavailable"


def _optional_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


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
        "stableCandidate",
        "stableCandidateTag",
        "stableCandidateSha",
        "stableCandidateQualificationEvidence",
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
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310: URLs are fixed release-control endpoints.
        return json.loads(response.read().decode("utf-8"))


def _http_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": "application/xml,application/json,text/plain"})
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310: URLs are fixed release-control endpoints.
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
    asset_names = [asset.get("name") for asset in assets if isinstance(asset, dict) and isinstance(asset.get("name"), str)]
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
        ("gcloud", "storage", "cat", object_path), check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
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
                "source_sha",
                "zip_sha256",
                "dmg_sha256",
                "qualification",
            ),
        ),
        "pointers": {
            "beta": _safe_firestore_document(
                project_id,
                "desktop_update_channels",
                "macos-beta",
                access_token,
                allowed_fields=("platform", "channel", "release_id", "version", "build_number", "generation", "updated_at"),
            ),
            "stable": _safe_firestore_document(
                project_id,
                "desktop_update_channels",
                "macos-stable",
                access_token,
                allowed_fields=("platform", "channel", "release_id", "version", "build_number", "generation", "updated_at"),
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
        "tracking": {"desktop_backend_prod_deployed_sha": tracking_sha} if tracking_sha else _unavailable("tracking tag is absent"),
        "codemagic": _unavailable("Codemagic API is not yet a release-control dependency"),
        "metrics": {name: _unavailable("metric collection is advisory work not yet wired") for name in METRIC_CONTRACTS},
    }


def _surface(
    identifier: str,
    status: str,
    classification: str,
    expected: dict[str, object],
    actual: dict[str, object],
    message: str,
    repair: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": identifier,
        "status": status,
        "classification": classification,
        "expected": expected,
        "actual": actual,
        "message": message,
    }
    if repair:
        result["repair"] = repair
    return result


def _unavailable_surface(identifier: str, expected: dict[str, object], actual: object) -> dict[str, object]:
    detail = actual if isinstance(actual, dict) else _unavailable("collector did not provide this surface")
    return _surface(
        identifier,
        "WARN",
        "unknown",
        expected,
        detail,
        "Surface was unavailable; it is not treated as a passing result.",
    )


def _phase(snapshot: dict[str, object]) -> str:
    github = snapshot.get("github_release")
    if isinstance(github, dict):
        metadata = github.get("metadata")
        if isinstance(metadata, dict):
            channel = _optional_string(metadata.get("channel"))
            if channel in {"candidate", "beta", "stable"}:
                return channel
    return "candidate"


def _check_target_surface(
    identifier: str, *, expected_release_id: str, actual: object, required: bool
) -> dict[str, object]:
    expected = {"release_id": expected_release_id}
    if _is_unavailable(actual):
        return _unavailable_surface(identifier, expected, actual)
    actual_id = _optional_string(actual.get("release_id")) if isinstance(actual, dict) else ""
    if not required:
        return _surface(
            identifier,
            "PASS",
            "safe_residue",
            {"required_for_phase": False},
            {"release_id": actual_id or None},
            "Surface is not required at this release phase.",
        )
    if actual_id == expected_release_id:
        return _surface(identifier, "PASS", "aligned", expected, {"release_id": actual_id}, "Release identity matches.")
    return _surface(
        identifier,
        "FAIL",
        "customer_visible_split",
        expected,
        {"release_id": actual_id or None},
        "Release identity disagrees with the requested release.",
        "Rerun desktop-release doctor after repairing the authoritative channel pointer with its expected generation.",
    )


def _appcast_surface(name: str, appcast: object, *, channel: str, release_id: str, required: bool) -> dict[str, object]:
    expected = {"channel": channel, "release_id": release_id}
    if _is_unavailable(appcast):
        return _unavailable_surface(name, expected, appcast)
    channels = appcast.get("channels") if isinstance(appcast, dict) else None
    actual_id = _optional_string(channels.get(channel)) if isinstance(channels, dict) else ""
    if not actual_id and not required:
        return _surface(name, "PASS", "safe_residue", expected, {}, "Channel is not required at this release phase.")
    if actual_id == release_id:
        return _surface(name, "PASS", "aligned", expected, {"channel": channel, "release_id": actual_id}, "Appcast channel matches.")
    return _surface(
        name,
        "FAIL",
        "customer_visible_split",
        expected,
        {"channel": channel, "release_id": actual_id or None},
        "Appcast channel does not resolve to the requested release.",
        "Repair the underlying pointer or legacy bridge, clear the desktop update cache, then rerun desktop-release doctor.",
    )


def _metric_report(metrics: object) -> list[dict[str, object]]:
    source = metrics if isinstance(metrics, dict) else {}
    report: list[dict[str, object]] = []
    for name in METRIC_CONTRACTS:
        value = source.get(name, _unavailable("metric collector did not provide this metric"))
        if _is_unavailable(value):
            report.append(
                {
                    "id": name,
                    "status": "unavailable",
                    "denominator": None,
                    "time_window": None,
                    "minimum_sample": None,
                    "value": None,
                    "reason": _optional_string(value.get("reason")),
                }
            )
            continue
        if not isinstance(value, dict):
            report.append(
                {
                    "id": name,
                    "status": "unavailable",
                    "denominator": None,
                    "time_window": None,
                    "minimum_sample": None,
                    "value": None,
                    "reason": "metric value had an invalid shape",
                }
            )
            continue
        report.append(
            {
                "id": name,
                "status": "available",
                "denominator": value.get("denominator"),
                "time_window": value.get("time_window"),
                "minimum_sample": value.get("minimum_sample"),
                "value": value.get("value"),
            }
        )
    return report


def evaluate_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    """Compare sanitized release surfaces without making a release mutation."""
    release_id = _optional_string(snapshot.get("release_id"))
    if not TAG_RE.fullmatch(release_id):
        raise ValueError("snapshot release_id must use v<version>+<build>-macos form")
    tag_sha = _optional_string(snapshot.get("tag_sha"))
    phase = _phase(snapshot)
    github = snapshot.get("github_release")
    if not isinstance(github, dict):
        github = _unavailable("collector did not provide GitHub release data")

    surfaces: list[dict[str, object]] = []
    if _is_unavailable(github):
        surfaces.append(_unavailable_surface("github_release", {"release_id": release_id}, github))
        metadata: dict[str, object] = {}
    else:
        metadata_raw = github.get("metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        assets = github.get("asset_names")
        asset_names = set(assets) if isinstance(assets, list) and all(isinstance(item, str) for item in assets) else set()
        expected_assets = {"Omi.zip"}
        missing_assets = sorted(expected_assets - asset_names)
        valid = (
            github.get("tag_name") == release_id
            and github.get("is_draft") is False
            and github.get("is_prerelease") is False
            and not missing_assets
        )
        surfaces.append(
            _surface(
                "github_release",
                "PASS" if valid else "FAIL",
                "aligned" if valid else "customer_visible_split",
                {"release_id": release_id, "published": True, "required_assets": sorted(expected_assets)},
                {
                    "release_id": github.get("tag_name"),
                    "is_draft": github.get("is_draft"),
                    "is_prerelease": github.get("is_prerelease"),
                    "missing_assets": missing_assets,
                },
                "GitHub release identity and required signed artifact are present."
                if valid
                else "GitHub release is missing, non-published, or does not match the requested release.",
            )
        )

        if phase == "stable" and github.get("stale_human_prose") is True:
            surfaces.append(
                _surface(
                    "human_release_prose",
                    "FAIL",
                    "reversible_drift",
                    {"channel": "stable", "stale_stable_blocker": False},
                    {"channel": "stable", "stale_stable_blocker": True},
                    "Machine metadata is stable while human prose still says stable is blocked.",
                    "Edit the GitHub release notes to remove the stale stable-blocker statement, then rerun desktop-release doctor.",
                )
            )
        else:
            surfaces.append(
                _surface(
                    "human_release_prose",
                    "PASS",
                    "aligned",
                    {"stale_stable_blocker": False},
                    {"stale_stable_blocker": bool(github.get("stale_human_prose"))},
                    "Human release prose does not contradict machine release state.",
                )
            )

    manifest = snapshot.get("manifest", _unavailable("collector did not provide the canonical manifest"))
    if _is_unavailable(manifest):
        surfaces.append(_unavailable_surface("canonical_manifest", {"release_id": release_id, "source_sha": tag_sha}, manifest))
    else:
        manifest_id = _optional_string(manifest.get("release_id")) if isinstance(manifest, dict) else ""
        manifest_sha = _optional_string(manifest.get("source_sha")) if isinstance(manifest, dict) else ""
        evidence = _optional_string(manifest.get("qualification", {}).get("evidence_asset")) if isinstance(manifest, dict) and isinstance(manifest.get("qualification"), dict) else ""
        metadata_evidence = _optional_string(metadata.get("qualifiedBetaEvidence"))
        required = phase in {"beta", "stable"}
        valid = manifest_id == release_id and manifest_sha == tag_sha and (not required or bool(evidence))
        if metadata_evidence and evidence and metadata_evidence != evidence:
            valid = False
        raw_plus_lookup = manifest_id == release_id.replace("+", " ")
        message = "Canonical manifest identity and qualification evidence match."
        repair = None
        if not valid:
            message = "Canonical manifest does not match the release identity or qualification evidence."
            repair = "Re-register the exact immutable manifest; use URL-encoded release IDs when reading Firestore paths."
        if raw_plus_lookup:
            message = "Canonical manifest ID contains a space where the release tag contains '+', indicating a raw-plus lookup error."
            repair = "Read the Firestore manifest through a URL-encoded release ID, then repair the manifest or pointer without changing the release tag."
        surfaces.append(
            _surface(
                "canonical_manifest",
                "PASS" if valid else "FAIL",
                "aligned" if valid else "reversible_drift",
                {"release_id": release_id, "source_sha": tag_sha, "qualification_evidence": metadata_evidence or None},
                {"release_id": manifest_id or None, "source_sha": manifest_sha or None, "qualification_evidence": evidence or None},
                message,
                repair,
            )
        )

    pointers = snapshot.get("pointers")
    pointers = pointers if isinstance(pointers, dict) else {}
    surfaces.append(
        _check_target_surface(
            "beta_pointer", expected_release_id=release_id, actual=pointers.get("beta", _unavailable("beta pointer was not collected")), required=phase in {"beta", "stable"}
        )
    )
    surfaces.append(
        _check_target_surface(
            "stable_pointer", expected_release_id=release_id, actual=pointers.get("stable", _unavailable("stable pointer was not collected")), required=phase == "stable"
        )
    )

    legacy = snapshot.get("legacy_release", _unavailable("legacy Firestore release was not collected"))
    if _is_unavailable(legacy):
        surfaces.append(_unavailable_surface("legacy_firestore_bridge", {"channel": phase}, legacy))
    else:
        actual_channel = _optional_string(legacy.get("channel")) if isinstance(legacy, dict) else ""
        actual_live = legacy.get("is_live") if isinstance(legacy, dict) else None
        required = phase in {"beta", "stable"}
        valid = not required or (actual_channel == phase and actual_live is True)
        surfaces.append(
            _surface(
                "legacy_firestore_bridge",
                "PASS" if valid else "FAIL",
                "aligned" if valid else "customer_visible_split",
                {"channel": phase, "is_live": required},
                {"channel": actual_channel or None, "is_live": actual_live},
                "Legacy bridge state matches the release phase." if valid else "Legacy appcast bridge does not match the release phase.",
            )
        )

    appcasts = snapshot.get("appcasts")
    appcasts = appcasts if isinstance(appcasts, dict) else {}
    current_channel = "stable" if phase == "stable" else "beta"
    required_appcast = phase in {"beta", "stable"}
    surfaces.append(
        _appcast_surface(
            "python_appcast", appcasts.get("python", _unavailable("Python appcast was not collected")), channel=current_channel, release_id=release_id, required=required_appcast
        )
    )
    surfaces.append(
        _appcast_surface(
            "rust_appcast", appcasts.get("rust", _unavailable("Rust appcast was not collected")), channel=current_channel, release_id=release_id, required=required_appcast
        )
    )

    static = snapshot.get("static")
    static = static if isinstance(static, dict) else {}
    static_surface = static.get(current_channel, _unavailable("static release route was not collected"))
    expected_static = {"channel": current_channel, "release_id": release_id}
    if _is_unavailable(static_surface):
        surfaces.append(_unavailable_surface("static_release_route", expected_static, static_surface))
    else:
        static_id = _optional_string(static_surface.get("release_id")) or _optional_string(static_surface.get("tag"))
        valid = not required_appcast or (static_id == release_id and static_surface.get("channel") == current_channel)
        surfaces.append(
            _surface(
                "static_release_route",
                "PASS" if valid else "FAIL",
                "aligned" if valid else "customer_visible_split",
                expected_static,
                {"channel": static_surface.get("channel"), "release_id": static_id or None},
                "Static route matches the active release channel." if valid else "Static route diverges from the active release channel.",
            )
        )

    backend = snapshot.get("backend", _unavailable("backend health was not collected"))
    if phase != "stable":
        surfaces.append(
            _surface("backend_health_identity", "PASS", "safe_residue", {"phase": phase}, {}, "Stable backend identity is not required before stable promotion.")
        )
    elif _is_unavailable(backend):
        surfaces.append(_unavailable_surface("backend_health_identity", {"release_tag": release_id, "release_sha": tag_sha}, backend))
    else:
        valid = backend.get("release_tag") == release_id and backend.get("release_sha") == tag_sha and backend.get("release_channel") == "stable"
        surfaces.append(
            _surface(
                "backend_health_identity",
                "PASS" if valid else "FAIL",
                "aligned" if valid else "customer_visible_split",
                {"release_tag": release_id, "release_sha": tag_sha, "release_channel": "stable"},
                {key: backend.get(key) for key in ("release_tag", "release_sha", "release_channel", "revision")},
                "Backend health reports the stable release identity." if valid else "Backend health identity differs from the stable release.",
            )
        )

    tracking = snapshot.get("tracking", _unavailable("tracking tag was not collected"))
    if phase != "stable":
        surfaces.append(_surface("tracking_tag", "PASS", "safe_residue", {"phase": phase}, {}, "Production tracking tag is not required before stable promotion."))
    elif _is_unavailable(tracking):
        surfaces.append(_unavailable_surface("tracking_tag", {"source_sha": tag_sha}, tracking))
    else:
        actual_sha = _optional_string(tracking.get("desktop_backend_prod_deployed_sha"))
        surfaces.append(
            _surface(
                "tracking_tag",
                "PASS" if actual_sha == tag_sha else "FAIL",
                "aligned" if actual_sha == tag_sha else "reversible_drift",
                {"source_sha": tag_sha},
                {"source_sha": actual_sha or None},
                "Production tracking tag matches the release source." if actual_sha == tag_sha else "Production tracking tag does not match the release source.",
            )
        )

    codemagic = snapshot.get("codemagic", _unavailable("Codemagic result was not collected"))
    if _is_unavailable(codemagic):
        surfaces.append(_unavailable_surface("codemagic_post_artifact", {"durable": True}, codemagic))
    else:
        artifact_status = _optional_string(codemagic.get("artifact_status")) if isinstance(codemagic, dict) else ""
        later_failure = _optional_string(codemagic.get("post_artifact_failure")) if isinstance(codemagic, dict) else ""
        valid = artifact_status == "passed" and not later_failure
        surfaces.append(
            _surface(
                "codemagic_post_artifact",
                "PASS" if valid else "WARN",
                "aligned" if valid else "unknown",
                {"artifact_status": "passed", "post_artifact_failure": None},
                {"artifact_status": artifact_status or None, "post_artifact_failure": later_failure or None},
                "Codemagic artifact and post-artifact state are durable." if valid else "Codemagic post-artifact state requires operator review.",
            )
        )

    metrics = _metric_report(snapshot.get("metrics"))
    if any(metric["status"] == "unavailable" for metric in metrics):
        surfaces.append(
            _surface(
                "operational_metrics",
                "WARN",
                "unknown",
                {"all_metrics_available": True},
                {"unavailable_metrics": [metric["id"] for metric in metrics if metric["status"] == "unavailable"]},
                "Unavailable metrics remain explicit and are not rendered as release success.",
            )
        )
    else:
        surfaces.append(
            _surface(
                "operational_metrics",
                "PASS",
                "aligned",
                {"all_metrics_available": True},
                {"all_metrics_available": True},
                "Operational metrics include their denominators, windows, and minimum samples.",
            )
        )

    statuses = {surface["status"] for surface in surfaces}
    overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "type": REPORT_TYPE,
        "release_id": release_id,
        "phase": phase,
        "generated_at": _utc_now(),
        "overall": overall,
        "surfaces": surfaces,
        "metrics": metrics,
        "privacy": {
            "raw_private_content_included": False,
            "omitted_fields": ["release prose", "prompts", "audio", "transcripts", "user identifiers", "credentials"],
        },
    }


def _summary(report: dict[str, object]) -> str:
    lines = [f"Desktop release doctor: {report['release_id']} ({report['phase']}) — {report['overall']}"]
    for surface in report["surfaces"]:
        lines.append(f"{surface['status']:<4} {surface['id']}: {surface['message']}")
        if "repair" in surface:
            lines.append(f"     repair: {surface['repair']}")
    unavailable = [metric["id"] for metric in report["metrics"] if metric["status"] == "unavailable"]
    if unavailable:
        lines.append(f"WARN operational metrics unavailable: {', '.join(unavailable)}")
    return "\n".join(lines) + "\n"


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
    summary = _summary(evidence)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
