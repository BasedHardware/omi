"""Universal graph routes preserve assertion-backed derived-state ownership."""

from fastapi import BackgroundTasks, HTTPException
import pytest

from routers import knowledge_graph as kg_router


@pytest.mark.parametrize("uid", ["uid-former-cohort", "uid-arbitrary-account"])
def test_graph_mutations_conflict_for_every_account_without_projection_mutation(uid):
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as delete_error:
        kg_router.delete_knowledge_graph(uid=uid)
    with pytest.raises(HTTPException) as rebuild_error:
        kg_router.rebuild_graph(background_tasks=background_tasks, uid=uid)

    assert delete_error.value.status_code == 409
    assert rebuild_error.value.status_code == 409
    assert delete_error.value.detail == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert rebuild_error.value.detail == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert background_tasks.tasks == []


def test_all_accounts_use_assertion_backed_graph_semantics():
    assert kg_router._is_assertion_backed_graph_account("uid-former-cohort") is True
    assert kg_router._is_assertion_backed_graph_account("uid-arbitrary-account") is True
