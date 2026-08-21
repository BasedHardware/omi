"""An on-prem deployment without Typesense must not 500 the conversation search.

`search_conversations` mapped only TRANSIENT failures to ConversationSearchUnavailableError (which the
router answers 503); anything else was re-raised as a bare Exception, so the "not configured" case
(`api_key is not defined`) propagated and FastAPI answered **500**. Proven live on the on-prem stack.

That endpoint is not only the app's search bar: the calendar sheet browses conversations by DATE through
the same call (`has_filter_only_browse`), so a 500 there breaks date filtering too — the thing a user
notices first.
"""

from __future__ import annotations

import pytest

from utils.conversations import search as search_mod


@pytest.fixture(autouse=True)
def _no_typesense(monkeypatch):
    monkeypatch.delenv('TYPESENSE_HOST', raising=False)
    monkeypatch.delenv('TYPESENSE_API_KEY', raising=False)


def test_typesense_configured_reads_both_halves(monkeypatch):
    assert search_mod.typesense_configured() is False
    monkeypatch.setenv('TYPESENSE_HOST', 'typesense')
    assert search_mod.typesense_configured() is False, 'a host without a key is not configured'
    monkeypatch.setenv('TYPESENSE_API_KEY', 'k')
    assert search_mod.typesense_configured() is True


def test_search_reports_unavailable_instead_of_five_hundred():
    """503 "unavailable", not a bare Exception the router turns into 500."""
    with pytest.raises(search_mod.ConversationSearchUnavailableError):
        search_mod.search_conversations(uid='u1', query='coffee')


def test_a_filter_only_browse_is_also_unavailable_not_a_crash():
    """The calendar sheet browses by date with an empty query through this same call."""
    with pytest.raises(search_mod.ConversationSearchUnavailableError):
        search_mod.search_conversations(uid='u1', query='', start_date=1, end_date=2)


def test_an_empty_request_still_short_circuits_without_touching_typesense():
    """No query and no filter is an empty page by definition — it must not need the search engine."""
    result = search_mod.search_conversations(uid='u1', query='')
    assert result['items'] == []


def test_the_hybrid_path_stays_fail_open():
    """Chat/assistants/MCP degrade to vector-only; they must not start raising."""
    assert search_mod.keyword_search_conversation_ids('u1', 'coffee') == []


def test_the_memory_index_predicate_is_the_same_one():
    """One definition of "is Typesense configured", not two drifting copies."""
    from utils.memory import atom_keyword_index

    assert atom_keyword_index.typesense_configured() is False


def test_an_injected_client_counts_as_configured(monkeypatch):
    """Regression: the gate asked the WRONG seam.

    The search call goes through the module-level ``client`` object, and upstream's own search suites
    (tests/unit/test_lock_bypass_fixes.py::TestSearchRedaction and friends) drive this function by patching
    exactly that attribute with a fake — no env vars involved. An env-only check answered "unconfigured"
    for a module that had a perfectly usable client, so five upstream tests started raising 503 instead of
    searching. Whatever the gate asks, it must be the same seam the call uses.
    """
    from unittest.mock import MagicMock

    monkeypatch.setattr(search_mod, 'client', MagicMock())

    assert search_mod.typesense_configured() is True
