"""set_canonical_memory_kg_extracted must return False (not escape as an unhandled error) when the
memory document was concurrently deleted. On the Mongo-backed db_client facade an ``update`` on a
missing doc raises the neutral store NotFound; the facade re-raises it as google's NotFound so the
helper's ``except FirestoreNotFound`` catches it identically to real Firestore (ADR-0044; cubic
review PR 10887, backend/utils/memory/canonical_kg_promotion.py)."""

from database.store.firestore_facade import NeutralFirestoreClient
from tests.store_fakes import FakeDocumentStore
from utils.memory import canonical_kg_promotion as promo


def test_returns_false_when_memory_document_is_missing():
    db_client = NeutralFirestoreClient(FakeDocumentStore())  # empty: the memory doc does not exist

    # update() on a missing path raises the neutral NotFound, which the facade re-raises as google
    # NotFound; the helper must swallow it and report a no-op rather than crash.
    assert promo.set_canonical_memory_kg_extracted('u1', 'mem-missing', db_client=db_client) is False
    assert (
        promo.set_canonical_memory_kg_extracted_without_touching_updated_at('u1', 'mem-missing', db_client=db_client)
        is False
    )
