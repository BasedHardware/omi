"""Pure comparison and rendering logic for the advisory desktop release doctor."""

from __future__ import annotations

import re
from datetime import datetime, timezone


SCHEMA_VERSION = 1
REPORT_TYPE = "desktop-release-evidence"
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")
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


def _unavailable(reason: str) -> dict[str, str]:
    return {"availability": "unavailable", "reason": reason}


def _is_unavailable(value: object) -> bool:
    return isinstance(value, dict) and value.get("availability") == "unavailable"


def _optional_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


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


def _github_surfaces(snapshot: dict[str, object], release_id: str, phase: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    github = snapshot.get("github_release")
    if not isinstance(github, dict):
        github = _unavailable("collector did not provide GitHub release data")
    if _is_unavailable(github):
        return [_unavailable_surface("github_release", {"release_id": release_id}, github)], {}

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
    release_surface = _surface(
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
    prose_surface = _surface(
        "human_release_prose",
        "PASS",
        "aligned",
        {"stale_stable_blocker": False},
        {"stale_stable_blocker": bool(github.get("stale_human_prose"))},
        "Human release prose does not contradict machine release state.",
    )
    if phase == "stable" and github.get("stale_human_prose") is True:
        prose_surface = _surface(
            "human_release_prose",
            "FAIL",
            "reversible_drift",
            {"channel": "stable", "stale_stable_blocker": False},
            {"channel": "stable", "stale_stable_blocker": True},
            "Machine metadata is stable while human prose still says stable is blocked.",
            "Edit the GitHub release notes to remove the stale stable-blocker statement, then rerun desktop-release doctor.",
        )
    return [release_surface, prose_surface], metadata


def _manifest_surface(snapshot: dict[str, object], release_id: str, tag_sha: str, phase: str, metadata: dict[str, object]) -> dict[str, object]:
    manifest = snapshot.get("manifest", _unavailable("collector did not provide the canonical manifest"))
    expected = {"release_id": release_id, "source_sha": tag_sha}
    if _is_unavailable(manifest):
        return _unavailable_surface("canonical_manifest", expected, manifest)

    manifest_id = _optional_string(manifest.get("release_id")) if isinstance(manifest, dict) else ""
    manifest_sha = _optional_string(manifest.get("source_sha")) if isinstance(manifest, dict) else ""
    qualification = manifest.get("qualification") if isinstance(manifest, dict) else None
    evidence = _optional_string(qualification.get("evidence_asset")) if isinstance(qualification, dict) else ""
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
    return _surface(
        "canonical_manifest",
        "PASS" if valid else "FAIL",
        "aligned" if valid else "reversible_drift",
        {**expected, "qualification_evidence": metadata_evidence or None},
        {"release_id": manifest_id or None, "source_sha": manifest_sha or None, "qualification_evidence": evidence or None},
        message,
        repair,
    )


def _channel_surfaces(snapshot: dict[str, object], release_id: str, phase: str) -> list[dict[str, object]]:
    pointers = snapshot.get("pointers")
    pointers = pointers if isinstance(pointers, dict) else {}
    surfaces = [
        _check_target_surface(
            "beta_pointer",
            expected_release_id=release_id,
            actual=pointers.get("beta", _unavailable("beta pointer was not collected")),
            required=phase in {"beta", "stable"},
        ),
        _check_target_surface(
            "stable_pointer",
            expected_release_id=release_id,
            actual=pointers.get("stable", _unavailable("stable pointer was not collected")),
            required=phase == "stable",
        ),
    ]
    current_channel = "stable" if phase == "stable" else "beta"
    required = phase in {"beta", "stable"}
    legacy = snapshot.get("legacy_release", _unavailable("legacy Firestore release was not collected"))
    if _is_unavailable(legacy):
        surfaces.append(_unavailable_surface("legacy_firestore_bridge", {"channel": phase}, legacy))
    else:
        actual_channel = _optional_string(legacy.get("channel")) if isinstance(legacy, dict) else ""
        actual_live = legacy.get("is_live") if isinstance(legacy, dict) else None
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
    surfaces.extend(
        (
            _appcast_surface(
                "python_appcast",
                appcasts.get("python", _unavailable("Python appcast was not collected")),
                channel=current_channel,
                release_id=release_id,
                required=required,
            ),
            _appcast_surface(
                "rust_appcast",
                appcasts.get("rust", _unavailable("Rust appcast was not collected")),
                channel=current_channel,
                release_id=release_id,
                required=required,
            ),
        )
    )
    static = snapshot.get("static")
    static = static if isinstance(static, dict) else {}
    static_surface = static.get(current_channel, _unavailable("static release route was not collected"))
    expected_static = {"channel": current_channel, "release_id": release_id}
    if _is_unavailable(static_surface):
        surfaces.append(_unavailable_surface("static_release_route", expected_static, static_surface))
        return surfaces
    static_id = _optional_string(static_surface.get("release_id")) or _optional_string(static_surface.get("tag"))
    valid = not required or (static_id == release_id and static_surface.get("channel") == current_channel)
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
    return surfaces


def _stable_surfaces(snapshot: dict[str, object], release_id: str, tag_sha: str, phase: str) -> list[dict[str, object]]:
    if phase != "stable":
        return [
            _surface("backend_health_identity", "PASS", "safe_residue", {"phase": phase}, {}, "Stable backend identity is not required before stable promotion."),
            _surface("tracking_tag", "PASS", "safe_residue", {"phase": phase}, {}, "Production tracking tag is not required before stable promotion."),
        ]

    surfaces: list[dict[str, object]] = []
    backend = snapshot.get("backend", _unavailable("backend health was not collected"))
    if _is_unavailable(backend):
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
    if _is_unavailable(tracking):
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
    return surfaces


def _operational_surfaces(snapshot: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    codemagic = snapshot.get("codemagic", _unavailable("Codemagic result was not collected"))
    if _is_unavailable(codemagic):
        surfaces = [_unavailable_surface("codemagic_post_artifact", {"durable": True}, codemagic)]
    else:
        artifact_status = _optional_string(codemagic.get("artifact_status")) if isinstance(codemagic, dict) else ""
        later_failure = _optional_string(codemagic.get("post_artifact_failure")) if isinstance(codemagic, dict) else ""
        valid = artifact_status == "passed" and not later_failure
        surfaces = [
            _surface(
                "codemagic_post_artifact",
                "PASS" if valid else "WARN",
                "aligned" if valid else "unknown",
                {"artifact_status": "passed", "post_artifact_failure": None},
                {"artifact_status": artifact_status or None, "post_artifact_failure": later_failure or None},
                "Codemagic artifact and post-artifact state are durable." if valid else "Codemagic post-artifact state requires operator review.",
            )
        ]

    metrics = _metric_report(snapshot.get("metrics"))
    unavailable = [metric["id"] for metric in metrics if metric["status"] == "unavailable"]
    surfaces.append(
        _surface(
            "operational_metrics",
            "WARN" if unavailable else "PASS",
            "unknown" if unavailable else "aligned",
            {"all_metrics_available": True},
            {"unavailable_metrics": unavailable} if unavailable else {"all_metrics_available": True},
            "Unavailable metrics remain explicit and are not rendered as release success."
            if unavailable
            else "Operational metrics include their denominators, windows, and minimum samples.",
        )
    )
    return surfaces, metrics


def _metric_report(metrics: object) -> list[dict[str, object]]:
    source = metrics if isinstance(metrics, dict) else {}
    report: list[dict[str, object]] = []
    for name in METRIC_CONTRACTS:
        value = source.get(name, _unavailable("metric collector did not provide this metric"))
        if _is_unavailable(value) or not isinstance(value, dict):
            reason = _optional_string(value.get("reason")) if isinstance(value, dict) else "metric value had an invalid shape"
            report.append(
                {
                    "id": name,
                    "status": "unavailable",
                    "denominator": None,
                    "time_window": None,
                    "minimum_sample": None,
                    "value": None,
                    "reason": reason,
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
    github_surfaces, metadata = _github_surfaces(snapshot, release_id, phase)
    channel_surfaces = _channel_surfaces(snapshot, release_id, phase)
    operational_surfaces, metrics = _operational_surfaces(snapshot)
    surfaces = [
        *github_surfaces,
        _manifest_surface(snapshot, release_id, tag_sha, phase, metadata),
        *channel_surfaces,
        *_stable_surfaces(snapshot, release_id, tag_sha, phase),
        *operational_surfaces,
    ]
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


def format_summary(report: dict[str, object]) -> str:
    lines = [f"Desktop release doctor: {report['release_id']} ({report['phase']}) — {report['overall']}"]
    for surface in report["surfaces"]:
        lines.append(f"{surface['status']:<4} {surface['id']}: {surface['message']}")
        if "repair" in surface:
            lines.append(f"     repair: {surface['repair']}")
    unavailable = [metric["id"] for metric in report["metrics"] if metric["status"] == "unavailable"]
    if unavailable:
        lines.append(f"WARN operational metrics unavailable: {', '.join(unavailable)}")
    return "\n".join(lines) + "\n"
