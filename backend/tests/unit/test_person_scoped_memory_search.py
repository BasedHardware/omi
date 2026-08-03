"""Person-scoped memory retrieval and proper-name recall for the legacy cohort.

Two defects are covered here.

1. **Nothing could ask for one person's memories.** ``MemoryDB.subject_entity_id`` is
   persisted and mirrored into the Pinecone metadata, and
   ``vector_db.find_similar_memories`` has always accepted a ``subject_entity_id``
   filter — but no caller ever passed one and no read queried the field, so
   "what do you know about <person>" and the desktop profile's Memories tab both
   resolved to nothing.
2. **Proper names were unretrievable.** ``search_memories_text`` was one Pinecone kNN
   call. Embedding a bare name against a short structural fact is the worst case for
   that ranking, which is exactly why conversation search grew a keyword leg (#5072).
   Memory search never did.

The legacy-principal tests below are the compatibility contract: a memory written before
any of this exists (no ``subject_entity_id``, no tags) must still be returned by an
unfiltered search, and an unfiltered search whose keyword leg finds nothing must render
byte-for-byte what it rendered before the leg existed.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import json  # noqa: E402

import database.memories as memories_db  # noqa: E402
import utils.memory.legacy_keyword_search as keyword_leg  # noqa: E402
import utils.retrieval.tool_services.memories as memories_svc  # noqa: E402
from routers import memories as memories_router  # noqa: E402
from utils.memory.default_read_rollout import MemoryReadDecision  # noqa: E402
from utils.memory.memory_system import MemorySystem  # noqa: E402

UID = "uid-legacy-principal"
PERSON_UUID = "5f2a9c31-7d64-4f1e-9a20-3c8b6e0d1f45"
OTHER_PERSON_UUID = "8b31d7a0-2e55-4c19-8f77-11a4c9de6b02"
SUBJECT = f"person:{PERSON_UUID}"
OTHER_SUBJECT = f"person:{OTHER_PERSON_UUID}"

CREATED = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)


def _memory(memory_id, content, *, tags=None, subject=None, created_at=CREATED, **extra):
    """A Firestore memory document, shaped so ``MemoryDB(**doc)`` validates."""
    doc = {
        'id': memory_id,
        'uid': UID,
        'content': content,
        'category': 'interesting',
        'created_at': created_at,
        'updated_at': created_at,
        'tags': list(tags or []),
        'subject_entity_id': subject,
    }
    doc.update(extra)
    return doc


# ---------------------------------------------------------------------------
# A corpus with one distinctive name in it and a lot of noise around it.
#
# "group" appears in 8 of 13 documents, so it is a common word here; "Sophia" appears in
# exactly one. That ratio is the whole point of the selectivity rule.
# ---------------------------------------------------------------------------
SOPHIA_FACT_ID = "mem-sophia"
SOPHIA_FACT = "Sophia Nakamura — in your “AV Founders” group (work); you know them via iMessage."


def _corpus():
    memories = [
        _memory(SOPHIA_FACT_ID, SOPHIA_FACT, tags=["people_intelligence", SUBJECT], subject=SUBJECT),
        _memory("mem-hobby", "Enjoys kiteboarding on weekends", tags=["kiteboarding"]),
    ]
    for index in range(8):
        memories.append(_memory(f"mem-group-{index}", f"Belongs to the running group number {index}"))
    for index in range(3):
        memories.append(_memory(f"mem-misc-{index}", f"Prefers oat milk in drink number {index}"))
    return memories


# ===========================================================================
# The keyword leg itself
# ===========================================================================
class TestKeywordLeg:
    @pytest.fixture(autouse=True)
    def corpus(self, monkeypatch):
        self.reads = []

        def _get_memories(uid, limit=100, offset=0, **kwargs):
            self.reads.append({'uid': uid, 'limit': limit, 'offset': offset})
            return _corpus()

        monkeypatch.setattr(keyword_leg.memory_db, "get_memories", _get_memories)

    def test_proper_name_is_retrievable(self):
        assert keyword_leg.keyword_search_legacy_memory_ids(UID, "Sophia", limit=5) == [SOPHIA_FACT_ID]

    def test_proper_name_survives_a_conversational_wrapper(self):
        """ "what do you know about Sophia" must not be diluted by its filler words."""
        ids = keyword_leg.keyword_search_legacy_memory_ids(UID, "what do you know about Sophia", limit=5)
        assert ids == [SOPHIA_FACT_ID]

    def test_common_word_alone_promotes_nothing(self):
        """The guard that keeps ordinary searches ranked exactly as they were."""
        assert keyword_leg.keyword_search_legacy_memory_ids(UID, "the running group", limit=5) == []

    def test_tags_are_searchable(self):
        """Provenance tags carry retrievable terms the content may not repeat."""
        assert keyword_leg.keyword_search_legacy_memory_ids(UID, "kiteboarding", limit=5) == ["mem-hobby"]

    def test_locked_memories_are_never_promoted(self, monkeypatch):
        monkeypatch.setattr(
            keyword_leg.memory_db,
            "get_memories",
            lambda *a, **k: [_memory(SOPHIA_FACT_ID, SOPHIA_FACT, is_locked=True)],
        )
        assert keyword_leg.keyword_search_legacy_memory_ids(UID, "Sophia", limit=5) == []

    def test_read_failure_is_fail_open(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("firestore down")

        monkeypatch.setattr(keyword_leg.memory_db, "get_memories", _boom)
        assert keyword_leg.keyword_search_legacy_memory_ids(UID, "Sophia", limit=5) == []

    def test_scan_is_bounded(self):
        keyword_leg.keyword_search_legacy_memory_ids(UID, "Sophia", limit=5, scan_limit=42)
        assert self.reads == [{'uid': UID, 'limit': 42, 'offset': 0}]

    def test_selectivity_ceiling_scales_with_the_window(self):
        # 10 documents -> ceiling 2. A term in 2 is evidence; a term in 3 is not.
        terms = [{'alpha'}, {'alpha'}, {'beta'}, {'beta'}, {'beta'}] + [{'noise'} for _ in range(5)]
        assert keyword_leg.selective_terms(['alpha', 'beta'], terms) == {'alpha'}


# ===========================================================================
# The by-subject Firestore read
# ===========================================================================
class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.id = data.get('id', '')

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    """Only what ``get_memories_by_subject`` uses: where(filter=...), limit(), stream()."""

    def __init__(self, docs):
        self._docs = docs

    def where(self, filter=None):  # noqa: A002 - matches the Firestore keyword
        matched = []
        for doc in self._docs:
            value = doc.get(filter.field_path)
            if filter.op_string == '==' and value == filter.value:
                matched.append(doc)
            elif filter.op_string == 'array_contains' and isinstance(value, list) and filter.value in value:
                matched.append(doc)
        return _FakeQuery(matched)

    def limit(self, count):
        return _FakeQuery(self._docs[:count])

    def stream(self):
        return [_FakeDoc(doc) for doc in self._docs]


class _FakeFirestore:
    def __init__(self, docs):
        self._docs = docs

    def collection(self, _name):
        return SimpleNamespace(document=lambda _uid: SimpleNamespace(collection=lambda _sub: _FakeQuery(self._docs)))


class TestGetMemoriesBySubject:
    def test_subject_entity_id_leg(self):
        docs = [
            _memory("mem-1", "Runs the Tuesday standup", subject=SUBJECT),
            _memory("mem-2", "Someone else entirely", subject=OTHER_SUBJECT),
            _memory("mem-3", "A memory with no subject at all"),
        ]
        found = memories_db.get_memories_by_subject(UID, SUBJECT, firestore_client=_FakeFirestore(docs))
        assert [m['id'] for m in found] == ["mem-1"]

    def test_tag_leg_reaches_facts_written_before_attribution(self):
        """The desktop People writer stamps ``person:<uuid>`` as a tag, not as a subject.

        Same id string, second column — so the union is still one identity, and a fact
        written by a client that knew the person before the extractor did is not lost.
        """
        docs = [_memory("mem-tagged", "Sophia — in your group", tags=["people_intelligence", SUBJECT])]
        found = memories_db.get_memories_by_subject(UID, SUBJECT, firestore_client=_FakeFirestore(docs))
        assert [m['id'] for m in found] == ["mem-tagged"]

    def test_both_legs_deduplicate(self):
        docs = [_memory("mem-both", "Attributed twice over", tags=[SUBJECT], subject=SUBJECT)]
        found = memories_db.get_memories_by_subject(UID, SUBJECT, firestore_client=_FakeFirestore(docs))
        assert [m['id'] for m in found] == ["mem-both"]

    def test_newest_first(self):
        older = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = datetime(2026, 6, 1, tzinfo=timezone.utc)
        docs = [
            _memory("mem-old", "Older fact", subject=SUBJECT, created_at=older),
            _memory("mem-new", "Newer fact", subject=SUBJECT, created_at=newer),
        ]
        found = memories_db.get_memories_by_subject(UID, SUBJECT, firestore_client=_FakeFirestore(docs))
        assert [m['id'] for m in found] == ["mem-new", "mem-old"]

    def test_rejected_and_superseded_facts_are_excluded(self):
        docs = [
            _memory("mem-ok", "Still true", subject=SUBJECT),
            _memory("mem-rejected", "User said no", subject=SUBJECT, user_review=False),
            _memory("mem-stale", "Superseded", subject=SUBJECT, invalid_at=CREATED),
        ]
        found = memories_db.get_memories_by_subject(UID, SUBJECT, firestore_client=_FakeFirestore(docs))
        assert [m['id'] for m in found] == ["mem-ok"]

    def test_empty_subject_reads_nothing(self):
        docs = [_memory("mem-1", "Anything", subject=SUBJECT)]
        assert memories_db.get_memories_by_subject(UID, "", firestore_client=_FakeFirestore(docs)) == []


# ===========================================================================
# search_memories_text
# ===========================================================================
@pytest.fixture
def legacy_cohort(monkeypatch):
    """Pin the service to the legacy read path and return a knob bag for its collaborators."""
    monkeypatch.setattr(memories_svc, "pin_memory_system", lambda *a, **k: MemorySystem.LEGACY)
    monkeypatch.setattr(
        memories_svc,
        "search_memory_default_chat_memories_vector_decision_text",
        lambda **kwargs: SimpleNamespace(
            read_decision=MemoryReadDecision.USE_LEGACY_SAFE, text=None, fallback_reason="test"
        ),
    )
    monkeypatch.setattr(memories_svc, "chat_legacy_read_authorized", lambda _result: True)
    monkeypatch.setattr(memories_svc.notification_db, "get_user_time_zone", lambda _uid: "UTC")

    knobs = SimpleNamespace(vector_calls=[], hydrated=[], keyword_ids=[], subject_docs=[])

    def _find_similar(uid, query, threshold=0.85, limit=5, subject_entity_id=None):
        knobs.vector_calls.append(
            {
                'uid': uid,
                'query': query,
                'threshold': threshold,
                'limit': limit,
                'subject_entity_id': subject_entity_id,
            }
        )
        return knobs.vector_matches

    knobs.vector_matches = []
    monkeypatch.setattr(memories_svc.vector_db, "find_similar_memories", _find_similar)
    monkeypatch.setattr(
        memories_svc.memory_db,
        "get_memories_by_ids",
        lambda _uid, ids: [doc for doc in knobs.hydrated if doc['id'] in set(ids)],
    )
    monkeypatch.setattr(memories_svc, "keyword_search_legacy_memory_ids", lambda *a, **k: knobs.keyword_ids)
    monkeypatch.setattr(memories_svc.memory_db, "get_memories_by_subject", lambda *a, **k: knobs.subject_docs)
    return knobs


# The exact string an unfiltered legacy search rendered before the keyword leg existed.
LEGACY_REFERENCE_OUTPUT = (
    "Found 2 memories matching 'cooking':\n"
    "\n"
    "- Likes pasta (relevance: 0.95, category: interesting, date: 2026-06-26)\n"
    "- Hates olives (relevance: 0.80, category: interesting, date: 2026-06-26)"
)


def _legacy_principal_docs():
    """Two memories from before subjects existed: no subject_entity_id, no tags."""
    return [
        _memory("mem-a", "Likes pasta"),
        _memory("mem-b", "Hates olives"),
    ]


class TestLegacyPrincipalUnchanged:
    """The compatibility contract. A subjectless memory and an unfiltered search."""

    def test_unfiltered_search_is_byte_identical(self, legacy_cohort):
        legacy_cohort.vector_matches = [
            {'memory_id': 'mem-a', 'score': 0.95},
            {'memory_id': 'mem-b', 'score': 0.80},
        ]
        legacy_cohort.hydrated = _legacy_principal_docs()
        legacy_cohort.keyword_ids = []

        out = memories_svc.search_memories_text(uid=UID, query="cooking")
        assert out == LEGACY_REFERENCE_OUTPUT

    def test_unfiltered_search_applies_no_subject_filter(self, legacy_cohort):
        legacy_cohort.vector_matches = [{'memory_id': 'mem-a', 'score': 0.95}]
        legacy_cohort.hydrated = _legacy_principal_docs()

        memories_svc.search_memories_text(uid=UID, query="cooking")
        assert legacy_cohort.vector_calls == [
            {'uid': UID, 'query': "cooking", 'threshold': 0.0, 'limit': 5, 'subject_entity_id': None}
        ]

    def test_keyword_leg_failure_leaves_the_result_unchanged(self, legacy_cohort, monkeypatch):
        """Fail-open: a broken keyword leg degrades to exactly the old behaviour."""

        def _boom(*args, **kwargs):
            raise RuntimeError("keyword leg exploded")

        monkeypatch.setattr(keyword_leg.memory_db, "get_memories", _boom)
        monkeypatch.setattr(
            memories_svc,
            "keyword_search_legacy_memory_ids",
            keyword_leg.keyword_search_legacy_memory_ids,
        )
        legacy_cohort.vector_matches = [
            {'memory_id': 'mem-a', 'score': 0.95},
            {'memory_id': 'mem-b', 'score': 0.80},
        ]
        legacy_cohort.hydrated = _legacy_principal_docs()

        assert memories_svc.search_memories_text(uid=UID, query="cooking") == LEGACY_REFERENCE_OUTPUT

    def test_subjectless_memories_still_surface(self, legacy_cohort):
        legacy_cohort.vector_matches = [{'memory_id': 'mem-a', 'score': 0.95}]
        legacy_cohort.hydrated = _legacy_principal_docs()

        out = memories_svc.search_memories_text(uid=UID, query="cooking")
        assert "Likes pasta" in out

    def test_empty_result_message_unchanged(self, legacy_cohort):
        legacy_cohort.vector_matches = []
        legacy_cohort.keyword_ids = []
        assert memories_svc.search_memories_text(uid=UID, query="cooking") == "No memories found matching 'cooking'."


class TestProperNameRecall:
    """The point of the keyword leg: a name the embedding ranking never returns."""

    @pytest.fixture(autouse=True)
    def wiring(self, legacy_cohort, monkeypatch):
        # The vector leg returns only unrelated facts — this is the miss being fixed.
        legacy_cohort.vector_matches = [
            {'memory_id': 'mem-group-0', 'score': 0.31},
            {'memory_id': 'mem-misc-0', 'score': 0.29},
        ]
        legacy_cohort.hydrated = _corpus()
        monkeypatch.setattr(keyword_leg.memory_db, "get_memories", lambda *a, **k: _corpus())
        self.knobs = legacy_cohort
        self.monkeypatch = monkeypatch

    @staticmethod
    def _result_lines(out):
        """Only the rendered memories — the header echoes the query and would false-match."""
        return [line for line in out.splitlines() if line.startswith("- ")]

    def test_vector_only_ranking_misses_the_name(self):
        """Baseline: with the keyword leg disabled the fact is simply not there."""
        self.monkeypatch.setattr(memories_svc, "keyword_search_legacy_memory_ids", lambda *a, **k: [])
        out = memories_svc.search_memories_text(uid=UID, query="what do you know about Sophia")
        assert not any("Sophia" in line for line in self._result_lines(out))

    def test_keyword_leg_recovers_the_name_and_ranks_it_first(self):
        self.monkeypatch.setattr(
            memories_svc,
            "keyword_search_legacy_memory_ids",
            keyword_leg.keyword_search_legacy_memory_ids,
        )
        out = memories_svc.search_memories_text(uid=UID, query="what do you know about Sophia")

        lines = self._result_lines(out)
        assert any(
            "Sophia Nakamura" in line for line in lines
        ), "the keyword leg did not recover the fact the embedding missed"
        assert lines[0].startswith("- Sophia Nakamura"), f"exact-name match was not ranked first: {lines}"
        # An exact match must not be presented to the model as zero-relevance.
        assert "relevance: 1.00" in lines[0]

    def test_ordinary_query_keeps_the_vector_ordering(self):
        """A query whose only matching term is common must not be reordered."""
        self.monkeypatch.setattr(
            memories_svc,
            "keyword_search_legacy_memory_ids",
            keyword_leg.keyword_search_legacy_memory_ids,
        )
        out = memories_svc.search_memories_text(uid=UID, query="the running group")
        lines = self._result_lines(out)
        assert lines[0].startswith("- Belongs to the running group number 0")
        assert not any("Sophia" in line for line in lines)


class TestPersonScopedSearch:
    def test_only_that_persons_memories_are_returned(self, legacy_cohort):
        legacy_cohort.subject_docs = [_memory("mem-sophia", SOPHIA_FACT, subject=SUBJECT)]
        legacy_cohort.vector_matches = []
        legacy_cohort.hydrated = [
            _memory("mem-sophia", SOPHIA_FACT, subject=SUBJECT),
            _memory("mem-other", "Marcus — in your climbing group", subject=OTHER_SUBJECT),
            _memory("mem-none", "A subjectless legacy fact"),
        ]

        out = memories_svc.search_memories_text(uid=UID, query="who are they", limit=5, person_id=PERSON_UUID)
        assert "Sophia Nakamura" in out
        assert "Marcus" not in out
        assert "subjectless legacy fact" not in out

    def test_vector_leg_is_filtered_by_the_same_subject(self, legacy_cohort):
        legacy_cohort.subject_docs = []
        legacy_cohort.vector_matches = []
        memories_svc.search_memories_text(uid=UID, query="who are they", person_id=PERSON_UUID)
        assert legacy_cohort.vector_calls[0]['subject_entity_id'] == SUBJECT

    def test_person_id_is_never_a_name(self):
        assert memories_svc.resolve_subject_entity_id(PERSON_UUID) == SUBJECT
        assert memories_svc.resolve_subject_entity_id("  ") is None
        assert memories_svc.resolve_subject_entity_id(None) is None

    def test_blank_query_skips_the_vector_leg(self, legacy_cohort):
        legacy_cohort.subject_docs = [_memory("mem-sophia", SOPHIA_FACT, subject=SUBJECT)]
        legacy_cohort.hydrated = [_memory("mem-sophia", SOPHIA_FACT, subject=SUBJECT)]

        out = memories_svc.search_memories_text(uid=UID, query="", person_id=PERSON_UUID)
        assert legacy_cohort.vector_calls == []
        assert "Sophia Nakamura" in out

    def test_no_person_memories_reports_empty(self, legacy_cohort):
        legacy_cohort.subject_docs = []
        legacy_cohort.vector_matches = []
        out = memories_svc.search_memories_text(uid=UID, query="who", person_id=PERSON_UUID)
        assert out == "No memories found matching 'who'."

    def test_canonical_cohort_narrows_to_the_subject(self, monkeypatch):
        monkeypatch.setattr(memories_svc, "pin_memory_system", lambda *a, **k: MemorySystem.CANONICAL)
        monkeypatch.setattr(memories_svc.notification_db, "get_user_time_zone", lambda _uid: "UTC")
        mine = SimpleNamespace(
            content="Sophia Nakamura — in your group",
            created_at=CREATED,
            category=SimpleNamespace(value="interesting"),
            subject_entity_id=SUBJECT,
            tags=[],
        )
        theirs = SimpleNamespace(
            content="Marcus — in your climbing group",
            created_at=CREATED,
            category=SimpleNamespace(value="interesting"),
            subject_entity_id=OTHER_SUBJECT,
            tags=[],
        )
        matches = [SimpleNamespace(memory=mine, score=0.9), SimpleNamespace(memory=theirs, score=0.9)]
        monkeypatch.setattr(
            memories_svc, "MemoryService", lambda *a, **k: SimpleNamespace(search=lambda *sa, **sk: matches)
        )

        out = memories_svc.search_memories_text(uid=UID, query="who", person_id=PERSON_UUID)
        assert "Sophia Nakamura" in out
        assert "Marcus" not in out

    def test_memory_default_read_cohort_refuses_rather_than_answering_unscoped(self, monkeypatch):
        """A cohort we cannot scope must not silently answer a different question."""
        monkeypatch.setattr(memories_svc, "pin_memory_system", lambda *a, **k: MemorySystem.LEGACY)
        monkeypatch.setattr(memories_svc.notification_db, "get_user_time_zone", lambda _uid: "UTC")
        monkeypatch.setattr(
            memories_svc,
            "search_memory_default_chat_memories_vector_decision_text",
            lambda **kwargs: SimpleNamespace(
                read_decision=MemoryReadDecision.USE_MEMORY,
                text="Found 3 memories about everything",
                fallback_reason=None,
            ),
        )
        out = memories_svc.search_memories_text(uid=UID, query="who", person_id=PERSON_UUID)
        assert out == "Person-scoped memory search is not available for this account yet."
        # The same cohort without a person filter is untouched.
        assert memories_svc.search_memories_text(uid=UID, query="who") == "Found 3 memories about everything"


# ===========================================================================
# GET /v3/memories/by-person/{person_id} — the structured read the desktop uses
# ===========================================================================
class TestByPersonEndpoint:
    @staticmethod
    def _body(response):
        return json.loads(response.body)

    def test_reads_by_subject_entity_id(self, monkeypatch):
        seen = {}

        def _by_subject(uid, subject_entity_id, **kwargs):
            seen['args'] = (uid, subject_entity_id, kwargs.get('limit'))
            return [_memory("mem-1", SOPHIA_FACT, subject=SUBJECT)]

        monkeypatch.setattr(memories_router.memories_db, "get_memories_by_subject", _by_subject)
        response = memories_router.get_memories_by_person(person_id=PERSON_UUID, limit=25, uid=UID)

        assert seen['args'] == (UID, SUBJECT, 25)
        body = self._body(response)
        assert [item['id'] for item in body] == ["mem-1"]
        assert body[0]['content'] == SOPHIA_FACT

    def test_tags_survive_the_response_contract(self, monkeypatch):
        """The desktop matches on the durable ``person:`` tag, so it has to be served."""
        monkeypatch.setattr(
            memories_router.memories_db,
            "get_memories_by_subject",
            lambda *a, **k: [_memory("mem-1", SOPHIA_FACT, tags=["people_intelligence", SUBJECT])],
        )
        body = self._body(memories_router.get_memories_by_person(person_id=PERSON_UUID, uid=UID))
        assert body[0]['tags'] == ["people_intelligence", SUBJECT]

    def test_locked_content_is_truncated_not_served(self, monkeypatch):
        long_content = "x" * 200
        monkeypatch.setattr(
            memories_router.memories_db,
            "get_memories_by_subject",
            lambda *a, **k: [_memory("mem-locked", long_content, subject=SUBJECT, is_locked=True)],
        )
        body = self._body(memories_router.get_memories_by_person(person_id=PERSON_UUID, uid=UID))
        assert body[0]['content'] == "x" * 70 + "..."

    def test_malformed_document_is_skipped_not_fatal(self, monkeypatch):
        broken = {'id': 'mem-broken'}  # no uid/content/created_at — cannot validate
        monkeypatch.setattr(
            memories_router.memories_db,
            "get_memories_by_subject",
            lambda *a, **k: [broken, _memory("mem-ok", "Still readable", subject=SUBJECT)],
        )
        body = self._body(memories_router.get_memories_by_person(person_id=PERSON_UUID, uid=UID))
        assert [item['id'] for item in body] == ["mem-ok"]

    def test_no_person_memories_is_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(memories_router.memories_db, "get_memories_by_subject", lambda *a, **k: [])
        assert self._body(memories_router.get_memories_by_person(person_id=PERSON_UUID, uid=UID)) == []
