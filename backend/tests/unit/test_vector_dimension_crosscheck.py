"""The embeddings dimension and the store's are two independent variables. Cross them (BACKLOG L19).

`QDRANT_VECTOR_DIM` and the dimension implied by `OMI_EMBEDDINGS_MODEL` were never compared — the only
"guarantee" was a comment in values.yaml. Measured on the live stack, the sharpest form of the problem is
not the mismatch itself but WHEN it surfaces:

    QDRANT_VECTOR_DIM=3072 (wrong), model bge-m3 = 1024, collections already created at 1024
      -> upsert into the EXISTING collection: accepted. The wrong value was never consulted.
      -> upsert into a NEW namespace: the collection is created at 3072 and every write to it fails
         with `Vector dimension error: expected dim: 3072, got 1024`.

So the value is consulted only at collection-creation time. A wrong one does nothing for weeks and then
breaks exactly one feature — the first to touch a new namespace — with the error appearing far from the
cause. A startup cross-check is the only thing that catches it when it is introduced.

It also covers the case an operator is more likely to hit: swapping the embeddings model for one with a
DIFFERENT dimension while the old collections are still there. Then the config may agree with nothing at
all, and the existing collections are the authority.

What this deliberately does NOT catch is a swap to a model of the SAME dimension: the vectors then land in
the same collection with an incompatible geometry and search quality degrades with no error anywhere,
because no record stores which model produced a vector. That needs somewhere to keep the model name and is
tracked separately (BACKLOG L19, second half).
"""

from __future__ import annotations

import pytest

from utils.vector import factory


@pytest.fixture(autouse=True)
def _qdrant_backend(monkeypatch):
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'qdrant')
    monkeypatch.setenv('QDRANT_URL', 'http://qdrant:6333')
    monkeypatch.setenv('QDRANT_VECTOR_DIM', '1024')


@pytest.fixture
def events(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(factory, 'record_fallback', lambda **kw: recorded.append(kw))
    return recorded


def _measure(dim: int):
    return lambda: dim


def test_agreement_is_silent(monkeypatch, events, caplog):
    import logging

    monkeypatch.setattr(factory, '_measure_embedding_dimension', _measure(1024))
    monkeypatch.setattr(factory, '_existing_collection_dimensions', lambda: {'omi_ns1': 1024})

    with caplog.at_level(logging.WARNING, logger='utils.vector.factory'):
        factory.validate_vector_dimension()

    assert caplog.text == ''
    assert events == []


def test_a_configured_dimension_that_the_model_contradicts_is_loud(monkeypatch, events, caplog):
    """The state that does nothing until a new namespace appears, and then breaks one feature."""
    import logging

    monkeypatch.setenv('QDRANT_VECTOR_DIM', '3072')
    monkeypatch.setattr(factory, '_measure_embedding_dimension', _measure(1024))
    monkeypatch.setattr(factory, '_existing_collection_dimensions', lambda: {})

    with caplog.at_level(logging.ERROR, logger='utils.vector.factory'):
        factory.validate_vector_dimension()

    assert 'STARTUP' in caplog.text
    assert 'QDRANT_VECTOR_DIM=3072' in caplog.text
    assert '1024' in caplog.text
    assert len(events) == 1
    assert events[0]['component'] == 'vector_store'
    assert events[0]['reason'] == 'capability_mismatch'
    assert events[0]['outcome'] == 'degraded'


def test_an_existing_collection_that_the_model_contradicts_is_loud(monkeypatch, events, caplog):
    """The likelier operator move: swap the embeddings model, leave the collections. Here the config and
    the model agree with each other and disagree with reality — so checking only the config would pass."""
    import logging

    monkeypatch.setenv('QDRANT_VECTOR_DIM', '768')
    monkeypatch.setattr(factory, '_measure_embedding_dimension', _measure(768))
    monkeypatch.setattr(factory, '_existing_collection_dimensions', lambda: {'omi_ns1': 1024, 'omi_ns2': 768})

    with caplog.at_level(logging.ERROR, logger='utils.vector.factory'):
        factory.validate_vector_dimension()

    assert 'omi_ns1' in caplog.text, 'the offending collection must be named'
    assert 'omi_ns2' not in caplog.text, 'the agreeing one is not a problem'
    assert len(events) == 1


def test_an_unreachable_embeddings_endpoint_does_not_break_startup(monkeypatch, events, caplog):
    """The check runs at import time in main.py. An endpoint that is not up yet is not a misconfiguration,
    and it must not take the API down or cry mismatch."""
    import logging

    def down():
        raise RuntimeError('connection refused')

    monkeypatch.setattr(factory, '_measure_embedding_dimension', down)
    monkeypatch.setattr(factory, '_existing_collection_dimensions', lambda: {})

    with caplog.at_level(logging.WARNING, logger='utils.vector.factory'):
        factory.validate_vector_dimension()

    assert events == [], 'unknown is not mismatched'
    assert 'could not measure' in caplog.text.lower()


def test_an_unreachable_store_is_not_a_mismatch_either(monkeypatch, events):
    monkeypatch.setattr(factory, '_measure_embedding_dimension', _measure(1024))
    monkeypatch.setattr(
        factory, '_existing_collection_dimensions', lambda: (_ for _ in ()).throw(RuntimeError('qdrant down'))
    )

    factory.validate_vector_dimension()

    assert events == []


def test_it_is_a_no_op_on_the_cloud_backend(monkeypatch, events, caplog):
    """Pinecone's dimension belongs to the index, provisioned outside this codebase: there is nothing here
    to cross-check, and nagging a cloud deployment about it would be noise."""
    import logging

    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'pinecone')
    called: list[str] = []
    monkeypatch.setattr(factory, '_measure_embedding_dimension', lambda: called.append('measured') or 1024)

    with caplog.at_level(logging.WARNING, logger='utils.vector.factory'):
        factory.validate_vector_dimension()

    assert called == [], 'it must not even call the embeddings endpoint'
    assert caplog.text == ''
    assert events == []


def test_it_is_a_no_op_when_no_store_is_configured(monkeypatch, events):
    """`QDRANT_URL` unset means the vector store is off (is_vector_available), and a deployment without
    one has nothing to reconcile."""
    monkeypatch.delenv('QDRANT_URL', raising=False)
    called: list[str] = []
    monkeypatch.setattr(factory, '_measure_embedding_dimension', lambda: called.append('measured') or 1024)

    factory.validate_vector_dimension()

    assert called == []
    assert events == []


def test_it_never_raises(monkeypatch):
    """Called at import time from main.py: whatever happens inside must not stop the process."""
    monkeypatch.setattr(factory, '_measure_embedding_dimension', _measure(1024))
    monkeypatch.setattr(
        factory, '_existing_collection_dimensions', lambda: (_ for _ in ()).throw(BaseException('anything'))
    )

    factory.validate_vector_dimension()
