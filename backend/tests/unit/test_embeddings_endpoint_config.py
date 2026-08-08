"""On-prem embeddings endpoint configuration (WP5, ADR-0035).

Embeddings are the one hard-cloud inference gap: by default they hit OpenAI
``text-embedding-3-large``, but an operator can point them at any
OpenAI-compatible endpoint (Ollama / vLLM / TEI) via ``OMI_EMBEDDINGS_BASE_URL``.
These tests pin the env contract and the no-egress delegation — no network.
"""

import pytest

from utils.llm import clients


def test_default_is_cloud_openai(monkeypatch):
    for var in (
        clients.EMBEDDINGS_BASE_URL_ENV_VAR,
        clients.EMBEDDINGS_MODEL_ENV_VAR,
        clients.EMBEDDINGS_API_KEY_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)
    assert clients._embeddings_base_url() == ''
    assert clients._embeddings_model() == 'text-embedding-3-large'
    # No base URL → no extra kwargs → unchanged cloud behaviour.
    assert clients._embeddings_ctor_kwargs() == {}


def test_local_endpoint_pins_all_constructions(monkeypatch):
    monkeypatch.setenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, 'http://ollama:11434/v1/')
    monkeypatch.delenv(clients.EMBEDDINGS_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(clients.EMBEDDINGS_MODEL_ENV_VAR, 'nomic-embed-text')

    assert clients._embeddings_base_url() == 'http://ollama:11434/v1'  # trailing slash stripped
    assert clients._embeddings_model() == 'nomic-embed-text'

    kwargs = clients._embeddings_ctor_kwargs()
    assert kwargs['base_url'] == 'http://ollama:11434/v1'
    # Local servers ignore the key but the OpenAI client demands a non-empty one.
    assert kwargs['api_key'] == 'not-set'
    # Required for Ollama: default True makes LangChain send token-id arrays, which it rejects.
    assert kwargs['check_embedding_ctx_length'] is False


def test_explicit_api_key_is_honoured(monkeypatch):
    monkeypatch.setenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, 'http://tei:8080/v1')
    monkeypatch.setenv(clients.EMBEDDINGS_API_KEY_ENV_VAR, 'secret-token')
    assert clients._embeddings_ctor_kwargs()['api_key'] == 'secret-token'


def test_local_endpoint_with_byok_openai_does_not_duplicate_api_key(monkeypatch):
    """On-prem + a BYOK OpenAI key must not pass ``api_key`` twice.

    The endpoint kwargs already carry ``api_key`` (OMI_EMBEDDINGS_API_KEY). Before the fix,
    ``_resolve()`` also passed ``api_key=byok`` alongside ``**_ctor_kwargs``, so BYOK OpenAI
    users' embeddings crashed with a duplicate-keyword ``TypeError``. On-prem pins every
    construction to the local endpoint, so BYOK resolves to the pinned default client.
    """
    monkeypatch.setenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, 'http://ollama:11434/v1')
    monkeypatch.setenv(clients.EMBEDDINGS_API_KEY_ENV_VAR, 'endpoint-key')
    monkeypatch.setenv(clients.EMBEDDINGS_MODEL_ENV_VAR, 'nomic-embed-text')
    monkeypatch.setattr(clients, 'get_byok_key', lambda provider: 'sk-user-byok' if provider == 'openai' else None)

    proxy = clients._OpenAIEmbeddingsProxy(
        model_factory=clients._embeddings_model,
        default=None,
        ctor_kwargs_factory=clients._embeddings_ctor_kwargs,
    )
    inst = proxy._resolve()  # must not raise TypeError: multiple values for 'api_key'
    # Pinned to the local endpoint (BYOK fell through to the default client), not a per-key
    # BYOK instance: a second _resolve() returns the very same cached default.
    assert inst is proxy._resolve()
    assert str(inst.openai_api_base).rstrip('/') == 'http://ollama:11434/v1'


def test_model_and_ctor_kwargs_resolve_at_call_time_not_at_construction(monkeypatch):
    """The proxy resolves model + ctor kwargs on first use, not when constructed.

    The module-level ``embeddings`` proxy is built at import; a construction-time snapshot would
    freeze the model/endpoint read at import and ignore env applied afterwards. Build the proxy, set
    the env AFTER, and first access must reflect the post-construction env (lazy, memoized).
    """
    proxy = clients._OpenAIEmbeddingsProxy(
        model_factory=clients._embeddings_model,
        default=None,
        ctor_kwargs_factory=clients._embeddings_ctor_kwargs,
    )
    # Applied AFTER the proxy exists — an __init__-time snapshot would miss both.
    monkeypatch.setenv(clients.EMBEDDINGS_MODEL_ENV_VAR, 'set-after-build')
    monkeypatch.setenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, 'http://tei:8080/v1')
    assert proxy._model == 'set-after-build'
    assert proxy._ctor_kwargs['base_url'] == 'http://tei:8080/v1'


def test_screen_activity_query_uses_local_endpoint_no_google(monkeypatch):
    """When a local endpoint is set, gemini_embed_query must not touch Google."""
    monkeypatch.setenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, 'http://ollama:11434/v1')

    called = {}

    def _fake_generate_embedding(text):
        called['text'] = text
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(clients, 'generate_embedding', _fake_generate_embedding)

    def _boom(*a, **k):  # any HTTP call would be a Google egress — fail loudly
        raise AssertionError('gemini_embed_query hit the network with a local endpoint configured')

    monkeypatch.setattr(clients.httpx, 'post', _boom)

    assert clients.gemini_embed_query('hello') == [0.1, 0.2, 0.3]
    assert called['text'] == 'hello'


def test_screen_activity_query_falls_back_to_google_when_unset(monkeypatch):
    """No local endpoint → the Google REST path is used (cloud stays first-class)."""
    monkeypatch.delenv(clients.EMBEDDINGS_BASE_URL_ENV_VAR, raising=False)

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {'embedding': {'values': [1.0, 2.0]}}

    captured = {}

    def _fake_post(url, **kwargs):
        captured['url'] = url
        return _Resp()

    monkeypatch.setattr(clients.httpx, 'post', _fake_post)
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)

    assert clients.gemini_embed_query('hi') == [1.0, 2.0]
    assert 'generativelanguage.googleapis.com' in captured['url']
