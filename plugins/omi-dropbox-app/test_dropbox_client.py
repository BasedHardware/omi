from unittest.mock import MagicMock, patch
import requests
from dropbox_client import DropboxClient


def _list_response(entries, has_more=False, cursor=None, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.text = "upstream error"
    response.json.return_value = {
        "entries": entries,
        "has_more": has_more,
        "cursor": cursor,
    }
    return response


def _entry(name):
    return {"name": name, "path_display": f"/{name}", ".tag": "file"}


def test_list_folder_follows_cursor_until_limit_is_reached():
    client = DropboxClient("fake_token")
    first = _list_response([_entry("one")], has_more=True, cursor="cursor-1")
    second = _list_response([_entry("two"), _entry("three")], has_more=True, cursor="cursor-2")

    with patch("dropbox_client.requests.post", side_effect=[first, second]) as mock_post:
        results, error = client.list_folder("/docs", limit=3)

    assert error is None
    assert [item["name"] for item in results] == ["one", "two", "three"]
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[1].kwargs["json"] == {"cursor": "cursor-1"}


def test_list_folder_stops_without_cursor_when_dropbox_has_no_more_pages():
    client = DropboxClient("fake_token")
    first = _list_response([_entry("one")], has_more=False)

    with patch("dropbox_client.requests.post", return_value=first) as mock_post:
        results, error = client.list_folder(limit=20)

    assert error is None
    assert [item["name"] for item in results] == ["one"]
    mock_post.assert_called_once()


def test_list_folder_returns_error_when_continuation_fails():
    client = DropboxClient("fake_token")
    first = _list_response([_entry("one")], has_more=True, cursor="cursor-1")
    continuation = _list_response([], status_code=500)

    with patch("dropbox_client.requests.post", side_effect=[first, continuation]):
        results, error = client.list_folder(limit=20)

    assert results is None
    assert error == "List continuation failed: upstream error"


def test_list_folder_rejects_has_more_without_cursor():
    client = DropboxClient("fake_token")
    first = _list_response([_entry("one")], has_more=True, cursor=None)

    with patch("dropbox_client.requests.post", return_value=first):
        results, error = client.list_folder(limit=20)

    assert results is None
    assert error == "List failed: Dropbox returned has_more without a cursor"


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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
