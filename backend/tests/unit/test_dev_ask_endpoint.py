"""The Developer-API ask endpoint answers from the user's own conversations.

POST /v1/dev/user/ask semantically searches the caller's conversations, then synthesizes
a cited answer from the most relevant ones via the same RAG the chat surface uses. It is
read-only, and must not invoke the LLM when no relevant conversation is found.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import dependencies as deps
import routers.developer as dev
import pytest
from fastapi import HTTPException
from utils.conversations.search import ConversationSearchUnavailableError


def _conv(cid="c1", title="Pricing sync", overview="We discussed pricing.", text="Raise prices 10%."):
    return SimpleNamespace(
        id=cid,
        structured=SimpleNamespace(title=title, overview=overview),
        transcript_segments=[SimpleNamespace(text=text)],
        created_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )


def test_ask_returns_a_grounded_cited_answer():
    with patch.object(dev, "search_conversations", return_value={"items": [{"id": "c1"}]}), patch.object(
        dev.conversations_db, "get_conversations_by_id", return_value=[{"id": "c1"}]
    ), patch.object(dev, "deserialize_conversations", return_value=[_conv()]), patch.object(
        dev, "qa_rag", return_value="You decided to raise prices 10%."
    ) as qa:
        resp = dev.ask_conversations(dev.DeveloperAskRequest(question="what did I decide about pricing?"), uid="u1")

    assert resp.answer == "You decided to raise prices 10%."
    assert [s.id for s in resp.sources] == ["c1"]
    assert resp.sources[0].title == "Pricing sync"
    # Retrieval flows into qa_rag as grounded, citation-enabled context.
    assert qa.call_args.kwargs["cited"] is True
    assert "Raise prices 10%." in qa.call_args.args[2]  # the context string


def test_ask_does_not_call_the_llm_when_no_conversation_matches():
    with patch.object(dev, "search_conversations", return_value={"items": []}), patch.object(dev, "qa_rag") as qa:
        resp = dev.ask_conversations(dev.DeveloperAskRequest(question="anything?"), uid="u1")

    assert "couldn't find" in resp.answer.lower()
    assert resp.sources == []
    qa.assert_not_called()  # no billable RAG call on an empty retrieval


def test_ask_excludes_discarded_conversations_from_retrieval():
    """Discarded/deleted conversations must never reach the LLM. search_conversations
    defaults include_discarded=True, so the endpoint must override it to False
    (maintainer review on #10314)."""
    with patch.object(dev, "search_conversations", return_value={"items": []}) as search, patch.object(dev, "qa_rag"):
        dev.ask_conversations(dev.DeveloperAskRequest(question="q"), uid="u1")

    assert search.call_args.kwargs.get("include_discarded") is False


def test_ask_drops_a_locked_conversation_even_when_the_search_index_is_stale():
    """The search index's is_locked can lag Firestore, so a stale hit could surface a
    since-locked conversation. The endpoint must re-check is_locked on the authoritative
    record and never send a locked conversation into the LLM (maintainer review on
    #10314)."""
    locked = {"id": "c1", "is_locked": True}
    unlocked = {"id": "c2"}
    with patch.object(dev, "search_conversations", return_value={"items": [{"id": "c1"}, {"id": "c2"}]}), patch.object(
        dev.conversations_db, "get_conversations_by_id", return_value=[locked, unlocked]
    ), patch.object(
        dev, "deserialize_conversations", side_effect=lambda raw: [_conv(cid=c["id"]) for c in raw]
    ) as deser, patch.object(
        dev, "qa_rag", return_value="answer"
    ):
        resp = dev.ask_conversations(dev.DeveloperAskRequest(question="q"), uid="u1")

    # The locked conversation was filtered before hydration; only the unlocked one remains.
    passed_to_deserialize = deser.call_args.args[0]
    assert [c["id"] for c in passed_to_deserialize] == ["c2"]
    assert [s.id for s in resp.sources] == ["c2"]


def test_ask_endpoint_is_bound_to_the_dev_ask_rate_limited_dependency():
    """The billable LLM endpoint carries its own tight per-key budget (dev:ask), not the
    cheap dev:conversations_read list limit — a leaked/overused key can't run the RAG path
    unbounded. Regression for the maintainer review on #10314."""
    from utils.rate_limit_config import RATE_POLICIES

    # dev:ask exists and is no looser than the LLM conversation-create budget, and tighter
    # than the cheap list-read limit the endpoint would otherwise have ridden.
    assert "dev:ask" in RATE_POLICIES
    assert RATE_POLICIES["dev:ask"][0] <= RATE_POLICIES["dev:conversations"][0]
    assert RATE_POLICIES["dev:ask"][0] < RATE_POLICIES["dev:conversations_read"][0]

    # The endpoint's auth dependency is the rate-limited one, and it enforces exactly the
    # dev:ask policy (fail-closed per-key) before returning the uid.
    enforced = {}

    async def fake_enforce(*, request, auth, policy_name):
        enforced["policy"] = policy_name

    auth = SimpleNamespace(uid="u1", app_id="a1", key_id="k1")
    with patch.object(deps, "_require_conversations_read_scope", lambda a: None), patch.object(
        deps, "_check_dev_api_key_rate_limit_async", fake_enforce
    ):
        uid = asyncio.run(deps.get_uid_with_conversations_read_ask(auth=auth, request=None))

    assert uid == "u1"
    assert enforced["policy"] == "dev:ask"


def test_ask_rejects_invalid_timezone():
    with pytest.raises(ValueError, match="valid IANA timezone"):
        dev.DeveloperAskRequest(question="when?", timezone="Not/A_Timezone")


def test_ask_maps_search_outage_to_503():
    with patch.object(dev, "search_conversations", side_effect=ConversationSearchUnavailableError("down")):
        with pytest.raises(HTTPException) as exc_info:
            dev.ask_conversations(dev.DeveloperAskRequest(question="when?"), uid="u1")

    assert exc_info.value.status_code == 503


def test_ask_merges_transcript_only_hits_before_rag():
    with patch.object(dev, "search_conversations", return_value={"items": []}), patch.object(
        dev, "resolve_mcp_conversation_search_ids", return_value=["c1"]
    ), patch.object(dev.conversations_db, "get_conversations_by_id", return_value=[{"id": "c1"}]), patch.object(
        dev, "deserialize_conversations", return_value=[_conv()]
    ), patch.object(
        dev, "qa_rag", return_value="answer"
    ) as qa:
        response = dev.ask_conversations(dev.DeveloperAskRequest(question="what was said?"), uid="u1")

    assert response.sources[0].id == "c1"
    qa.assert_called_once()


def test_ask_lives_on_public_developer_api_not_app_client_firebase():
    """POST /v1/dev/user/ask is developerApiKey-only. It must not appear in the Firebase
    app-client OpenAPI (which would stamp firebaseBearer and mis-teach agents/SDKs).
    Regression for the docs-accuracy review on #10314."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    public = json.loads((root / "docs/api-reference/openapi.json").read_text(encoding='utf-8'))
    app_client = json.loads((root / "docs/api-reference/app-client-openapi.json").read_text(encoding='utf-8'))

    ask = public["paths"]["/v1/dev/user/ask"]["post"]
    assert ask["security"] == [{"developerApiKey": []}]
    assert "/v1/dev/user/ask" not in app_client["paths"]
