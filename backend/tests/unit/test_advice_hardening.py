from unittest.mock import MagicMock, patch
import pytest

from database.advice import (
    _clean_str,
    create_advice,
    delete_advice,
    get_advice,
    mark_all_advice_read,
    update_advice,
)


class TestCleanStr:
    def test_valid(self):
        assert _clean_str("hello", "content") == "hello"
        assert _clean_str("  world  ", "content") == "world"

    def test_empty_or_whitespace_raises(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            _clean_str("", "uid")
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            _clean_str("   ", "uid")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            _clean_str(None, "uid")
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            _clean_str(123, "uid")


class TestAdviceDatabaseValidation:
    def test_create_advice_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            create_advice("", "content")
        with pytest.raises(ValueError, match="content must be a non-empty string"):
            create_advice("uid1", "")

    def test_get_advice_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            get_advice("")

    def test_update_advice_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            update_advice("", "adv1", is_read=True)
        with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
            update_advice("uid1", "", is_read=True)

    def test_delete_advice_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            delete_advice("", "adv1")
        with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
            delete_advice("uid1", "")

    def test_mark_all_advice_read_validation(self):
        with pytest.raises(ValueError, match="uid must be a non-empty string"):
            mark_all_advice_read("")


class TestAdviceDatabaseExecution:
    @patch("database.advice.db")
    def test_create_advice_clamping_and_write(self, mock_db):
        mock_doc = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

        doc = create_advice("user_123", "   Drink more water   ", confidence=1.5)
        assert doc["content"] == "Drink more water"
        assert doc["confidence"] == 1.0  # Clamped to 1.0
        mock_doc.set.assert_called_once()
