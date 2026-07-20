from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database.desktop_update_channels import (
    _build_pointer,
    _rollback_macos_beta_transaction,
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
            expected_generation=4,
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
        pointer = _build_pointer(
            current,
            target,
            transition="rollback",
            platform="macos",
            channel="beta",
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
            _build_pointer(
                current,
                target,
                transition="rollback",
                platform="macos",
                channel="beta",
                release_id=target["release_id"],
                expected_current_release_id="v0.12.83+12083-macos",
                expected_generation=7,
            )
        with pytest.raises(ValueError, match="generation mismatch"):
            _build_pointer(
                current,
                target,
                transition="rollback",
                platform="macos",
                channel="beta",
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
            _build_pointer(
                current,
                unqualified,
                transition="rollback",
                platform="macos",
                channel="beta",
                release_id=unqualified["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=7,
            )


class TestEmergencyBetaPromotionRules:
    """Emergency promotion is ordinary promotion with the T2 gate relaxed.

    These cover the break-glass contract: it may ship unqualified builds to
    beta, it must still compare-and-swap, and it must never reach stable.
    """

    def _unqualified(self):
        return normalize_release_manifest(
            _manifest(
                release_id="v0.12.87+12087-macos",
                version="0.12.87+12087",
                build_number=12087,
                qualification={"tier": "T2", "passed": False},
            )
        )

    def _current(self):
        return {"release_id": "v0.12.86+12086-macos", "build_number": 12086, "generation": 9}

    def test_promotes_an_unqualified_build_and_marks_the_pointer_emergency(self):
        current = self._current()
        target = self._unqualified()
        pointer = _build_pointer(
            current,
            target,
            transition="emergency",
            platform="macos",
            channel="beta",
            release_id=target["release_id"],
            expected_current_release_id=current["release_id"],
            expected_generation=9,
        )
        assert pointer["release_id"] == target["release_id"]
        assert pointer["generation"] == 10
        assert pointer["emergency"] is True

    def test_normal_promotion_still_rejects_the_same_unqualified_build(self):
        with pytest.raises(ValueError, match="qualification"):
            _build_pointer(
                self._current(),
                self._unqualified(),
                transition="promote",
                platform="macos",
                channel="beta",
                release_id="v0.12.87+12087-macos",
                expected_generation=9,
            )

    @pytest.mark.parametrize(
        "expected_release_id, expected_generation, message",
        [
            ("v0.12.99+12099-macos", 9, "current release mismatch"),
            ("v0.12.86+12086-macos", 3, "generation mismatch"),
        ],
    )
    def test_rejects_a_stale_compare_and_swap(self, expected_release_id, expected_generation, message):
        with pytest.raises(ValueError, match=message):
            _build_pointer(
                self._current(),
                self._unqualified(),
                transition="emergency",
                platform="macos",
                channel="beta",
                release_id="v0.12.87+12087-macos",
                expected_current_release_id=expected_release_id,
                expected_generation=expected_generation,
            )

    def test_is_roll_forward_only(self):
        current = {"release_id": "v0.12.86+12086-macos", "build_number": 12086, "generation": 9}
        older = normalize_release_manifest(
            _manifest(
                release_id="v0.12.80+12080-macos",
                version="0.12.80+12080",
                build_number=12080,
                qualification={"tier": "T2", "passed": False},
            )
        )
        with pytest.raises(ValueError, match="roll-forward only"):
            _build_pointer(
                current,
                older,
                transition="emergency",
                platform="macos",
                channel="beta",
                release_id=older["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=9,
            )

    @pytest.mark.parametrize("channel", ["stable"])
    def test_never_reaches_stable(self, channel):
        current = self._current()
        target = self._unqualified()
        with pytest.raises(ValueError, match="only permitted for the macos beta channel"):
            _build_pointer(
                current,
                target,
                transition="emergency",
                platform="macos",
                channel=channel,
                release_id=target["release_id"],
                expected_current_release_id=current["release_id"],
                expected_generation=9,
            )
