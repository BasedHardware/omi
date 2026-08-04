"""Regression: POST /v1/conversations/search 500s whenever speaker_id is set.

The speaker filter was pushed into Typesense as `transcript_segments.is_user:=true` /
`transcript_segments.person_id:=<id>`, but the `conversations` collection has no transcript_segments
field at all (the Firestore -> Typesense sync only carries userId/created_at/discarded/started_at/
finished_at/structured.*). Typesense rejected the whole query with
400 "Could not find a filter field named `transcript_segments.is_user` in the schema", which
search_conversations re-raised and surfaced as HTTP 500 -- so speaker-filtered search had been 100%
broken in prod since it shipped.

The filter now runs against the hydrated Firestore documents instead. Pinned against a fake Typesense
client, no live services.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
# The Typesense client validates its config, so give it inert values. It never connects in these
# tests: the client attribute is replaced with a fake before any call.
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


@pytest.mark.parametrize("speaker_id", ["user", "person-123"])
def test_speaker_id_never_reaches_typesense_filter_by(monkeypatch, speaker_id):
    rec = {}
    monkeypatch.setattr(search_mod, "client", _fake_client(rec))
    search_mod.search_conversations(uid="u1", query="hi", speaker_id=speaker_id)
    # Before the fix filter_by carried transcript_segments.*, which is not in the schema -> 400 -> 500.
    assert "transcript_segments" not in rec["params"]["filter_by"]
    assert rec["params"]["filter_by"].startswith("userId:=u1")


def test_speaker_id_alone_still_browses_instead_of_early_returning(monkeypatch):
    # An empty query plus a speaker filter must still hit Typesense (browse), not short-circuit to [].
    rec = {}
    monkeypatch.setattr(search_mod, "client", _fake_client(rec))
    search_mod.search_conversations(uid="u1", query="", speaker_id="user")
    assert rec["params"]["q"] == "*"


# Fields the live Typesense `conversations` collection actually indexes, i.e. the only fields
# filter_by may reference. Verified against the prod collection schema: everything else it carries is
# under structured.*, which conversation search does not filter on.
_TYPESENSE_FILTERABLE_FIELDS = {"userId", "created_at", "discarded", "started_at", "finished_at"}


def _filter_fields(filter_by):
    fields = set()
    for clause in filter_by.split("&&"):
        clause = clause.strip()
        if clause:
            fields.add(clause.split(":", 1)[0].strip())
    return fields


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"include_discarded": False},
        {"start_date": 100, "end_date": 200},
        {"speaker_id": "user"},
        {"speaker_id": "person-1"},
        {"include_discarded": False, "start_date": 100, "end_date": 200, "speaker_id": "user"},
    ],
)
def test_every_filter_field_exists_in_the_typesense_schema(monkeypatch, kwargs):
    """Guard: no argument combination may build a filter on a field the serving index lacks.

    Typesense rejects the entire query (400) when filter_by names an unknown field, so one such
    field breaks the whole search rather than just its own predicate.
    """
    rec = {}
    monkeypatch.setattr(search_mod, "client", _fake_client(rec))
    search_mod.search_conversations(uid="u1", query="hi", **kwargs)
    assert _filter_fields(rec["params"]["filter_by"]) <= _TYPESENSE_FILTERABLE_FIELDS


def _conv(segments):
    return {"id": "c1", "transcript_segments": segments}


@pytest.mark.parametrize(
    "conversation,speaker_id,expected",
    [
        (_conv([{"is_user": True, "person_id": None}]), "user", True),
        (_conv([{"is_user": False, "person_id": "p1"}]), "user", False),
        (_conv([{"is_user": False, "person_id": "p1"}]), "p1", True),
        (_conv([{"is_user": False, "person_id": "p2"}]), "p1", False),
        (_conv([{"is_user": False, "person_id": None}, {"is_user": True}]), "user", True),
        # No filter requested -> everything matches, even without a transcript.
        (_conv([]), None, True),
        ({"id": "c1"}, None, True),
        # Missing/degenerate transcripts must not raise; they simply do not match.
        ({"id": "c1"}, "user", False),
        ({"id": "c1", "transcript_segments": None}, "user", False),
        ({"id": "c1", "transcript_segments": "oops"}, "user", False),
        (_conv([None, {"is_user": True}]), "user", True),
    ],
)
def test_conversation_matches_speaker(conversation, speaker_id, expected):
    assert search_mod.conversation_matches_speaker(conversation, speaker_id) is expected
