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


def test_list_folder_pagination_success():
    client = DropboxClient("fake_token")
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {
        "entries": [
            {
                "name": "file1.txt",
                "path_display": "/file1.txt",
                ".tag": "file",
                "size": 1024,
                "server_modified": "2026-01-01T12:00:00Z",
            }
        ],
        "has_more": True,
        "cursor": "cursor_page1",
    }

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {
        "entries": [
            {
                "name": "file2.txt",
                "path_display": "/file2.txt",
                ".tag": "file",
                "size": 2048,
                "server_modified": "2026-01-02T12:00:00Z",
            }
        ],
        "has_more": False,
        "cursor": None,
    }

    with patch("requests.post", side_effect=[mock_resp1, mock_resp2]) as mock_post:
        results, err = client.list_folder("/docs", limit=20)
        assert err is None
        assert results is not None
        assert len(results) == 2
        assert results[0]["name"] == "file1.txt"
        assert results[0]["type"] == "file"
        assert results[0]["size"] == 1024
        assert results[1]["name"] == "file2.txt"
        assert results[1]["size"] == 2048
        assert mock_post.call_count == 2
        # Check first call endpoint and payload
        args1, kwargs1 = mock_post.call_args_list[0]
        assert args1[0] == f"{client.API_BASE}/files/list_folder"
        assert kwargs1["json"]["path"] == "/docs"
        # Check second call endpoint and payload
        args2, kwargs2 = mock_post.call_args_list[1]
        assert args2[0] == f"{client.API_BASE}/files/list_folder/continue"
        assert kwargs2["json"] == {"cursor": "cursor_page1"}


def test_list_folder_pagination_continue_error():
    client = DropboxClient("fake_token")
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {
        "entries": [
            {
                "name": "file1.txt",
                "path_display": "/file1.txt",
                ".tag": "file",
                "size": 1024,
                "server_modified": "2026-01-01T12:00:00Z",
            }
        ],
        "has_more": True,
        "cursor": "cursor_page1",
    }

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 500
    mock_resp2.text = "Internal server error"

    with patch("requests.post", side_effect=[mock_resp1, mock_resp2]) as mock_post:
        results, err = client.list_folder("/docs", limit=20)
        assert results is None
        assert err == "List failed during pagination: Internal server error"
        assert mock_post.call_count == 2


def test_list_folder_initial_error():
    client = DropboxClient("fake_token")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "path not found"

    with patch("requests.post", return_value=mock_resp) as mock_post:
        results, err = client.list_folder("/nonexistent", limit=20)
        assert results is None
        assert err == "List failed: path not found"
        assert mock_post.call_count == 1

