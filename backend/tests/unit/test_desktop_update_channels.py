from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database.desktop_update_channels import (
    _build_channel_pointer,
    _build_beta_rollback_pointer,
    _emergency_promotion_audit_id,
    _rollback_macos_beta_transaction,
    _emergency_promote_macos_beta_transaction,
    emergency_promote_macos_beta_channel,
    get_channel_release,
    normalize_release_manifest,
    register_release_manifest,
    verify_emergency_macos_beta_reconciliation,
)


def _manifest(**overrides):
    data = {
        "release_id": "v0.12.64+12064-macos",
        "platform": "macos",
        "version": "0.12.64+12064",
        "build_number": 12064,
        "zip_url": "https://github.com/BasedHardware/omi/releases/download/test/Omi.zip",
        "dmg_url": "https://github.com/BasedHardware/omi/releases/download/test/Omi.dmg",
        "ed_signature": "sparkle-signature",
        "published_at": "2026-07-09T12:00:00Z",
        "changelog": ["Qualified beta"],
        "mandatory": False,
        "source_sha": "a" * 40,
        "zip_sha256": "b" * 64,
        "dmg_sha256": "c" * 64,
        "qualification": {"tier": "T2", "passed": True},
    }
    data.update(overrides)
    return data


def _emergency_manifest(*, release_id, version, build_number, reason, expires_at, evidence, incident_id="10063"):
    return normalize_release_manifest(
        _manifest(
            release_id=release_id,
            version=version,
            build_number=build_number,
            qualification={
                "tier": "emergency",
                "passed": False,
                "emergency_evidence": {
                    "emergencyPromotion": True,
                    "release_tag": release_id,
                    "source_sha": "a" * 40,
                    "incident_id": incident_id,
                    "reason": reason,
                    "operator": "release-operator",
                    "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                    "approvers": ["alice", "bob"],
                    "evidence": evidence,
                },
            },
        )
    )


class TestNormalizeReleaseManifest:
    def test_accepts_complete_manifest(self):
        result = normalize_release_manifest(_manifest())
        assert result["build_number"] == 12064
        assert result["qualification"]["tier"] == "T2"

    @pytest.mark.parametrize("field", ["release_id", "version", "zip_url", "ed_signature", "source_sha"])
    def test_rejects_missing_required_fields(self, field):
        data = _manifest()
        data.pop(field)
        with pytest.raises(ValueError, match=field):
            normalize_release_manifest(data)

    def test_rejects_non_https_assets(self):
        with pytest.raises(ValueError, match="https URL"):
            normalize_release_manifest(_manifest(zip_url="http://example.com/Omi.zip"))

    def test_requires_dmg_for_macos(self):
        with pytest.raises(ValueError, match="dmg_url"):
            normalize_release_manifest(_manifest(dmg_url=None))


class TestReleaseManifestPersistence:
    def test_register_is_idempotent_for_identical_manifest(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = _manifest()
        ref = MagicMock()
        ref.get.return_value = snapshot
        client = MagicMock()
        client.collection.return_value.document.return_value = ref

        result = register_release_manifest(_manifest(), firestore_client=client)

        assert result == normalize_release_manifest(_manifest())
        ref.create.assert_not_called()

    def test_register_rejects_release_id_mutation(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = _manifest(version="0.12.63+12063")
        ref = MagicMock()
        ref.get.return_value = snapshot
        client = MagicMock()
        client.collection.return_value.document.return_value = ref

        with pytest.raises(ValueError, match="immutable"):
            register_release_manifest(_manifest(), firestore_client=client)

    def test_resolves_pointer_to_manifest(self):
        pointer_snapshot = MagicMock(exists=True)
        pointer_snapshot.to_dict.return_value = {
            "release_id": _manifest()["release_id"],
            "generation": 4,
            "updated_at": "2026-07-09T12:00:00Z",
        }
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = _manifest()
        pointer_ref = MagicMock()
        pointer_ref.get.return_value = pointer_snapshot
        manifest_ref = MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        collection = MagicMock()
        collection.document.side_effect = [pointer_ref, manifest_ref]
        client = MagicMock()
        client.collection.return_value = collection

        result = get_channel_release("macos", "beta", firestore_client=client)

        assert result is not None
        assert result["pointer"]["generation"] == 4
        assert result["manifest"]["release_id"] == _manifest()["release_id"]


class TestChannelPromotionRules:
    def test_first_qualified_promotion_sets_generation_and_build(self):
        pointer = _build_channel_pointer(
            {},
            normalize_release_manifest(_manifest()),
            platform="macos",
            channel="beta",
            release_id=_manifest()["release_id"],
            expected_generation=0,
        )
        assert pointer["generation"] == 1
        assert pointer["build_number"] == 12064

    def test_idempotent_retry_does_not_increment_generation(self):
        current = {
            "platform": "macos",
            "channel": "beta",
            "release_id": _manifest()["release_id"],
            "version": _manifest()["version"],
            "build_number": 12064,
            "generation": 4,
        }
        pointer = _build_channel_pointer(
            current,
            normalize_release_manifest(_manifest()),
            platform="macos",
            channel="beta",
            release_id=_manifest()["release_id"],
            expected_generation=4,
        )
        assert pointer is current
        assert pointer["generation"] == 4

    def test_rejects_rollback(self):
        current = {"release_id": "newer", "build_number": 13000, "generation": 2}
        with pytest.raises(ValueError, match="roll-forward only"):
            _build_channel_pointer(
                current,
                normalize_release_manifest(_manifest()),
                platform="macos",
                channel="beta",
                release_id=_manifest()["release_id"],
                expected_generation=2,
            )

    def test_rejects_unqualified_release(self):
        manifest = normalize_release_manifest(_manifest(qualification={"passed": False, "tier": "T2"}))
        with pytest.raises(ValueError, match="qualification"):
            _build_channel_pointer(
                {},
                manifest,
                platform="macos",
                channel="beta",
                release_id=manifest["release_id"],
                expected_generation=None,
            )


class TestMacosBetaRollbackRules:
    def test_rolls_back_qualified_release_and_creates_immutable_audit(self):
        current = {
            "platform": "macos",
            "channel": "beta",
            "release_id": "v0.12.84+12084-macos",
            "version": "0.12.84+12084",
            "build_number": 12084,
            "generation": 7,
        }
        target = normalize_release_manifest(
            _manifest(release_id="v0.12.73+12073-macos", version="0.12.73+12073", build_number=12073)
        )
        pointer = _build_beta_rollback_pointer(
            current,
            target,
            release_id=target["release_id"],
            expected_current_release_id=current["release_id"],
            expected_generation=7,
        )

        pointer_snapshot = MagicMock(exists=True)
        pointer_snapshot.to_dict.return_value = current
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = target
        pointer_ref = MagicMock()
        pointer_ref.get.return_value = pointer_snapshot
        manifest_ref = MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        audit_ref = MagicMock()
        transaction = MagicMock()

        result = _rollback_macos_beta_transaction.to_wrap(
            transaction,
            pointer_ref,
            manifest_ref,
            audit_ref,
            release_id=target["release_id"],
            expected_current_release_id=current["release_id"],
            expected_generation=7,
            audit_id="audit-123",
            occurred_at=pointer["updated_at"],
        )

        assert result["pointer"]["release_id"] == target["release_id"]
        assert result["pointer"]["generation"] == 8
        assert result["audit"] == {
            "audit_id": "audit-123",
            "operation": "macos_beta_rollback",
            "platform": "macos",
            "channel": "beta",
            "previous_release_id": current["release_id"],
            "previous_generation": 7,
            "target_release_id": target["release_id"],
            "generation": 8,
            "occurred_at": pointer["updated_at"],
        }
        transaction.create.assert_called_once_with(audit_ref, result["audit"])
        transaction.set.assert_called_once_with(pointer_ref, result["pointer"])

    def test_rejects_stale_current_release_or_generation(self):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        target = normalize_release_manifest(
            _manifest(release_id="v0.12.73+12073-macos", version="0.12.73+12073", build_number=12073)
        )

        with pytest.raises(ValueError, match="current release mismatch"):
            _build_beta_rollback_pointer(
                current,
                target,
                release_id=target["release_id"],
                expected_current_release_id="v0.12.83+12083-macos",
                expected_generation=7,
            )
        with pytest.raises(ValueError, match="generation mismatch"):
            _build_beta_rollback_pointer(
                current,
                target,
                release_id=target["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=6,
            )

    def test_rejects_unqualified_or_non_macos_target(self):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        unqualified = normalize_release_manifest(
            _manifest(
                release_id="v0.12.73+12073-macos",
                version="0.12.73+12073",
                build_number=12073,
                qualification={"tier": "T2", "passed": False},
            )
        )
        with pytest.raises(ValueError, match="qualification"):
            _build_beta_rollback_pointer(
                current,
                unqualified,
                release_id=unqualified["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=7,
            )


class TestMacosBetaEmergencyPromotionRules:
    def test_advances_only_newer_beta_and_creates_append_only_audit(self):
        current = {
            "platform": "macos",
            "channel": "beta",
            "release_id": "v0.12.84+12084-macos",
            "version": "0.12.84+12084",
            "build_number": 12084,
            "generation": 7,
        }
        occurred_at = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        expires_at = occurred_at + timedelta(hours=1)
        pointer_snapshot = MagicMock(exists=True)
        pointer_snapshot.to_dict.return_value = current
        evidence = {
            "signed_smoke_url": "https://example.test/smoke.json",
            "signed_smoke_sha256": "d" * 64,
            "behavioral_url": "https://example.test/behavior.json",
            "behavioral_sha256": "e" * 64,
            "source_gate_url": "https://example.test/check",
            "zip_sha256": "b" * 64,
            "dmg_sha256": "c" * 64,
        }
        target = _emergency_manifest(
            release_id="v0.12.85+12085-macos",
            version="0.12.85+12085",
            build_number=12085,
            reason="qualification runner is unavailable during an incident",
            expires_at=expires_at,
            evidence=evidence,
        )
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = target
        pointer_ref = MagicMock()
        pointer_ref.get.return_value = pointer_snapshot
        manifest_ref = MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        audit_ref = MagicMock()
        transaction = MagicMock()

        result = _emergency_promote_macos_beta_transaction.to_wrap(
            transaction,
            pointer_ref,
            manifest_ref,
            audit_ref,
            release_id=target["release_id"],
            source_sha=target["source_sha"],
            expected_current_release_id=current["release_id"],
            expected_generation=7,
            incident_id="10063",
            reason="qualification runner is unavailable during an incident",
            operator="release-operator",
            expires_at=expires_at,
            approvers=["alice", "bob"],
            evidence=evidence,
            audit_id="audit-123",
            occurred_at=occurred_at,
        )

        assert result["pointer"] == {
            "platform": "macos",
            "channel": "beta",
            "release_id": target["release_id"],
            "version": target["version"],
            "build_number": 12085,
            "generation": 8,
            "updated_at": occurred_at,
        }
        assert result["audit"]["emergencyPromotion"] is True
        assert result["audit"]["platform"] == "macos"
        assert result["audit"]["channel"] == "beta"
        assert result["audit"]["approvers"] == ["alice", "bob"]
        assert result["audit"]["operator"] == "release-operator"
        transaction.create.assert_called_once_with(audit_ref, result["audit"])
        transaction.set.assert_called_once_with(pointer_ref, result["pointer"])

    def test_rejects_altered_artifact_evidence_before_the_pointer_write(self):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        pointer_snapshot = MagicMock(exists=True)
        pointer_snapshot.to_dict.return_value = current
        evidence = {
            "signed_smoke_url": "https://example.test/smoke.json",
            "signed_smoke_sha256": "d" * 64,
            "behavioral_url": "https://example.test/behavior.json",
            "behavioral_sha256": "e" * 64,
            "source_gate_url": "https://example.test/check",
            "zip_sha256": "f" * 64,
            "dmg_sha256": "c" * 64,
        }
        target = _emergency_manifest(
            release_id="v0.12.85+12085-macos",
            version="0.12.85+12085",
            build_number=12085,
            reason="runner unavailable",
            expires_at=datetime(2026, 7, 19, 13, 0, tzinfo=timezone.utc),
            evidence={**evidence, "zip_sha256": "b" * 64},
        )
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = target
        pointer_ref, manifest_ref, audit_ref, transaction = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        pointer_ref.get.return_value = pointer_snapshot
        manifest_ref.get.return_value = manifest_snapshot
        with pytest.raises(ValueError, match="does not match the immutable manifest"):
            _emergency_promote_macos_beta_transaction.to_wrap(
                transaction,
                pointer_ref,
                manifest_ref,
                audit_ref,
                release_id=target["release_id"],
                source_sha=target["source_sha"],
                expected_current_release_id=current["release_id"],
                expected_generation=7,
                incident_id="10063",
                reason="runner unavailable",
                operator="release-operator",
                expires_at=datetime(2026, 7, 19, 13, 0, tzinfo=timezone.utc),
                approvers=["alice", "bob"],
                evidence=evidence,
                audit_id="audit-123",
                occurred_at=datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
            )
        transaction.create.assert_not_called()
        transaction.set.assert_not_called()

    @pytest.mark.parametrize(
        ("approvers", "expires_at", "evidence", "message"),
        [
            (["alice"], "2026-07-19T13:00:00Z", None, "exactly two"),
            (["alice", "alice"], "2026-07-19T13:00:00Z", None, "exactly two"),
            (["alice", "bob"], "2026-07-19T11:59:00Z", None, "expired"),
            (["alice", "bob"], "2026-07-19T17:00:01Z", None, "may not exceed"),
            (["alice", "bob"], "2026-07-19T13:00:00Z", {}, "evidence is incomplete"),
        ],
    )
    def test_rejects_invalid_or_expired_break_glass_authorization(self, approvers, expires_at, evidence, message):
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        valid_evidence = {
            "signed_smoke_url": "https://example.test/smoke.json",
            "signed_smoke_sha256": "d" * 64,
            "behavioral_url": "https://example.test/behavior.json",
            "behavioral_sha256": "e" * 64,
            "source_gate_url": "https://example.test/check",
            "zip_sha256": "b" * 64,
            "dmg_sha256": "c" * 64,
        }
        with pytest.raises(ValueError, match=message):
            emergency_promote_macos_beta_channel(
                "v0.12.85+12085-macos",
                source_sha="a" * 40,
                expected_current_release_id="v0.12.84+12084-macos",
                expected_generation=7,
                incident_id="10063",
                reason="runner unavailable",
                operator="release-operator",
                expires_at=expires_at,
                approvers=approvers,
                evidence=valid_evidence if evidence is None else evidence,
                firestore_client=MagicMock(),
                now=now,
            )

        with pytest.raises(ValueError, match="operator"):
            emergency_promote_macos_beta_channel(
                "v0.12.85+12085-macos",
                source_sha="a" * 40,
                expected_current_release_id="v0.12.84+12084-macos",
                expected_generation=7,
                incident_id="10063",
                reason="runner unavailable",
                operator="not a github login",
                expires_at="2026-07-19T13:00:00Z",
                approvers=["alice", "bob"],
                evidence=valid_evidence,
                firestore_client=MagicMock(),
                now=now,
            )

    def test_beta_rollback_rejects_non_macos_target(self):
        current = normalize_release_manifest(_manifest())
        windows = normalize_release_manifest(
            _manifest(
                release_id="v0.12.73+12073-windows",
                platform="windows",
                version="0.12.73+12073",
                build_number=12073,
                dmg_url=None,
            )
        )
        with pytest.raises(ValueError, match="macos"):
            _build_beta_rollback_pointer(
                current,
                windows,
                release_id=windows["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=7,
            )


class TestMacosBetaEmergencyReconciliation:
    def test_verifies_the_immutable_emergency_decision_and_append_only_audit(self):
        release_id = "v0.12.85+12085-macos"
        source_sha = "a" * 40
        audit_id = _emergency_promotion_audit_id(release_id, source_sha)
        evidence = {
            "signed_smoke_url": "https://example.test/smoke.json",
            "signed_smoke_sha256": "d" * 64,
            "behavioral_url": "https://example.test/behavior.json",
            "behavioral_sha256": "e" * 64,
            "source_gate_url": "https://example.test/check",
            "zip_sha256": "b" * 64,
            "dmg_sha256": "c" * 64,
        }
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = _emergency_manifest(
            release_id=release_id,
            version="0.12.85+12085",
            build_number=12085,
            reason="qualification runner is unavailable during an incident",
            expires_at=datetime(2026, 7, 19, 13, 0, tzinfo=timezone.utc),
            evidence=evidence,
        )
        audit_snapshot = MagicMock(exists=True)
        audit_snapshot.to_dict.return_value = {
            "audit_id": audit_id,
            "operation": "macos_beta_emergency_forward_promotion",
            "platform": "macos",
            "channel": "beta",
            "emergencyPromotion": True,
            "target_release_id": release_id,
            "source_sha": source_sha,
            "incident_id": "10063",
            "previous_generation": 7,
            "generation": 8,
        }
        manifest_ref, audit_ref = MagicMock(), MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        audit_ref.get.return_value = audit_snapshot
        manifests, audits = MagicMock(), MagicMock()
        manifests.document.return_value = manifest_ref
        audits.document.return_value = audit_ref
        client = MagicMock()
        client.collection.side_effect = [manifests, audits]

        result = verify_emergency_macos_beta_reconciliation(
            release_id,
            source_sha=source_sha,
            incident_id="10063",
            firestore_client=client,
        )

        emergency_evidence = manifest_snapshot.to_dict.return_value["qualification"]["emergency_evidence"]
        assert result == {
            "emergency_reconciled": True,
            "release_id": release_id,
            "source_sha": source_sha,
            "incident_id": "10063",
            "audit_id": audit_id,
            "generation": 8,
            "emergency_evidence": emergency_evidence,
        }
        manifests.document.assert_called_once_with(release_id)
        audits.document.assert_called_once_with(audit_id)

    def test_rejects_a_normal_manifest_even_when_its_release_identity_matches(self):
        release_id = "v0.12.85+12085-macos"
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = _manifest(
            release_id=release_id,
            version="0.12.85+12085",
            build_number=12085,
        )
        manifest_ref = MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        manifests = MagicMock()
        manifests.document.return_value = manifest_ref
        client = MagicMock()
        client.collection.return_value = manifests

        with pytest.raises(ValueError, match="immutable manifest"):
            verify_emergency_macos_beta_reconciliation(
                release_id,
                source_sha="a" * 40,
                incident_id="10063",
                firestore_client=client,
            )

        assert client.collection.call_count == 1

    def test_rejects_an_audit_bound_to_a_different_incident(self):
        release_id = "v0.12.85+12085-macos"
        source_sha = "a" * 40
        audit_id = _emergency_promotion_audit_id(release_id, source_sha)
        evidence = {
            "signed_smoke_url": "https://example.test/smoke.json",
            "signed_smoke_sha256": "d" * 64,
            "behavioral_url": "https://example.test/behavior.json",
            "behavioral_sha256": "e" * 64,
            "source_gate_url": "https://example.test/check",
            "zip_sha256": "b" * 64,
            "dmg_sha256": "c" * 64,
        }
        manifest_snapshot = MagicMock(exists=True)
        manifest_snapshot.to_dict.return_value = _emergency_manifest(
            release_id=release_id,
            version="0.12.85+12085",
            build_number=12085,
            reason="qualification runner is unavailable during an incident",
            expires_at=datetime(2026, 7, 19, 13, 0, tzinfo=timezone.utc),
            evidence=evidence,
            incident_id="10063",
        )
        audit_snapshot = MagicMock(exists=True)
        audit_snapshot.to_dict.return_value = {
            "audit_id": audit_id,
            "operation": "macos_beta_emergency_forward_promotion",
            "platform": "macos",
            "channel": "beta",
            "emergencyPromotion": True,
            "target_release_id": release_id,
            "source_sha": source_sha,
            "incident_id": "10064",
            "previous_generation": 7,
            "generation": 8,
        }
        manifest_ref, audit_ref = MagicMock(), MagicMock()
        manifest_ref.get.return_value = manifest_snapshot
        audit_ref.get.return_value = audit_snapshot
        manifests, audits = MagicMock(), MagicMock()
        manifests.document.return_value = manifest_ref
        audits.document.return_value = audit_ref
        client = MagicMock()
        client.collection.side_effect = [manifests, audits]

        with pytest.raises(ValueError, match="audit does not match.*incident"):
            verify_emergency_macos_beta_reconciliation(
                release_id,
                source_sha=source_sha,
                incident_id="10063",
                firestore_client=client,
            )
