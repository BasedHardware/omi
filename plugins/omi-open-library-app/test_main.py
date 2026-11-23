from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

from fastapi.testclient import TestClient

from main import _clean_text, _description_text, _subject_slug, _work_id, app


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


def test_work_id_accepts_slug_urls_and_rejects_other_keys():
    assert _work_id("OL45883W") == "OL45883W"
    assert _work_id("ol45883w") == "OL45883W"
    assert _work_id("works/OL45883W") == "OL45883W"
    assert _work_id("/works/OL45883W/The_Adventures_of_Tom_Sawyer") == "OL45883W"
    assert _work_id("https://openlibrary.org/works/OL45883W/The_Adventures_of_Tom_Sawyer") == "OL45883W"
    assert _work_id("https://openlibrary.org/works/OL45883W.json") == "OL45883W"
    assert _work_id("OL45883M") is None
    assert _work_id("see OL45883W in the notes") is None
    assert _work_id(None) is None
    assert _work_id("") is None


def test_description_keeps_paragraphs_and_titles_stay_flat():
    assert _description_text("First paragraph.\n\nSecond paragraph.") == "First paragraph.\n\nSecond paragraph."
    assert _description_text("<p>First paragraph.</p><p>Second paragraph.</p>") == "First paragraph.\nSecond paragraph."
    assert _description_text({"type": "/type/text", "value": "One.\n\nTwo."}) == "One.\n\nTwo."
    assert _clean_text("First paragraph.\n\nSecond paragraph.") == "First paragraph. Second paragraph."


def test_slug_url_fetches_the_work_and_keeps_description_lines():
    client = TestClient(app)
    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {
            "title": "The Adventures of Tom Sawyer",
            "description": "First paragraph.\n\nSecond paragraph.",
            "subjects": ["Fiction"],
        }
        resp = client.post(
            "/tools/get_book_details",
            json={"work_id": "https://openlibrary.org/works/OL45883W/The_Adventures_of_Tom_Sawyer"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert "Open Library work: OL45883W" in body["result"]
    assert "First paragraph.\n\nSecond paragraph." in body["result"]
    assert "First paragraph. Second paragraph." not in body["result"]
    mock_req.assert_awaited_once()
    assert mock_req.await_args[0][0] == "/works/OL45883W.json"


def test_non_work_id_does_not_call_open_library():
    client = TestClient(app)
    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        resp = client.post("/tools/get_book_details", json={"work_id": "OL45883M"})

    assert resp.status_code == 200
    assert resp.json()["error"] == "Provide a valid Open Library work_id like OL45883W or an ISBN."
    mock_req.assert_not_awaited()
