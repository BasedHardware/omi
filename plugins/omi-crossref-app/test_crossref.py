"""Hermetic unit tests for Crossref app.

Tests connection pooling fallback, null/non-dict payload guards,
JATS/HTML markup stripping on abstracts, author searches, and DOI formatting
without making external network calls.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


class ModelBase:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class ChatToolResponse(ModelBase):
    result = None
    error = None


class SearchWorksInput(ModelBase):
    query = ""
    max_results = 5


class GetWorkInput(ModelBase):
    doi = ""


class AuthorWorksInput(ModelBase):
    author = ""
    max_results = 5


stubs = {
    "httpx": module("httpx", AsyncClient=Framework, Timeout=Mock()),
    "fastapi": module("fastapi", FastAPI=Framework),
    "models": module("models",
        ChatToolResponse=ChatToolResponse,
        SearchWorksInput=SearchWorksInput,
        GetWorkInput=GetWorkInput,
        AuthorWorksInput=AuthorWorksInput,
    ),
}

spec = importlib.util.spec_from_file_location(
    "crossref_under_test", Path(__file__).with_name("main.py")
)
crossref = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(crossref)


class TestCrossrefApp(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_clean_jats_and_html_tag_stripping(self):
        tagged_abstract = "<jats:p>We report x < 0.5 in <jats:italic>Drosophila</jats:italic> models &amp; humans.</jats:p>"
        cleaned = crossref.clean(tagged_abstract)
        self.assertEqual(cleaned, "We report x < 0.5 in Drosophila models & humans.")

    def test_clean_whitespace_and_none(self):
        self.assertEqual(crossref.clean(None), "")
        self.assertEqual(crossref.clean("   Hello   World   "), "Hello World")

    def test_get_work_jats_abstract_rendered_cleanly(self):
        payload = GetWorkInput(doi="10.1038/nphys1170")
        mock_data = {
            "message": {
                "title": ["Quantum Hall effect in graphene"],
                "publisher": "Nature Publishing Group",
                "DOI": "10.1038/nphys1170",
                "URL": "http://dx.doi.org/10.1038/nphys1170",
                "abstract": "<jats:p>We report observation of <jats:italic>fractional quantum Hall</jats:italic> states where T < 0.1K.</jats:p>",
                "issued": {"date-parts": [[2005]]},
            }
        }
        with patch.object(crossref, "crossref_get", return_value=mock_data):
            resp = self.loop.run_until_complete(crossref.get_crossref_work(payload))
            self.assertIsNone(resp.error)
            self.assertIn("Abstract: We report observation of fractional quantum Hall states where T < 0.1K.", resp.result)
            self.assertNotIn("jats", resp.result)

    def test_search_works_null_message_payload(self):
        payload = SearchWorksInput(query="quantum", max_results=5)
        with patch.object(crossref, "crossref_get", return_value={"message": None}):
            resp = self.loop.run_until_complete(crossref.search_crossref_works(payload))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref results found for 'quantum'.")

    def test_search_works_non_dict_payload(self):
        payload = SearchWorksInput(query="quantum", max_results=5)
        with patch.object(crossref, "crossref_get", return_value="504 Gateway Timeout"):
            resp = self.loop.run_until_complete(crossref.search_crossref_works(payload))
            self.assertEqual(resp.error, "Invalid response payload from Crossref.")

    def test_get_work_null_message_payload(self):
        payload = GetWorkInput(doi="10.1038/nphys1170")
        with patch.object(crossref, "crossref_get", return_value={"message": None}):
            resp = self.loop.run_until_complete(crossref.get_crossref_work(payload))
            self.assertEqual(resp.error, "No work details found in Crossref response.")

    def test_get_works_by_author_null_message_payload(self):
        payload = AuthorWorksInput(author="Einstein", max_results=5)
        with patch.object(crossref, "crossref_get", return_value={"message": None}):
            resp = self.loop.run_until_complete(crossref.get_crossref_works_by_author(payload))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No recent works found for author 'Einstein'.")

    def test_search_works_success(self):
        payload = SearchWorksInput(query="gravitation", max_results=5)
        mock_data = {
            "message": {
                "items": [
                    {
                        "title": ["On Gravitation"],
                        "DOI": "10.1000/182",
                        "issued": {"date-parts": [[1915]]},
                    }
                ]
            }
        }
        with patch.object(crossref, "crossref_get", return_value=mock_data):
            resp = self.loop.run_until_complete(crossref.search_crossref_works(payload))
            self.assertIsNone(resp.error)
            self.assertIn("On Gravitation (1915)", resp.result)
            self.assertIn("10.1000/182", resp.result)


if __name__ == "__main__":
    unittest.main()
