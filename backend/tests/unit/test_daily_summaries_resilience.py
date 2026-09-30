import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from backend.database.daily_summaries import (
    upsert_desktop_daily_usage,
    get_desktop_daily_usage,
    create_daily_summary,
    get_daily_summary,
    _validate_identifier,
    _validate_and_get_counter,
    DESKTOP_DAILY_USAGE_COUNTER_FIELDS,
)


@pytest.fixture
def mock_firestore():
    with patch("backend.database.daily_summaries._get_firestore") as mock:
        db = MagicMock()
        mock.return_value = db
        yield db


class TestValidateIdentifier:
    def test_valid_identifier(self):
        assert _validate_identifier("valid_id", "test_field") == "valid_id"

    def test_whitespace_trimmed(self):
        assert _validate_identifier("  valid_id  ", "test_field") == "valid_id"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="test_field cannot be empty"):
            _validate_identifier("", "test_field")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="test_field cannot be empty"):
            _validate_identifier("   ", "test_field")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="test_field must be a string"):
            _validate_identifier(123, "test_field")

    def test_path_separator_raises(self):
        with pytest.raises(ValueError, match="test_field cannot contain path separators"):
            _validate_identifier("invalid/id", "test_field")


class TestValidateAndGetCounter:
    def test_valid_positive_int(self):
        assert _validate_and_get_counter(42, "test_field") == 42

    def test_zero(self):
        assert _validate_and_get_counter(0, "test_field") == 0

    def test_negative_int(self):
        assert _validate_and_get_counter(-10, "test_field") == 0

    def test_boolean_false(self):
        assert _validate_and_get_counter(False, "test_field") == 0

    def test_boolean_true(self):
        assert _validate_and_get_counter(True, "test_field") == 0

    def test_non_int_type(self):
        assert _validate_and_get_counter("not_an_int", "test_field") == 0

    def test_none(self):
        assert _validate_and_get_counter(None, "test_field") == 0


@pytest.mark.asyncio
async def test_upsert_desktop_daily_usage_partial_counters(mock_firestore):
    mock_transaction = MagicMock()
    mock_firestore.transaction.return_value = mock_transaction

    doc_ref = MagicMock()
    mock_firestore.collection.return_value.document.return_value.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        doc_ref
    )

    snapshot = MagicMock()
    snapshot.exists = False
    doc_ref.get.return_value = snapshot

    await upsert_desktop_daily_usage(
        uid="test_uid",
        date="2026-09-30",
        client_device_id="device_1",
        counters={"total_active_time": 100},
    )

    mock_firestore.transaction.assert_called_once()
    doc_ref.set.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_desktop_daily_usage_invalid_identifier(mock_firestore):
    with pytest.raises(ValueError, match="uid cannot be empty"):
        await upsert_desktop_daily_usage(
            uid="",
            date="2026-09-30",
            client_device_id="device_1",
            counters={},
        )


@pytest.mark.asyncio
async def test_get_desktop_daily_usage_invalid_identifier(mock_firestore):
    result = await get_desktop_daily_usage(
        uid="",
        date="2026-09-30",
        client_device_id="device_1",
    )
    assert result is None


@pytest.mark.asyncio
async def test_get_desktop_daily_usage_not_found(mock_firestore):
    doc_ref = MagicMock()
    mock_firestore.collection.return_value.document.return_value.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        doc_ref
    )

    snapshot = MagicMock()
    snapshot.exists = False
    doc_ref.get.return_value = snapshot

    result = await get_desktop_daily_usage(
        uid="test_uid",
        date="2026-09-30",
        client_device_id="device_1",
    )
    assert result is None


@pytest.mark.asyncio
async def test_create_daily_summary_invalid_summary_data(mock_firestore):
    with pytest.raises(ValueError, match="summary_data must be a dictionary"):
        await create_daily_summary(
            uid="test_uid",
            date="2026-09-30",
            summary_data="not_a_dict",
        )


@pytest.mark.asyncio
async def test_create_daily_summary_missing_id(mock_firestore):
    with pytest.raises(ValueError, match="summary_data must contain an 'id' field"):
        await create_daily_summary(
            uid="test_uid",
            date="2026-09-30",
            summary_data={"other_field": "value"},
        )


@pytest.mark.asyncio
async def test_get_daily_summary_invalid_identifier(mock_firestore):
    result = await get_daily_summary(
        uid="",
        date="2026-09-30",
        summary_id="summary_1",
    )
    assert result is None


@pytest.mark.asyncio
async def test_get_daily_summary_not_found(mock_firestore):
    doc_ref = MagicMock()
    mock_firestore.collection.return_value.document.return_value.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        doc_ref
    )

    snapshot = MagicMock()
    snapshot.exists = False
    doc_ref.get.return_value = snapshot

    result = await get_daily_summary(
        uid="test_uid",
        date="2026-09-30",
        summary_id="summary_1",
    )
    assert result is None
