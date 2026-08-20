"""Graph mutation routes must gate on real per-account canonical state.

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
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name: scheduled.append((uid, user_name)))

    response = client.post("/v1/knowledge-graph/rebuild")

    assert response.status_code == 200
    assert response.json()["status"] == "rebuilding"
    # The route hands the delete to the rebuild itself; see the regression tests below.
    assert deleted == []
    assert scheduled == [(UID, "Ada")]


def test_rebuild_does_not_delete_the_graph_before_the_rebuild_runs(client, monkeypatch, deleted, fallbacks):
    # The route used to delete the graph and only then schedule the rebuild, so any
    # background task that never ran — process restart, pod eviction — left the user
    # with no graph at all behind a 200 that said "rebuilding".
    _legacy_principal(monkeypatch)

    # Stands in for a task that is scheduled and then never executes.
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name: None)

    response = client.post("/v1/knowledge-graph/rebuild")

    assert response.status_code == 200
    assert deleted == []


def test_a_regate_that_flips_after_the_response_leaves_the_graph_intact(client, monkeypatch, deleted, fallbacks):
    # The task re-checks the gate after the response is returned. An account that
    # becomes assertion-backed in that window no-ops the rebuild — which used to mean
    # the legacy graph stayed deleted, with nothing left to own it.
    _head(monkeypatch, _failed_head(Reason.MISSING_STATE_HEAD))
    answers = iter([False, True])  # route says legacy, the task's re-check says assertion-backed
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: next(answers))

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("legacy rebuild ran for an account that became assertion-backed")

    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _must_not_run)

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

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert rebuild.status_code == 409
    assert delete.status_code == 409
    assert rebuild.json()["detail"] == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
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
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name: scheduled.append(uid))

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert deleted == []
    assert scheduled == []
    assert rebuild.status_code == 503
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

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert rebuild.status_code == 409
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


def test_rebuild_task_feeds_unlocked_memories_to_the_legacy_rebuild(monkeypatch):
    _legacy_principal(monkeypatch)

    class _Memory:
        def __init__(self, memory_id: str, content: str, is_locked: bool = False):
            self.id = memory_id
            self.content = content
            self.is_locked = is_locked

    class _Service:
        def __init__(self, **_kwargs: Any):
            pass

        def read(self, uid: str, **_kwargs: Any):
            return [_Memory("m1", "one"), _Memory("m2", "locked", is_locked=True)]

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(kg_router, "MemoryService", _Service)
    monkeypatch.setattr(
        kg_router,
        "_run_rebuild_knowledge_graph",
        lambda uid, memories, user_name: captured.update(uid=uid, memories=memories, user_name=user_name),
    )

    kg_router._rebuild_graph_task(UID, "Ada")

    assert captured["memories"] == [{"id": "m1", "content": "one"}]
    assert captured["user_name"] == "Ada"


def test_rebuild_task_is_a_noop_for_an_assertion_backed_account(monkeypatch):
    _head(monkeypatch, _failed_head(Reason.MISSING_STATE_HEAD))
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: True)

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("legacy rebuild ran for an assertion-backed account")

    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _must_not_run)

    kg_router._rebuild_graph_task(UID, "Ada")


def test_rebuild_task_is_a_noop_when_the_canonical_probe_is_unanswered(monkeypatch):
    # The task re-runs the decision after the route already deleted the graph.
    # An unanswered probe must stop it there rather than rebuild blindly.
    _head(monkeypatch, _failed_head(Reason.READ_FAILED))
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)

    class _Service:
        def __init__(self, **_kwargs: Any):
            pass

        def read(self, uid: str, **_kwargs: Any):
            return []

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("legacy rebuild ran while canonical state was unverified")

    monkeypatch.setattr(kg_router, "MemoryService", _Service)
    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _must_not_run)

    kg_router._rebuild_graph_task(UID, "Ada")
