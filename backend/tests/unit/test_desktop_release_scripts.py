import importlib.util
import json
from pathlib import Path
import tempfile

import pytest
from database.desktop_update_channels import _build_pointer, normalize_release_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / ".github" / "scripts"
PROMOTE_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_beta.yml"
PROMOTE_PROD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_prod.yml"
QUALIFY_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_qualify_beta.yml"
CODEMAGIC_CONFIG = REPO_ROOT / "codemagic.yaml"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mark_beta = _load("mark_desktop_release_beta", "mark-desktop-release-beta.py")
prepare_beta = _load("prepare_desktop_beta_promotion", "prepare-desktop-beta-promotion.py")
repair_installer = _load("desktop_repair_installer", "desktop_repair_installer.py")
qualification_evidence = _load("desktop_qualification_evidence", "desktop_qualification_evidence.py")


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


def _evidence():
    return {
        "schema_version": 1,
        "release_id": "v0.12.64+12064-macos",
        "source_sha": "a" * 40,
        "source_qualification": {"passed": True, "tier": "T2", "subject": "source-built named-bundle"},
        "signed_artifact_verification": {"passed": True, "subject": "exact signed ZIP/DMG bytes"},
        "artifacts": {
            "Omi.zip": {"url": "https://example.com/Omi.zip", "sha256": "b" * 64, "signature": "signature"},
            "omi.dmg": {"url": "https://example.com/omi.dmg", "sha256": "c" * 64},
        },
    }


def _prepare(release=None, *, allow_stable_channel=False):
    return prepare_beta.prepare_manifest(
        _release() if release is None else release,
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
        qualification_evidence=_evidence(),
        allow_stable_channel=allow_stable_channel,
    )


def test_mark_beta_changes_only_visibility_fields():
    result = mark_beta.mark_beta(_release()["body"])
    assert "isLive: true" in result
    assert "channel: beta" in result
    assert "qualifiedBetaSha: " + "a" * 40 in result


def test_prepare_manifest_requires_exact_qualification_and_assets():
    manifest = _prepare()
    assert manifest["build_number"] == 12064
    assert manifest["qualification"]["tier"] == "T2"
    assert manifest["qualification"]["source"] == "trusted_github_actions_artifact"
    assert manifest["qualification"]["evidence_asset"] == "qualification-evidence.json"
    assert manifest["qualification"]["source_subject"] == "source-built named-bundle"
    assert manifest["qualification"]["signed_artifact_subject"] == "exact signed ZIP/DMG bytes"
    assert manifest["changelog"] == ["Fixed updates", "Improved recovery"]


def test_beta_static_redirect_uses_the_qualified_dmg_on_every_surface():
    workflow = PROMOTE_BETA_WORKFLOW.read_text(encoding="utf-8")
    redirect = workflow.split("Update existing beta download redirect", 1)[1]
    assert redirect.count('manifest["dmg_url"]') == 1
    assert redirect.count("['dmg_url']") == 2
    assert "beta_dmg_url" not in redirect


def test_prepare_manifest_rejects_caller_hashes_that_do_not_match_trusted_evidence():
    """Promotion can only bind bytes independently recorded by qualification."""
    evidence = {
        "schema_version": 1,
        "release_id": "v0.12.64+12064-macos",
        "source_sha": "a" * 40,
        "artifacts": {
            "Omi.zip": {"url": "https://example.com/Omi.zip", "sha256": "b" * 64, "signature": "signature"},
            "omi.dmg": {"url": "https://example.com/omi.dmg", "sha256": "c" * 64},
        },
        "source_qualification": {"passed": True, "tier": "T2", "subject": "source-built named-bundle"},
        "signed_artifact_verification": {"passed": True, "subject": "exact signed ZIP/DMG bytes"},
    }

    with pytest.raises(ValueError, match="qualification evidence"):
        prepare_beta.prepare_manifest(
            _release(),
            "v0.12.64+12064-macos",
            "a" * 40,
            "1" * 64,
            "2" * 64,
            qualification_evidence=evidence,
        )


def test_qualified_artifact_replacement_is_rejected_before_beta_or_stable_pointering():
    release = _release()
    release["assets"] = [
        {"name": name, "url": f"https://example.com/{name}", "digest": ""} for name in ("Omi.zip", "omi.dmg")
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = {}
        for name, content in (
            ("Omi.zip", b"stable zip"),
            ("omi.dmg", b"stable dmg"),
        ):
            path = root / name
            path.write_bytes(content)
            paths[name] = path
        gate = root / "gate.json"
        gate.write_text(json.dumps({"passed": True, "release_tag": release["tagName"]}))
        evidence = qualification_evidence.build_evidence(
            release, release["tagName"], "a" * 40, {**paths, "__candidate_gate__": gate}
        )
        paths["Omi.zip"].write_bytes(b"replacement")
        with pytest.raises(ValueError, match="Omi.zip hash differs"):
            qualification_evidence.verify_evidence(
                evidence,
                release,
                release["tagName"],
                "a" * 40,
                {name: qualification_evidence.file_sha256(path) for name, path in paths.items()},
            )


def test_local_candidate_evidence_beta_stable_repoint_and_retry_simulation():
    """No-cloud release-path simulation keeps both pointers bound to exact bytes."""
    manifest = normalize_release_manifest(_prepare())
    beta = _build_pointer(
        {},
        manifest,
        transition="promote",
        platform="macos",
        channel="beta",
        release_id=manifest["release_id"],
        expected_generation=0,
    )
    stable = _build_pointer(
        {},
        manifest,
        transition="promote",
        platform="macos",
        channel="stable",
        release_id=manifest["release_id"],
        expected_generation=0,
    )
    retry = _build_pointer(
        stable,
        manifest,
        transition="promote",
        platform="macos",
        channel="stable",
        release_id=manifest["release_id"],
        expected_generation=0,
    )
    assert retry is stable
    retained = dict(manifest, release_id="v0.12.63+12063-macos", version="0.12.63+12063", build_number=12063)
    repointed = _build_pointer(
        stable,
        retained,
        transition="repoint",
        platform="macos",
        channel="stable",
        release_id=retained["release_id"],
        expected_generation=stable["generation"],
        expected_current_release_id=stable["release_id"],
    )
    assert beta["release_id"] == manifest["release_id"]
    assert repointed["release_id"] == retained["release_id"]
    assert manifest["zip_sha256"] == "b" * 64


def test_stable_repair_bundle_uses_the_retained_manifest_installer_identity():
    manifest = _prepare()

    bundle = repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")

    assert bundle["repair_object"] == "stable/v0.12.64+12064-macos/repair.json"
    assert bundle["repair"]["channel"] == "stable"
    assert bundle["repair"]["installer_sha256"] == "c" * 64
    assert bundle["repair"]["installer_url"] == "https://example.com/omi.dmg"
    assert "/Applications" in bundle["landing_page"]


@pytest.mark.parametrize("field, value", [("platform", "windows"), ("dmg_sha256", "not-a-digest")])
def test_stable_repair_bundle_rejects_incomplete_or_wrong_platform_manifest(field, value):
    manifest = _prepare()
    manifest[field] = value

    with pytest.raises(ValueError):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


def test_stable_repair_bundle_requires_the_release_publication_time():
    manifest = _prepare()
    manifest.pop("published_at")

    with pytest.raises(ValueError, match="published_at"):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


def test_prepare_manifest_ignores_mutable_legacy_qualification_metadata():
    release = _release()
    release["body"] = (
        release["body"]
        .replace("qualifiedBeta: true", "blessed: true")
        .replace("qualifiedBetaAt:", "blessedAt:")
        .replace("qualifiedBetaSha:", "blessedSha:")
        .replace("qualifiedBetaTier:", "blessedTier:")
        .replace("qualifiedBetaEvidence:", "blessedEvidence:")
    )
    manifest = _prepare(release)
    assert manifest["qualification"]["source"] == "trusted_github_actions_artifact"


def test_prepare_manifest_allows_an_already_stable_release_only_for_repair_retries():
    release = _release()
    release["body"] = (
        release["body"].replace("isLive: false", "isLive: true").replace("channel: candidate", "channel: stable")
    )

    with pytest.raises(SystemExit, match="candidate or beta"):
        _prepare(release)

    manifest = _prepare(release, allow_stable_channel=True)
    assert manifest["release_id"] == "v0.12.64+12064-macos"


def test_prepare_manifest_rejects_unqualified_candidate():
    release = _release()
    evidence = _evidence()
    evidence["source_qualification"] = {"passed": False, "tier": "T2"}
    with pytest.raises(ValueError, match="source-built named-bundle T2"):
        prepare_beta.prepare_manifest(
            release,
            "v0.12.64+12064-macos",
            "a" * 40,
            "b" * 64,
            "c" * 64,
            qualification_evidence=evidence,
        )


def test_beta_pointer_advances_before_legacy_visibility():
    workflow = PROMOTE_BETA_WORKFLOW.read_text()
    manifest = workflow.index("      - name: Register immutable release manifest")
    pointer = workflow.index("      - name: Advance explicit beta pointer")
    github = workflow.index("      - name: Mark GitHub release live beta")
    bridge = workflow.index("      - name: Bridge beta for legacy desktop clients")

    assert manifest < pointer < github < bridge


def test_automatic_beta_is_pauseable_and_rejects_stale_tags():
    workflow = PROMOTE_BETA_WORKFLOW.read_text()
    automatic_gate = workflow.index("      - name: Validate automatic beta request")
    candidate_download = workflow.index("      - name: Download and validate qualified candidate")

    assert "automatic:" in workflow
    assert "DESKTOP_AUTO_BETA_ENABLED" in workflow
    assert "newest is $LATEST_TAG" in workflow
    assert "git for-each-ref --count=1 --sort=-v:refname" in workflow
    assert "git tag -l 'v*-macos' --sort=-v:refname | head -1" not in workflow
    assert automatic_gate < candidate_download


def test_qualification_is_serialized_by_tag_and_retried_without_release_body_state():
    codemagic = CODEMAGIC_CONFIG.read_text()
    dispatch = codemagic[codemagic.index("      - name: Dispatch trusted macOS beta qualification") :]
    qualification = QUALIFY_BETA_WORKFLOW.read_text()

    assert "duplicate dispatches" in dispatch
    assert 'gh release edit "$CM_TAG"' not in dispatch
    assert "group: desktop-beta-qualification-${{ inputs.release_tag }}" in qualification
    assert "cancel-in-progress: false" in qualification
    assert "for attempt in 1 2 3" in dispatch
    assert "desktop_qualification_dispatch.py" not in qualification
    assert "steps.candidate.outcome == 'success' && steps.qualify.outcome == 'success'" in qualification


def test_qualification_and_promotion_bind_the_single_artifact_pair_to_an_immutable_run_artifact():
    qualification = QUALIFY_BETA_WORKFLOW.read_text()
    promotion = PROMOTE_BETA_WORKFLOW.read_text()

    for asset in ("Omi.zip", "Omi.dmg", "omi.dmg"):
        assert asset in qualification
        assert asset in promotion
    assert "actions/upload-artifact@v7" in qualification
    assert "qualification_run_id" in promotion
    assert "actions/download-artifact@v7" in promotion
    assert "--beta-zip-sha256" not in promotion
    assert "--beta-dmg-sha256" not in promotion
    assert "git tag -l 'v*-macos' --sort=-v:refname | head -1" not in qualification


def test_stable_promotion_remains_manual_only():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    assert "on:\n  workflow_dispatch:" in workflow
    assert "\n  schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "confirm:" in workflow
    assert "promote-stable" in workflow


def test_stable_workflow_allows_retained_repoint_but_requires_current_beta_for_promote_and_safe_retries():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    assert "check_stable_pointer_precondition.py" in workflow
    assert "Fetch exact retained qualified manifest" in workflow
    assert "actions/download-artifact@v7" not in workflow
    assert "prepare-desktop-beta-promotion.py" not in workflow
    assert "Register immutable release manifest" not in workflow
    assert "appcast.xml?identity=stable" in workflow
    assert "verify_stable_appcast.py" in workflow
    assert 'Authorization: Bearer $ACCESS_TOKEN' in workflow
    assert 'Authorization: Bearer ***' not in workflow
    assert 'ref: main' in workflow


def test_qualification_run_is_bound_to_the_exact_main_dispatch_and_workflow():
    for workflow in (PROMOTE_BETA_WORKFLOW.read_text(), PROMOTE_PROD_WORKFLOW.read_text()):
        assert 'gh api "repos/$REPO/actions/runs/$QUALIFICATION_RUN_ID"' in workflow
        assert 'jq -r .repository.full_name' in workflow
        assert 'jq -r .head_repository.full_name' in workflow
        assert 'jq -r .event' in workflow
        assert '= workflow_dispatch' in workflow
        assert 'jq -r .path' in workflow
        assert '= .github/workflows/desktop_qualify_beta.yml' in workflow
        assert 'jq -r .head_branch' in workflow
        assert '= main' in workflow
        assert 'jq -r .head_sha' in workflow


def test_beta_promotion_controls_are_pinned_to_main_and_only_accept_lost_response_generation_plus_one():
    workflow = PROMOTE_BETA_WORKFLOW.read_text()

    assert 'ref: main' in workflow
    manifest = normalize_release_manifest(_prepare())
    current = {
        "platform": "macos",
        "channel": "beta",
        "release_id": manifest["release_id"],
        "version": manifest["version"],
        "build_number": 12064,
        "generation": 4,
    }
    assert (
        _build_pointer(
            current,
            manifest,
            transition="promote",
            platform="macos",
            channel="beta",
            release_id=manifest["release_id"],
            expected_generation=3,
        )
        is current
    )


def test_stable_repair_is_published_immutably_before_stable_pointer_advances():
    """Static wiring contract: a stable pointer is never advanced ahead of its repair artifact."""
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    immutable_repair = workflow.index("      - name: Publish immutable stable repair installer")
    pointer = workflow.index("      - name: Advance explicit stable pointer")
    legacy_bridge = workflow.index("      - name: Bridge stable for legacy desktop clients")
    latest_route = workflow.index("      - name: Publish latest stable repair route")

    assert immutable_repair < pointer < legacy_bridge < latest_route
    assert "Fetch exact retained qualified manifest" in workflow
    assert "gh release download" not in workflow
    assert "--if-generation-match=0" in workflow
    assert "manifest_sha256" in workflow
    assert '"$BASE/macos-beta"' in workflow
    assert "expected_current_release_id:" in workflow
    assert "expected_generation:" in workflow
    assert "gcloud run deploy" not in workflow
