"""Unit tests for related-PMID selection (issue #13646)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Provide minimal stubs if running directly without site-packages
try:
    import httpx
    import fastapi
    import pydantic
except ImportError:
    import types

    httpx_stub = types.ModuleType("httpx")
    httpx_stub.AsyncClient = type("AsyncClient", (), {})
    sys.modules.setdefault("httpx", httpx_stub)

    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.FastAPI = type("FastAPI", (), {"__init__": lambda self, **kwargs: None, "get": lambda self, *a, **kw: lambda f: f, "post": lambda self, *a, **kw: lambda f: f})
    fastapi_stub.Request = type("Request", (), {})
    sys.modules.setdefault("fastapi", fastapi_stub)

    fastapi_resp_stub = types.ModuleType("fastapi.responses")
    fastapi_resp_stub.HTMLResponse = type("HTMLResponse", (), {})
    sys.modules.setdefault("fastapi.responses", fastapi_resp_stub)

    pydantic_stub = types.ModuleType("pydantic")
    pydantic_stub.BaseModel = type("BaseModel", (), {})
    sys.modules.setdefault("pydantic", pydantic_stub)

from main import _select_related_pmids


def test_excludes_source_pmid_when_first():
    links = ["19304878", "14630660", "22909249", "20739307", "31278684"]
    assert _select_related_pmids(links, "19304878", 1) == ["14630660"]
    assert _select_related_pmids(links, "19304878", 5) == [
        "14630660",
        "22909249",
        "20739307",
        "31278684",
    ]


def test_excludes_source_pmid_when_not_first():
    links = ["14630660", "19304878", "22909249"]
    assert _select_related_pmids(links, "19304878", 5) == ["14630660", "22909249"]


def test_source_only_response_yields_no_related():
    assert _select_related_pmids(["19304878"], "19304878", 5) == []


def test_no_source_present_is_unaffected():
    links = ["14630660", "22909249", "20739307"]
    assert _select_related_pmids(links, "19304878", 2) == ["14630660", "22909249"]


def test_handles_integer_ids_consistently():
    links = [19304878, 14630660, 22909249]
    assert _select_related_pmids(links, "19304878", 5) == ["14630660", "22909249"]


if __name__ == "__main__":
    test_excludes_source_pmid_when_first()
    test_excludes_source_pmid_when_not_first()
    test_source_only_response_yields_no_related()
    test_no_source_present_is_unaffected()
    test_handles_integer_ids_consistently()
    print("test_related OK")
