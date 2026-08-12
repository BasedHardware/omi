"""set_canonical_memory_kg_extracted must catch the neutral store NotFound (not the Firestore-only
google.api_core NotFound) so a concurrently-deleted memory returns False instead of escaping as an
unhandled error (cubic review PR 10887, backend/utils/memory/canonical_kg_promotion.py)."""

from database import document_store
from tests.store_fakes import FakeDocumentStore
from utils.memory import canonical_kg_promotion as promo


def test_returns_false_when_memory_document_is_missing(monkeypatch):
    store = FakeDocumentStore()  # empty: the memory doc does not exist
    monkeypatch.setattr(document_store, '_store', lambda: store)

    # update() on a missing path raises the neutral NotFound; the helper must swallow it -> False.
    assert promo.set_canonical_memory_kg_extracted('u1', 'mem-missing') is False
    assert promo.set_canonical_memory_kg_extracted_without_touching_updated_at('u1', 'mem-missing') is False
