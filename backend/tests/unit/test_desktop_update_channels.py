from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database.desktop_update_channels import (
    _build_pointer,
    get_channel_release,
    normalize_release_manifest,
    register_release_manifest,
)


def _manifest(**overrides):
    data = {
        "release_id": "v0.12.64+12064-macos",
        "platform": "macos",
        "version": "0.12.64+12064",
        "build_number": 12064,
        "zip_url": "https://github.com/BasedHardware/omi/releases/download/test/Omi.zip",
        "dmg_url": "https://github.com/BasedHardware/omi/releases/download/test/Omi.dmg",
        "beta_zip_url": "https://github.com/BasedHardware/omi/releases/download/test/Omi.Beta.zip",
        "beta_dmg_url": "https://github.com/BasedHardware/omi/releases/download/test/omi-beta.dmg",
        "ed_signature": "sparkle-signature",
        "beta_ed_signature": "beta-sparkle-signature",
        "published_at": "2026-07-09T12:00:00Z",
        "changelog": ["Qualified beta"],
        "mandatory": False,
        "source_sha": "a" * 40,
        "zip_sha256": "b" * 64,
        "dmg_sha256": "c" * 64,
        "beta_zip_sha256": "d" * 64,
        "beta_dmg_sha256": "e" * 64,
        "qualification": {"tier": "T2", "passed": True},
    }
    data.update(overrides)
    return data


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

    def test_requires_all_beta_identity_artifact_fields_for_macos(self):
        for field in ("beta_zip_url", "beta_dmg_url", "beta_ed_signature", "beta_zip_sha256", "beta_dmg_sha256"):
            with pytest.raises(ValueError, match=field):
                normalize_release_manifest(_manifest(**{field: None}))


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
        manifest = normalize_release_manifest(_manifest(qualification={"passed": False, "tier": "T2"}))
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
            _manifest(release_id="v0.12.73+12073-macos", version="0.12.73+12073", build_number=12073)
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
            _manifest(release_id="v0.12.73+12073-macos", version="0.12.73+12073", build_number=12073)
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
        target = normalize_release_manifest(_manifest(qualification={"tier": "T2", "passed": False}))
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
