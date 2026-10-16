"""Unit tests for database.api_key_metadata — document_id sanitization,
datetime coercion boundaries, scope/prefix normalization, and repair
detection."""

from datetime import datetime, timezone

import pytest

from database.api_key_metadata import (
    ApiKeyMetadataRepair,
    _coerce_utc_datetime,
    is_valid_api_key_hash,
    normalize_api_key_scopes,
    project_api_key_metadata,
)


class _Ts:
    """Firestore-style timestamp exposing to_datetime()."""

    def __init__(self, dt):
        self._dt = dt

    def to_datetime(self):
        return self._dt


class TestDocumentId:
    def test_document_id_is_stripped(self):
        out = project_api_key_metadata(document_id='  doc1  ', raw={}, snapshot_create_time=None, key_kind='mcp')
        assert out.metadata['id'] == 'doc1'

    def test_blank_document_id_raises(self):
        with pytest.raises(ValueError):
            project_api_key_metadata(document_id='   ', raw={}, snapshot_create_time=None, key_kind='mcp')

    def test_nonstring_document_id_raises(self):
        with pytest.raises(ValueError):
            project_api_key_metadata(document_id=7, raw={}, snapshot_create_time=None, key_kind='mcp')


class TestDatetimeCoercion:
    def test_firestore_timestamp_object_coerced(self):
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert _coerce_utc_datetime(_Ts(dt)) == dt

    def test_iso_string_coerced(self):
        assert _coerce_utc_datetime('2025-06-01T12:00:00Z') == datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)

    def test_naive_datetime_assumes_utc(self):
        assert _coerce_utc_datetime(datetime(2025, 1, 1)) == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_malformed_types_return_none(self):
        assert _coerce_utc_datetime([1, 2]) is None
        assert _coerce_utc_datetime(object()) is None

    def test_overflow_boundary_returns_none(self):
        far = datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc)
        # offset conversion past datetime range -> OverflowError -> None
        assert _coerce_utc_datetime(far) == far

    def test_to_datetime_wrong_type_returns_none(self):
        class Bad:
            def to_datetime(self):
                return 'not a datetime'

        assert _coerce_utc_datetime(Bad()) is None


class TestScopeNormalization:
    def test_scopes_are_stripped(self):
        out = normalize_api_key_scopes(
            [' memories ', 'integrations '],
            allowed_scopes=['memories', 'integrations'],
        )
        assert out == ['memories', 'integrations']

    def test_unknown_scopes_dropped(self):
        out = normalize_api_key_scopes(['memories', 'admin'], allowed_scopes=['memories'])
        assert out == ['memories']

    def test_none_value_returns_missing(self):
        assert normalize_api_key_scopes(None, allowed_scopes=['a']) is None


class TestProjection:
    def test_raw_token_name_repaired(self):
        raw = {'name': 'omi_mcp_' + 'a' * 32}
        out = project_api_key_metadata(document_id='d1', raw=raw, snapshot_create_time=None, key_kind='mcp')
        assert ApiKeyMetadataRepair.NAME in out.repairs

    def test_key_prefix_whitespace_normalized(self):
        raw = {'key_prefix': '  omi_mcp_ab12...cd34  '}
        out = project_api_key_metadata(document_id='d1', raw=raw, snapshot_create_time=None, key_kind='mcp')
        assert ApiKeyMetadataRepair.KEY_PREFIX not in out.repairs

    def test_hash_validation_shape(self):
        assert is_valid_api_key_hash('a' * 64)
        assert not is_valid_api_key_hash('z' * 64)
