"""Hermetic regression tests: optional tool parameters sent as JSON null must take
their defaults instead of failing validation, and validation errors must return HTTP 200
with ChatToolResponse(error=...) per Omi chat tool protocol.

The Omi backend builds non-required manifest parameters with default None and, with
the pinned langchain-core 1.3.3, forwards defaulted fields in the request body as JSON null.
Requests such as {"query": "attention is all you need", "max_results": null, "min_year": null}
and {"author_id": "1741101", "max_results": null} must succeed with default max_results=5.

Runs with pure standard library / FastAPI / httpx stubs or real packages. Zero network dependencies.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
import main


class TestNullOptionalsAndValidation(unittest.IsolatedAsyncioTestCase):
    def test_search_papers_request_coerces_null_max_results_and_min_year(self):
        req = models.SearchPapersRequest(
            query="  deep learning  ",
            max_results=None,
            min_year=None
        )
        self.assertEqual(req.query, "deep learning")
        self.assertEqual(req.max_results, 5)
        self.assertIsNone(req.min_year)

    def test_search_papers_request_bounds_and_string_coercion(self):
        req_string = models.SearchPapersRequest(query="nlp", max_results="8", min_year="2020")
        self.assertEqual(req_string.max_results, 8)
        self.assertEqual(req_string.min_year, 2020)

        # Clamping
        req_clamp_high = models.SearchPapersRequest(query="nlp", max_results=99)
        self.assertEqual(req_clamp_high.max_results, 10)

        req_clamp_low = models.SearchPapersRequest(query="nlp", max_results=-5)
        self.assertEqual(req_clamp_low.max_results, 1)

    def test_get_author_papers_request_coerces_null_max_results(self):
        req = models.GetAuthorPapersRequest(
            author_id="  1741101  ",
            max_results=None
        )
        self.assertEqual(req.author_id, "1741101")
        self.assertEqual(req.max_results, 5)

    def test_get_paper_request_strips_whitespace(self):
        req = models.GetPaperRequest(paper_id_or_doi="  10.1038/nature12345  ")
        self.assertEqual(req.paper_id_or_doi, "10.1038/nature12345")

    async def test_search_papers_handler_succeeds_with_defaulted_parameters(self):
        req = models.SearchPapersRequest(query="transformers", max_results=None, min_year=None)
        mock_payload = {
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "year": 2017,
                    "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
                    "venue": "NeurIPS",
                    "citationCount": 90000,
                    "url": "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263c9b72e776"
                }
            ]
        }
        with patch.object(main, "api_get", new=AsyncMock(return_value=mock_payload)):
            response = await main.search_papers(req)
        self.assertIsNone(response.error)
        self.assertIn("Attention Is All You Need", response.result)
        self.assertIn("Ashish Vaswani", response.result)

    async def test_author_papers_handler_succeeds_with_defaulted_parameters(self):
        req = models.GetAuthorPapersRequest(author_id="1741101", max_results=None)
        mock_payload = {
            "name": "Geoffrey Hinton",
            "papers": [
                {
                    "title": "Deep Learning",
                    "year": 2015,
                    "citationCount": 50000,
                    "url": "https://semanticscholar.org/paper/xyz"
                }
            ]
        }
        with patch.object(main, "api_get", new=AsyncMock(return_value=mock_payload)):
            response = await main.get_author_papers(req)
        self.assertIsNone(response.error)
        self.assertIn("Recent papers by Geoffrey Hinton", response.result)
        self.assertIn("Deep Learning", response.result)


if __name__ == "__main__":
    unittest.main()
