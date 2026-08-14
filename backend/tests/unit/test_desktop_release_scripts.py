import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import tempfile

import pytest
from database.desktop_update_channels import _build_pointer, normalize_release_manifest
from tests.unit.fixtures.desktop_release_manifest import make_desktop_release_manifest as _manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / ".github" / "scripts"
PROMOTE_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_beta.yml"
PROMOTE_PROD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_prod.yml"
QUALIFY_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_qualify_beta.yml"
CODEMAGIC_CONFIG = REPO_ROOT / "codemagic.yaml"
DMGBUILD_SETTINGS = REPO_ROOT / "desktop" / "macos" / "dmg-assets" / "dmgbuild_settings.py"
QUALIFICATION_ADMISSION = SCRIPTS / "desktop_qualification_admission.py"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair_installer = _load("desktop_repair_installer", "desktop_repair_installer.py")
qualification_evidence = _load("desktop_qualification_evidence", "desktop_qualification_evidence.py")
manifest_contract = _load("desktop_release_manifest", "desktop_release_manifest.py")
promotion_policy = _load("desktop_prod_promotion_policy", "check-desktop-prod-promotion-policy.py")


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


def _beta_uid_continuity() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "firebase_auth": {
            "project": "based-hardware",
            "release_probe_uid": "omi-release-probe",
            "token_claims": "production_project_verified",
        },
        "development_serving_reads": {
            "python": {
                "url": "https://api.omiapi.com/",
                "production_authority_url": "https://api.omi.me/",
                "operation": "production_sentinel_development_read_cleanup",
                "status": "passed",
            },
            "desktop_backend": {
                "url": "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/",
                "operation": "authenticated_proxy_authority_read",
                "status": "passed",
            },
        },
        "redaction": {"customer_content_printed": False, "tokens_printed": False},
    }


def test_canonical_manifest_is_the_exact_immutable_object_registered_and_promoted():
    """Validation, registration, and promotion share the v1 executable contract."""
    accepted = manifest_contract.validate_manifest(_manifest())
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


# omi-test-quality: source-inspection -- static contract: reusable workflow capability boundary.
def test_beta_workflow_has_only_the_narrow_server_owned_promotion_capability():
    workflow = PROMOTE_BETA_WORKFLOW.read_text(encoding="utf-8")
    assert "/v2/desktop/beta/promote-candidate" in workflow
    assert 'Authorization: Bearer ${BETA_PROMOTION_TOKEN}' in workflow
    assert '--data "{\\"tag\\":\\"${RELEASE_TAG}\\"}"' in workflow
    assert "workflow_call:" in workflow
    assert "workflow_run:" not in workflow
    assert "desktop_qualify_beta.yml" not in workflow
    assert "qualification_run_id" not in workflow
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
    ):
        assert forbidden not in workflow


# omi-test-quality: source-inspection -- static contract: a CI shell publication path cannot be exercised hermetically.
def _canonical_candidate_reservation_contract(workflow: str) -> bool:
    """Recognize only an executable reserve immediately before canonical publication."""
    start = workflow.find("      - name: Create GitHub release\n")
    end = workflow.find("      - name: Promote signed candidate to Omi Beta\n", start)
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
        workflow.replace(reserve, "/v2/desktop/beta/promote-candidate")
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


def test_codemagic_promotes_exact_candidate_without_dispatching_qualification():
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
    manual_main_run = {**trusted_tag_run, "head_branch": "main", "head_sha": "b" * 40}
    admission.validate_qualification_run(manual_main_run, "BasedHardware/omi", tag, candidate_sha)
    untrusted_control_run = {**trusted_tag_run, "head_branch": "release", "head_sha": "b" * 40}
    with pytest.raises(ValueError, match="candidate tag controls or trusted main controls"):
        admission.validate_qualification_run(untrusted_control_run, "BasedHardware/omi", tag, candidate_sha)
    malformed_manual_run = {**trusted_tag_run, "head_branch": "main", "head_sha": "not-a-commit"}
    with pytest.raises(ValueError, match="immutable dispatch SHA"):
        admission.validate_qualification_run(malformed_manual_run, "BasedHardware/omi", tag, candidate_sha)

    codemagic = CODEMAGIC_CONFIG.read_text(encoding="utf-8")
    qualification = QUALIFY_BETA_WORKFLOW.read_text(encoding="utf-8")
    assert "/v2/desktop/beta/promote-candidate" in codemagic
    assert '--data "{\\"tag\\":\\"${CM_TAG}\\"}"' in codemagic
    assert "gh workflow run desktop_qualify_beta.yml" not in codemagic
    assert 'git -C "$source_dir" checkout --quiet --detach "refs/tags/$RELEASE_TAG"' in qualification
    # The release attachment is content-addressed from the exact checked-out
    # candidate SHA and evidence digest, not a mutable tag-only filename.
    assert 'asset="qualification-evidence-${TARGET_SHA}-${digest}.json"' in qualification
    assert 'digest=$(shasum -a 256 "$QUALIFICATION_STAGE/qualification-evidence.json"' in qualification
    assert "gh release upload" in qualification
    assert "desktop-qualification-backend-compatibility-" in qualification


def test_codemagic_produces_canonical_app_and_strictly_verifiable_dmg():
    workflow = CODEMAGIC_CONFIG.read_text(encoding="utf-8")
    dmg_helper = (REPO_ROOT / "desktop/macos/scripts/create-desktop-dmgs.sh").read_text(encoding="utf-8")
    smoke = (REPO_ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh").read_text(encoding="utf-8")
    assert workflow.count('APP_NAME: "Omi"') == 1
    assert 'APP_NAME: "omi"' not in workflow
    assert "scripts/create-desktop-dmgs.sh" in workflow
    assert "xattr -d com.apple.FinderInfo" in dmg_helper
    assert "xattr -d com.apple.ResourceFork" in dmg_helper
    assert 'codesign --verify --deep --strict --verbose=2 "$staged_app"' in dmg_helper
    assert 'xcrun stapler validate "$staged_app"' in dmg_helper
    assert 'dmg_app_name="$(expected_app_bundle_name)"' in smoke
    assert 'dmg_app="$DMG_MOUNTPOINT/$dmg_app_name"' in smoke
    assert "DMG-contained $dmg_app_name failed deep strict codesign verification" in smoke


def test_dmgbuild_does_not_attach_finder_info_to_the_signed_app():
    settings = runpy.run_path(
        str(DMGBUILD_SETTINGS),
        init_globals={"defines": {"app_name": "Omi", "app_path": "/tmp/Omi.app"}},
    )

    assert settings.get("hide_extensions", []) == []


def test_universal_release_stages_and_smokes_both_sharp_architectures():
    prepare = (REPO_ROOT / "desktop/macos/scripts/prepare-agent-runtime.sh").read_text(encoding="utf-8")
    smoke = (REPO_ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh").read_text(encoding="utf-8")
    assert "stage_darwin_sharp_arches" in prepare
    assert "for package_arch in arm64 x64" in prepare
    assert 'npm install --prefix "$overlay" --force' in prepare
    assert "@img/sharp-darwin-$package_arch@$sharp_version" in prepare
    assert "@img/sharp-libvips-darwin-$package_arch@$libvips_version" in prepare
    assert "for sharp_arch in arm64 x64" in prepare
    assert "agent runtime missing Sharp/libvips darwin-$sharp_arch pair" in smoke


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
        proof = root / "beta-uid-continuity.json"
        proof.write_text(json.dumps(_beta_uid_continuity()), encoding="utf-8")
        evidence = qualification_evidence.build_evidence(
            release, release["tagName"], "a" * 40, {**paths, "__candidate_gate__": gate}, beta_uid_continuity_path=proof
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


def test_qualification_evidence_accepts_the_side_by_side_beta_artifact_pair():
    # INV-BETA-1: releases shipping the Omi Beta identity qualify all four
    # artifacts; the beta zip's appcast signature comes from betaEdSignature.
    body = _release()["body"].replace(
        "edSignature: signature", "edSignature: signature\nbetaEdSignature: beta-signature"
    )
    release = _release(body=body)
    release["assets"] = [
        {"name": name, "url": f"https://example.com/{name}", "digest": ""}
        for name in ("Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg")
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = {}
        for name, content in (
            ("Omi.zip", b"stable zip"),
            ("omi.dmg", b"stable dmg"),
            ("Omi.Beta.zip", b"beta zip"),
            ("omi-beta.dmg", b"beta dmg"),
        ):
            path = root / name
            path.write_bytes(content)
            paths[name] = path
        gate = root / "gate.json"
        gate.write_text(json.dumps({"passed": True, "release_tag": release["tagName"], "source_sha": "a" * 40}))
        proof = root / "beta-uid-continuity.json"
        proof.write_text(json.dumps(_beta_uid_continuity()), encoding="utf-8")
        evidence = qualification_evidence.build_evidence(
            release,
            release["tagName"],
            "a" * 40,
            {**paths, "__candidate_gate__": gate},
            beta_uid_continuity_path=proof,
        )
        assert set(evidence["artifacts"]) == {"Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg"}
        assert evidence["artifacts"]["Omi.Beta.zip"]["signature"] == "beta-signature"

        # A partial beta pair must fail closed.
        partial = dict(paths)
        del partial["omi-beta.dmg"]
        with pytest.raises(ValueError, match="exact qualified"):
            qualification_evidence.build_evidence(
                release, release["tagName"], "a" * 40, {**partial, "__candidate_gate__": gate}
            )


def test_qualification_evidence_cli_accepts_the_beta_artifact_pair_end_to_end():
    # Regression: the qualify workflow passes --asset Omi.Beta.zip=…/omi-beta.dmg=…;
    # the CLI must accept them through the same shape the workflow uses.
    import subprocess
    import sys

    body = _release()["body"].replace(
        "edSignature: signature", "edSignature: signature\nbetaEdSignature: beta-signature"
    )
    release = _release(body=body)
    release["assets"] = [
        {"name": name, "url": f"https://example.com/{name}", "digest": ""}
        for name in ("Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg")
    ]
    script = Path(__file__).parents[3] / ".github/scripts/desktop_qualification_evidence.py"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        release_json = root / "release.json"
        # gh release view uses tagName; the CLI reads the same shape.
        release_json.write_text(json.dumps(release))
        asset_args = []
        for name, content in (
            ("Omi.zip", b"stable zip"),
            ("omi.dmg", b"stable dmg"),
            ("Omi.Beta.zip", b"beta zip"),
            ("omi-beta.dmg", b"beta dmg"),
        ):
            path = root / name
            path.write_bytes(content)
            asset_args += ["--asset", f"{name}={path}"]
        gate = root / "gate.json"
        gate.write_text(json.dumps({"passed": True, "release_tag": release["tagName"], "source_sha": "a" * 40}))
        proof = root / "beta-uid-continuity.json"
        proof.write_text(json.dumps(_beta_uid_continuity()), encoding="utf-8")
        evidence_out = root / "evidence.json"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "build",
                "--release-json",
                str(release_json),
                "--release-tag",
                release["tagName"],
                "--source-sha",
                "a" * 40,
                "--candidate-gate",
                str(gate),
                "--beta-uid-continuity-evidence",
                str(proof),
                *asset_args,
                "--evidence",
                str(evidence_out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        written = json.loads(evidence_out.read_text(encoding="utf-8"))
        assert set(written["artifacts"]) == {"Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg"}


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
    manifest = normalize_release_manifest(_manifest())
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
    manifest = _manifest()

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
    manifest = _manifest()
    manifest[field] = value

    with pytest.raises(ValueError):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


def test_stable_repair_bundle_requires_the_release_publication_time():
    manifest = _manifest()
    manifest.pop("published_at")

    with pytest.raises(ValueError, match="published_at"):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


def test_codemagic_beta_promotion_is_bounded_idempotent_and_has_no_release_body_state():
    codemagic = CODEMAGIC_CONFIG.read_text(encoding="utf-8")
    promotion = codemagic[codemagic.index("      - name: Promote signed candidate to Omi Beta") :]

    assert "Retries are idempotent" in promotion
    assert 'gh release edit "$CM_TAG"' not in promotion
    assert "for attempt in 1 2 3" in promotion
    assert "ERROR: Beta promotion was not confirmed after bounded retry" in promotion
    assert promotion.index("ERROR: Beta promotion was not confirmed after bounded retry") < promotion.rindex("exit 1")
    assert "desktop_qualify_beta.yml" not in promotion


def test_qualification_publishes_the_single_artifact_pair_and_immutable_evidence_for_server_readback():
    qualification = QUALIFY_BETA_WORKFLOW.read_text(encoding="utf-8")

    for asset in ("Omi.zip", "omi.dmg"):
        assert asset in qualification
    assert "actions/upload-artifact@v7" in qualification
    assert "--qualification-run-id \"$GITHUB_RUN_ID\"" in qualification
    assert "gh release upload" in qualification
    assert 'asset="qualification-evidence-${TARGET_SHA}-${digest}.json"' in qualification
    assert '"$QUALIFICATION_STAGE/qualification-evidence.json#$asset"' in qualification
    assert "git tag -l 'v*-macos' --sort=-v:refname | head -1" not in qualification


def test_stable_promotion_remains_manual_only():
    workflow = PROMOTE_PROD_WORKFLOW.read_text(encoding="utf-8")

    assert "on:\n  workflow_dispatch:" in workflow
    assert "\n  schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "confirm:" in workflow
    assert "promote-stable" in workflow


def test_stable_promotion_policy_guard_matches_the_workflow_owned_contract():
    assert promotion_policy.validate(PROMOTE_PROD_WORKFLOW.read_text(encoding="utf-8")) == []


def test_stable_workflow_reads_current_beta_and_owns_its_cas_inputs():
    workflow = PROMOTE_PROD_WORKFLOW.read_text(encoding="utf-8")

    assert "Read current pointers and capture workflow-owned CAS inputs" in workflow
    assert "Fetch exact retained Beta manifest" in workflow
    assert "actions/download-artifact@v7" not in workflow
    assert "Register immutable release manifest" not in workflow
    assert "appcast.xml?identity=stable" in workflow
    assert "verify_stable_appcast.py" in workflow
    assert 'Authorization: Bearer $ACCESS_TOKEN' in workflow
    assert 'Authorization: Bearer ***' not in workflow
    assert 'ref: ${{ inputs.release_tag }}' in workflow
    assert "operation:" not in workflow
    assert "repoint" not in workflow


def test_stable_workflow_uses_current_beta_manifest_without_qualification_lookup():
    workflow = PROMOTE_PROD_WORKFLOW.read_text(encoding="utf-8")
    assert "desktop_qualify_beta.yml" not in workflow
    assert "desktop_qualification_admission.py" not in workflow
    assert 'text(beta, "release_id") != os.environ["RELEASE_TAG"]' in workflow


def test_beta_pointer_lost_response_retry_remains_exact_and_generation_stable():
    manifest = normalize_release_manifest(_manifest())
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
    workflow = PROMOTE_PROD_WORKFLOW.read_text(encoding="utf-8")

    immutable_repair = workflow.index("      - name: Publish immutable stable repair installer")
    pointer = workflow.index("      - name: Advance explicit stable pointer")
    legacy_bridge = workflow.index("      - name: Bridge stable for legacy desktop clients")
    latest_route = workflow.index("      - name: Publish latest stable repair route")

    assert immutable_repair < pointer < legacy_bridge < latest_route
    assert "Fetch exact retained Beta manifest" in workflow
    assert "gh release download" not in workflow
    assert "--if-generation-match=0" in workflow
    assert "manifest_sha256" in workflow
    assert '"$BASE/macos-beta"' in workflow
    assert "EXPECTED_RELEASE_ID" in workflow
    assert "EXPECTED_GENERATION" in workflow
    assert "gcloud run deploy" not in workflow


def test_release_process_guard_rejects_reintroduced_qualification_trigger(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    guard = _load("release_process_guards", "check-release-process-guards.py")
    promotion_text = PROMOTE_BETA_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_run:" not in promotion_text

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for relative_path in (
            ".github/workflows/desktop_qualify_beta.yml",
            ".github/workflows/desktop_promote_beta.yml",
            ".github/workflows/desktop_recover_beta.yml",
            ".github/scripts/check-desktop-auto-beta-candidate.py",
        ):
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / relative_path, target)

        promotion = root / ".github/workflows/desktop_promote_beta.yml"
        promotion.write_text(promotion_text + "\n# workflow_run:\n", encoding="utf-8")
        guard.ROOT = root
        errors = guard.check_desktop_qualification_runner()
        assert any("still depends on qualification" in error for error in errors), errors

        promotion.write_text(promotion_text, encoding="utf-8")
        assert guard.check_desktop_qualification_runner() == []
