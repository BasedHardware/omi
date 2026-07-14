"""Regression: search_conversations clamps unbounded/None page and per_page instead of 500ing.

SearchRequest.page/per_page are Optional and unbounded, so a client sending null, 0, a negative, or a
huge value reached search_conversations and either raised TypeError (len(...) >= per_page, page + 1) or
forwarded an out-of-range value to Typesense (RequestMalformed), surfacing as HTTP 500 on both
POST /v1/conversations/search and the integration conversation search. The util now clamps page to >= 1
and per_page to [1, 250] at the shared boundary. Pinned against a fake Typesense client, no live services.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
# The Typesense client is constructed at import time and validates its config, so give it inert values.
# It never connects in these tests: the client attribute is replaced with a fake before any call.
os.environ.setdefault("TYPESENSE_HOST", "localhost")
os.environ.setdefault("TYPESENSE_HOST_PORT", "8108")
os.environ.setdefault("TYPESENSE_PROTOCOL", "http")
os.environ.setdefault("TYPESENSE_API_KEY", "test-key")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

import utils.conversations.search as search_mod  # noqa: E402


def _fake_client(recorder):
    fake = MagicMock()
    fake.collections.__getitem__.return_value.documents.search.side_effect = lambda params: recorder.update(
        params=dict(params)
    ) or {"hits": []}
    return fake


@pytest.mark.parametrize(
    "page,per_page,exp_page,exp_per_page",
    [
        (None, None, 1, 10),  # nullable -> defaults, no TypeError
        (0, 0, 1, 10),  # zero -> floor / default
        (-5, -5, 1, 1),  # negative -> floor to 1
        (3, 100000, 3, 250),  # huge per_page -> Typesense 250-hit cap
    ],
)
def test_search_conversations_clamps_pagination(monkeypatch, page, per_page, exp_page, exp_per_page):
    rec = {}
    monkeypatch.setattr(search_mod, "client", _fake_client(rec))
    # Before the fix each of these either raised TypeError or forwarded an out-of-range value to Typesense.
    result = search_mod.search_conversations(uid="u1", query="hi", page=page, per_page=per_page)
    assert rec["params"]["page"] == exp_page  # what Typesense actually received
    assert rec["params"]["per_page"] == exp_per_page
    assert result["current_page"] == exp_page
    assert result["per_page"] == exp_per_page


def test_search_conversations_empty_query_branch_is_also_clamped(monkeypatch):
    # The empty-query early return echoes page/per_page; it must be clamped too (never None).
    monkeypatch.setattr(search_mod, "client", _fake_client({}))
    result = search_mod.search_conversations(uid="u1", query="", per_page=None, page=None)
    assert result["per_page"] == 10
    assert result["current_page"] == 1
