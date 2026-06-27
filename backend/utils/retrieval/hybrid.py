"""
Hybrid retrieval helpers — fuse semantic (vector) ranking with keyword (BM25) ranking.

Pure vector search misses exact-keyword queries ("phone number", a specific name,
an acronym) where the literal token matters more than semantic similarity. We rerank
the over-fetched vector candidates with BM25 over their text and fuse the two rankings
with Reciprocal Rank Fusion (RRF). This is the mem0-V3 / Graphiti pattern and needs no
extra dependency or index — BM25 runs in-memory over the small candidate set.
"""

import math
import re
from typing import List, Dict

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def bm25_scores(query: str, docs: List[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    """Classic Okapi BM25 score of `query` against each doc in `docs` (same order)."""
    doc_tokens = [_tokenize(d) for d in docs]
    n = len(doc_tokens)
    if n == 0:
        return []

    avgdl = (sum(len(d) for d in doc_tokens) / n) or 1.0

    df: Dict[str, int] = {}
    for toks in doc_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1

    q_terms = _tokenize(query)
    scores: List[float] = []
    for toks in doc_tokens:
        if not toks:
            scores.append(0.0)
            continue
        freq: Dict[str, int] = {}
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
        dl = len(toks)
        s = 0.0
        for t in q_terms:
            tf = freq.get(t)
            if not tf:
                continue
            n_t = df.get(t, 0)
            idf = math.log(1 + (n - n_t + 0.5) / (n_t + 0.5))
            s += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def rrf_rerank(query: str, candidates: List[dict], limit: int, k: int = 60) -> List[dict]:
    """Rerank vector candidates by fusing their vector rank with a BM25 keyword rank.

    `candidates` must be ordered best-first by vector relevance and each must carry a
    'content' key. Returns a new list (copies), best-first, truncated to `limit`, each
    annotated with '_hybrid_score' and '_bm25'.
    """
    if not candidates:
        return []

    contents = [c.get("content", "") for c in candidates]
    bm = bm25_scores(query, contents)

    # vector rank = position in the input list (0 = best)
    vec_rank = {i: i for i in range(len(candidates))}
    # bm25 rank = position after sorting by BM25 score desc (stable on ties)
    bm_order = sorted(range(len(candidates)), key=lambda i: (bm[i], -i), reverse=True)
    bm_rank = {i: r for r, i in enumerate(bm_order)}

    fused: List[dict] = []
    for i, c in enumerate(candidates):
        item = dict(c)
        item["_bm25"] = bm[i]
        item["_hybrid_score"] = 1.0 / (k + vec_rank[i] + 1) + 1.0 / (k + bm_rank[i] + 1)
        fused.append(item)

    fused.sort(key=lambda x: x["_hybrid_score"], reverse=True)
    return fused[: max(0, limit)]
