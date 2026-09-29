import pytest
from unittest.mock import MagicMock, patch
from backend.database.screen_frames import get_screen_frame, _clean_id

def test_clean_id_valid():
    assert _clean_id("valid_id-123") == "valid_id-123"

def test_clean_id_path_traversal():
    with pytest.raises(ValueError):
        _clean_id("../etc/passwd")
    with pytest.raises(ValueError):
        _clean_id("foo/bar")
    with pytest.raises(ValueError):
        _clean_id("foo\\bar")

def test_clean_id_null_byte():
    with pytest.raises(ValueError):
        _clean_id("abc\0def")

def test_clean_id_empty_or_long():
    with pytest.raises(ValueError):
        _clean_id("")
    with pytest.raises(ValueError):
        _clean_id("a" * 300)

def test_get_screen_frame_sanitization():
    mock_db = MagicMock()
    with pytest.raises(ValueError):
        get_screen_frame("../bad", "conv1", "frame1", firestore_client=mock_db)
