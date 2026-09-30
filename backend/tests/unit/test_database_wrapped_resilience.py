import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from backend.database.wrapped import (
    _validate_identifier,
    _validate_year,
    _get_wrapped_doc_path,
    get_wrapped,
    create_wrapped,
    update_wrapped_status,
    update_wrapped_progress,
    reset_wrapped_for_regeneration,
    is_wrapped_stuck,
    VALID_WRAPPED_STATUSES,
    MIN_YEAR,
    MAX_YEAR
)
from backend.models.wrapped import WrappedStatus


class TestInputValidation:
    """Tests for identifier and year validation."""

    def test_validate_identifier_valid(self):
        assert _validate_identifier("user123") == "user123"
        assert _validate_identifier("  user123  ") == "user123"

    def test_validate_identifier_empty(self):
        with pytest.raises(ValueError, match="non-empty string"):
            _validate_identifier("")
        with pytest.raises(ValueError, match="non-empty string"):
            _validate_identifier(None)

    def test_validate_identifier_whitespace(self):
        with pytest.raises(ValueError, match="whitespace"):
            _validate_identifier("   ")

    def test_validate_identifier_path_traversal(self):
        with pytest.raises(ValueError, match="path separators"):
            _validate_identifier("user/123")
        with pytest.raises(ValueError, match="path separators"):
            _validate_identifier("../user")

    def test_validate_year_valid(self):
        assert _validate_year(2023) == 2023
        assert _validate_year(MIN_YEAR) == MIN_YEAR
        assert _validate_year(MAX_YEAR) == MAX_YEAR

    def test_validate_year_invalid_type(self):
        with pytest.raises(ValueError, match="integer"):
            _validate_year("2023")
        with pytest.raises(ValueError, match="integer"):
            _validate_year(2023.5)

    def test_validate_year_out_of_bounds(self):
        with pytest.raises(ValueError, match=f"between {MIN_YEAR} and {MAX_YEAR}"):
            _validate_year(MIN_YEAR - 1)
        with pytest.raises(ValueError, match=f"between {MIN_YEAR} and {MAX_YEAR}"):
            _validate_year(MAX_YEAR + 1)


class TestDocumentPathConstruction:
    """Tests for document path construction with validation."""

    def test_get_wrapped_doc_path_valid(self):
        path = _get_wrapped_doc_path("user123", 2023)
        assert path == "wrapped/user123/2023"

    def test_get_wrapped_doc_path_invalid_uid(self):
        with pytest.raises(ValueError):
            _get_wrapped_doc_path("", 2023)
        with pytest.raises(ValueError):
            _get_wrapped_doc_path("user/123", 2023)

    def test_get_wrapped_doc_path_invalid_year(self):
        with pytest.raises(ValueError):
            _get_wrapped_doc_path("user123", 1999)
        with pytest.raises(ValueError):
            _get_wrapped_doc_path("user123", 2101)


class TestWrappedOperations:
    """Tests for wrapped CRUD operations with resilience."""

    @pytest.mark.asyncio
    async def test_get_wrapped_invalid_inputs(self):
        with patch("backend.database.wrapped.db.get_document", new_callable=AsyncMock):
            # Invalid uid should return None without calling db
            result = await get_wrapped("", 2023)
            assert result is None

            result = await get_wrapped("user/123", 2023)
            assert result is None

            # Invalid year should return None without calling db
            result = await get_wrapped("user123", 1999)
            assert result is None

    @pytest.mark.asyncio
    async def test_create_wrapped_invalid_data(self):
        with pytest.raises(ValueError, match="dictionary"):
            await create_wrapped("user123", 2023, "not_a_dict")

    @pytest.mark.asyncio
    async def test_update_wrapped_status_invalid(self):
        with pytest.raises(ValueError, match="Invalid status"):
            await update_wrapped_status("user123", 2023, "invalid_status")

        with pytest.raises(ValueError, match="dictionary or None"):
            await update_wrapped_status("user123", 2023, WrappedStatus.PENDING, "not_a_dict")

    @pytest.mark.asyncio
    async def test_update_wrapped_progress_invalid(self):
        with pytest.raises(ValueError, match="dictionary"):
            await update_wrapped_progress("user123", 2023, "not_a_dict")


class TestStuckDetection:
    """Tests for stuck detection resilience."""

    def test_is_wrapped_stuck_none_data(self):
        assert is_wrapped_stuck(None) is False

    def test_is_wrapped_stuck_non_dict(self):
        assert is_wrapped_stuck("not_a_dict") is False
        assert is_wrapped_stuck(123) is False

    def test_is_wrapped_stuck_invalid_stale_minutes(self):
        assert is_wrapped_stuck({"last_updated": datetime.utcnow().isoformat()}, 0) is False
        assert is_wrapped_stuck({"last_updated": datetime.utcnow().isoformat()}, -1) is False
        assert is_wrapped_stuck({"last_updated": datetime.utcnow().isoformat()}, "30") is False

    def test_is_wrapped_stuck_missing_last_updated(self):
        assert is_wrapped_stuck({}) is False
        assert is_wrapped_stuck({"last_updated": None}) is False

    def test_is_wrapped_stuck_valid_stale(self):
        stale_time = datetime.utcnow() - timedelta(minutes=40)
        data = {"last_updated": stale_time.isoformat()}
        assert is_wrapped_stuck(data, 30) is True

    def test_is_wrapped_stuck_valid_fresh(self):
        fresh_time = datetime.utcnow() - timedelta(minutes=10)
        data = {"last_updated": fresh_time.isoformat()}
        assert is_wrapped_stuck(data, 30) is False

    def test_is_wrapped_stuck_invalid_timestamp_format(self):
        assert is_wrapped_stuck({"last_updated": "invalid-timestamp"}) is False