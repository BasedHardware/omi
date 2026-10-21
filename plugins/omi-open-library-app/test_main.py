from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

from fastapi.testclient import TestClient

from main import _subject_slug, app


def test_subject_slug_ascii():
    assert _subject_slug("science fiction") == "science_fiction"
    assert _subject_slug("history") == "history"
    assert _subject_slug("  space   flight  ") == "space_flight"


def test_subject_slug_unicode():
    assert _subject_slug("español") == "español"
    assert _subject_slug("中文") == "中文"
    assert _subject_slug("música") == "música"
    assert _subject_slug("日本語") == "日本語"


def test_subject_slug_punctuation_dropped():
    assert _subject_slug("science / fiction?") == "science_fiction"
    assert _subject_slug("art & design") == "art_design"
    assert _subject_slug("c++") == "c"
    assert _subject_slug("history: ancient") == "history_ancient"


def test_subject_slug_blank_and_invalid():
    assert _subject_slug("") is None
    assert _subject_slug("   ") is None
    assert _subject_slug("???///") is None
    assert _subject_slug(None) is None


def test_search_subject_unicode_encoding_and_response():
    client = TestClient(app)

    mock_data = {
        "name": "español",
        "works": [
            {
                "key": "/works/OL123W",
                "title": "Don Quijote",
                "authors": [{"name": "Miguel de Cervantes"}],
                "first_publish_year": 1605,
            }
        ],
    }

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_data

        resp = client.post("/tools/search_subject", json={"subject": "español", "limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "Don Quijote" in data["result"]

        mock_req.assert_awaited_once()
        called_path = mock_req.await_args[0][0]
        assert called_path == "/subjects/espa%C3%B1ol.json"
        # Verify decoding matches canonical subject
        slug_segment = called_path.removeprefix("/subjects/").removesuffix(".json")
        assert unquote(slug_segment) == "español"


def test_search_subject_non_latin_chinese():
    client = TestClient(app)

    mock_data = {
        "name": "中文",
        "works": [
            {
                "key": "/works/OL456W",
                "title": "Chinese Literature",
                "authors": [{"name": "Lu Xun"}],
                "first_publish_year": 1918,
            }
        ],
    }

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_data

        resp = client.post("/tools/search_subject", json={"subject": "中文", "limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "Chinese Literature" in data["result"]

        mock_req.assert_awaited_once()
        called_path = mock_req.await_args[0][0]
        assert called_path == "/subjects/%E4%B8%AD%E6%96%87.json"
        slug_segment = called_path.removeprefix("/subjects/").removesuffix(".json")
        assert unquote(slug_segment) == "中文"


def test_search_subject_missing_subject():
    client = TestClient(app)
    resp = client.post("/tools/search_subject", json={"subject": "   "})
    assert resp.status_code == 200
    assert resp.json()["error"] == "Provide a subject to browse."
