"""Screen-activity vector deletes must respect Pinecone's per-delete id limit.

Prod, 2026-08-30/31 (`backend-sync`): every account-deletion wipe for one uid
failed with

    delete_account purge screen activity vectors failed for <uid>: (400)
    required derived purge failed: screen_activity_vectors

``delete_screen_activity_vectors`` passed every screenshot id in a single
``index.delete`` call. Pinecone rejects more than 1,000 ids with a 400, and this
purge is a *required* one, so the wipe aborted before the Firestore delete, the
record was marked failed, and it retried on that same 400 indefinitely. Any
account with more than 1,000 screenshots could not be deleted at all.

Every sibling batch delete in this module already chunks at 1,000.
"""

from unittest.mock import MagicMock

import pytest

from database import vector_db


@pytest.fixture
def index(monkeypatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(vector_db, 'index', fake)
    return fake


def test_delete_stays_within_the_thousand_id_limit(index: MagicMock) -> None:
    vector_db.delete_screen_activity_vectors('user-1', [f'sa-{n}' for n in range(2500)])

    assert index.delete.call_count == 3
    sizes = [len(call.kwargs['ids']) for call in index.delete.call_args_list]
    assert sizes == [1000, 1000, 500]
    assert all(call.kwargs['namespace'] == vector_db.SCREEN_ACTIVITY_NAMESPACE for call in index.delete.call_args_list)


def test_every_id_is_deleted_exactly_once(index: MagicMock) -> None:
    vector_db.delete_screen_activity_vectors('user-1', [f'sa-{n}' for n in range(1001)])

    deleted = [vector_id for call in index.delete.call_args_list for vector_id in call.kwargs['ids']]
    assert deleted == [f'user-1-sa-sa-{n}' for n in range(1001)]


def test_a_small_delete_still_makes_one_call(index: MagicMock) -> None:
    vector_db.delete_screen_activity_vectors('user-1', ['sa-1', 'sa-2'])

    index.delete.assert_called_once_with(
        ids=['user-1-sa-sa-1', 'user-1-sa-sa-2'], namespace=vector_db.SCREEN_ACTIVITY_NAMESPACE
    )


def test_no_ids_issues_no_call(index: MagicMock) -> None:
    vector_db.delete_screen_activity_vectors('user-1', [])

    index.delete.assert_not_called()
