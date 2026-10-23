"""Unit tests verifying defensive boundary guards in desktop_previews."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
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
    _required_string,
    _optional_string,
)


def _valid_manifest() -> dict:
    return {
        "slug": "feature-test",
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "app_name": "Omi Preview (feature-test)",
        "bundle_id": "com.omi.preview.p0375d1f909",
        "url_scheme": "omi-preview-p0375d1f909",
        "built_at": "2026-09-30T12:00:00Z",
        "signer": "Developer ID Application: Based Hardware Inc (ABC123XYZ)",
        "notarization": "stapled",
        "dmg_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "dmg_url": "https://storage.googleapis.com/omi_macos_updates/previews/feature-test/0123456789abcdef0123456789abcdef01234567/Omi-Preview.dmg",
    }


def test_normalize_preview_manifest_rejects_non_dict():
    """Verify normalize_preview_manifest rejects non-dictionary data."""
    with pytest.raises(ValueError, match="preview manifest must be a dictionary"):
        normalize_preview_manifest(None)
    with pytest.raises(ValueError, match="preview manifest must be a dictionary"):
        normalize_preview_manifest("invalid")


def test_slug_and_sha_defensive_types():
    """Verify slug, source_sha, and sha256 strictly reject non-string types and invalid patterns."""
    with pytest.raises(ValueError, match="slug must be a string"):
        _slug(123)
    with pytest.raises(ValueError, match="source_sha must be a string"):
        _source_sha(123)
    with pytest.raises(ValueError, match="dmg_sha256 must be a string"):
        _sha256(123)

    # Empty / whitespace-only
    with pytest.raises(ValueError, match="slug must use lowercase letters"):
        _slug("   ")


def test_publish_preview_rejects_invalid_generation_types():
    """Verify publish_preview strictly rejects booleans, strings, or negative values for expected_generation."""
    manifest = _valid_manifest()
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation=True)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation=-5)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        publish_preview(manifest, expected_generation="2")


def test_delist_preview_rejects_invalid_types():
    """Verify delist_preview rejects non-string slugs and boolean or negative expected_generation."""
    with pytest.raises(ValueError, match="slug must be a string"):
        delist_preview(None, expected_generation=0)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation=True)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation=-1)
    with pytest.raises(ValueError, match="expected_generation must be a non-negative integer"):
        delist_preview("feature-test", expected_generation="0")


def test_get_preview_rejects_non_string():
    """Verify get_preview_manifest and get_current_preview reject non-string keys."""
    with pytest.raises(ValueError, match="slug must be a string"):
        get_current_preview(123)
    with pytest.raises(ValueError, match="slug must be a string"):
        get_preview_manifest(None, "0123456789abcdef0123456789abcdef01234567")
    with pytest.raises(ValueError, match="source_sha must be a string"):
        get_preview_manifest("feature-test", 123)


def test_build_preview_pointer_naive_datetime_coercion():
    """Verify naive datetime passed as updated_at is coerced to UTC."""
    current = {"generation": 0, "source_sha": "oldsha"}
    manifest = {"slug": "feature-test", "source_sha": "newsha"}
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    pointer = _build_preview_pointer(current, manifest, expected_generation=0, updated_at=naive_dt)
    assert pointer["updated_at"].tzinfo == timezone.utc
    assert pointer["generation"] == 1


def test_build_preview_pointer_aware_non_utc_conversion():
    """Verify aware non-UTC datetime passed as updated_at is converted to UTC cleanly."""
    from datetime import timedelta

    current = {"generation": 0, "source_sha": "oldsha"}
    manifest = {"slug": "feature-test", "source_sha": "newsha"}
    tz_offset = timezone(timedelta(hours=5))
    aware_dt = datetime(2026, 9, 30, 17, 0, 0, tzinfo=tz_offset)
    pointer = _build_preview_pointer(current, manifest, expected_generation=0, updated_at=aware_dt)
    assert pointer["updated_at"].tzinfo == timezone.utc
    assert pointer["updated_at"] == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    assert pointer["generation"] == 1


def test_build_preview_pointer_rejects_non_dict():
    """Verify _build_preview_pointer rejects non-dict inputs."""
    with pytest.raises(ValueError, match="current pointer must be a dictionary"):
        _build_preview_pointer("not-a-dict", {}, expected_generation=0)
    with pytest.raises(ValueError, match="manifest must be a dictionary"):
        _build_preview_pointer({}, "not-a-dict", expected_generation=0)


@pytest.mark.parametrize('payload', [None, False, 42, [], b'{}'])
def test_untrusted_preview_payloads_fail_before_any_database_access(payload):
    client = MagicMock()
    with pytest.raises(ValueError, match='preview manifest must be a dictionary'):
        publish_preview(payload, firestore_client=client)
    with pytest.raises(ValueError, match='data payload must be a dictionary'):
        _required_string(payload, 'slug')
    with pytest.raises(ValueError, match='data payload must be a dictionary'):
        _optional_string(payload, 'notes')
    client.assert_not_called()
    assert not client.mock_calls


@pytest.mark.parametrize('generation', [True, False, -1, 0.5, '0', {}, []])
def test_untrusted_generations_still_reject_bool_coercion_and_nonintegers(generation):
    client = MagicMock()
    with pytest.raises(ValueError, match='expected_generation must be a non-negative integer'):
        publish_preview(_valid_manifest(), expected_generation=generation, firestore_client=client)
    with pytest.raises(ValueError, match='expected_generation must be a non-negative integer'):
        delist_preview('feature-test', expected_generation=generation, firestore_client=client)
    with pytest.raises(ValueError, match='expected_generation must be a non-negative integer'):
        _build_preview_pointer({}, {}, expected_generation=generation)
    assert not client.mock_calls


@pytest.mark.parametrize('updated_at', [False, 0, '', [], {}])
def test_untrusted_pointer_timestamp_is_not_coerced_or_silently_accepted(updated_at):
    with pytest.raises(ValueError, match='updated_at must be a datetime'):
        _build_preview_pointer(
            {'generation': 0},
            {'slug': 'feature-test', 'source_sha': 'newsha'},
            expected_generation=0,
            updated_at=updated_at,
        )
