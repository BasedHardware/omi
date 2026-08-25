"""Two E2E fakes that had drifted from the contracts they stand in for.

A fake that is more permissive than the real thing does not merely miss a bug — it makes the assertions
written against it *lie*. Both of these were found by a port audit, and both confirmed by reading the
code before touching it.

L9  testing/e2e/fakes/vector_search.py hand-rolled its own filter matcher instead of using
    utils/vector/filters.matches(), the canonical in-memory interpreter its unit-test sibling
    (tests/vector_store_fakes.py) already uses. The copy drifted three ways, and one of them is
    load-bearing: an operator it did not know fell through to `return True`, so
    `{'memory_schema_version': {'$exists': False}}` — the ns2 legacy barrier — matched EVERYTHING in
    every retrieval E2E.

L8  testing/e2e/fakes/storage.py replaces google.cloud.storage.Client, i.e. it sits BELOW the object
    store adapter, but raised FileNotFoundError. The GCS adapter only translates
    google.api_core.exceptions.NotFound, so in E2E a missing object never became ObjectNotFound and the
    six `except ObjectNotFound` handlers in utils/other/storage.py were unreachable. Its own twin
    (testing/sync_cloud_tasks_stack/storage.py) already raises the SDK error.
"""

from __future__ import annotations

import pytest

# --- L9: the vector fake must interpret the neutral filter contract, not its own dialect ---------


@pytest.fixture
def vector_fake():
    from testing.e2e.fakes.vector_search import DeterministicEmbeddings, FakeVectorStore

    embeddings = DeterministicEmbeddings()
    store = FakeVectorStore(embeddings)
    # The fake scores on the text the vector carries (DeterministicVector), so build the values the way
    # production does — through the embeddings — rather than passing a bare list that scores 0.
    store.upsert(
        "ns2",
        [
            {"id": "legacy", "values": embeddings.embed_query("coffee"), "metadata": {"uid": "u1"}},
            {
                "id": "canonical",
                "values": embeddings.embed_query("coffee"),
                "metadata": {"uid": "u1", "memory_schema_version": 1},
            },
        ],
    )
    return store


def _ids(hits):
    return sorted(hit["id"] for hit in hits)


def _Q():
    """A query vector carrying its text, exactly as database.vector_db builds one."""
    from testing.e2e.fakes.vector_search import DeterministicEmbeddings

    return DeterministicEmbeddings().embed_query("coffee")


def test_exists_false_is_the_legacy_barrier_not_a_no_op(vector_fake):
    """The defect: an unknown operator fell through to `return True`, so this matched everything and
    every retrieval E2E asserting the ns2 legacy barrier proved nothing."""
    hits = vector_fake.query("ns2", _Q(), top_k=10, filter={"memory_schema_version": {"$exists": False}})
    assert _ids(hits) == ["legacy"]


def test_exists_true_is_its_mirror(vector_fake):
    hits = vector_fake.query("ns2", _Q(), top_k=10, filter={"memory_schema_version": {"$exists": True}})
    assert _ids(hits) == ["canonical"]


def test_a_clause_next_to_and_is_not_discarded(vector_fake):
    """`return all(...)` on the $and key ended the loop, so sibling keys were never evaluated."""
    hits = vector_fake.query(
        "ns2",
        _Q(),
        top_k=10,
        filter={"$and": [{"uid": "u1"}], "memory_schema_version": {"$exists": False}},
    )
    assert _ids(hits) == ["legacy"], 'the sibling clause was dropped'


def test_a_filter_outside_the_contract_is_refused(vector_fake):
    """The real adapters call neutral_filters.validate(); a fake that accepts more than they do lets an
    out-of-contract filter pass E2E and fail in production."""
    from utils.vector.filters import UnsupportedFilterError

    with pytest.raises(UnsupportedFilterError):
        vector_fake.query("ns2", _Q(), top_k=10, filter={"uid": {"$regex": "^u"}})


def test_the_supported_operators_still_behave(vector_fake):
    """Legacy principals: the operators the old matcher DID handle must keep working."""
    assert _ids(vector_fake.query("ns2", _Q(), top_k=10, filter={"uid": "u1"})) == ["canonical", "legacy"]
    assert _ids(vector_fake.query("ns2", _Q(), top_k=10, filter={"uid": {"$in": ["u1", "u2"]}})) == [
        "canonical",
        "legacy",
    ]
    assert _ids(vector_fake.query("ns2", _Q(), top_k=10, filter={"memory_schema_version": {"$gte": 1}})) == [
        "canonical"
    ]
    assert _ids(vector_fake.query("ns2", _Q(), top_k=10, filter={"$or": [{"uid": "u1"}, {"uid": "zzz"}]})) == [
        "canonical",
        "legacy",
    ]


# --- L8: the storage fake sits below the adapter, so it must speak the SDK's language ------------


@pytest.fixture
def fake_gcs():
    """The fake's own setup/teardown — it keeps its root in a module global, not an env var."""
    from testing.e2e.fakes import storage as fake_storage

    fake_storage.setup_fake_storage()
    try:
        yield fake_storage
    finally:
        fake_storage.teardown_fake_storage()


def test_a_missing_object_raises_the_sdk_error_the_adapter_translates(fake_gcs, tmp_path):
    """The fake replaces google.cloud.storage.Client, so raising FileNotFoundError meant the adapter's
    NotFound -> ObjectNotFound translation never ran in E2E, and six `except ObjectNotFound` handlers
    were unreachable."""
    from google.api_core.exceptions import NotFound

    from testing.e2e.fakes import storage as fake_storage

    client = fake_storage.FakeStorageClient()
    blob = client.bucket('b1').blob('missing.txt')

    for call in (blob.reload, blob.download_as_bytes, lambda: blob.download_to_filename(str(tmp_path / 'x'))):
        with pytest.raises(NotFound):
            call()


def test_the_adapter_turns_that_into_the_neutral_error(fake_gcs, monkeypatch):
    """The point of the change: the neutral error the product catches now reaches it in E2E too."""
    from testing.e2e.fakes import storage as fake_storage
    from utils.object_store.errors import ObjectNotFound

    monkeypatch.setattr('google.cloud.storage.Client', fake_storage.FakeStorageClient)

    from utils.object_store.adapters.gcs import GCSObjectStore

    with pytest.raises(ObjectNotFound):
        GCSObjectStore().get_bytes('b1', 'missing.txt')


def test_reading_an_object_that_exists_still_works(fake_gcs):
    from testing.e2e.fakes import storage as fake_storage

    client = fake_storage.FakeStorageClient()
    blob = client.bucket('b1').blob('there.txt')
    blob.upload_from_string('hello')
    assert blob.download_as_bytes() == b'hello'
    blob.reload()
