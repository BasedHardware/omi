"""update_advice must return None (404) when the advice is deleted mid-update, not crash with a 500.

PATCH /v1/advice/{advice_id} -> update_advice must tolerate the advice vanishing concurrently. The
original bug surfaced two Firestore-specific races (update() raising NotFound; a re-read returning
None). On the neutral storage port these collapse into one contract: the existence gate and the
write share a transaction, so a missing advice yields None (404) and is never resurrected, while a
present advice is patched and returned with its id. Exercised through the real _store() seam via
FakeDocumentStore.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest  # noqa: E402

import database.advice as advice  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(advice, "_store", lambda: fake)
    return fake


def test_missing_advice_returns_none(store):
    # No advice document seeded: the update must return None (404) and must not create one.
    assert advice.update_advice("u", "adv1", is_read=True) is None
    assert not store.exists("users/u/advice/adv1")  # never resurrected


def test_missing_advice_dismiss_returns_none(store):
    # Same guard on the dismiss path — a vanished advice yields None, not a crash or a zombie doc.
    assert advice.update_advice("u", "adv1", is_dismissed=True) is None
    assert not store.exists("users/u/advice/adv1")


def test_happy_path_returns_dict_with_id(store):
    store.set("users/u/advice/adv1", {"id": "adv1", "content": "hi", "is_read": False})

    result = advice.update_advice("u", "adv1", is_read=True)

    assert result["id"] == "adv1"
    assert result["content"] == "hi"
    assert result["is_read"] is True
    assert "updated_at" in result
    # The stored document reflects the patch.
    assert store.get("users/u/advice/adv1").to_dict()["is_read"] is True
