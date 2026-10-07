"""Unit tests for efetch abstract extraction (issue #13199)."""

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

from main import _extract_abstract_from_efetch_xml


def test_extracts_unlabeled_abstract():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <Article>
            <Abstract>
              <AbstractText>This paper studies sleep.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    assert _extract_abstract_from_efetch_xml(xml) == "This paper studies sleep."


def test_extracts_labeled_abstract_sections():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <Article>
            <Abstract>
              <AbstractText Label="BACKGROUND">Prior work.</AbstractText>
              <AbstractText Label="METHODS">We measured X.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    out = _extract_abstract_from_efetch_xml(xml)
    assert "BACKGROUND: Prior work." in out
    assert "METHODS: We measured X." in out


def test_returns_empty_for_missing_or_bad_xml():
    assert _extract_abstract_from_efetch_xml("<not-closed") == ""
    assert _extract_abstract_from_efetch_xml("<PubmedArticleSet></PubmedArticleSet>") == ""


if __name__ == "__main__":
    test_extracts_unlabeled_abstract()
    test_extracts_labeled_abstract_sections()
    test_returns_empty_for_missing_or_bad_xml()
    print("test_abstract OK")
