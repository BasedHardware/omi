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
QUALIFICATION_ADMISSION = SCRIPTS / "desktop_qualification_admission.py"


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
manifest_contract = _load("desktop_release_manifest", "desktop_release_manifest.py")


def _release(body: str | None = None):
    tag = "v0.12.64+12064-macos"
    evidence = "qualification-evidence-v0.12.64+12064-macos.json"
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
            {"name": "Omi.zip", "url": f"https://github.com/BasedHardware/omi/releases/download/{tag}/Omi.zip"},
            {"name": "omi.dmg", "url": f"https://github.com/BasedHardware/omi/releases/download/{tag}/omi.dmg"},
            {"name": evidence, "url": f"https://github.com/BasedHardware/omi/releases/download/{tag}/{evidence}"},
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
            "Omi.zip": {
                "url": "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip",
                "sha256": "b" * 64,
                "signature": "signature",
            },
            "omi.dmg": {
                "url": "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg",
                "sha256": "c" * 64,
            },
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
        qualification_evidence_sha256="sha256:" + "d" * 64,
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
    assert manifest["qualification_tier"] == "T2"
    assert manifest["qualification_passed"] is True
    assert manifest["qualification_evidence_asset"] == "qualification-evidence-v0.12.64+12064-macos.json"
    assert manifest["changelog"] == ["Fixed updates", "Improved recovery"]


def test_prepared_manifest_is_the_exact_immutable_object_registered_and_promoted():
    """Preparation, registration, and promotion share the v1 executable contract."""
    release = _release()
    tag = release["tagName"]
    for asset in release["assets"]:
        asset["url"] = f"https://github.com/BasedHardware/omi/releases/download/{tag}/{asset['name']}"
    evidence = _evidence()
    evidence["artifacts"]["Omi.zip"]["url"] = release["assets"][0]["url"]
    evidence["artifacts"]["omi.dmg"]["url"] = release["assets"][1]["url"]

    prepared = prepare_beta.prepare_manifest(
        release,
        tag,
        "a" * 40,
        "b" * 64,
        "c" * 64,
        qualification_evidence=evidence,
        qualification_evidence_sha256="sha256:" + "d" * 64,
    )

    accepted = manifest_contract.validate_manifest(prepared)
    registered = normalize_release_manifest(accepted)
    pointer = _build_pointer(
        {},
        registered,
        transition="promote",
        platform="macos",
        channel="beta",
        release_id=registered["release_id"],
        expected_generation=0,
    )

    assert registered == accepted
    assert pointer["release_id"] == accepted["release_id"]


def test_beta_workflow_has_only_the_narrow_server_owned_promotion_capability():
    workflow = PROMOTE_BETA_WORKFLOW.read_text(encoding="utf-8")
    assert "/v2/desktop/beta/promote-qualified" in workflow
    assert 'Authorization: Bearer ${BETA_PROMOTION_TOKEN}' in workflow
    assert '--data "{\\"tag\\":\\"${RELEASE_TAG}\\"}"' in workflow
    for forbidden in (
        "gcloud",
        "google-github-actions/auth",
        "GCP_CREDENTIALS",
        "ADMIN_KEY",
        "RELEASE_SECRET",
        "GCS_",
        "stable",
        "rollback",
        "emergency",
        "Backend-Rust",
    ):
        assert forbidden not in workflow


# omi-test-quality: source-inspection -- static contract: a CI shell publication path cannot be exercised hermetically.
def _canonical_candidate_reservation_contract(workflow: str) -> bool:
    """Recognize only an executable reserve immediately before canonical publication."""
    start = workflow.find("      - name: Create GitHub release\n")
    end = workflow.find("      - name: Dispatch trusted macOS beta qualification\n", start)
    if start < 0 or end < 0:
        return False
    publish = workflow[start:end]
    reserve = publish.find("/v2/desktop/beta/candidates/reserve")
    create = publish.find('gh release create "$CM_TAG"')
    guard = publish.rfind("set -euo pipefail", 0, reserve)
    return (
        guard >= 0
        and "set +e" not in publish[guard:reserve]
        and 'Authorization: Bearer ${BETA_PROMOTION_TOKEN}' in publish
        and '--data "{\\"tag\\":\\"${CM_TAG}\\"}"' in publish
        and reserve >= 0
        and create >= 0
        and reserve < create
    )


def test_codemagic_reserves_the_exact_candidate_before_every_canonical_publish_and_rejects_bypasses():
    workflow = CODEMAGIC_CONFIG.read_text(encoding="utf-8")
    assert _canonical_candidate_reservation_contract(workflow)

    publication = 'gh release create "$CM_TAG"'
    reserve = "/v2/desktop/beta/candidates/reserve"
    assert not _canonical_candidate_reservation_contract(
        workflow.replace(reserve, "/v2/desktop/beta/promote-qualified")
    )
    assert not _canonical_candidate_reservation_contract(
        workflow.replace(reserve, "reserve-placeholder").replace(publication, f"{publication}\n{reserve}")
    )
    assert not _canonical_candidate_reservation_contract(
        workflow.replace(
            '            set -euo pipefail\n            test -n "${BETA_PROMOTION_TOKEN:-}"',
            '            set +e\n            test -n "${BETA_PROMOTION_TOKEN:-}"',
        )
    )
    assert not _canonical_candidate_reservation_contract(
        workflow.replace('{\\"tag\\":\\"${CM_TAG}\\"}', '{\\"tag\\":\\"${CM_TAG}\\",\\"channel\\":\\"beta\\"}')
    )


def test_qualification_workflow_binds_immutable_controls_and_candidate_identity():
    """A later main commit cannot replace controls or invalidate tag-bound evidence."""
    admission = _load("desktop_qualification_admission", "desktop_qualification_admission.py")
    tag = "v0.12.64+12064-macos"
    candidate_sha = "a" * 40
    trusted_tag_run = {
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "BasedHardware/omi"},
        "head_repository": {"full_name": "BasedHardware/omi"},
        "event": "workflow_dispatch",
        "path": ".github/workflows/desktop_qualify_beta.yml",
        "head_branch": tag,
        "head_sha": candidate_sha,
        "name": "Qualify Desktop Beta Candidate",
    }

    admission.validate_qualification_run(trusted_tag_run, "BasedHardware/omi", tag, candidate_sha)
    drifted_main_run = {**trusted_tag_run, "head_branch": "main", "head_sha": "b" * 40}
    with pytest.raises(ValueError, match="candidate tag"):
        admission.validate_qualification_run(drifted_main_run, "BasedHardware/omi", tag, candidate_sha)

    codemagic = CODEMAGIC_CONFIG.read_text(encoding="utf-8")
    qualification = QUALIFY_BETA_WORKFLOW.read_text(encoding="utf-8")
    assert '-f release_tag="$CM_TAG" --ref "$CM_TAG"' in codemagic
    assert "ref: ${{ inputs.release_tag }}" in qualification
    assert "qualification-evidence-${RELEASE_TAG}.json" in qualification
    assert "gh release upload" in qualification


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
            qualification_evidence_sha256="sha256:" + "d" * 64,
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
        gate.write_text(json.dumps({"passed": True, "release_tag": release["tagName"], "source_sha": "a" * 40}))
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


def test_qualification_evidence_rejects_candidate_gate_from_a_different_source():
    release = _release()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = {}
        for name, content in (("Omi.zip", b"zip"), ("omi.dmg", b"dmg")):
            path = root / name
            path.write_bytes(content)
            paths[name] = path
        gate = root / "gate.json"
        gate.write_text(json.dumps({"passed": True, "release_tag": release["tagName"], "source_sha": "b" * 40}))

        with pytest.raises(ValueError, match="passing candidate gate"):
            qualification_evidence.build_evidence(
                release, release["tagName"], "a" * 40, {**paths, "__candidate_gate__": gate}
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
    assert manifest["zip_sha256"] == "sha256:" + "b" * 64


def test_stable_repair_bundle_uses_the_retained_manifest_installer_identity():
    manifest = _prepare()

    bundle = repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")

    assert bundle["repair_object"] == "stable/v0.12.64+12064-macos/repair.json"
    assert bundle["repair"]["channel"] == "stable"
    assert bundle["repair"]["installer_sha256"] == "sha256:" + "c" * 64
    assert (
        bundle["repair"]["installer_url"]
        == "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg"
    )
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
    assert manifest["qualification_passed"] is True


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
            qualification_evidence_sha256="sha256:" + "d" * 64,
        )


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


def test_qualification_publishes_the_single_artifact_pair_and_immutable_evidence_for_server_readback():
    qualification = QUALIFY_BETA_WORKFLOW.read_text()

    for asset in ("Omi.zip", "omi.dmg"):
        assert asset in qualification
    assert "actions/upload-artifact@v7" in qualification
    assert "--qualification-run-id \"$GITHUB_RUN_ID\"" in qualification
    assert "gh release upload" in qualification
    assert "qualification-evidence-${RELEASE_TAG}.json" in qualification
    assert "git tag -l 'v*-macos' --sort=-v:refname | head -1" not in qualification


def test_stable_promotion_remains_manual_only():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    assert "on:\n  workflow_dispatch:" in workflow
    assert "\n  schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "confirm:" in workflow
    assert "promote-stable" in workflow


def test_stable_workflow_reads_current_beta_and_owns_its_cas_inputs():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    assert "Read current pointers and capture workflow-owned CAS inputs" in workflow
    assert "Fetch exact retained qualified manifest" in workflow
    assert "actions/download-artifact@v7" not in workflow
    assert "prepare-desktop-beta-promotion.py" not in workflow
    assert "Register immutable release manifest" not in workflow
    assert "appcast.xml?identity=stable" in workflow
    assert "verify_stable_appcast.py" in workflow
    assert 'Authorization: Bearer $ACCESS_TOKEN' in workflow
    assert 'Authorization: Bearer ***' not in workflow
    assert 'ref: ${{ inputs.release_tag }}' in workflow
    assert "operation:" not in workflow
    assert "repoint" not in workflow


def test_stable_workflow_selects_its_own_trusted_qualification():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()
    assert (
        'actions/workflows/desktop_qualify_beta.yml/runs?event=workflow_dispatch&status=completed&per_page=100'
        in workflow
    )
    assert "desktop_qualification_admission.py" in workflow
    assert "qualification_run_id:" not in workflow


def test_beta_pointer_lost_response_retry_remains_exact_and_generation_stable():
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
    assert "EXPECTED_RELEASE_ID" in workflow
    assert "EXPECTED_GENERATION" in workflow
    assert "gcloud run deploy" not in workflow
