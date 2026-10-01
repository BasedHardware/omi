"""Unit tests verifying defensive boundary guards in desktop_update_channels."""

from datetime import datetime, timezone
import pytest

from database.desktop_update_channels import (
    admit_qualified_beta_manifest,
    build_channel_pointer,
    get_channel_release,
    get_release_manifest,
    promote_channel,
    reserve_beta_candidate,
    set_beta_admission_enabled,
)


def _valid_manifest() -> dict:
    return {
        "release_id": "v0.12.85+12085-macos",
        "platform": "macos",
        "channel": "stable",
        "version": "0.12.85",
        "build_number": 12085,
        "qualification_tier": "T2",
        "qualification_passed": True,
        "created_at": "2026-09-30T12:00:00Z",
        "dmg_url": "https://storage.googleapis.com/omi_macos_updates/releases/Omi-0.12.85.dmg",
        "dmg_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    }


def test_build_pointer_rejects_non_dict_payloads():
    """Verify build_channel_pointer strictly rejects non-dict current and manifest."""
    with pytest.raises(ValueError, match="current pointer must be a dictionary"):
        build_channel_pointer(
            "not-a-dict", {}, transition="promote", platform="macos", channel="stable", release_id="v1", expected_generation=None  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="manifest must be a dictionary"):
        build_channel_pointer(
            {}, "not-a-dict", transition="promote", platform="macos", channel="stable", release_id="v1", expected_generation=None  # type: ignore[arg-type]
        )


def test_build_pointer_rejects_invalid_generation_types():
    """Verify build_channel_pointer strictly rejects booleans, negative numbers, or invalid generation types."""
    current = {"generation": 2, "build_number": 100}
    manifest = {
        "platform": "macos",
        "qualification_tier": "T2",
        "qualification_passed": True,
        "version": "1.0.0",
        "build_number": 200,
    }
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        build_channel_pointer(
            current, manifest, transition="promote", platform="macos", channel="stable", release_id="v2", expected_generation=True  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        build_channel_pointer(
            current, manifest, transition="promote", platform="macos", channel="stable", release_id="v2", expected_generation=-1
        )


def test_build_pointer_coerces_naive_datetime():
    """Verify build_channel_pointer coerces a naive updated_at datetime to UTC."""
    current = {"generation": 0, "build_number": 100}
    manifest = {
        "platform": "macos",
        "qualification_tier": "T2",
        "qualification_passed": True,
        "version": "1.0.0",
        "build_number": 200,
    }
    naive_dt = datetime(2026, 9, 30, 14, 0, 0)
    pointer = build_channel_pointer(
        current,
        manifest,
        transition="promote",
        platform="macos",
        channel="stable",
        release_id="v2",
        expected_generation=0,
        updated_at=naive_dt,
    )
    assert pointer["updated_at"].tzinfo == timezone.utc


def test_promote_channel_rejects_invalid_input_types():
    """Verify promote_channel fails fast on non-string platform, channel, or release_id."""
    with pytest.raises(ValueError, match="platform must be a string"):
        promote_channel(123, "stable", "v1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="channel must be a string"):
        promote_channel("macos", 123, "v1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="release_id must be a string"):
        promote_channel("macos", "stable", 123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        promote_channel("macos", "stable", "v1", expected_generation="invalid")  # type: ignore[arg-type]


def test_get_channel_release_and_manifest_reject_non_string():
    """Verify get_channel_release and get_release_manifest reject non-string arguments."""
    with pytest.raises(ValueError, match="platform must be a string"):
        get_channel_release(123, "stable")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="channel must be a string"):
        get_channel_release("macos", 123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="release_id must be a string"):
        get_release_manifest(123)  # type: ignore[arg-type]


def test_set_beta_admission_enabled_rejects_non_bool():
    """Verify set_beta_admission_enabled strictly rejects non-boolean inputs."""
    with pytest.raises(ValueError, match="beta admission enabled must be a boolean"):
        set_beta_admission_enabled("true")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="beta admission enabled must be a boolean"):
        set_beta_admission_enabled(1)  # type: ignore[arg-type]


def test_reserve_beta_candidate_rejects_non_canonical_tag():
    """Verify reserve_beta_candidate rejects non-canonical candidate tags."""
    with pytest.raises(ValueError, match="candidate tag must be a canonical macOS tag"):
        reserve_beta_candidate("v0.12.0")
    with pytest.raises(ValueError, match="candidate tag must be a canonical macOS tag"):
        reserve_beta_candidate(None)  # type: ignore[arg-type]
