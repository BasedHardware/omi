"""Live contract test: embeddings against a real OpenAI-compatible endpoint (WP5, ADR-0035).

Unlike the hermetic unit test (mocked), this exercises the REAL public path —
``generate_embedding`` / ``gemini_embed_query`` — against a running Ollama/vLLM/TEI,
proving the on-prem embeddings gap is actually closed (a real vector comes back,
of the expected dimension, with no OpenAI/Google egress).

Gated on ``OMI_EMBEDDINGS_BASE_URL`` (skips when no endpoint is configured), like
the vector/auth contract tests. Reaches the endpoint on loopback under
``--network host`` (allowed by the hermetic guard). Run:

  docker run --rm --network host \
    -e OMI_EMBEDDINGS_BASE_URL=http://127.0.0.1:11434/v1 \
    -e OMI_EMBEDDINGS_MODEL=bge-m3 \
    -e OMI_EMBEDDINGS_EXPECTED_DIM=1024 \
    -v /work/omi/src/omi:/repo -w /repo/backend omi-onprem-backend-test:v2 \
    python -m pytest tests/contract/test_embeddings_live_contract.py -q -p no:cacheprovider
"""

import os

import pytest

from utils.llm import clients

_BASE_URL = os.getenv('OMI_EMBEDDINGS_BASE_URL', '').strip()

pytestmark = pytest.mark.skipif(
    not _BASE_URL,
    reason='OMI_EMBEDDINGS_BASE_URL not set — live embeddings endpoint required',
)

_EXPECTED_DIM = int(os.getenv('OMI_EMBEDDINGS_EXPECTED_DIM', '0') or '0')


@pytest.fixture
def live_embeddings():
    """Rebuild the module-level proxy from the current env (it is constructed at
    import time, before the test env is applied)."""
    previous = clients.embeddings
    clients.embeddings = clients._OpenAIEmbeddingsProxy(
        model_factory=clients._embeddings_model,
        default=None,
        ctor_kwargs_factory=clients._embeddings_ctor_kwargs,
    )
    try:
        yield
    finally:
        clients.embeddings = previous


def _assert_vector(vec):
    assert isinstance(vec, list) and vec, 'expected a non-empty vector'
    assert all(isinstance(x, float) for x in vec), 'expected floats'
    # Not a degenerate all-zero vector.
    assert any(x != 0.0 for x in vec), 'expected a non-trivial embedding'
    if _EXPECTED_DIM:
        assert len(vec) == _EXPECTED_DIM, f'dim {len(vec)} != expected {_EXPECTED_DIM}'


def test_generate_embedding_returns_real_vector(live_embeddings):
    vec = clients.generate_embedding('the quick brown fox jumps over the lazy dog')
    _assert_vector(vec)


def test_embeddings_are_deterministic_and_distinct(live_embeddings):
    a1 = clients.generate_embedding('cat')
    a2 = clients.generate_embedding('cat')
    b = clients.generate_embedding('quantum chromodynamics')
    _assert_vector(a1)
    _assert_vector(b)
    assert len(a1) == len(b)
    # Same input → same vector (stable model); different input → different vector.
    assert a1 == pytest.approx(a2, abs=1e-4)
    assert a1 != pytest.approx(b, abs=1e-3)


def test_screen_activity_query_uses_local_endpoint(live_embeddings):
    # With a local endpoint configured, gemini_embed_query delegates to the same path (no Google).
    vec = clients.gemini_embed_query('screen activity search text')
    _assert_vector(vec)
