"""A model swap at the SAME dimension must be caught at boot (ADR-0086, BACKLOG L19).

`validate_vector_dimension` already crosses the embeddings dimension with the store's. The case it
cannot see is the one that leaves no trace: swapping `nomic-embed-text` for another 768-dimensional
model puts vectors of the right length and an incompatible geometry into the same collection. Nothing
is rejected; search just gets worse, for everyone, silently.

So the model that wrote a namespace is recorded in the document store when the collection is created,
and crossed at boot. The rules that matter, and that these tests hold:

  * unknown is not mismatched — every collection that exists today has no record, and a boot must adopt
    it rather than report it;
  * the check runs only after the dimensions agree, so the louder fault is never buried under this one;
  * recording is best-effort — a bookkeeping failure must not break the write that triggered it.
"""

from __future__ import annotations

import pytest

from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def store(monkeypatch):
    """A fresh store per test, injected at the module's own seam.

    `namespace_state` is a port consumer: it calls `get_document_store()`, not the `db` proxy, so
    `install_fake_db_client` (which patches the client accessor) would not reach it — and the factory's
    store is a process-level singleton, so state would leak between tests. Patching `_store` is both the
    right seam and the isolated one.
    """
    from utils.vector import namespace_state

    fake = FakeDocumentStore()
    monkeypatch.setattr(namespace_state, '_store', lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _model(monkeypatch):
    monkeypatch.setenv('OMI_EMBEDDINGS_MODEL', 'bge-m3')


# --- the record ------------------------------------------------------------------------------------


def test_a_namespace_with_no_record_is_adopted_not_reported(store):
    """The state of every existing deployment on the boot after this ships. Reporting it would make them
    all fail a check over a fact nobody could have recorded."""
    from utils.vector.namespace_state import compare_namespace_model, read_namespace_state

    assert compare_namespace_model('omi_ns1', model='bge-m3', dim=1024) is None
    assert read_namespace_state('omi_ns1') == {'namespace': 'omi_ns1', 'model': 'bge-m3', 'dim': 1024}


def test_the_same_model_is_silent(store):
    from utils.vector.namespace_state import compare_namespace_model, record_namespace_state

    record_namespace_state('omi_ns1', model='bge-m3', dim=1024)

    assert compare_namespace_model('omi_ns1', model='bge-m3', dim=1024) is None


def test_a_different_model_at_the_same_dimension_is_reported(store):
    """The whole point. Same dimension, so no other check can see it."""
    from utils.vector.namespace_state import compare_namespace_model, record_namespace_state

    record_namespace_state('omi_ns1', model='nomic-embed-text', dim=1024)

    problem = compare_namespace_model('omi_ns1', model='bge-m3', dim=1024)

    assert problem is not None
    assert 'nomic-embed-text' in problem and 'bge-m3' in problem and 'omi_ns1' in problem


def test_an_adoption_does_not_overwrite_a_later_disagreement(store):
    """Adoption happens once. A second boot with a different model must report, not re-adopt."""
    from utils.vector.namespace_state import compare_namespace_model

    assert compare_namespace_model('omi_ns1', model='bge-m3', dim=1024) is None

    assert compare_namespace_model('omi_ns1', model='other-model', dim=1024) is not None


def test_a_record_without_a_model_name_is_treated_as_unknown(store):
    """Defensive: a half-written record must not be read as 'a different model'."""
    from utils.vector.namespace_state import compare_namespace_model

    store.set('vector_namespace_state/omi_ns1', {'namespace': 'omi_ns1', 'dim': 1024})

    assert compare_namespace_model('omi_ns1', model='bge-m3', dim=1024) is None


def test_forgetting_a_namespace_removes_its_record(store):
    """The obligation that comes with keeping state: a list that only grows rots into one nobody reads."""
    from utils.vector.namespace_state import forget_namespace_state, read_namespace_state, record_namespace_state

    record_namespace_state('omi_ns1', model='bge-m3', dim=1024)
    forget_namespace_state('omi_ns1')

    assert read_namespace_state('omi_ns1') is None


def test_recording_never_raises(monkeypatch):
    """A safety net that can break the thing it protects is worse than none."""
    from utils.vector import namespace_state

    class _Broken:
        def set(self, *_a, **_k):
            raise RuntimeError('store down')

    monkeypatch.setattr(namespace_state, '_store', lambda: _Broken())

    namespace_state.record_namespace_state('omi_ns1', model='bge-m3', dim=1024)  # must not raise


# --- the boot check --------------------------------------------------------------------------------


@pytest.fixture
def qdrant_env(monkeypatch):
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'qdrant')
    monkeypatch.setenv('QDRANT_URL', 'http://qdrant:6333')
    monkeypatch.setenv('QDRANT_VECTOR_DIM', '1024')


def _run_startup(monkeypatch, *, existing, measured=1024):
    from utils.vector import factory

    monkeypatch.setattr(factory, '_measure_embedding_dimension', lambda: measured)
    monkeypatch.setattr(factory, '_existing_collection_dimensions', lambda: existing)
    factory.validate_vector_dimension()


def test_the_boot_check_reports_a_swapped_model(store, qdrant_env, monkeypatch, caplog):
    from utils.vector.namespace_state import record_namespace_state

    record_namespace_state('omi_ns1', model='nomic-embed-text', dim=1024)

    with caplog.at_level('ERROR'):
        _run_startup(monkeypatch, existing={'omi_ns1': 1024})

    assert any('DIFFERENT embeddings model' in record.getMessage() for record in caplog.records)


def test_the_boot_check_is_silent_when_the_model_agrees(store, qdrant_env, monkeypatch, caplog):
    from utils.vector.namespace_state import record_namespace_state

    record_namespace_state('omi_ns1', model='bge-m3', dim=1024)

    with caplog.at_level('ERROR'):
        _run_startup(monkeypatch, existing={'omi_ns1': 1024})

    assert not caplog.records


def test_a_dimension_mismatch_is_not_buried_under_a_model_mismatch(store, qdrant_env, monkeypatch, caplog):
    """Ordering, deliberately: the dimension fault rejects every write and is the urgent one. Reporting
    both at once would bury it under a quality problem."""
    from utils.vector.namespace_state import record_namespace_state

    record_namespace_state('omi_ns1', model='nomic-embed-text', dim=1024)

    with caplog.at_level('ERROR'):
        _run_startup(monkeypatch, existing={'omi_ns1': 768})

    messages = [record.getMessage() for record in caplog.records]
    assert any('different dimension' in message for message in messages)
    assert not any('DIFFERENT embeddings model' in message for message in messages)
