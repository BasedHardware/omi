"""Live end-to-end on-prem semantic search (WP5, ADR-0035 + ADR-0033).

The real user-facing feature, proven with real local components: embed text with
a local OpenAI-compatible endpoint (Ollama), upsert the vectors into a local
Qdrant, query with a semantically related phrase, and assert the right document
ranks first. No cloud embeddings, no cloud vector store.

Gated on OMI_EMBEDDINGS_BASE_URL + QDRANT_URL (skips otherwise). Both services are
reached on loopback under --network host. Run:

  docker run --rm --network host \
    -e OMI_EMBEDDINGS_BASE_URL=http://127.0.0.1:11434/v1 -e OMI_EMBEDDINGS_MODEL=bge-m3 \
    -e VECTOR_STORE_BACKEND=qdrant -e QDRANT_URL=http://127.0.0.1:6333 -e QDRANT_VECTOR_DIM=1024 \
    -v /work/omi/src/omi:/repo -w /repo/backend omi-onprem-backend-test:v2 \
    python -m pytest tests/contract/test_onprem_search_roundtrip.py -q -p no:cacheprovider
"""

import os

import pytest

from utils.llm import clients
from utils.vector.factory import get_vector_store

pytestmark = pytest.mark.skipif(
    not (os.getenv('OMI_EMBEDDINGS_BASE_URL', '').strip() and os.getenv('QDRANT_URL', '').strip()),
    reason='needs a live embeddings endpoint (OMI_EMBEDDINGS_BASE_URL) and Qdrant (QDRANT_URL)',
)

_NAMESPACE = 'wp5_roundtrip'

_DOCS = {
    'cat': 'The cat stretched out and slept on the warm windowsill in the afternoon sun.',
    'python': 'Python is a widely used programming language for data science and machine learning.',
    'paris': 'The Eiffel Tower is the most famous iron landmark in Paris, the capital of France.',
    'coffee': 'She brewed a strong espresso and the kitchen filled with the smell of fresh coffee.',
}


@pytest.fixture
def live_store():
    # Rebuild the embeddings proxy from the test env (constructed at import with defaults).
    clients.embeddings = clients._OpenAIEmbeddingsProxy(
        model_factory=clients._embeddings_model,
        default=None,
        ctor_kwargs_factory=clients._embeddings_ctor_kwargs,
    )
    store = get_vector_store()
    # Ensure a clean namespace across reruns.
    store.delete_by_ids(_NAMESPACE, list(_DOCS.keys()))
    records = [
        {'id': key, 'values': clients.generate_embedding(text), 'metadata': {'topic': key, 'text': text}}
        for key, text in _DOCS.items()
    ]
    written = store.upsert(_NAMESPACE, records)
    assert written == len(_DOCS)
    try:
        yield store
    finally:
        store.delete_by_ids(_NAMESPACE, list(_DOCS.keys()))


@pytest.mark.parametrize(
    'query,expected_top',
    [
        ('a feline dozing in the sunshine', 'cat'),
        ('writing code for artificial intelligence', 'python'),
        ('a well-known monument in the French capital', 'paris'),
        ('making a hot caffeinated drink in the morning', 'coffee'),
    ],
)
def test_semantic_search_ranks_the_right_document_first(live_store, query, expected_top):
    qvec = clients.generate_embedding(query)
    assert len(qvec) == int(os.environ['QDRANT_VECTOR_DIM'])
    hits = live_store.query(_NAMESPACE, qvec, top_k=len(_DOCS), include_metadata=True)
    assert hits, 'expected at least one hit'
    top = hits[0]
    assert top['id'] == expected_top, (
        f"query {query!r}: expected {expected_top!r} first, got "
        f"{[(h['id'], round(h['score'], 3)) for h in hits]}"
    )
    # Scores must be ordered (descending similarity).
    scores = [h['score'] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_metadata_roundtrips_through_the_store(live_store):
    qvec = clients.generate_embedding('cat sleeping in the sun')
    hits = live_store.query(_NAMESPACE, qvec, top_k=1, include_metadata=True)
    assert hits[0]['metadata']['topic'] == 'cat'
    assert 'windowsill' in hits[0]['metadata']['text']
