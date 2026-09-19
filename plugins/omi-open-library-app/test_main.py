"""Hermetic regression tests for plugins/omi-open-library-app/main.py.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the module under test, so the suite runs without
site-packages or network access (`python3 plugins/omi-open-library-app/test_main.py`
from the repo root, or `python -m unittest` inside the plugin directory). The
async chat-tool handlers run under asyncio.run with _request_json stubbed to
return canned Open Library payloads.

Covers BasedHardware/omi#13939: non-dict upstream payloads, null or non-list
docs/works collections, non-dict collection elements, and null or non-dict
authors/publishers/subjects entries must produce clean ChatToolResponse
values instead of raising AttributeError or TypeError.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "fastapi.responses", "pydantic")


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, response=None):
            super().__init__(message)
            self.response = response

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub main._request_json; no network allowed")

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = _AsyncClient
    sys.modules["httpx"] = httpx

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        def post(self, *args, **kwargs):
            return lambda handler: handler

    fastapi.FastAPI = FastAPI
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    fastapi.responses = responses
    sys.modules["fastapi.responses"] = responses

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules


def _call(handler, request_body, *, payload=None, error=None):
    """Invoke a chat-tool handler with _request_json stubbed.

    Returns (ChatToolResponse, AsyncMock) so tests can assert on the upstream
    path/params the handler requested.
    """
    if error is not None:
        stub = mock.AsyncMock(side_effect=error)
    else:
        stub = mock.AsyncMock(return_value=payload)
    with mock.patch.object(main, "_request_json", new=stub):
        result = asyncio.run(handler(request_body))
    return result, stub


def _status_error(code):
    return main.httpx.HTTPStatusError(
        f"status {code}", response=types.SimpleNamespace(status_code=code)
    )


_SEARCH_DOC = {
    "key": "/works/OL45883W",
    "title": "Dune",
    "author_name": ["Frank Herbert"],
    "first_publish_year": 1965,
    "subject": ["Science fiction", "Desert"],
}

_WORK_PAYLOAD = {
    "title": "Dune",
    "description": {"value": "Epic <b>science fiction</b> saga."},
    "subjects": ["Desert planet", "Science fiction"],
    "created": {"value": "2020-01-02T03:04:05"},
}

_ISBN = "9780441172719"

_ISBN_PAYLOAD = {
    f"ISBN:{_ISBN}": {
        "title": "Dune",
        "authors": [{"name": "Frank Herbert"}, "junk", 7],
        "publishers": [{"name": "Chilton"}],
        "publish_date": "1965",
        "subjects": [{"name": "Science fiction"}, "junk"],
        "url": "https://openlibrary.org/books/OL7353617M/Dune",
    }
}

_SUBJECT_WORK = {
    "key": "/works/OL45883W",
    "title": "Dune",
    "authors": [{"name": "Frank Herbert"}],
    "first_publish_year": 1965,
    "edition_count": 42,
}


class SubjectSlugTests(unittest.TestCase):
    def test_ascii_and_whitespace(self):
        cases = {
            "science fiction": "science_fiction",
            "history": "history",
            "  space   flight  ": "space_flight",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(main._subject_slug(raw), expected)

    def test_unicode_preserved(self):
        for raw in ("español", "中文", "música", "日本語"):
            with self.subTest(raw=raw):
                self.assertEqual(main._subject_slug(raw), raw)

    def test_punctuation_dropped(self):
        cases = {
            "science / fiction?": "science_fiction",
            "art & design": "art_design",
            "c++": "c",
            "history: ancient": "history_ancient",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(main._subject_slug(raw), expected)

    def test_blank_and_invalid(self):
        for raw in ("", "   ", "???///", None):
            with self.subTest(raw=raw):
                self.assertIsNone(main._subject_slug(raw))


class SearchBooksTests(unittest.TestCase):
    def test_returns_formatted_results(self):
        resp, stub = _call(
            main.search_books, {"query": "dune"}, payload={"docs": [_SEARCH_DOC]}
        )
        self.assertIsNone(resp.error)
        self.assertIn('Books for "dune":', resp.result)
        self.assertIn("1. Dune", resp.result)
        self.assertIn("Frank Herbert", resp.result)
        self.assertIn("OL45883W", resp.result)
        stub.assert_awaited_once()
        self.assertEqual(stub.await_args.args[0], "/search.json")
        self.assertEqual(stub.await_args.kwargs["params"]["q"], "dune")

    def test_passes_filters_and_clamps_limit(self):
        resp, stub = _call(
            main.search_books,
            {"author": "herbert", "subject": "sci-fi", "limit": 99},
            payload={"docs": []},
        )
        self.assertEqual(resp.result, "No matching books found.")
        params = stub.await_args.kwargs["params"]
        self.assertEqual(params["author"], "herbert")
        self.assertEqual(params["subject"], "sci-fi")
        self.assertEqual(params["limit"], 10)

    def test_non_dict_payload_returns_clean_error(self):
        for bad in ("rate limited", ["not", "a", "dict"], 5, None):
            with self.subTest(payload=type(bad).__name__):
                resp, _ = _call(main.search_books, {"query": "dune"}, payload=bad)
                self.assertIsNone(resp.result)
                self.assertIsNotNone(resp.error)

    def test_malformed_docs_collection_returns_no_results(self):
        for bad_docs in (None, "oops", {"a": 1}, 5, True):
            with self.subTest(docs=repr(bad_docs)):
                resp, _ = _call(
                    main.search_books, {"query": "dune"}, payload={"docs": bad_docs}
                )
                self.assertIsNone(resp.error)
                self.assertEqual(resp.result, "No matching books found.")

    def test_missing_docs_key_returns_no_results(self):
        resp, _ = _call(main.search_books, {"query": "dune"}, payload={"numFound": 0})
        self.assertIsNone(resp.error)
        self.assertEqual(resp.result, "No matching books found.")

    def test_non_dict_docs_elements_are_skipped(self):
        payload = {"docs": ["junk", None, 42, _SEARCH_DOC]}
        resp, _ = _call(main.search_books, {"query": "dune"}, payload=payload)
        self.assertIsNone(resp.error)
        self.assertIn("1. Dune", resp.result)
        self.assertNotIn("junk", resp.result)

    def test_all_non_dict_docs_returns_no_results(self):
        resp, _ = _call(
            main.search_books, {"query": "dune"}, payload={"docs": ["a", None, 7]}
        )
        self.assertIsNone(resp.error)
        self.assertEqual(resp.result, "No matching books found.")

    def test_requires_a_query_parameter(self):
        resp, stub = _call(main.search_books, {})
        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Provide query, author, or subject.")
        stub.assert_not_awaited()

    def test_http_error_returns_clean_error(self):
        resp, _ = _call(
            main.search_books,
            {"query": "dune"},
            error=main.httpx.HTTPError("connection reset"),
        )
        self.assertIsNone(resp.result)
        self.assertIn("Open Library search failed", resp.error)


class GetBookDetailsTests(unittest.TestCase):
    def test_work_details_happy_path(self):
        resp, stub = _call(
            main.get_book_details, {"work_id": "OL45883W"}, payload=_WORK_PAYLOAD
        )
        self.assertIsNone(resp.error)
        self.assertIn("Dune", resp.result)
        self.assertIn("https://openlibrary.org/works/OL45883W", resp.result)
        self.assertIn("Desert planet", resp.result)
        self.assertIn("Epic science fiction saga.", resp.result)
        self.assertIn("Record created: 2020-01-02", resp.result)
        self.assertEqual(stub.await_args.args[0], "/works/OL45883W.json")

    def test_work_non_dict_payload_returns_clean_error(self):
        for bad in ("error page", ["x"], 9, None):
            with self.subTest(payload=type(bad).__name__):
                resp, _ = _call(
                    main.get_book_details, {"work_id": "OL45883W"}, payload=bad
                )
                self.assertIsNone(resp.result)
                self.assertIsNotNone(resp.error)

    def test_work_404_returns_not_found(self):
        resp, _ = _call(
            main.get_book_details, {"work_id": "OL999W"}, error=_status_error(404)
        )
        self.assertIsNone(resp.error)
        self.assertEqual(resp.result, "No matching Open Library record found.")

    def test_work_500_returns_clean_error(self):
        resp, _ = _call(
            main.get_book_details, {"work_id": "OL999W"}, error=_status_error(500)
        )
        self.assertIsNone(resp.result)
        self.assertIn("Open Library details request failed", resp.error)

    def test_isbn_details_happy_path(self):
        resp, stub = _call(
            main.get_book_details, {"isbn": _ISBN}, payload=_ISBN_PAYLOAD
        )
        self.assertIsNone(resp.error)
        self.assertIn("Dune", resp.result)
        self.assertIn("Frank Herbert", resp.result)
        self.assertIn("Publisher: Chilton", resp.result)
        self.assertIn("Subjects: Science fiction", resp.result)
        self.assertEqual(stub.await_args.args[0], "/api/books")
        self.assertEqual(
            stub.await_args.kwargs["params"]["bibkeys"], f"ISBN:{_ISBN}"
        )

    def test_isbn_non_dict_payload_returns_clean_error(self):
        for bad in ("error page", ["x"], 9):
            with self.subTest(payload=type(bad).__name__):
                resp, _ = _call(
                    main.get_book_details, {"isbn": _ISBN}, payload=bad
                )
                self.assertIsNone(resp.result)
                self.assertIsNotNone(resp.error)

    def test_isbn_missing_or_non_dict_book_returns_not_found(self):
        for book_value in ("junk", None, 5, {}, ["x"]):
            with self.subTest(book=repr(book_value)):
                resp, _ = _call(
                    main.get_book_details,
                    {"isbn": _ISBN},
                    payload={f"ISBN:{_ISBN}": book_value},
                )
                self.assertIsNone(resp.error)
                self.assertEqual(
                    resp.result,
                    f"No Open Library details found for ISBN {_ISBN}.",
                )

    def test_isbn_isbn_key_absent_returns_not_found(self):
        resp, _ = _call(main.get_book_details, {"isbn": _ISBN}, payload={})
        self.assertIsNone(resp.error)
        self.assertEqual(
            resp.result, f"No Open Library details found for ISBN {_ISBN}."
        )

    def test_isbn_malformed_nested_lists(self):
        payload = {
            f"ISBN:{_ISBN}": {
                "title": "Dune",
                "authors": None,
                "publishers": "Chilton Books",
                "subjects": {"name": "Sci-fi"},
                "url": {"link": "x"},
            }
        }
        resp, _ = _call(main.get_book_details, {"isbn": _ISBN}, payload=payload)
        self.assertIsNone(resp.error)
        self.assertIn("Author: unknown author", resp.result)
        self.assertNotIn("Publisher:", resp.result)
        self.assertNotIn("Subjects:", resp.result)

    def test_requires_identifier(self):
        resp, stub = _call(main.get_book_details, {})
        self.assertIsNone(resp.result)
        self.assertEqual(
            resp.error,
            "Provide a valid Open Library work_id like OL45883W or an ISBN.",
        )
        stub.assert_not_awaited()

    def test_http_error_returns_clean_error(self):
        resp, _ = _call(
            main.get_book_details,
            {"work_id": "OL45883W"},
            error=main.httpx.HTTPError("connection reset"),
        )
        self.assertIsNone(resp.result)
        self.assertIn("Open Library details request failed", resp.error)


class SearchSubjectTests(unittest.TestCase):
    def test_happy_path(self):
        payload = {"name": "Science fiction", "works": [_SUBJECT_WORK]}
        resp, stub = _call(
            main.search_subject, {"subject": "science fiction"}, payload=payload
        )
        self.assertIsNone(resp.error)
        self.assertIn("Open Library books for subject Science fiction:", resp.result)
        self.assertIn("1. Dune", resp.result)
        self.assertIn("Frank Herbert", resp.result)
        self.assertIn("Editions: 42", resp.result)
        self.assertEqual(stub.await_args.args[0], "/subjects/science_fiction.json")

    def test_unicode_slug_encoding(self):
        cases = (
            ("español", "/subjects/espa%C3%B1ol.json", "Don Quijote"),
            ("中文", "/subjects/%E4%B8%AD%E6%96%87.json", "Chinese Literature"),
        )
        for subject, expected_path, title in cases:
            with self.subTest(subject=subject):
                payload = {
                    "name": subject,
                    "works": [
                        {
                            "key": "/works/OL1W",
                            "title": title,
                            "authors": [{"name": "An Author"}],
                            "first_publish_year": 1605,
                        }
                    ],
                }
                resp, stub = _call(
                    main.search_subject, {"subject": subject}, payload=payload
                )
                self.assertIsNone(resp.error)
                self.assertIn(title, resp.result)
                stub.assert_awaited_once()
                called_path = stub.await_args.args[0]
                self.assertEqual(called_path, expected_path)
                slug_segment = called_path.removeprefix("/subjects/").removesuffix(
                    ".json"
                )
                self.assertEqual(unquote(slug_segment), subject)

    def test_non_dict_payload_returns_clean_error(self):
        for bad in ("rate limited", ["x"], 5, None):
            with self.subTest(payload=type(bad).__name__):
                resp, _ = _call(
                    main.search_subject, {"subject": "fantasy"}, payload=bad
                )
                self.assertIsNone(resp.result)
                self.assertIsNotNone(resp.error)

    def test_malformed_works_collection_returns_no_results(self):
        for bad_works in (None, "oops", {"a": 1}, 7):
            with self.subTest(works=repr(bad_works)):
                resp, _ = _call(
                    main.search_subject,
                    {"subject": "fantasy"},
                    payload={"works": bad_works},
                )
                self.assertIsNone(resp.error)
                self.assertEqual(
                    resp.result, "No books found for subject fantasy."
                )

    def test_non_dict_work_elements_and_bad_authors(self):
        payload = {
            "name": "Fantasy",
            "works": [
                "junk",
                {"title": "Real", "authors": "not-a-list", "key": "/works/OL2W"},
            ],
        }
        resp, _ = _call(main.search_subject, {"subject": "fantasy"}, payload=payload)
        self.assertIsNone(resp.error)
        self.assertIn("1. Real", resp.result)
        self.assertIn("unknown author", resp.result)
        self.assertNotIn("junk", resp.result)

    def test_missing_subject(self):
        resp, stub = _call(main.search_subject, {"subject": "   "})
        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Provide a subject to browse.")
        stub.assert_not_awaited()

    def test_404_returns_not_found(self):
        resp, _ = _call(
            main.search_subject, {"subject": "nope"}, error=_status_error(404)
        )
        self.assertIsNone(resp.error)
        self.assertEqual(resp.result, "No Open Library subject found for nope.")

    def test_http_error_returns_clean_error(self):
        resp, _ = _call(
            main.search_subject,
            {"subject": "fantasy"},
            error=main.httpx.HTTPError("connection reset"),
        )
        self.assertIsNone(resp.result)
        self.assertIn("Open Library subject search failed", resp.error)


class FormatterGuardTests(unittest.TestCase):
    def test_format_book_non_dict(self):
        for bad in ("junk", None, 5, ["x"]):
            with self.subTest(doc=repr(bad)):
                text = main._format_book(bad, 1)
                self.assertIn("1. Untitled", text)
                self.assertIn("unknown author", text)

    def test_format_subject_work_non_dict(self):
        for bad in ("junk", None, 5, ["x"]):
            with self.subTest(work=repr(bad)):
                text = main._format_subject_work(bad, 1)
                self.assertIn("1. Untitled", text)
                self.assertIn("unknown author", text)

    def test_format_subject_work_non_list_authors(self):
        text = main._format_subject_work(
            {"title": "Real", "authors": {"name": "Nested"}}, 1
        )
        self.assertIn("unknown author", text)


class ManifestTests(unittest.TestCase):
    def test_tools_manifest_exposes_three_no_auth_tools(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        names = {tool["name"] for tool in manifest["tools"]}
        self.assertEqual(names, {"search_books", "get_book_details", "search_subject"})
        self.assertTrue(all(tool["auth_required"] is False for tool in manifest["tools"]))


if __name__ == "__main__":
    unittest.main()
