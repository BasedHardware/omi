"""Unit tests verifying defensive boundary guards in desktop_previews."""

from datetime import datetime, timezone
import pytest

from database.desktop_previews import (
    delist_preview,
    get_current_preview,
    get_preview_manifest,
    normalize_preview_manifest,
    publish_preview,
    _build_preview_pointer,
    _slug,
    _source_sha,
    _sha256,
)


def _valid_manifest() -> dict:
    return {
        "slug": "feature-test",
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "app_name": "Omi Preview (feature-test)",
        "bundle_id": "com.omi.preview.p48ec788481",
        "url_scheme": "omi-preview-p48ec788481",
        "built_at": "2026-09-30T12:00:00Z",
        "signer": "Developer ID Application: Based Hardware Inc (ABC123XYZ)",
        "notarization": "stapled",
        "dmg_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "dmg_url": "https://storage.googleapis.com/omi_macos_updates/previews/feature-test/0123456789abcdef0123456789abcdef01234567/Omi-Preview.dmg",
    }


def test_normalize_preview_manifest_rejects_non_dict():
    """Verify normalize_preview_manifest rejects non-dictionary data."""
    with pytest.raises(ValueError, match="preview manifest must be a dictionary"):
        normalize_preview_manifest(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="preview manifest must be a dictionary"):
        normalize_preview_manifest("invalid")  # type: ignore[arg-type]


def test_slug_and_sha_defensive_types():
    """Verify slug, source_sha, and sha256 strictly reject non-string types and invalid patterns."""
    with pytest.raises(ValueError, match="slug must be a string"):
        _slug(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source_sha must be a string"):
        _source_sha(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dmg_sha256 must be a string"):
        _sha256(123)  # type: ignore[arg-type]

    # Empty / whitespace-only
    with pytest.raises(ValueError, match="slug must use lowercase letters"):
        _slug("   ")


def test_publish_preview_rejects_invalid_generation_types():
    """Verify publish_preview strictly rejects booleans, strings, or negative values for expected_generation."""
    manifest = _valid_manifest()
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation=-5)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation="2")  # type: ignore[arg-type]


def test_delist_preview_rejects_invalid_types():
    """Verify delist_preview rejects non-string slugs and boolean or negative expected_generation."""
    with pytest.raises(ValueError, match="slug must be a string"):
        delist_preview(None, expected_generation=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation=-1)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation="0")  # type: ignore[arg-type]


def test_get_preview_rejects_non_string():
    """Verify get_preview_manifest and get_current_preview reject non-string keys."""
    with pytest.raises(ValueError, match="slug must be a string"):
        get_current_preview(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="slug must be a string"):
        get_preview_manifest(None, "0123456789abcdef0123456789abcdef01234567")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source_sha must be a string"):
        get_preview_manifest("feature-test", 123)  # type: ignore[arg-type]


def test_build_preview_pointer_naive_datetime_coercion():
    """Verify naive datetime passed as updated_at is coerced to UTC."""
    current = {"generation": 0, "source_sha": "oldsha"}
    manifest = {"slug": "feature-test", "source_sha": "newsha"}
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    pointer = _build_preview_pointer(current, manifest, expected_generation=0, updated_at=naive_dt)
    assert pointer["updated_at"].tzinfo == timezone.utc
    assert pointer["generation"] == 1


def test_build_preview_pointer_rejects_non_dict():
    """Verify _build_preview_pointer rejects non-dict inputs."""
    with pytest.raises(ValueError, match="current pointer must be a dictionary"):
        _build_preview_pointer("not-a-dict", {}, expected_generation=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="manifest must be a dictionary"):
        _build_preview_pointer({}, "not-a-dict", expected_generation=0)  # type: ignore[arg-type]
