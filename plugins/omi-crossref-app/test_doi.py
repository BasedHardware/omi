"""DOI resolver links must identify the same work as the bare DOI."""

from unittest.mock import patch
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

import main


@pytest.mark.parametrize(
    "value, doi",
    [
        ("10.1038/nphys1170", "10.1038/nphys1170"),
        (" https://doi.org/10.1038/nphys1170 ", "10.1038/nphys1170"),
        ("http://dx.doi.org/10.1038/nphys1170", "10.1038/nphys1170"),
        ("HTTPS://DOI.ORG/10.1038/nphys1170", "10.1038/nphys1170"),
        ("doi:10.1038/nphys1170", "10.1038/nphys1170"),
        ("https://doi.org/10.1000/a%23b?download=1#section", "10.1000/a#b"),
        ("10.1000/a%23b", "10.1000/a%23b"),
        ("https://doi.org/10.1000/a%2523b", "10.1000/a%23b"),
    ],
)
def test_lookup_normalizes_doi_at_http_boundary(value, doi):
    requests = []

    def respond(request):
        requests.append(request)
        assert str(request.url) == f"https://api.crossref.org/works/{quote(doi, safe='')}"
        return httpx.Response(200, json={"message": {"title": ["Example work"], "DOI": doi}})

    original_client = httpx.AsyncClient
    with patch.object(main.httpx, "AsyncClient", side_effect=lambda **kw: original_client(
        transport=httpx.MockTransport(respond), **kw
    )):
        with TestClient(main.app) as client:
            response = client.post("/tools/get_crossref_work", json={"doi": value})
    assert response.status_code == 200
    assert response.json()["error"] is None
    assert "Title: Example work" in response.json()["result"]
    assert len(requests) == 1


@pytest.mark.parametrize("value", [
    "https://example.com/10.1038/nphys1170",
    "https://doi.org.evil.example/10.1038/nphys1170",
    "https://doi.org/",
    "https://doi.org/invalid",
    "not-a-doi",
    "10.1000/../works",
])
def test_invalid_lookup_does_not_request_crossref(value):
    with patch.object(main.httpx, "AsyncClient") as client_factory:
        with TestClient(main.app) as client:
            response = client.post("/tools/get_crossref_work", json={"doi": value})
    assert response.status_code == 200
    assert response.json()["error"]
    client_factory.assert_not_called()
