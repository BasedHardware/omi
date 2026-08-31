"""On the local embeddings endpoint (check_embedding_ctx_length disabled for Ollama), LangChain's
over-context splitting is off, so the proxy must cap input length itself or a long memory fails to embed
(cubic review PR 10887, clients.py:264). No-op on the cloud path."""

import asyncio

from utils.llm.clients import _OpenAIEmbeddingsProxy


def _proxy(ctor_kwargs):
    return _OpenAIEmbeddingsProxy(lambda: "m", None, lambda: ctor_kwargs)


def test_local_path_caps_long_input():
    long = "x" * 50000
    p = _proxy({"check_embedding_ctx_length": False})  # local endpoint
    assert len(p._cap_local_input(long)) == 32000  # default cap ~8k tokens
    assert [len(t) for t in p._cap_local_input([long, "short"])] == [32000, 5]


def test_cap_is_configurable(monkeypatch):
    monkeypatch.setenv("OMI_EMBEDDINGS_MAX_INPUT_CHARS", "100")
    p = _proxy({"check_embedding_ctx_length": False})
    assert len(p._cap_local_input("y" * 5000)) == 100


def test_cloud_path_does_not_cap():
    long = "x" * 50000
    p = _proxy({})  # cloud OpenAI: LangChain handles ctx length
    assert p._cap_local_input(long) == long


def test_async_wrapper_caps_keyword_input(monkeypatch):
    # aembed_query(text=...)/aembed_documents(texts=...) called with KEYWORDS (args empty) must still be
    # capped on the local endpoint (cubic PR 10887 clients.py:416).
    captured: dict = {}

    class _Fake:
        async def aembed_query(self, text):
            captured["text"] = text
            return [0.0]

        async def aembed_documents(self, texts):
            captured["texts"] = texts
            return [[0.0]]

    monkeypatch.setattr(_OpenAIEmbeddingsProxy, "_resolve", lambda self: _Fake())
    p = _proxy({"check_embedding_ctx_length": False})  # local endpoint
    long = "x" * 50000
    asyncio.run(p.aembed_query(text=long))
    assert len(captured["text"]) == 32000
    asyncio.run(p.aembed_documents(texts=[long, "short"]))
    assert [len(t) for t in captured["texts"]] == [32000, 5]
