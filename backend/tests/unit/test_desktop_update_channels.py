from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock

import pytest

from database.desktop_update_channels import (
    BETA_ADMISSION_COLLECTION,
    BETA_ADMISSION_DOCUMENT,
    _admit_qualified_beta_transaction,
    _build_pointer,
    admit_qualified_beta_manifest,
    capture_beta_admission,
    get_channel_release,
    get_release_manifest,
    normalize_release_manifest,
    promote_channel,
    register_release_manifest,
    reserve_beta_candidate,
    set_beta_admission_enabled,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def _manifest(**overrides):
    data = {
        "schema_version": 1,
        "release_id": "v0.12.64+12064-macos",
        "platform": "macos",
        "version": "0.12.64",
        "build_number": 12064,
        "app_source_sha": "a" * 40,
        "zip_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip",
        "dmg_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg",
        "ed_signature": "sparkle-signature",
        "qualification_evidence_asset": "qualification-evidence-v0.12.64+12064-macos.json",
        "qualification_evidence_sha256": "sha256:" + "d" * 64,
        "qualification_tier": "T2",
        "qualification_passed": True,
        "backend_mode": "app_only",
        "compatibility_contract": {
            "schema_version": 1,
            "app_release_id": "v0.12.64+12064-macos",
            "app_version": "0.12.64",
            "app_build_number": 12064,
            "backend_mode": "app_only",
            "environment_contract_version": "desktop-backend-env-v1",
        },
        "environment_contract_version": "desktop-backend-env-v1",
        "created_at": "2026-07-09T12:00:00Z",
        "published_at": "2026-07-09T12:00:00Z",
        "changelog": ["Qualified beta"],
        "mandatory": False,
        "zip_sha256": "sha256:" + "b" * 64,
        "dmg_sha256": "sha256:" + "c" * 64,
    }
    data.update(overrides)
    return data


def _control(*, enabled=True, tag="v0.12.64+12064-macos", generation=1, **overrides):
    data = {
        "schema_version": 1,
        "promotion_enabled": enabled,
        "latest_reserved_tag": tag,
        "latest_reserved_build_number": 12064 if tag else None,
        "control_generation": generation,
        "latest_reserved_at": datetime(2026, 7, 9, 12, tzinfo=timezone.utc) if tag else None,
        "admission_updated_at": datetime(2026, 7, 9, 12, tzinfo=timezone.utc) if tag else None,
    }
    data.update(overrides)
    return data


class TestNormalizeReleaseManifest:
    def test_accepts_complete_manifest(self):
        result = normalize_release_manifest(_manifest())
        assert result["build_number"] == 12064
        assert result["qualification_tier"] == "T2"

    @pytest.mark.parametrize("field", ["release_id", "version", "zip_url", "ed_signature", "app_source_sha"])
    def test_rejects_missing_required_fields(self, field):
        data = _manifest()
        data.pop(field)
        with pytest.raises(ValueError, match=field):
            normalize_release_manifest(data)

    def test_rejects_non_https_assets(self):
        with pytest.raises(ValueError, match="github.com release asset URL"):
            normalize_release_manifest(_manifest(zip_url="http://example.com/Omi.zip"))

    def test_requires_dmg_for_macos(self):
        with pytest.raises(ValueError, match="dmg_url"):
            normalize_release_manifest(_manifest(dmg_url=None))


class TestReleaseManifestPersistence:
    def test_registered_manifest_round_trips_through_retry_retained_read_and_promotion(self):
        """A Firestore snapshot preserves the canonical manifest bytes exactly."""
        client = StrictFirestore()
        manifest = _manifest()

        registered = register_release_manifest(manifest, firestore_client=client)
        stored = client.rows[("desktop_release_manifests", manifest["release_id"])]
        assert stored == manifest
        assert stored["created_at"] == manifest["created_at"]
        assert isinstance(stored["created_at"], str)

        assert register_release_manifest(manifest, firestore_client=client) == registered
        assert get_release_manifest(manifest["release_id"], firestore_client=client) == registered

        pointer = promote_channel(
            "macos",
            "stable",
            manifest["release_id"],
            expected_generation=0,
            firestore_client=client,
        )
        resolved = get_channel_release("macos", "stable", firestore_client=client)

        assert pointer["generation"] == 1
        assert resolved is not None
        assert resolved["manifest"] == registered
        assert client.rows[("desktop_release_manifests", manifest["release_id"])] == manifest
        assert (
            promote_channel(
                "macos",
                "stable",
                manifest["release_id"],
                expected_generation=0,
                firestore_client=client,
            )
            == pointer
        )

    def test_qualified_beta_admission_preserves_created_canonical_manifest_for_exact_retry_and_resolution(self):
        """The transaction-created snapshot is the canonical object Beta subsequently resolves."""
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control()})
        manifest = normalize_release_manifest(_manifest())
        canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()

        first = admit_qualified_beta_manifest(manifest, control_generation=1, firestore_client=client)
        created = client.transactions[-1].creates
        assert created == [(('desktop_release_manifests', manifest['release_id']), manifest)]
        assert json.dumps(created[0][1], sort_keys=True, separators=(',', ':')).encode() == canonical_bytes
        assert client.rows[('desktop_release_manifests', manifest['release_id'])] == manifest
        assert (
            json.dumps(
                client.rows[('desktop_release_manifests', manifest['release_id'])],
                sort_keys=True,
                separators=(',', ':'),
            ).encode()
            == canonical_bytes
        )
        assert (
            client.rows[('desktop_release_manifests', manifest['release_id'])]['created_at'] == manifest['created_at']
        )
        assert isinstance(client.rows[('desktop_release_manifests', manifest['release_id'])]['created_at'], str)

        retry = admit_qualified_beta_manifest(manifest, control_generation=1, firestore_client=client)
        assert client.transactions[-1].creates == []
        assert retry['idempotent'] is True
        assert retry['pointer']['generation'] == first['pointer']['generation'] == 1

        resolved = get_channel_release('macos', 'beta', firestore_client=client)
        assert resolved is not None
        assert resolved['manifest'] == manifest
        assert json.dumps(resolved['manifest'], sort_keys=True, separators=(',', ':')).encode() == canonical_bytes


class TestBetaAdmissionControl:
    def test_first_reservation_creates_a_paused_control_and_same_tag_is_write_free(self):
        client = StrictFirestore()

        first = reserve_beta_candidate("v0.12.64+12064-macos", firestore_client=client)
        retry = reserve_beta_candidate("v0.12.64+12064-macos", firestore_client=client)

        assert first["promotion_enabled"] is False
        assert first["control_generation"] == 1
        assert retry == first
        assert len(client.transactions) == 2
        assert client.transactions[0].sets
        assert client.transactions[1].sets == []

    def test_higher_reservation_preserves_pause_and_fences_prior_capture(self):
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control(enabled=True)})
        captured = capture_beta_admission("v0.12.64+12064-macos", firestore_client=client)
        newer = reserve_beta_candidate("v0.12.65+12065-macos", firestore_client=client)

        assert captured["control_generation"] == 1
        assert newer["promotion_enabled"] is True
        assert newer["control_generation"] == 2
        with pytest.raises(ValueError, match="reservation|generation"):
            admit_qualified_beta_manifest(
                _manifest(), control_generation=captured["control_generation"], firestore_client=client
            )
        assert ("desktop_release_manifests", _manifest()["release_id"]) not in client.rows
        assert ("desktop_update_channels", "macos-beta") not in client.rows

        paused = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control(enabled=False)})
        assert reserve_beta_candidate("v0.12.65+12065-macos", firestore_client=paused)["promotion_enabled"] is False

    @pytest.mark.parametrize(
        "tag",
        ["v0.12.63+12063-macos", "v0.12.64+12064-macos"],
    )
    def test_lower_or_same_build_different_tag_is_rejected(self, tag):
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control()})
        if tag == "v0.12.64+12064-macos":
            tag = "v0.12.63+12064-macos"
        with pytest.raises(ValueError, match="roll forward"):
            reserve_beta_candidate(tag, firestore_client=client)

    def test_pause_transition_invalidates_inflight_promotion_and_pause_without_reservation_rejects_resume(self):
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control(enabled=True)})
        captured = capture_beta_admission("v0.12.64+12064-macos", firestore_client=client)
        paused = set_beta_admission_enabled(False, firestore_client=client)

        assert paused["control_generation"] == captured["control_generation"] + 1
        with pytest.raises(ValueError, match="disabled|generation"):
            admit_qualified_beta_manifest(
                _manifest(), control_generation=captured["control_generation"], firestore_client=client
            )

        empty = StrictFirestore()
        with pytest.raises(ValueError, match="reservation"):
            set_beta_admission_enabled(True, firestore_client=empty)

    def test_reservation_then_resume_allows_a_commit_and_later_reservation_keeps_that_commit_valid(self):
        client = StrictFirestore()
        reserved = reserve_beta_candidate("v0.12.64+12064-macos", firestore_client=client)
        enabled = set_beta_admission_enabled(True, firestore_client=client)
        first = admit_qualified_beta_manifest(
            _manifest(), control_generation=enabled["control_generation"], firestore_client=client
        )
        newer = reserve_beta_candidate("v0.12.65+12065-macos", firestore_client=client)

        assert reserved["promotion_enabled"] is False
        assert enabled["promotion_enabled"] is True
        assert first["pointer"]["release_id"] == _manifest()["release_id"]
        assert newer["control_generation"] == enabled["control_generation"] + 1
        assert client.rows[("desktop_update_channels", "macos-beta")]["release_id"] == _manifest()["release_id"]

    def test_paused_or_superseded_idempotent_pointer_retry_has_no_writes(self):
        manifest = _manifest()
        client = StrictFirestore(
            {
                (BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control(enabled=False),
                ("desktop_release_manifests", manifest["release_id"]): manifest,
                ("desktop_update_channels", "macos-beta"): {
                    "release_id": manifest["release_id"],
                    "build_number": manifest["build_number"],
                    "generation": 4,
                },
            }
        )
        with pytest.raises(ValueError, match="disabled"):
            admit_qualified_beta_manifest(manifest, control_generation=1, firestore_client=client)
        assert client.transactions[-1].creates == []
        assert client.transactions[-1].sets == []

        client.rows[(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT)] = _control(
            enabled=True,
            tag="v0.12.65+12065-macos",
            latest_reserved_build_number=12065,
            generation=2,
        )
        with pytest.raises(ValueError, match="reservation|generation"):
            admit_qualified_beta_manifest(manifest, control_generation=1, firestore_client=client)
        assert client.transactions[-1].creates == []
        assert client.transactions[-1].sets == []

    @pytest.mark.parametrize(
        "bad",
        [
            {},
            _control(schema_version=True),
            _control(control_generation=True),
            _control(latest_reserved_build_number=True),
            _control(latest_reserved_tag=None, latest_reserved_build_number=12064),
            _control(extra="nope"),
        ],
    )
    def test_malformed_control_fails_closed_without_manifest_or_pointer_writes(self, bad):
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): bad})
        with pytest.raises(ValueError, match="admission control"):
            capture_beta_admission("v0.12.64+12064-macos", firestore_client=client)
        assert ("desktop_release_manifests", _manifest()["release_id"]) not in client.rows

    def test_admission_transaction_reads_control_first_and_all_docs_before_writes(self):
        client = StrictFirestore({(BETA_ADMISSION_COLLECTION, BETA_ADMISSION_DOCUMENT): _control(enabled=True)})
        receipt = admit_qualified_beta_manifest(_manifest(), control_generation=1, firestore_client=client)

        transaction = client.transactions[-1]
        assert receipt["pointer"]["channel"] == "beta"
        assert transaction.sets

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
        snapshot.to_dict.return_value = _manifest(
            release_id="v0.12.63+12063-macos",
            version="0.12.63",
            build_number=12063,
            zip_url="https://github.com/BasedHardware/omi/releases/download/v0.12.63+12063-macos/Omi.zip",
            dmg_url="https://github.com/BasedHardware/omi/releases/download/v0.12.63+12063-macos/omi.dmg",
            compatibility_contract={
                "schema_version": 1,
                "app_release_id": "v0.12.63+12063-macos",
                "app_version": "0.12.63",
                "app_build_number": 12063,
                "backend_mode": "app_only",
                "environment_contract_version": "desktop-backend-env-v1",
            },
        )
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

    def test_reads_retained_manifest_without_a_channel_or_release_metadata(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = _manifest()
        ref = MagicMock()
        ref.get.return_value = snapshot
        client = MagicMock()
        client.collection.return_value.document.return_value = ref

        assert get_release_manifest(_manifest()["release_id"], firestore_client=client) == normalize_release_manifest(
            _manifest()
        )


class TestChannelPromotionRules:
    def test_qualified_beta_transaction_touches_only_its_manifest_and_beta_pointer(self):
        manifest = normalize_release_manifest(
            _manifest(
                release_id="v0.12.93+12093-macos",
                version="0.12.93",
                build_number=12093,
                zip_url="https://github.com/BasedHardware/omi/releases/download/v0.12.93+12093-macos/Omi.zip",
                dmg_url="https://github.com/BasedHardware/omi/releases/download/v0.12.93+12093-macos/omi.dmg",
                compatibility_contract={
                    "schema_version": 1,
                    "app_release_id": "v0.12.93+12093-macos",
                    "app_version": "0.12.93",
                    "app_build_number": 12093,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
            )
        )
        missing_manifest = MagicMock(exists=False)
        current_beta = MagicMock(exists=True)
        current_beta.to_dict.return_value = {
            "release_id": "v0.12.92+12092-macos",
            "build_number": 12092,
            "generation": 3,
        }
        control_ref, manifest_ref, beta_ref, stable_ref = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        control = _control(
            enabled=True,
            tag=manifest["release_id"],
            generation=6,
            latest_reserved_build_number=manifest["build_number"],
        )
        control_ref.get.return_value = MagicMock(exists=True)
        control_ref.get.return_value.to_dict.return_value = control
        manifest_ref.get.return_value = missing_manifest
        beta_ref.get.return_value = current_beta
        transaction = MagicMock()

        receipt = _admit_qualified_beta_transaction.to_wrap(
            transaction, control_ref, beta_ref, manifest_ref, manifest, 6
        )

        assert receipt["pointer"]["channel"] == "beta"
        assert receipt["pointer"]["generation"] == 4
        transaction.create.assert_called_once()
        transaction.set.assert_called_once_with(beta_ref, receipt["pointer"])
        assert stable_ref.method_calls == []

    def test_qualified_beta_transaction_lost_response_retry_is_idempotent_without_a_second_pointer_write(self):
        manifest = normalize_release_manifest(_manifest())
        existing_manifest = MagicMock(exists=True)
        existing_manifest.to_dict.return_value = manifest
        current_beta = MagicMock(exists=True)
        current_beta.to_dict.return_value = {
            "release_id": manifest["release_id"],
            "build_number": manifest["build_number"],
            "generation": 4,
        }
        control_ref, manifest_ref, beta_ref = MagicMock(), MagicMock(), MagicMock()
        control_ref.get.return_value = MagicMock(exists=True)
        control_ref.get.return_value.to_dict.return_value = _control(
            enabled=True,
            tag=manifest["release_id"],
            generation=6,
            latest_reserved_build_number=manifest["build_number"],
        )
        manifest_ref.get.return_value = existing_manifest
        beta_ref.get.return_value = current_beta
        transaction = MagicMock()

        receipt = _admit_qualified_beta_transaction.to_wrap(
            transaction, control_ref, beta_ref, manifest_ref, manifest, 6
        )

        assert receipt["idempotent"] is True
        transaction.create.assert_not_called()
        transaction.set.assert_not_called()

    def test_qualified_beta_cas_race_never_stages_a_stable_or_cache_side_effect(self):
        manifest = normalize_release_manifest(_manifest())
        missing_manifest = MagicMock(exists=False)
        raced_beta = MagicMock(exists=True)
        raced_beta.to_dict.return_value = {"release_id": "v0.12.99+12099-macos", "build_number": 12099, "generation": 8}
        control_ref, manifest_ref, beta_ref = MagicMock(), MagicMock(), MagicMock()
        control_ref.get.return_value = MagicMock(exists=True)
        control_ref.get.return_value.to_dict.return_value = _control(
            enabled=True,
            tag=manifest["release_id"],
            generation=6,
            latest_reserved_build_number=manifest["build_number"],
        )
        manifest_ref.get.return_value = missing_manifest
        beta_ref.get.return_value = raced_beta
        transaction = MagicMock()

        with pytest.raises(ValueError, match="roll-forward only"):
            _admit_qualified_beta_transaction.to_wrap(transaction, control_ref, beta_ref, manifest_ref, manifest, 6)

        # The race is rejected before either mutable write is staged, and this
        # helper has no cache authority.
        transaction.create.assert_not_called()
        transaction.set.assert_not_called()

    def test_first_qualified_promotion_sets_generation_and_build(self):
        pointer = _build_pointer(
            {},
            normalize_release_manifest(_manifest()),
            transition="promote",
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
        pointer = _build_pointer(
            current,
            normalize_release_manifest(_manifest()),
            transition="promote",
            platform="macos",
            channel="beta",
            release_id=_manifest()["release_id"],
            expected_generation=3,
            expected_current_release_id="previous-release",
        )
        assert pointer is current
        assert pointer["generation"] == 4

    def test_rejects_rollback(self):
        current = {"release_id": "newer", "build_number": 13000, "generation": 2}
        with pytest.raises(ValueError, match="roll-forward only"):
            _build_pointer(
                current,
                normalize_release_manifest(_manifest()),
                transition="promote",
                platform="macos",
                channel="beta",
                release_id=_manifest()["release_id"],
                expected_generation=2,
            )

    def test_rejects_unqualified_release(self):
        manifest = _manifest(qualification_passed=False)
        with pytest.raises(ValueError, match="qualification"):
            _build_pointer(
                {},
                manifest,
                transition="promote",
                platform="macos",
                channel="beta",
                release_id=manifest["release_id"],
                expected_generation=None,
            )


class TestPointerRepointRules:
    def test_qualified_manifest_moves_the_same_release_from_beta_to_stable(self):
        """Local dry run of candidate evidence -> qualified manifest -> both pointers."""
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
            release_id=beta["release_id"],
            expected_generation=0,
        )

        assert beta["release_id"] == manifest["release_id"] == stable["release_id"]
        assert beta["generation"] == stable["generation"] == 1

    def test_repoints_a_qualified_retained_manifest_with_compare_and_swap(self):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        target = normalize_release_manifest(
            _manifest(
                release_id="v0.12.73+12073-macos",
                version="0.12.73",
                build_number=12073,
                zip_url="https://github.com/BasedHardware/omi/releases/download/v0.12.73+12073-macos/Omi.zip",
                dmg_url="https://github.com/BasedHardware/omi/releases/download/v0.12.73+12073-macos/omi.dmg",
                compatibility_contract={
                    "schema_version": 1,
                    "app_release_id": "v0.12.73+12073-macos",
                    "app_version": "0.12.73",
                    "app_build_number": 12073,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
            )
        )

        pointer = _build_pointer(
            current,
            target,
            transition="repoint",
            platform="macos",
            channel="beta",
            release_id=target["release_id"],
            expected_current_release_id=current["release_id"],
            expected_generation=7,
        )

        assert pointer["release_id"] == target["release_id"]
        assert pointer["generation"] == 8

    @pytest.mark.parametrize(
        "expected_release_id, expected_generation, message",
        [
            ("v0.12.83+12083-macos", 7, "current release mismatch"),
            ("v0.12.84+12084-macos", 6, "generation mismatch"),
        ],
    )
    def test_rejects_stale_repoint_compare_and_swap(self, expected_release_id, expected_generation, message):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        target = normalize_release_manifest(
            _manifest(
                release_id="v0.12.73+12073-macos",
                version="0.12.73",
                build_number=12073,
                zip_url="https://github.com/BasedHardware/omi/releases/download/v0.12.73+12073-macos/Omi.zip",
                dmg_url="https://github.com/BasedHardware/omi/releases/download/v0.12.73+12073-macos/omi.dmg",
                compatibility_contract={
                    "schema_version": 1,
                    "app_release_id": "v0.12.73+12073-macos",
                    "app_version": "0.12.73",
                    "app_build_number": 12073,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
            )
        )
        with pytest.raises(ValueError, match=message):
            _build_pointer(
                current,
                target,
                transition="repoint",
                platform="macos",
                channel="beta",
                release_id=target["release_id"],
                expected_current_release_id=expected_release_id,
                expected_generation=expected_generation,
            )

    def test_repoint_rejects_unqualified_manifest(self):
        current = {"release_id": "v0.12.84+12084-macos", "build_number": 12084, "generation": 7}
        target = _manifest(qualification_passed=False)
        with pytest.raises(ValueError, match="qualification"):
            _build_pointer(
                current,
                target,
                transition="repoint",
                platform="macos",
                channel="stable",
                release_id=target["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=7,
            )
