"""Pluggable embedders with an input-hash cache (DESIGN L7).

``Embedder`` is anything with ``model``, ``dimension`` and ``embed(texts)``.

- :class:`FakeEmbedder` is deterministic and offline (hashed bag of words, L2
  normalised), so texts that share words score higher under cosine. Tests only.
- :class:`ProductEmbedder` calls the product's own embedding client
  (``utils.llm.clients.embeddings``), which routes through ``OMI_LLM_GATEWAY_URL``,
  i.e. the lab LLM proxy and its USD ledger. It is never used in tests.
- :class:`CachedEmbedder` wraps either one and caches vectors on disk keyed by
  ``sha256(model, text)``, so a re-seed or a re-run costs nothing.

:class:`LangchainEmbeddingsAdapter` exposes an embedder as the
``embed_query``/``embed_documents`` object that ``database.vector_db`` and
``utils.llm.clients.generate_embedding`` call; :func:`install_embeddings` swaps it in.
"""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Protocol, Sequence

_TOKEN = re.compile(r'[a-z0-9]+')


class Embedder(Protocol):
    model: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic offline embedder. Shared words raise cosine similarity."""

    def __init__(self, dimension: int = 64, model: str = 'fake-hash-bow-v1'):
        self.dimension = dimension
        self.model = model
        self.calls = 0
        self.texts_embedded = 0

    def _vector(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        tokens = _TOKEN.findall((text or '').lower()) or ['<empty>']
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            slot = int.from_bytes(digest[:4], 'big') % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            values[slot] += sign
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        self.texts_embedded += len(texts)
        return [self._vector(text) for text in texts]


class ProductEmbedder:
    """The production embedding client; requests go through the lab proxy and its cap."""

    def __init__(self, model: str = 'text-embedding-3-large', dimension: int = 3072, client: Any = None):
        self.model = model
        self.dimension = dimension
        if client is None:
            # Bind the real client now, before install_embeddings() swaps the module name.
            from utils.llm import clients

            client = clients.embeddings
        self._client = client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, row)) for row in self._client.embed_documents(list(texts))]


def input_hash(model: str, text: str) -> str:
    return hashlib.sha256(json.dumps([model, text], ensure_ascii=False).encode('utf-8')).hexdigest()


class CachedEmbedder:
    """Disk cache under ``<cache_dir>/<kk>/<key>.json`` (same fan-out as the run cache)."""

    def __init__(self, inner: Embedder, cache_dir: Path | None = None):
        self.inner = inner
        self.model = inner.model
        self.dimension = inner.dimension
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._memory: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / key[:2] / f'{key}.json'

    def _get(self, key: str) -> list[float] | None:
        with self._lock:
            if key in self._memory:
                return self._memory[key]
        path = self._path(key)
        if path is not None and path.exists():
            values = json.loads(path.read_text(encoding='utf-8'))['values']
            with self._lock:
                self._memory[key] = values
            return values
        return None

    def _put(self, key: str, values: list[float]) -> None:
        with self._lock:
            self._memory[key] = values
        path = self._path(key)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'model': self.model, 'values': values}, stream)
            os.replace(tmp, path)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [input_hash(self.model, text) for text in texts]
        result: list[list[float] | None] = [self._get(key) for key in keys]
        missing = [i for i, row in enumerate(result) if row is None]
        with self._lock:
            self.hits += len(texts) - len(missing)
            self.misses += len(missing)
        if missing:
            fresh = self.inner.embed([texts[i] for i in missing])
            if len(fresh) != len(missing):
                raise RuntimeError('embedder returned the wrong number of vectors')
            for i, values in zip(missing, fresh):
                if len(values) != self.dimension:
                    raise RuntimeError(f'embedder returned dimension {len(values)}, expected {self.dimension}')
                self._put(keys[i], values)
                result[i] = values
        return [list(row) for row in result if row is not None]


class LangchainEmbeddingsAdapter:
    """The ``embed_query``/``embed_documents`` surface the product calls."""

    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def embed_query(self, text: str) -> list[float]:
        return self.embedder.embed([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.embed(list(texts))

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)


def install_embeddings(stack: ExitStack, embedder: Embedder) -> LangchainEmbeddingsAdapter:
    """Route every product embedding call through ``embedder`` for the block."""
    from testing.pipeline_lab.stack.patching import replace_everywhere
    from utils.llm import clients

    adapter = LangchainEmbeddingsAdapter(embedder)
    replace_everywhere(stack, clients.embeddings, adapter)
    return adapter
