from datetime import datetime, timezone
import hashlib
import json

import pytest

import database.desktop_update_channels as channels_db
import database.desktop_beta_breakglass as breakglass_db
from database.desktop_update_channels import (
    BETA_ADMISSION_COLLECTION,
    BETA_ADMISSION_DOCUMENT,
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
from database.desktop_beta_breakglass import (
    BETA_BREAKGLASS_AUDITS_COLLECTION,
    emergency_rollout_beta,
    rollback_beta,
)
from tests.store_fakes import FakeDocumentStore
from tests.unit.fixtures.desktop_release_manifest import make_desktop_release_manifest as _manifest

CONTROL_PATH = f"{BETA_ADMISSION_COLLECTION}/{BETA_ADMISSION_DOCUMENT}"
BETA_POINTER_PATH = "desktop_update_channels/macos-beta"
STABLE_POINTER_PATH = "desktop_update_channels/macos-stable"


@pytest.fixture
def store(monkeypatch):
    """Inject one FakeDocumentStore at the ``_store`` seam of both cluster modules."""
    fake = FakeDocumentStore()
    monkeypatch.setattr(channels_db, "_store", lambda: fake)
    monkeypatch.setattr(breakglass_db, "_store", lambda: fake)
    return fake


def _manifest_path(release_id):
    return f"desktop_release_manifests/{release_id}"


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
    def test_registered_manifest_round_trips_through_retry_retained_read_and_promotion(self, store):
        """A stored snapshot preserves the canonical manifest bytes exactly."""
        manifest = _manifest()

        registered = register_release_manifest(manifest)
        stored = store.get(_manifest_path(manifest["release_id"])).to_dict()
        assert stored == manifest
        assert stored["created_at"] == manifest["created_at"]
        assert isinstance(stored["created_at"], str)

        assert register_release_manifest(manifest) == registered
        assert get_release_manifest(manifest["release_id"]) == registered

        pointer = promote_channel("macos", "stable", manifest["release_id"], expected_generation=0)
        resolved = get_channel_release("macos", "stable")

        assert pointer["generation"] == 1
        assert resolved is not None
        assert resolved["manifest"] == registered
        assert store.get(_manifest_path(manifest["release_id"])).to_dict() == manifest
        assert promote_channel("macos", "stable", manifest["release_id"], expected_generation=0) == pointer

    def test_qualified_beta_admission_preserves_created_canonical_manifest_for_exact_retry_and_resolution(self, store):
        """The transaction-created snapshot is the canonical object Beta subsequently resolves."""
        store.set(CONTROL_PATH, _control())
        manifest = normalize_release_manifest(_manifest())
        canonical_bytes = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()

        first = admit_qualified_beta_manifest(manifest, control_generation=1)
        stored = store.get(_manifest_path(manifest["release_id"])).to_dict()
        assert stored == manifest
        assert json.dumps(stored, sort_keys=True, separators=(',', ':')).encode() == canonical_bytes
        assert stored["created_at"] == manifest["created_at"]
        assert isinstance(stored["created_at"], str)

        retry = admit_qualified_beta_manifest(manifest, control_generation=1)
        assert retry["idempotent"] is True
        assert retry["pointer"]["generation"] == first["pointer"]["generation"] == 1

        resolved = get_channel_release("macos", "beta")
        assert resolved is not None
        assert resolved["manifest"] == manifest
        assert json.dumps(resolved["manifest"], sort_keys=True, separators=(',', ':')).encode() == canonical_bytes


class TestBetaAdmissionControl:
    def test_first_reservation_creates_a_paused_control_and_same_tag_is_write_free(self, store):
        first = reserve_beta_candidate("v0.12.64+12064-macos")
        revision_after_first = store._updated[CONTROL_PATH]
        retry = reserve_beta_candidate("v0.12.64+12064-macos")

        assert first["promotion_enabled"] is False
        assert first["control_generation"] == 1
        assert retry == first
        # An identical reservation is write-free: the control revision is unchanged.
        assert store._updated[CONTROL_PATH] == revision_after_first

    def test_higher_reservation_preserves_pause_and_fences_prior_capture(self, store):
        store.set(CONTROL_PATH, _control(enabled=True))
        captured = capture_beta_admission("v0.12.64+12064-macos")
        newer = reserve_beta_candidate("v0.12.65+12065-macos")

        assert captured["control_generation"] == 1
        assert newer["promotion_enabled"] is True
        assert newer["control_generation"] == 2
        with pytest.raises(ValueError, match="reservation|generation"):
            admit_qualified_beta_manifest(_manifest(), control_generation=captured["control_generation"])
        assert _manifest_path(_manifest()["release_id"]) not in store._docs
        assert BETA_POINTER_PATH not in store._docs

        store.set(CONTROL_PATH, _control(enabled=False))
        assert reserve_beta_candidate("v0.12.65+12065-macos")["promotion_enabled"] is False

    @pytest.mark.parametrize("tag", ["v0.12.63+12063-macos", "v0.12.64+12064-macos"])
    def test_lower_or_same_build_different_tag_is_rejected(self, tag, store):
        store.set(CONTROL_PATH, _control())
        if tag == "v0.12.64+12064-macos":
            tag = "v0.12.63+12064-macos"
        with pytest.raises(ValueError, match="roll forward"):
            reserve_beta_candidate(tag)

    def test_pause_transition_invalidates_inflight_promotion_and_pause_without_reservation_rejects_resume(self, store):
        store.set(CONTROL_PATH, _control(enabled=True))
        captured = capture_beta_admission("v0.12.64+12064-macos")
        paused = set_beta_admission_enabled(False)

        assert paused["control_generation"] == captured["control_generation"] + 1
        with pytest.raises(ValueError, match="disabled|generation"):
            admit_qualified_beta_manifest(_manifest(), control_generation=captured["control_generation"])

        store.delete(CONTROL_PATH)
        with pytest.raises(ValueError, match="reservation"):
            set_beta_admission_enabled(True)

    def test_reservation_then_resume_allows_a_commit_and_later_reservation_keeps_that_commit_valid(self, store):
        reserved = reserve_beta_candidate("v0.12.64+12064-macos")
        enabled = set_beta_admission_enabled(True)
        first = admit_qualified_beta_manifest(_manifest(), control_generation=enabled["control_generation"])
        newer = reserve_beta_candidate("v0.12.65+12065-macos")

        assert reserved["promotion_enabled"] is False
        assert enabled["promotion_enabled"] is True
        assert first["pointer"]["release_id"] == _manifest()["release_id"]
        assert newer["control_generation"] == enabled["control_generation"] + 1
        assert store.get(BETA_POINTER_PATH).to_dict()["release_id"] == _manifest()["release_id"]

    def test_paused_or_superseded_idempotent_pointer_retry_has_no_writes(self, store):
        manifest = _manifest()
        store.set(CONTROL_PATH, _control(enabled=False))
        store.set(_manifest_path(manifest["release_id"]), manifest)
        store.set(
            BETA_POINTER_PATH,
            {"release_id": manifest["release_id"], "build_number": manifest["build_number"], "generation": 4},
        )
        before = dict(store._updated)
        with pytest.raises(ValueError, match="disabled"):
            admit_qualified_beta_manifest(manifest, control_generation=1)
        assert store._updated == before

        store.set(
            CONTROL_PATH,
            _control(enabled=True, tag="v0.12.65+12065-macos", latest_reserved_build_number=12065, generation=2),
        )
        before = dict(store._updated)
        with pytest.raises(ValueError, match="reservation|generation"):
            admit_qualified_beta_manifest(manifest, control_generation=1)
        assert store._updated == before

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
    def test_malformed_control_fails_closed_without_manifest_or_pointer_writes(self, bad, store):
        store.set(CONTROL_PATH, bad)
        with pytest.raises(ValueError, match="admission control"):
            capture_beta_admission("v0.12.64+12064-macos")
        assert _manifest_path(_manifest()["release_id"]) not in store._docs

    def test_admission_transaction_reads_control_first_and_all_docs_before_writes(self, store):
        store.set(CONTROL_PATH, _control(enabled=True))
        receipt = admit_qualified_beta_manifest(_manifest(), control_generation=1)

        assert receipt["pointer"]["channel"] == "beta"
        assert store.get(BETA_POINTER_PATH).to_dict()["release_id"] == _manifest()["release_id"]

    def test_register_is_idempotent_for_identical_manifest(self, store):
        manifest = _manifest()
        store.set(_manifest_path(manifest["release_id"]), manifest)
        revision_before = store._updated[_manifest_path(manifest["release_id"])]

        result = register_release_manifest(manifest)

        assert result == normalize_release_manifest(manifest)
        # Idempotent registration re-creates nothing: the stored revision is unchanged.
        assert store._updated[_manifest_path(manifest["release_id"])] == revision_before

    def test_register_rejects_release_id_mutation(self, store):
        # A doc already retained at this release_id's path but carrying different immutable metadata.
        store.set(
            _manifest_path(_manifest()["release_id"]),
            _manifest(
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
            ),
        )

        with pytest.raises(ValueError, match="immutable"):
            register_release_manifest(_manifest())

    def test_resolves_pointer_to_manifest(self, store):
        store.set(
            BETA_POINTER_PATH,
            {"release_id": _manifest()["release_id"], "generation": 4, "updated_at": "2026-07-09T12:00:00Z"},
        )
        store.set(_manifest_path(_manifest()["release_id"]), _manifest())

        result = get_channel_release("macos", "beta")

        assert result is not None
        assert result["pointer"]["generation"] == 4
        assert result["manifest"]["release_id"] == _manifest()["release_id"]

    def test_reads_retained_manifest_without_a_channel_or_release_metadata(self, store):
        store.set(_manifest_path(_manifest()["release_id"]), _manifest())

        assert get_release_manifest(_manifest()["release_id"]) == normalize_release_manifest(_manifest())


class TestChannelPromotionRules:
    def test_qualified_beta_transaction_touches_only_its_manifest_and_beta_pointer(self, store):
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
        store.set(
            CONTROL_PATH,
            _control(
                enabled=True,
                tag=manifest["release_id"],
                generation=6,
                latest_reserved_build_number=manifest["build_number"],
            ),
        )
        store.set(BETA_POINTER_PATH, {"release_id": "v0.12.92+12092-macos", "build_number": 12092, "generation": 3})

        receipt = admit_qualified_beta_manifest(manifest, control_generation=6)

        assert receipt["pointer"]["channel"] == "beta"
        assert receipt["pointer"]["generation"] == 4
        # Touches only its own manifest and the Beta pointer; Stable is untouched.
        assert store.get(_manifest_path(manifest["release_id"])).to_dict() == manifest
        assert store.get(BETA_POINTER_PATH).to_dict()["release_id"] == manifest["release_id"]
        assert STABLE_POINTER_PATH not in store._docs

    def test_qualified_beta_transaction_lost_response_retry_is_idempotent_without_a_second_pointer_write(self, store):
        manifest = normalize_release_manifest(_manifest())
        store.set(
            CONTROL_PATH,
            _control(
                enabled=True,
                tag=manifest["release_id"],
                generation=6,
                latest_reserved_build_number=manifest["build_number"],
            ),
        )
        store.set(_manifest_path(manifest["release_id"]), manifest)
        store.set(
            BETA_POINTER_PATH,
            {"release_id": manifest["release_id"], "build_number": manifest["build_number"], "generation": 4},
        )
        before = dict(store._updated)

        receipt = admit_qualified_beta_manifest(manifest, control_generation=6)

        assert receipt["idempotent"] is True
        # No second write to either the manifest or the pointer.
        assert store._updated == before

    def test_qualified_beta_cas_race_never_stages_a_stable_or_cache_side_effect(self, store):
        manifest = normalize_release_manifest(_manifest())
        store.set(
            CONTROL_PATH,
            _control(
                enabled=True,
                tag=manifest["release_id"],
                generation=6,
                latest_reserved_build_number=manifest["build_number"],
            ),
        )
        store.set(BETA_POINTER_PATH, {"release_id": "v0.12.99+12099-macos", "build_number": 12099, "generation": 8})
        before = dict(store._updated)

        with pytest.raises(ValueError, match="roll-forward only"):
            admit_qualified_beta_manifest(manifest, control_generation=6)

        # The race is rejected before either mutable write is staged.
        assert store._updated == before
        assert STABLE_POINTER_PATH not in store._docs

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


class TestBetaBreakglass:
    def _stored(self, build: int, *, qualified: bool = True):
        tag = f"v0.12.{build - 12000}+{build}-macos"
        return normalize_release_manifest(
            _manifest(
                release_id=tag,
                version=f"0.12.{build - 12000}",
                build_number=build,
                zip_url=f"https://github.com/BasedHardware/omi/releases/download/{tag}/Omi.zip",
                dmg_url=f"https://github.com/BasedHardware/omi/releases/download/{tag}/omi.dmg",
                qualification_tier="T2" if qualified else "emergency",
                qualification_passed=qualified,
                qualification_evidence_asset=(
                    "qualification-evidence-" + tag + ".json" if qualified else "desktop-smoke-result.json"
                ),
                compatibility_contract={
                    "schema_version": 1,
                    "app_release_id": tag,
                    "app_version": f"0.12.{build - 12000}",
                    "app_build_number": build,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
            )
        )

    def _request(self, current: str, target: str, generation: int, *, operation: str):
        return {
            "current_release_id": current,
            "target_release_id": target,
            "expected_generation": generation,
            "actor": "release-operator",
            "reason": "Beta crashes before startup",
            "incident_url": "https://github.com/BasedHardware/omi/issues/12345",
            "request_id": "https://github.com/BasedHardware/omi/actions/runs/12345/attempts/1",
            "normal_path_unavailable": "qualification runner is unavailable" if operation == "rollout" else None,
        }

    def test_rollback_only_repoints_retained_t2_manifest_and_pauses_admission_atomically(self, store):
        broken, known_good = self._stored(12084), self._stored(12073)
        store.set(CONTROL_PATH, _control(enabled=True, generation=7))
        store.set(_manifest_path(broken["release_id"]), broken)
        store.set(_manifest_path(known_good["release_id"]), known_good)
        store.set(
            BETA_POINTER_PATH,
            {"release_id": broken["release_id"], "build_number": broken["build_number"], "generation": 4},
        )

        receipt = rollback_beta(
            self._request(broken["release_id"], known_good["release_id"], 4, operation="rollback"),
            now=datetime(2026, 7, 22, 12, 5, tzinfo=timezone.utc),
        )
        assert receipt["pointer"]["release_id"] == known_good["release_id"]
        assert store.get(CONTROL_PATH).to_dict()["promotion_enabled"] is False
        audit_id = hashlib.sha256(
            "https://github.com/BasedHardware/omi/actions/runs/12345/attempts/1".encode()
        ).hexdigest()
        audit = store.get(f"{BETA_BREAKGLASS_AUDITS_COLLECTION}/{audit_id}").to_dict()
        assert audit["operation"] == "rollback"
        assert audit["resulting_generation"] == 5

    def test_breakglass_rejects_invalid_incident_identity_and_stale_cas_without_writes(self, store):
        broken, target = self._stored(12084), self._stored(12073)

        def seed():
            store._docs.clear()
            store._updated.clear()
            store.set(CONTROL_PATH, _control(enabled=True, generation=7))
            store.set(_manifest_path(broken["release_id"]), broken)
            store.set(_manifest_path(target["release_id"]), target)
            store.set(
                BETA_POINTER_PATH,
                {"release_id": broken["release_id"], "build_number": broken["build_number"], "generation": 4},
            )

        for field, value in (
            ("incident_url", "https://example.com/incident"),
            ("request_id", "manual-request-id"),
            ("expected_generation", 3),
        ):
            seed()
            request = self._request(broken["release_id"], target["release_id"], 4, operation="rollback")
            request[field] = value
            with pytest.raises(ValueError):
                rollback_beta(request, now=datetime(2026, 7, 22, 12, tzinfo=timezone.utc))
            assert store.get(BETA_POINTER_PATH).to_dict()["release_id"] == broken["release_id"]
            assert not any(path.startswith(BETA_BREAKGLASS_AUDITS_COLLECTION + "/") for path in store._docs)

    def test_emergency_rollout_requires_higher_exact_evidence_and_preserves_failed_qualification_truth(self, store):
        broken, emergency = self._stored(12084), self._stored(12085, qualified=False)
        store.set(CONTROL_PATH, _control(enabled=True, generation=7))
        store.set(_manifest_path(broken["release_id"]), broken)
        store.set(
            BETA_POINTER_PATH,
            {"release_id": broken["release_id"], "build_number": broken["build_number"], "generation": 4},
        )
        request = self._request(broken["release_id"], emergency["release_id"], 4, operation="rollout")
        receipt = emergency_rollout_beta(request, emergency, now=datetime(2026, 7, 22, 12, 5, tzinfo=timezone.utc))
        assert receipt["pointer"]["release_id"] == emergency["release_id"]
        assert store.get(_manifest_path(emergency["release_id"])).to_dict()["qualification_passed"] is False
        assert store.get(CONTROL_PATH).to_dict()["promotion_enabled"] is False

    def test_audit_collision_or_write_failure_leaves_pointer_unchanged(self, store):
        broken, target = self._stored(12084), self._stored(12073)
        request = self._request(broken["release_id"], target["release_id"], 4, operation="rollback")
        store.set(CONTROL_PATH, _control(enabled=True, generation=7))
        store.set(_manifest_path(broken["release_id"]), broken)
        store.set(_manifest_path(target["release_id"]), target)
        store.set(
            BETA_POINTER_PATH,
            {"release_id": broken["release_id"], "build_number": broken["build_number"], "generation": 4},
        )
        audit_id = hashlib.sha256(str(request["request_id"]).encode()).hexdigest()
        store.set(f"{BETA_BREAKGLASS_AUDITS_COLLECTION}/{audit_id}", {"already": "exists"})

        with pytest.raises(Exception):
            rollback_beta(request)
        assert store.get(BETA_POINTER_PATH).to_dict()["release_id"] == broken["release_id"]
