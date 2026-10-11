"""
Comprehensive unit and endpoint test suite for Omi PubMed App.
Fully hermetic - zero external network dependencies.
"""

import unittest
from unittest.mock import AsyncMock, patch
import httpx

import main


class NormalizationAndHelperTests(unittest.TestCase):
    def test_normalize_pmid_bare_numbers(self):
        self.assertEqual(main._normalize_pmid("12345678"), "12345678")
        self.assertEqual(main._normalize_pmid("  987654321  "), "987654321")
        self.assertEqual(main._normalize_pmid("1"), "1")
        self.assertEqual(main._normalize_pmid("123456789012"), "123456789012")

    def test_normalize_pmid_prefixes(self):
        self.assertEqual(main._normalize_pmid("PMID: 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("pmid:34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("PMID 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("pmid 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("PMID:34567890"), "34567890")

    def test_normalize_pmid_urls(self):
        self.assertEqual(
            main._normalize_pmid("https://pubmed.ncbi.nlm.nih.gov/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://pubmed.ncbi.nlm.nih.gov/34567890"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("http://pubmed.ncbi.nlm.nih.gov/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://www.ncbi.nlm.nih.gov/pubmed/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://www.ncbi.nlm.nih.gov/pubmed/34567890"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("pubmed.ncbi.nlm.nih.gov/34567890"),
            "34567890",
        )

    def test_normalize_pmid_invalid(self):
        self.assertIsNone(main._normalize_pmid(""))
        self.assertIsNone(main._normalize_pmid("   "))
        self.assertIsNone(main._normalize_pmid(None))
        self.assertIsNone(main._normalize_pmid("abc"))
        self.assertIsNone(main._normalize_pmid("pmid:abc"))
        self.assertIsNone(main._normalize_pmid("123456789012345678"))  # >12 digits
        self.assertIsNone(main._normalize_pmid("https://example.com/34567890"))

    def test_clamp_max_results(self):
        self.assertEqual(main._clamp_max_results(5), 5)
        self.assertEqual(main._clamp_max_results("7"), 7)
        self.assertEqual(main._clamp_max_results(0), 1)
        self.assertEqual(main._clamp_max_results(20), 10)
        self.assertEqual(main._clamp_max_results("invalid", default=5), 5)

    def test_extract_article_fields(self):
        record = {
            "title": "Clinical &amp; Molecular Study",
            "pubdate": "2026 Sep 18",
            "source": "Nature Medicine",
            "elocationid": "10.1038/s41591-026-001",
            "authors": [
                {"name": "Alice Smith"},
                {"name": "Bob Jones"},
                "Charlie Brown",  # String entry fallback
            ],
            "abstract": "Key findings regarding genomic markers.",
        }
        res = main._extract_article_fields(record)
        self.assertEqual(res["title"], "Clinical & Molecular Study")
        self.assertEqual(res["pubdate"], "2026 Sep 18")
        self.assertEqual(res["source"], "Nature Medicine")
        self.assertEqual(res["doi"], "10.1038/s41591-026-001")
        self.assertEqual(res["authors"], ["Alice Smith", "Bob Jones", "Charlie Brown"])
        self.assertEqual(res["abstract"], "Key findings regarding genomic markers.")

    def test_extract_article_fields_malformed(self):
        res = main._extract_article_fields({})
        self.assertEqual(res["title"], "Untitled")
        self.assertEqual(res["authors"], [])
        self.assertEqual(res["abstract"], "")


class MockResponse:
    def __init__(self, json_data=None, text_data="", status_code=200):
        self._json_data = json_data or {}
        self.text = text_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("HTTP Error", request=None, response=self)


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health_endpoint(self):
        resp = await self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    async def test_home_endpoint(self):
        resp = await self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Omi PubMed App", resp.text)

    async def test_manifest_endpoints(self):
        resp1 = await self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp1.status_code, 200)
        tools = resp1.json().get("tools", [])
        self.assertEqual(len(tools), 3)
        endpoints = [t["endpoint"] for t in tools]
        self.assertIn("/tools/search_pubmed", endpoints)
        self.assertIn("/tools/get_pubmed_article", endpoints)
        self.assertIn("/tools/get_related_pubmed", endpoints)

        resp2 = await self.client.get("/manifest.json")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json(), resp2.json())

    @patch.object(httpx.AsyncClient, "get")
    async def test_search_pubmed_success(self, mock_get):
        mock_esearch = MockResponse(json_data={"esearchresult": {"idlist": ["123456", "789012"]}})
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["123456", "789012"],
                "123456": {"title": "Study A", "fulljournalname": "Journal One", "pubdate": "2026 Jan"},
                "789012": {"title": "Study B", "source": "Journal Two", "pubdate": "2026 Feb"},
            }
        })
        mock_get.side_effect = [mock_esearch, mock_esummary]

        resp = await self.client.post("/tools/search_pubmed", json={"query": "genomics", "max_results": 2})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Top PubMed results for: genomics", data["result"])
        self.assertIn("1. PMID 123456: Study A (Journal One, 2026 Jan)", data["result"])
        self.assertIn("2. PMID 789012: Study B (Journal Two, 2026 Feb)", data["result"])

    async def test_search_pubmed_empty_query(self):
        resp = await self.client.post("/tools/search_pubmed", json={"query": "   "})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "query is required")

    @patch.object(httpx.AsyncClient, "get")
    async def test_search_pubmed_no_results(self, mock_get):
        mock_esearch = MockResponse(json_data={"esearchresult": {"idlist": []}})
        mock_get.return_value = mock_esearch

        resp = await self.client.post("/tools/search_pubmed", json={"query": "nonexistentterm12345"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No PubMed results found for: nonexistentterm12345", resp.json()["result"])

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_pubmed_article_success_bare_pmid(self, mock_get):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_efetch = MockResponse(text_data="""<PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
            <Abstract><AbstractText Label="RESULTS">Found significant quantum effects.</AbstractText></Abstract>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>""")
        mock_get.side_effect = [mock_esummary, mock_efetch]

        resp = await self.client.post("/tools/get_pubmed_article", json={"pmid": "12345678"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("PMID 12345678", data["result"])
        self.assertIn("Title: Quantum Biology Discovery", data["result"])
        self.assertIn("Authors: Dr. Smith", data["result"])
        self.assertIn("Abstract: RESULTS: Found significant quantum effects.", data["result"])

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_pubmed_article_success_with_url(self, mock_get):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_get.return_value = mock_esummary

        resp = await self.client.post(
            "/tools/get_pubmed_article",
            json={"pmid": "https://pubmed.ncbi.nlm.nih.gov/12345678/"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["error"])
        self.assertIn("PMID 12345678", resp.json()["result"])

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_pubmed_article_success_with_prefix(self, mock_get):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_get.return_value = mock_esummary

        resp = await self.client.post("/tools/get_pubmed_article", json={"pmid": "PMID: 12345678"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["error"])
        self.assertIn("PMID 12345678", resp.json()["result"])

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_pubmed_article_nonexistent_returns_clean_error(self, mock_get):
        # Reproducing NCBI's documented error structure for non-existent PMIDs
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["999999999"],
                "999999999": {"uid": "999999999", "error": "cannot get document summary"}
            }
        })
        mock_get.return_value = mock_esummary

        resp = await self.client.post("/tools/get_pubmed_article", json={"pmid": "999999999"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertEqual(data["error"], "No PubMed record found for PMID 999999999")

    async def test_get_pubmed_article_invalid_id(self):
        resp = await self.client.post("/tools/get_pubmed_article", json={"pmid": "not-a-valid-id"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "pmid must be a numeric PubMed ID")

    async def test_get_pubmed_article_empty_id(self):
        resp = await self.client.post("/tools/get_pubmed_article", json={"pmid": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "pmid is required")

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_related_pubmed_success(self, mock_get):
        mock_elink = MockResponse(json_data={
            "linksets": [{
                "linksetdbs": [{
                    "links": ["100", "200", "300"]
                }]
            }]
        })
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["200", "300"],
                "200": {"title": "Related Paper 1", "source": "J Cell Biol", "pubdate": "2025"},
                "300": {"title": "Related Paper 2", "source": "Nature", "pubdate": "2026"},
            }
        })
        mock_get.side_effect = [mock_elink, mock_esummary]

        resp = await self.client.post("/tools/get_related_pubmed", json={"pmid": "100", "max_results": 2})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Related PubMed articles for PMID 100:", data["result"])
        self.assertIn("1. PMID 200: Related Paper 1 (J Cell Biol, 2025)", data["result"])
        self.assertIn("2. PMID 300: Related Paper 2 (Nature, 2026)", data["result"])

    @patch.object(httpx.AsyncClient, "get")
    async def test_get_related_pubmed_no_links(self, mock_get):
        mock_elink = MockResponse(json_data={"linksets": []})
        mock_get.return_value = mock_elink

        resp = await self.client.post("/tools/get_related_pubmed", json={"pmid": "12345"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No related articles found for PMID 12345", resp.json()["result"])

    async def test_get_related_pubmed_invalid_pmid(self):
        resp = await self.client.post("/tools/get_related_pubmed", json={"pmid": "invalid!"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "pmid must be a numeric PubMed ID")


if __name__ == "__main__":
    unittest.main()
