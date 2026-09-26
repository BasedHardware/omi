import pytest
from fastapi import status
from fastapi.testclient import TestClient
from backend.routers.desktop_tts_updates import promote_release
from backend.main import app

client = TestClient(app)

def test_promote_release_not_found():
    with pytest.raises(Exception) as exc_info:
        promote_release("", {})
    assert "release not found" not in str(exc_info.value.detail)
    assert "invalid release state" in str(exc_info.value.detail)

def test_promote_release_already_stable():
    with pytest.raises(Exception) as exc_info:
        promote_release("valid_id", {"status": "stable"})
    assert "already stable" not in str(exc_info.value.detail)
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

def test_promote_release_unhandled_exception():
    with pytest.raises(Exception) as exc_info:
        promote_release("invalid_id", {"invalid": "data"})
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "internal server error" not in str(exc_info.value.detail)

def test_promote_release_server_error():
    with pytest.raises(Exception) as exc_info:
        promote_release(None, {})
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR