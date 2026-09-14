import unittest
from urllib.parse import parse_qs, urlsplit

import httpx

import main


def _encoded_search_query(params: dict) -> str:
    """Round-trips params through httpx's own request builder, exactly like
    _request_arxiv does, so the test exercises the real encoding path."""
    request = httpx.Request("GET", main.ARXIV_API_URL, params=params)
    return urlsplit(str(request.url)).query


class BuildSearchQueryTest(unittest.TestCase):
    def test_single_word_query_reaches_arxiv_unmangled(self):
        query = main._build_search_query({"query": "transformer"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertEqual(parse_qs(encoded)["search_query"], ["all:transformer"])

    def test_multi_word_query_is_plus_joined_not_percent_2b(self):
        query = main._build_search_query({"query": "machine learning"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertIn("search_query=all%3Amachine+learning", encoded)
        self.assertNotIn("%2B", encoded)
        self.assertEqual(parse_qs(encoded)["search_query"], ["all:machine learning"])

    def test_combined_fields_use_and_not_percent_2b(self):
        query = main._build_search_query({"query": "transformer", "title": "attention"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertIn("search_query=all%3Atransformer+AND+ti%3Aattention", encoded)
        self.assertNotIn("%2B", encoded)

    def test_author_search_endpoint_query_is_not_double_encoded(self):
        encoded = _encoded_search_query({"search_query": f"au:{main._clean_text('Yann LeCun')}"})
        self.assertIn("search_query=au%3AYann+LeCun", encoded)
        self.assertNotIn("%2B", encoded)


if __name__ == "__main__":
    unittest.main()
