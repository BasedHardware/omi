import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / ".github" / "scripts"
PROMOTE_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_beta.yml"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mark_beta = _load("mark_desktop_release_beta", "mark-desktop-release-beta.py")
prepare_beta = _load("prepare_desktop_beta_promotion", "prepare-desktop-beta-promotion.py")
nominate_stable = _load("nominate_desktop_stable_candidate", "nominate-desktop-stable-candidate.py")


def _release(body: str | None = None):
    tag = "v0.12.64+12064-macos"
    evidence = "qualification-evidence.json"
    default_body = f"""<!-- KEY_VALUE_START
isLive: false
channel: candidate
edSignature: signature
changelog: Fixed updates|Improved recovery
qualifiedBeta: true
qualifiedBetaAt: 2026-07-09T12:00:00Z
qualifiedBetaSha: {'a' * 40}
qualifiedBetaTier: 2
qualifiedBetaEvidence: {evidence}
KEY_VALUE_END -->"""
    return {
        "tagName": tag,
        "body": default_body if body is None else body,
        "isDraft": False,
        "isPrerelease": False,
        "publishedAt": "2026-07-09T11:00:00Z",
        "assets": [
            {"name": "Omi.zip", "url": "https://example.com/Omi.zip"},
            {"name": "omi.dmg", "url": "https://example.com/omi.dmg"},
            {"name": evidence, "url": "https://example.com/evidence.json"},
        ],
    }


def test_mark_beta_changes_only_visibility_fields():
    result = mark_beta.mark_beta(_release()["body"])
    assert "isLive: true" in result
    assert "channel: beta" in result
    assert "qualifiedBetaSha: " + "a" * 40 in result


def test_prepare_manifest_requires_exact_qualification_and_assets():
    manifest = prepare_beta.prepare_manifest(
        _release(),
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )
    assert manifest["build_number"] == 12064
    assert manifest["qualification"]["tier"] == "T2"
    assert manifest["changelog"] == ["Fixed updates", "Improved recovery"]


def test_prepare_manifest_accepts_legacy_qualification_metadata():
    release = _release()
    release["body"] = (
        release["body"]
        .replace("qualifiedBeta: true", "blessed: true")
        .replace("qualifiedBetaAt:", "blessedAt:")
        .replace("qualifiedBetaSha:", "blessedSha:")
        .replace("qualifiedBetaTier:", "blessedTier:")
        .replace("qualifiedBetaEvidence:", "blessedEvidence:")
    )
    manifest = prepare_beta.prepare_manifest(
        release,
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )
    assert manifest["qualification"]["metadata_source"] == "legacy"


def test_prepare_manifest_rejects_unqualified_candidate():
    release = _release()
    release["body"] = release["body"].replace("qualifiedBeta: true", "qualifiedBeta: false")
    with pytest.raises(SystemExit, match="qualifiedBeta"):
        prepare_beta.prepare_manifest(
            release,
            "v0.12.64+12064-macos",
            "a" * 40,
            "b" * 64,
            "c" * 64,
        )


def test_qualified_beta_can_be_nominated_as_stable_candidate():
    release = _release()
    release["body"] = (
        release["body"].replace("isLive: false", "isLive: true").replace("channel: candidate", "channel: beta")
    )
    body = nominate_stable.nominate(
        release,
        release_tag="v0.12.64+12064-macos",
        target_sha="a" * 40,
        beta_release_id="v0.12.64+12064-macos",
        nominator="release-operator",
        rationale="soak gates passed",
        soak_review="24h reviewed",
        telemetry_review="crash telemetry reviewed",
        release_notes_review="stable notes reviewed",
        nominated_at="2026-07-10T12:00:00Z",
    )
    assert "stableCandidate: true" in body
    assert "stableCandidateQualificationEvidence: qualification-evidence.json" in body


def test_stable_nomination_rejects_non_current_beta():
    release = _release()
    release["body"] = (
        release["body"].replace("isLive: false", "isLive: true").replace("channel: candidate", "channel: beta")
    )
    with pytest.raises(SystemExit, match="beta pointer"):
        nominate_stable.nominate(
            release,
            release_tag="v0.12.64+12064-macos",
            target_sha="a" * 40,
            beta_release_id="v0.12.63+12063-macos",
            nominator="release-operator",
            rationale="soak gates passed",
            soak_review="24h reviewed",
            telemetry_review="crash telemetry reviewed",
            release_notes_review="stable notes reviewed",
            nominated_at="2026-07-10T12:00:00Z",
        )


def test_beta_pointer_advances_before_legacy_visibility():
    workflow = PROMOTE_BETA_WORKFLOW.read_text()
    manifest = workflow.index("      - name: Register immutable release manifest")
    pointer = workflow.index("      - name: Advance explicit beta pointer")
    github = workflow.index("      - name: Mark GitHub release live beta")
    bridge = workflow.index("      - name: Bridge beta for legacy desktop clients")

    assert manifest < pointer < github < bridge
