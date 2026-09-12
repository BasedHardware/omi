"""Unit tests for PubMed related-paper lookup PMID exclusion (issue #13646)."""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app, _filter_related_pmids


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --------------------------------------------------------------------------- #
# Unit Tests for _filter_related_pmids
# --------------------------------------------------------------------------- #

def test_source_first_with_limit_one():
    """When source PMID is the first item, max_results=1 selects the first *other* article."""
    source_pmid = "19304878"
    links = ["19304878", "14630660", "22909249", "18205193"]
    result = _filter_related_pmids(links, source_pmid, max_results=1)
    assert result == ["14630660"], f"Expected ['14630660'] but got {result}"


def test_source_later_in_list():
    """When source PMID appears later in the list, it is excluded and order is preserved."""
    source_pmid = "14630660"
    links = ["19304878", "14630660", "22909249", "18205193"]
    result = _filter_related_pmids(links, source_pmid, max_results=3)
    assert result == ["19304878", "22909249", "18205193"]


def test_source_only_response():
    """When links only contains the source PMID, result is empty."""
    source_pmid = "19304878"
    links = ["19304878"]
    result = _filter_related_pmids(links, source_pmid, max_results=5)
    assert result == []


def test_no_source_present():
    """When source PMID is not in links, all links are preserved up to max_results."""
    source_pmid = "99999999"
    links = ["19304878", "14630660", "22909249"]
    result = _filter_related_pmids(links, source_pmid, max_results=2)
    assert result == ["19304878", "14630660"]


def test_integer_pmids_handling():
    """Handles integer PMIDs returned by NCBI JSON parser consistently with string source."""
    source_pmid = "19304878"
    links = [19304878, 14630660, 22909249]
    result = _filter_related_pmids(links, source_pmid, max_results=2)
    assert result == ["14630660", "22909249"]


# --------------------------------------------------------------------------- #
# Endpoint Integration Tests with Mock NCBI Responses
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
async def test_endpoint_excludes_source_pmid(monkeypatch):
    """End-to-end /tools/get_related_pubmed excludes source PMID from summaries and results."""
    source_pmid = "19304878"

    # Mock _fetch_json to return elink data starting with source PMID
    async def mock_fetch_json(client, endpoint, params):
        assert endpoint == "elink.fcgi"
        assert params["id"] == source_pmid
        return {
            "linksets": [
                {
                    "linksetdbs": [
                        {
                            "linkname": "pubmed_pubmed",
                            "links": [19304878, 14630660, 22909249],
                        }
                    ]
                }
            ]
        }

    # Mock _fetch_summaries
    requested_summary_ids = []
    async def mock_fetch_summaries(client, pmids):
        requested_summary_ids.extend(pmids)
        return {
            "14630660": {
                "title": "Related Paper One",
                "fulljournalname": "Journal of Testing",
                "pubdate": "2024",
            }
        }

    monkeypatch.setattr("main._fetch_json", mock_fetch_json)
    monkeypatch.setattr("main._fetch_summaries", mock_fetch_summaries)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/tools/get_related_pubmed", json={"pmid": source_pmid, "max_results": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") is None
        # Must request summaries for the related article, NOT the source article
        assert requested_summary_ids == ["14630660"]
        assert "1. PMID 14630660" in data["result"]
        assert "1. PMID 19304878" not in data["result"]


@pytest.mark.anyio
async def test_endpoint_source_only_avoids_summary_call(monkeypatch):
    """When NCBI elink returns only the source PMID, no summary call is made."""
    source_pmid = "19304878"

    async def mock_fetch_json(client, endpoint, params):
        return {
            "linksets": [
                {
                    "linksetdbs": [
                        {
                            "linkname": "pubmed_pubmed",
                            "links": ["19304878"],
                        }
                    ]
                }
            ]
        }

    summary_called = False
    async def mock_fetch_summaries(client, pmids):
        nonlocal summary_called
        summary_called = True
        return {}

    monkeypatch.setattr("main._fetch_json", mock_fetch_json)
    monkeypatch.setattr("main._fetch_summaries", mock_fetch_summaries)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/tools/get_related_pubmed", json={"pmid": source_pmid, "max_results": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert not summary_called, "Should not call _fetch_summaries when no other related articles exist"
        assert f"No related articles found for PMID {source_pmid}" in data["result"]
