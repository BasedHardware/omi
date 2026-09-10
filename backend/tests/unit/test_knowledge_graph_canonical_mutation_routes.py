"""Graph mutation routes must gate on real per-account canonical state.

Rebuild is the exception since the Brain Map redesign: it replaces only the
shared (rebuilt) store and never touches canonical assertions, and the read
merges the two with canonical winning, so it is open to every account and
consults no canonical probe at all. ``DELETE`` still destroys the shared store
an assertion-backed account may be citing, so it keeps the gate below.

`165c041a93` gated rebuild/delete on a per-account predicate: canonical state
established, or stored memory-graph assertions. `5724a10084` replaced that body
with an unconditional `return True`, so every account got

    409 Canonical knowledge graph state is derived from canonical memories and
    cannot be deleted or rebuilt directly.

including accounts with no `memory_state/head` at all — canonical intake is
fenced in production, and the convergence shipped no backfill, so there was no
derived state to protect. Mobile rendered the 409 body straight to the screen.
`fbb005c15b` restored the GET fallback; this suite covers the mutation side.

The gate is tri-state on purpose. `GET` may fail open on any unavailable
canonical read; these routes delete the legacy store, so only a positive
"there is no state head" answer may unlock them. Every other unavailable
reason — a timed-out head read above all — must leave the graph alone.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg
from utils.memory.v3.account_generation_source import (
    V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
    V3AccountGenerationFailureReason as Reason,
    V3TrustedAccountGenerationResult as TrustedHead,
)
from utils.other import endpoints as auth

UID = "uid-arbitrary-account"
HEAD_PATH = f"users/{UID}/memory_state/head"

# Every way the trusted head read can fail other than "the document is absent".
# None of these establishes that the account has no canonical state.
INDETERMINATE_REASONS = [
    Reason.READ_FAILED,
    Reason.MALFORMED_STATE_HEAD,
    Reason.UNSUPPORTED_SCHEMA,
    Reason.UID_MISMATCH,
    Reason.SOURCE_MISMATCH,
    Reason.MALFORMED_ACCOUNT_GENERATION,
]


def _established_head() -> TrustedHead:
    """A well-formed state head: canonical apply has committed for this account."""
    return TrustedHead(
        uid=UID,
        source_path=HEAD_PATH,
        account_generation=3,
        head_commit_id="commit-9",
        commit_sequence=7,
        source=V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
        schema_version=V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    )


def _failed_head(reason: Reason) -> TrustedHead:
    return TrustedHead(uid=UID, source_path=HEAD_PATH, read_error_reason=reason)


def _head(monkeypatch, result: TrustedHead) -> None:
    """Stub the one trusted head read the gate's probe performs."""
    monkeypatch.setattr(kg, "read_memory_v3_trusted_account_generation", lambda **_kw: result)


@pytest.fixture(autouse=True)
def _no_firestore(monkeypatch):
    # The probe resolves a client before reading; never build a real one here.
    monkeypatch.setattr(kg, "get_firestore_client", lambda: object())
    monkeypatch.setattr(kg_router, "get_firestore_client", lambda: object())


@pytest.fixture
def client(monkeypatch):
    # Rate limiting is not under test here and its counters leak across cases.
    monkeypatch.setattr(auth, "_enforce_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.fixture
def deleted(monkeypatch):
    """Record legacy graph deletions and keep them out of Firestore."""
    calls: List[str] = []
    monkeypatch.setattr(kg_db, "delete_knowledge_graph", lambda uid, **_kw: calls.append(uid))
    monkeypatch.setattr(kg_router, "get_user_name", lambda uid: "Ada")
    return calls


@pytest.fixture
def fallbacks(monkeypatch):
    """Record shared fallback telemetry emitted by the fail-open branch."""
    calls: List[Dict[str, Any]] = []
    monkeypatch.setattr(kg_router, "record_fallback", lambda **kwargs: calls.append(kwargs))
    return calls


def _legacy_principal(monkeypatch) -> None:
    """No memory_state/head, no assertions — the unmigrated majority."""
    _head(monkeypatch, _failed_head(Reason.MISSING_STATE_HEAD))
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)


def test_legacy_principal_can_rebuild(client, monkeypatch, deleted, fallbacks):
    _legacy_principal(monkeypatch)
    scheduled: List[Any] = []
    # TestClient runs background tasks inline; the task itself has its own tests.
    monkeypatch.setattr(
        kg_router, "_rebuild_graph_task", lambda uid, user_name, rebuild_id=None: scheduled.append((uid, user_name))
    )

    response = client.post("/v1/knowledge-graph/rebuild")

    assert response.status_code == 200
    assert response.json()["status"] == "rebuilding"
    # The route names the rebuild it started so a client can wait for that one.
    assert len(response.json()["rebuild_id"]) == 32
    # The route hands the delete to the rebuild itself; see the regression tests below.
    assert deleted == []
    assert scheduled == [(UID, "Ada")]


def test_the_rebuild_task_stamps_its_id_and_never_overwrites_a_later_rebuilds_status(monkeypatch):
    # Two rebuilds can run at once. The earlier one finishing must not turn the
    # later one's `running` into `complete`, or a client waiting on the later
    # one would load a graph that is still being replaced.
    writes: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}

    def write_status(uid, status, *, db_client=None, only_for_rebuild_id=None):
        if only_for_rebuild_id and current.get("rebuild_id") not in (None, only_for_rebuild_id):
            return False
        current.clear()
        current.update(status)
        writes.append(dict(status))
        return True

    monkeypatch.setattr(kg_db, "write_knowledge_graph_rebuild_status", write_status)
    monkeypatch.setattr(kg_router, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        kg_router, "collect_brain_map_sources", lambda uid, **_kw: SimpleNamespace(payloads=[], counts={})
    )
    monkeypatch.setattr(
        kg_router, "_run_rebuild_knowledge_graph", lambda uid, payloads, user_name: {"nodes": [], "edges": []}
    )

    kg_router._rebuild_graph_task(UID, "Ada", "first")
    assert [(w["status"], w["rebuild_id"]) for w in writes] == [("running", "first"), ("complete", "first")]

    # A later rebuild is running when the first one's task reports again.
    current.clear()
    current.update({"status": "running", "rebuild_id": "second"})
    writes.clear()
    kg_router._rebuild_graph_task(UID, "Ada", "first")
    assert writes == []
    assert current == {"status": "running", "rebuild_id": "second"}


class _StatusDocumentStore:
    """The single rebuild-status document as the production fence navigates it."""

    def __init__(self) -> None:
        self.payload: Dict[str, Any] = {}

    def collection(self, _name: str) -> "_StatusDocumentStore":
        return self

    def document(self, _name: str) -> "_StatusDocumentStore":
        return self

    def get(self) -> Any:
        store = self

        class _Snapshot:
            exists = bool(store.payload)

            @staticmethod
            def to_dict() -> Dict[str, Any]:
                return dict(store.payload)

        return _Snapshot()

    def set(self, data: Dict[str, Any]) -> None:
        self.payload = dict(data)


def _fenced_rebuild_task(monkeypatch) -> _StatusDocumentStore:
    """The rebuild task wired to the production fence over an in-memory document."""
    store = _StatusDocumentStore()
    monkeypatch.setattr(kg_router, "get_firestore_client", lambda: store)
    monkeypatch.setattr(
        kg_router, "collect_brain_map_sources", lambda uid, **_kw: SimpleNamespace(payloads=[], counts={})
    )
    monkeypatch.setattr(
        kg_router, "_run_rebuild_knowledge_graph", lambda uid, payloads, user_name: {"nodes": [], "edges": []}
    )
    return store


def test_a_second_rebuild_reports_its_own_completion_after_the_first_finished(monkeypatch):
    # The first rebuild completed and its id owns the status document. The next
    # rebuild must take the document over when it starts: a client waits for the
    # id of the rebuild *it* started, so a rebuild that cannot claim the
    # document reports failure to its client no matter how well it ran.
    store = _fenced_rebuild_task(monkeypatch)

    kg_router._rebuild_graph_task(UID, "Ada", "first")
    assert store.payload["status"] == "complete"
    assert store.payload["rebuild_id"] == "first"

    kg_router._rebuild_graph_task(UID, "Ada", "second")
    assert store.payload["status"] == "complete"
    assert store.payload["rebuild_id"] == "second"


def test_a_new_rebuild_claims_the_status_document_and_finishes_are_fenced(monkeypatch):
    # The production fence: a rebuild starting always claims the document —
    # whatever is there is from an earlier rebuild, and a rebuild wedged in
    # `running` by a crash must not lock every later rebuild out of reporting.
    # A finish only lands while the document still belongs to that rebuild, so
    # an earlier rebuild finishing cannot turn a later one's `running` into its
    # own `complete`.
    store = _StatusDocumentStore()

    def write(status: str, rebuild_id: str) -> bool:
        return kg_db.write_knowledge_graph_rebuild_status(
            UID, {"status": status, "rebuild_id": rebuild_id}, db_client=store, only_for_rebuild_id=rebuild_id
        )

    assert write("running", "first")
    assert store.payload["rebuild_id"] == "first"

    # A later rebuild starts while the first is still running: it takes over.
    assert write("running", "second")
    assert store.payload["rebuild_id"] == "second"

    # The earlier rebuild finishing must not overwrite the later one's running.
    assert not write("complete", "first")
    assert store.payload["status"] == "running"
    assert store.payload["rebuild_id"] == "second"

    # The later rebuild finishing lands.
    assert write("complete", "second")
    assert store.payload["status"] == "complete"
    assert store.payload["rebuild_id"] == "second"


def test_a_new_rebuild_claims_the_status_document_even_when_it_says_complete(monkeypatch):
    # The sequential case: the document holds a finished rebuild. The next
    # rebuild's claim must still land — that document describes a rebuild that
    # is over, not one a client is still waiting on.
    store = _StatusDocumentStore()
    assert kg_db.write_knowledge_graph_rebuild_status(
        UID, {"status": "complete", "rebuild_id": "first"}, db_client=store, only_for_rebuild_id="first"
    )

    assert kg_db.write_knowledge_graph_rebuild_status(
        UID, {"status": "running", "rebuild_id": "second"}, db_client=store, only_for_rebuild_id="second"
    )
    assert store.payload["status"] == "running"
    assert store.payload["rebuild_id"] == "second"


def test_a_status_store_failure_neither_fails_the_rebuild_nor_the_graph_read(client, monkeypatch, fallbacks):
    # The status document is how a client waits; it is never a reason to lose
    # the rebuild that already ran, nor to fail a read of the graph itself.
    def broken(*_args, **_kwargs):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(kg_db, "write_knowledge_graph_rebuild_status", broken)
    monkeypatch.setattr(kg_db, "read_knowledge_graph_rebuild_status", broken)
    monkeypatch.setattr(kg_router, "get_firestore_client", lambda: object())
    ran: List[str] = []
    monkeypatch.setattr(
        kg_router, "collect_brain_map_sources", lambda uid, **_kw: SimpleNamespace(payloads=[], counts={})
    )
    monkeypatch.setattr(
        kg_router,
        "_run_rebuild_knowledge_graph",
        lambda uid, payloads, user_name: ran.append(uid) or {"nodes": [], "edges": []},
    )
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)
    monkeypatch.setattr(kg_db, "get_knowledge_graph", lambda uid, **_kw: {"nodes": [], "edges": []})
    monkeypatch.setattr(
        kg_router.canonical_graph_service,
        "get_canonical_knowledge_graph",
        broken,
    )

    kg_router._rebuild_graph_task(UID, "Ada", "only")
    assert ran == [UID]
    assert kg_router._rebuild_status_payload(UID) is None


def test_rebuild_does_not_delete_the_graph_before_the_rebuild_runs(client, monkeypatch, deleted, fallbacks):
    # The route used to delete the graph and only then schedule the rebuild, so any
    # background task that never ran — process restart, pod eviction — left the user
    # with no graph at all behind a 200 that said "rebuilding".
    _legacy_principal(monkeypatch)

    # Stands in for a task that is scheduled and then never executes.
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name, rebuild_id=None: None)

    response = client.post("/v1/knowledge-graph/rebuild")

    assert response.status_code == 200
    assert deleted == []


def test_the_legacy_rebuild_still_clears_the_graph_itself(monkeypatch):
    # The route relies on this: dropping its eager delete is only safe while
    # `rebuild_knowledge_graph` clears the old graph itself, so a rebuild cannot
    # merge new extractions into stale nodes. The clear now runs at the end of the
    # rebuild rather than the start (#11923), but it still runs.
    llm_kg = kg_router._knowledge_graph_llm_module()
    calls: List[str] = []
    monkeypatch.setattr(kg_db, "delete_knowledge_graph", lambda uid, **_kw: calls.append(uid))
    monkeypatch.setattr(kg_db, "get_knowledge_graph", lambda uid, **_kw: {"nodes": [], "edges": []})

    llm_kg.rebuild_knowledge_graph(UID, [], "Ada", db_client=object())

    assert calls == [UID]


def test_legacy_principal_can_delete(client, monkeypatch, deleted, fallbacks):
    _legacy_principal(monkeypatch)

    response = client.delete("/v1/knowledge-graph")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert deleted == [UID]


def test_the_legacy_fail_open_reports_shared_fallback_telemetry(client, monkeypatch, deleted, fallbacks):
    # AGENTS.md: a fail-open branch calls the shared record_fallback helper.
    # Silent UX healing is fine; a silently degraded mutation path is not.
    _legacy_principal(monkeypatch)

    assert client.delete("/v1/knowledge-graph").status_code == 200

    assert len(fallbacks) == 1
    assert fallbacks[0]["component"] == "knowledge_graph"
    assert fallbacks[0]["from_mode"] == "canonical_graph"
    assert fallbacks[0]["to_mode"] == "legacy_graph"
    assert fallbacks[0]["outcome"] == "degraded"


def test_a_conflicting_account_reports_no_fallback(client, monkeypatch, deleted, fallbacks):
    # The conflict is a hard refusal, not a degraded path; it must not inflate
    # the fallback counter that measures how many accounts still run on legacy.
    _head(monkeypatch, _established_head())

    assert client.delete("/v1/knowledge-graph").status_code == 409

    assert fallbacks == []


def test_an_established_head_with_zero_assertions_still_conflicts(client, monkeypatch, deleted, fallbacks):
    # The state head is the "canonical state established" signal, not whether a
    # materialized page happens to carry assertions. An account mid-migration
    # can have a committed head and zero graph assertions; its graph is still
    # derived state, and rebuild/delete must not touch it.
    _head(monkeypatch, _established_head())

    def _must_not_be_consulted(*_args: Any, **_kwargs: Any) -> bool:  # pragma: no cover - asserts absence
        raise AssertionError("an established head must decide the gate on its own")

    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", _must_not_be_consulted)

    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name, rebuild_id=None: None)

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    # Rebuild only replaces the shared store and merges under the assertions,
    # so an established head is not a reason to refuse it.
    assert rebuild.status_code == 200
    assert delete.status_code == 409
    assert delete.json()["detail"] == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert deleted == []


@pytest.mark.parametrize("reason", INDETERMINATE_REASONS, ids=lambda reason: reason.value)
def test_an_unanswered_canonical_probe_must_not_delete_the_legacy_graph(
    client, monkeypatch, deleted, fallbacks, reason
):
    # A head read that timed out, or a head we cannot parse, does not establish
    # that the account has no canonical state. Treating it as "unestablished"
    # turns a transient Firestore blip into permanent loss of the legacy graph.
    _head(monkeypatch, _failed_head(reason))
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)
    scheduled: List[Any] = []
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name, rebuild_id=None: scheduled.append(uid))

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert deleted == []
    # The rebuild never reads the probe: it cannot harm canonical state.
    assert scheduled == [UID]
    assert rebuild.status_code == 200
    assert delete.status_code == 503
    assert delete.json()["detail"] == kg_router.CANONICAL_GRAPH_STATE_UNVERIFIED


def test_a_malformed_head_without_a_read_error_must_not_delete_the_legacy_graph(
    client, monkeypatch, deleted, fallbacks
):
    # A head that reads cleanly but carries no commit sequence is not a usable
    # revision fence, and it is not evidence of an unprovisioned account either.
    _head(
        monkeypatch,
        TrustedHead(
            uid=UID,
            source_path=HEAD_PATH,
            account_generation=3,
            head_commit_id="commit-9",
            commit_sequence=None,
        ),
    )
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)

    delete = client.delete("/v1/knowledge-graph")

    assert delete.status_code == 503
    assert deleted == []


def test_stored_assertions_still_conflict_without_a_state_head(client, monkeypatch, deleted, fallbacks):
    # Assertion-backed graphs are derived state even when no state head exists;
    # they must not be rebuilt or deleted through here.
    _head(monkeypatch, _failed_head(Reason.MISSING_STATE_HEAD))
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: True)
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name, rebuild_id=None: None)

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert rebuild.status_code == 200
    assert delete.status_code == 409
    assert deleted == []


def test_the_decision_is_per_account_not_a_constant(monkeypatch):
    _head(monkeypatch, _failed_head(Reason.MISSING_STATE_HEAD))
    monkeypatch.setattr(
        kg_db,
        "has_stored_memory_graph_assertions",
        lambda uid, **_kw: uid == "uid-assertion-backed",
    )

    assert kg_router._legacy_graph_mutation_decision("uid-assertion-backed") is kg_router.LegacyGraphMutation.CONFLICT
    assert kg_router._legacy_graph_mutation_decision("uid-arbitrary-account") is kg_router.LegacyGraphMutation.ALLOWED


class _StatusStore:
    """Records rebuild status writes in order."""

    def __init__(self) -> None:
        self.writes: List[Dict[str, Any]] = []

    def write(
        self, uid: str, status: Dict[str, Any], *, db_client: Any = None, only_for_rebuild_id: Any = None
    ) -> bool:
        assert uid == UID
        assert status["rebuild_id"] == only_for_rebuild_id, "every write is fenced to the rebuild that makes it"
        self.writes.append(dict(status))
        return True


@pytest.fixture
def status_store(monkeypatch) -> _StatusStore:
    store = _StatusStore()
    monkeypatch.setattr(kg_db, "write_knowledge_graph_rebuild_status", store.write)
    return store


def test_rebuild_task_feeds_every_source_to_the_extractor_and_records_completion(monkeypatch, status_store):
    from utils.memory.brain_map_sources import BrainMapSources

    payloads = [{"id": "m1", "content": "one"}, {"id": "conversation:c1", "content": "Conversation: Standup"}]
    counts = {"memories": 1, "conversations": 1, "people": 0, "goals": 0}
    monkeypatch.setattr(
        kg_router,
        "collect_brain_map_sources",
        lambda uid, **_kw: BrainMapSources(payloads=payloads, counts=counts),
    )
    captured: Dict[str, Any] = {}

    def _run(uid: str, memories: List[Dict[str, Any]], user_name: str) -> Dict[str, Any]:
        captured.update(uid=uid, memories=memories, user_name=user_name)
        return {"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [{"id": "e1"}]}

    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _run)

    kg_router._rebuild_graph_task(UID, "Ada")

    assert captured["memories"] == payloads
    assert captured["user_name"] == "Ada"
    assert [write["status"] for write in status_store.writes] == ["running", "complete"]
    done = status_store.writes[-1]
    assert done["nodes_count"] == 2 and done["edges_count"] == 1
    assert done["sources"] == counts
    assert done["finished_at"] >= done["started_at"]


def test_rebuild_task_records_failure_instead_of_leaving_the_status_running(monkeypatch, status_store):
    def _explode(uid: str, **_kw: Any):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(kg_router, "collect_brain_map_sources", _explode)

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("extraction ran without sources")

    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _must_not_run)

    kg_router._rebuild_graph_task(UID, "Ada")

    assert [write["status"] for write in status_store.writes] == ["running", "failed"]


def test_rebuild_task_never_touches_canonical_state(monkeypatch, status_store):
    # The task must not read the canonical probe or delete assertions: it is
    # allowed for assertion-backed accounts precisely because it cannot.
    def _must_not_probe(**_kw: Any):  # pragma: no cover - asserts absence
        raise AssertionError("rebuild consulted the canonical state head")

    monkeypatch.setattr(kg, "read_memory_v3_trusted_account_generation", _must_not_probe)
    monkeypatch.setattr(kg_db, "delete_memory_graph_assertion", _must_not_probe)
    from utils.memory.brain_map_sources import BrainMapSources

    monkeypatch.setattr(
        kg_router,
        "collect_brain_map_sources",
        lambda uid, **_kw: BrainMapSources(payloads=[], counts={}),
    )
    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", lambda *_a, **_k: {"nodes": [], "edges": []})

    kg_router._rebuild_graph_task(UID, "Ada")

    assert status_store.writes[-1]["status"] == "complete"
