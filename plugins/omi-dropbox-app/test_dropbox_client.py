from unittest.mock import MagicMock, patch
import requests
from dropbox_client import DropboxClient


def test_download_file_immediate_success():
    client = DropboxClient("fake_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"sample file bytes"

    with patch("requests.post", return_value=mock_resp) as mock_post:
        data, err = client.download_file("/test.txt")
        assert err is None
        assert data == b"sample file bytes"
        assert mock_post.call_count == 1


def test_download_file_non_retryable_http_error():
    client = DropboxClient("fake_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "File not found"

    with patch("requests.post", return_value=mock_resp) as mock_post:
        data, err = client.download_file("/missing.txt")
        assert data is None
        assert "Failed to download file: File not found" in err
        assert mock_post.call_count == 1


def test_download_file_retries_on_timeout_and_succeeds():
    client = DropboxClient("fake_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"recovered content"

    # 1st attempt: Timeout, 2nd attempt: Success
    side_effects = [requests.exceptions.Timeout("timed out"), mock_resp]

    with patch("requests.post", side_effect=side_effects) as mock_post, \
         patch("time.sleep", return_value=None):
        data, err = client.download_file("/transient.txt")
        assert err is None
        assert data == b"recovered content"
        assert mock_post.call_count == 2


def test_download_file_retries_on_connection_error_and_succeeds():
    client = DropboxClient("fake_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"recovered from disconnect"

    # 1st attempt: ConnectionError, 2nd attempt: Success
    side_effects = [requests.exceptions.ConnectionError("connection reset"), mock_resp]

    with patch("requests.post", side_effect=side_effects) as mock_post, \
         patch("time.sleep", return_value=None):
        data, err = client.download_file("/disconnect.txt")
        assert err is None
        assert data == b"recovered from disconnect"
        assert mock_post.call_count == 2


def test_download_file_exhausts_retries_and_returns_clean_error():
    client = DropboxClient("fake_token")
    side_effects = [
        requests.exceptions.Timeout("timed out 1"),
        requests.exceptions.Timeout("timed out 2"),
        requests.exceptions.Timeout("timed out 3"),
    ]

    with patch("requests.post", side_effect=side_effects) as mock_post, \
         patch("time.sleep", return_value=None):
        data, err = client.download_file("/failing.txt")
        assert data is None
        assert "Error downloading file: timed out 3" in err
        assert mock_post.call_count == 3
