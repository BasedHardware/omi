import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / ".github" / "scripts"
PROMOTE_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_beta.yml"
PROMOTE_PROD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_promote_prod.yml"
EMERGENCY_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_emergency_promote_beta.yml"
QUALIFY_BETA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop_qualify_beta.yml"
CODEMAGIC_CONFIG = REPO_ROOT / "codemagic.yaml"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mark_beta = _load("mark_desktop_release_beta", "mark-desktop-release-beta.py")
mark_emergency_beta = _load("mark_desktop_release_emergency_beta", "mark-desktop-release-emergency-beta.py")
emergency_promotion = _load("check_desktop_emergency_beta_promotion", "check-desktop-emergency-beta-promotion.py")
prepare_beta = _load("prepare_desktop_beta_promotion", "prepare-desktop-beta-promotion.py")
nominate_stable = _load("nominate_desktop_stable_candidate", "nominate-desktop-stable-candidate.py")
repair_installer = _load("desktop_repair_installer", "desktop_repair_installer.py")


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


def test_emergency_metadata_records_two_bound_approvals_without_making_the_release_stable():
    result = mark_emergency_beta.mark_emergency_beta(
        _release()["body"],
        {
            "emergencyPromotion": True,
            "release_tag": "v0.12.64+12064-macos",
            "source_sha": "a" * 40,
            "incident_id": "10063",
            "reason": "qualification runner unavailable",
            "operator": "release-operator",
            "expires_at": "2026-07-19T13:00:00Z",
            "operation_id": "d" * 64,
            "approvers": ["alice", "bob"],
            "evidence": {"behavioral_url": "https://example.test/behavior.json"},
        },
    )
    assert "emergencyPromotion: true" in result
    assert "emergencyPromotionApprovers: alice,bob" in result
    assert "emergencyPromotionOperator: release-operator" in result
    assert "emergencyPromotionOperationId: " + "d" * 64 in result
    assert "channel: beta" in result
    assert "channel: stable" not in result


def test_emergency_approval_parser_requires_two_distinct_authorized_commenters_bound_to_the_candidate():
    comments = [
        {
            "body": f"Emergency beta promotion approval: v0.12.64+12064-macos {'a' * 40} 2026-07-19T13:00:00Z",
            "author_association": "MEMBER",
            "user": {"login": "alice"},
        },
        {
            "body": f"Emergency beta promotion approval: v0.12.64+12064-macos {'a' * 40} 2026-07-19T13:00:00Z",
            "author_association": "OWNER",
            "user": {"login": "bob"},
        },
    ]
    assert emergency_promotion.approval_identities(
        comments, "v0.12.64+12064-macos", "a" * 40, "2026-07-19T13:00:00Z"
    ) == ["alice", "bob"]

    comments[1]["author_association"] = "CONTRIBUTOR"
    with pytest.raises(SystemExit, match="exactly two"):
        emergency_promotion.approval_identities(comments, "v0.12.64+12064-macos", "a" * 40, "2026-07-19T13:00:00Z")


def test_emergency_operation_id_is_stable_across_github_retries():
    operation_id = emergency_promotion.emergency_operation_id("v0.12.64+12064-macos", "a" * 40, "10063")

    assert operation_id == emergency_promotion.emergency_operation_id("v0.12.64+12064-macos", "a" * 40, "10063")
    assert operation_id != emergency_promotion.emergency_operation_id("v0.12.64+12064-macos", "a" * 40, "10064")


def test_emergency_incident_state_normalizes_github_open_casing():
    assert emergency_promotion.incident_is_open({"number": 10063, "state": "OPEN"}, "10063")
    assert emergency_promotion.incident_is_open({"number": "10063", "state": "open"}, "10063")
    assert not emergency_promotion.incident_is_open({"number": 10063, "state": "closed"}, "10063")


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
    assert manifest["qualification"]["qualified_at"] == "2026-07-09T12:00:00Z"
    assert manifest["changelog"] == ["Fixed updates", "Improved recovery"]


def test_stable_repair_bundle_uses_an_immutable_gcs_artifact():
    manifest = prepare_beta.prepare_manifest(
        _release(),
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )

    bundle = repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")

    assert bundle["artifact_object"] == "stable/v0.12.64+12064-macos/Omi.dmg"
    assert bundle["repair_object"] == "stable/v0.12.64+12064-macos/repair.json"
    assert bundle["repair"]["channel"] == "stable"
    assert bundle["repair"]["installer_sha256"] == "c" * 64
    assert bundle["repair"]["installer_url"] == (
        "https://storage.googleapis.com/omi_macos_updates/stable/v0.12.64+12064-macos/Omi.dmg"
    )
    assert "example.com" not in bundle["latest"]["installer_url"]
    assert "/Applications" in bundle["landing_page"]


@pytest.mark.parametrize("field, value", [("platform", "windows"), ("dmg_sha256", "not-a-digest")])
def test_stable_repair_bundle_rejects_incomplete_or_wrong_platform_manifest(field, value):
    manifest = prepare_beta.prepare_manifest(
        _release(),
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )
    manifest[field] = value

    with pytest.raises(ValueError):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


def test_stable_repair_bundle_requires_the_release_publication_time():
    manifest = prepare_beta.prepare_manifest(
        _release(),
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )
    manifest.pop("published_at")

    with pytest.raises(ValueError, match="published_at"):
        repair_installer.build_repair_bundle(manifest, "gs://omi_macos_updates")


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
    assert manifest["qualification"]["blessed_at"] == "2026-07-09T12:00:00Z"
    assert "qualified_at" not in manifest["qualification"]


def test_prepare_manifest_allows_an_already_stable_release_only_for_repair_retries():
    release = _release()
    release["body"] = (
        release["body"].replace("isLive: false", "isLive: true").replace("channel: candidate", "channel: stable")
    )

    with pytest.raises(SystemExit, match="candidate or beta"):
        prepare_beta.prepare_manifest(
            release,
            "v0.12.64+12064-macos",
            "a" * 40,
            "b" * 64,
            "c" * 64,
        )

    manifest = prepare_beta.prepare_manifest(
        release,
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
        allow_stable_channel=True,
    )
    assert manifest["release_id"] == "v0.12.64+12064-macos"


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
        beta_source_sha="a" * 40,
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
            beta_source_sha="a" * 40,
            nominator="release-operator",
            rationale="soak gates passed",
            soak_review="24h reviewed",
            telemetry_review="crash telemetry reviewed",
            release_notes_review="stable notes reviewed",
            nominated_at="2026-07-10T12:00:00Z",
        )


def test_stable_nomination_rejects_beta_manifest_from_another_sha():
    release = _release()
    release["body"] = (
        release["body"].replace("isLive: false", "isLive: true").replace("channel: candidate", "channel: beta")
    )
    with pytest.raises(SystemExit, match="beta manifest source SHA"):
        nominate_stable.nominate(
            release,
            release_tag="v0.12.64+12064-macos",
            target_sha="a" * 40,
            beta_release_id="v0.12.64+12064-macos",
            beta_source_sha="b" * 40,
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


def test_emergency_reconciliation_recovers_after_a_failed_promotion_before_notifying_or_monitoring():
    """Static contract: downstream incident work cannot be skipped with promote."""
    workflow = EMERGENCY_BETA_WORKFLOW.read_text()
    pointer = workflow.index("      - name: Register manifest and compare-and-swap only macOS beta")
    stable_proof = workflow.index("      - name: Prove Stable pointer, release metadata, and appcast are unchanged")
    promote_job = workflow.index("  promote:")
    reconcile_job = workflow.index("  reconcile:")
    github_metadata = workflow.index(
        "      - name: Reconcile explicit emergency release metadata after beta pointer CAS"
    )
    notify_job = workflow.index("  notify:")
    notify = workflow.index("      - name: Notify incident responders immediately")
    promote = workflow[promote_job:reconcile_job]
    reconciliation = workflow[reconcile_job:notify_job]

    assert pointer < stable_proof < reconcile_job < github_metadata < notify_job < notify
    assert "authoritative macOS beta pointer compare-and-swap did not succeed" in workflow
    workflow_concurrency = workflow[workflow.index("concurrency:") : workflow.index("jobs:")]
    emergency_group = "group: desktop-emergency-beta-promotion-${{ github.run_id }}-${{ github.run_attempt }}"
    assert emergency_group in workflow_concurrency
    assert "cancel-in-progress: false" in workflow_concurrency
    assert "group: desktop-beta-promotion" not in promote
    assert "--workflow-run-id" not in promote
    assert "--workflow-run-attempt" not in promote
    assert "needs: promote" in reconciliation
    assert "if: ${{ always() }}" in reconciliation
    assert "environment: prod" in reconciliation
    assert "id: reconcile" in reconciliation
    assert "emergency_reconciled: ${{ steps.reconcile.outputs.emergency_reconciled }}" in reconciliation
    assert "emergency-promote-beta/reconciliation" in reconciliation
    assert "source_sha=$SOURCE_SHA" in reconciliation
    assert "incident_id=$INCIDENT_ID" in reconciliation
    assert "operation_id=$OPERATION_ID" in reconciliation
    assert "emergency_evidence" in reconciliation
    reconciliation_error = "authoritative emergency transaction reconciliation did not verify"
    reconciliation_error += " tag/SHA/incident/operation"
    assert reconciliation_error in reconciliation
    assert 'echo "emergency_reconciled=true" >> "$GITHUB_OUTPUT"' in reconciliation
    assert "gh api --paginate --slurp" in workflow
    assert "for comment in page" in workflow

    notification = workflow[notify_job : workflow.index("  monitor:")]
    monitor = workflow[workflow.index("  monitor:") :]
    expected_condition = "if: ${{ always() && needs.reconcile.outputs.emergency_reconciled == 'true' }}"
    assert "needs: reconcile" in notification
    assert "needs: reconcile" in monitor
    assert expected_condition in notification
    assert expected_condition in monitor
    assert "needs: promote" not in notification
    assert "needs: promote" not in monitor
    assert "environment: prod" not in notification
    assert "environment: prod" not in monitor


def test_qualification_claims_are_serialized_by_the_trusted_runner_only():
    codemagic = CODEMAGIC_CONFIG.read_text()
    dispatch = codemagic[codemagic.index("      - name: Dispatch trusted macOS beta qualification") :]
    qualification = QUALIFY_BETA_WORKFLOW.read_text()

    assert "authoritative atomic" in dispatch
    assert 'gh release edit "$CM_TAG"' not in dispatch
    assert "group: desktop-beta-qualification-${{ inputs.release_tag }}" in qualification
    assert "cancel-in-progress: false" in qualification
    assert "desktop_qualification_dispatch.py claim" in qualification
    assert "desktop_qualification_dispatch.py complete" in qualification


def test_stable_promotion_remains_manual_only():
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    assert "on:\n  workflow_dispatch:" in workflow
    assert "\n  schedule:" not in workflow
    assert "\n  push:" not in workflow
    assert "confirm:" in workflow
    assert "promote-stable" in workflow


def test_stable_repair_is_published_immutably_before_stable_pointer_advances():
    """Static wiring contract: a stable pointer is never advanced ahead of its repair artifact."""
    workflow = PROMOTE_PROD_WORKFLOW.read_text()

    immutable_repair = workflow.index("      - name: Publish immutable stable repair installer")
    legacy_bridge = workflow.index("      - name: Promote Firestore release stable")
    pointer = workflow.index("      - name: Advance explicit stable pointer")
    latest_route = workflow.index("      - name: Publish latest stable repair route")

    assert immutable_repair < legacy_bridge < pointer < latest_route
    assert "--json tagName,body,isDraft,isPrerelease,publishedAt,assets" in workflow
    assert "--pattern 'Omi.zip' --pattern 'Omi.dmg' --pattern 'omi.dmg'" in workflow
    assert "--pattern '*.dmg'" not in workflow
    assert "Expected exactly one qualified Omi.dmg or omi.dmg release asset." in workflow
    assert "--if-generation-match=0" in workflow
