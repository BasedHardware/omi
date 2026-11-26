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
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Protocol, Sequence
from testing.pipeline_lab.store import private_subdir

_TOKEN = re.compile(r'[a-z0-9]+')
logger = logging.getLogger(__name__)
# Seeding a real day sent 60-64 texts per call; the dev gateway answered every one of those
# with a provider 5xx after ~18 s while every 30-32 text call succeeded. Lab calls stay small.
EMBED_BATCH_ITEMS = int(os.environ.get('OMI_PIPELINE_LAB_EMBED_BATCH', '24') or 24)


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
    """The production embedding client; requests go through the lab proxy and its cap.

    The client is bound lazily (inside the lab env, so the product module reads lab
    settings), and :func:`install_embeddings` binds it before swapping the module name.
    """

    def __init__(self, model: str = 'text-embedding-3-large', dimension: int = 3072, client: Any = None):
        self.model = model
        self.dimension = dimension
        self._client = client

    def bind(self) -> None:
        if self._client is None:
            from utils.llm import clients

            self._client = clients.embeddings

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.bind()
        return [list(map(float, row)) for row in self._client.embed_documents(list(texts))]


def _provider_side_failure(error: BaseException) -> bool:
    """True for an upstream 5xx or a transport failure; False for a cap stop (402) or a 4xx."""
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    if isinstance(status, int):
        return status >= 500
    return isinstance(error, (OSError, TimeoutError)) or type(error).__name__ in {
        'ConnectError',
        'ReadTimeout',
        'RemoteProtocolError',
    }


def placeholder_vector(key: str, dimension: int) -> list[float]:
    """A deterministic unit vector from ``key``: near-orthogonal to real embeddings in high
    dimension, so a text without a real vector neither surfaces in nor distorts retrieval."""
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(f'{key}:{counter}'.encode()).digest()
        values.extend((byte - 127.5) for byte in digest)
        counter += 1
    values = values[:dimension]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


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
        self.failed = 0  # texts the provider refused even alone; they got a placeholder vector

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
            private_subdir(path.parent)
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
            fresh: list[list[float] | None] = []
            for start in range(0, len(missing), EMBED_BATCH_ITEMS):
                fresh.extend(self._embed_resilient([texts[i] for i in missing[start : start + EMBED_BATCH_ITEMS]]))
            if len(fresh) != len(missing):
                raise RuntimeError('embedder returned the wrong number of vectors')
            for i, values in zip(missing, fresh):
                if values is None:  # provider refused this one text every time: placeholder, not cached
                    result[i] = placeholder_vector(keys[i], self.dimension)
                    continue
                if len(values) != self.dimension:
                    raise RuntimeError(f'embedder returned dimension {len(values)}, expected {self.dimension}')
                self._put(keys[i], values)
                result[i] = values
        return [list(row) for row in result if row is not None]

    def _embed_resilient(self, texts: list[str]) -> list[list[float] | None]:
        """Embed ``texts``; on a provider-side failure, bisect to isolate the texts that fail.

        A real day hit an OpenAI 5xx that repeated on one batch while every other batch
        succeeded. Halving keeps the good texts' real vectors; a single text that still fails
        gets ``None`` and is counted in ``failed``. Spend-cap stops and client errors are
        re-raised untouched (only server-side failures are bisected).
        """
        try:
            return list(self.inner.embed(texts))
        except Exception as error:
            if not _provider_side_failure(error):
                raise
            if len(texts) == 1:
                with self._lock:
                    self.failed += 1
                logger.warning('pipeline_lab_embedding_failed items=1 error=%s', type(error).__name__)
                return [None]
        mid = len(texts) // 2
        return self._embed_resilient(texts[:mid]) + self._embed_resilient(texts[mid:])


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

    for candidate in (embedder, getattr(embedder, 'inner', None)):
        if isinstance(candidate, ProductEmbedder):
            candidate.bind()  # capture the real client before its module name is swapped
    adapter = LangchainEmbeddingsAdapter(embedder)
    replace_everywhere(stack, clients.embeddings, adapter)
    return adapter
