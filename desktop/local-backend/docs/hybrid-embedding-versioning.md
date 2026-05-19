# Hybrid embedding versioning (ADR)

## Problem

Cloud desktop uses **3072-dimensional** `gemini-embedding-001` vectors stored in GRDB
(`staged_tasks.embedding`, `screenshots.embedding`). Hybrid mode cannot use the Omi
Gemini proxy (`EmbeddingService.proxyBaseURL` is empty in local daemon mode).

Switching embedders changes vector dimension and semantic space. Mixed indexes produce
garbage similarity scores.

## Schema (desktop GRDB)

After migration `hybridEmbeddingMetadata`:

| Table | Columns |
|-------|---------|
| `screenshots` | `embedding_model TEXT`, `embedding_dim INTEGER` |
| `staged_tasks` | `embedding_model TEXT`, `embedding_dim INTEGER` |

Null `embedding_model` means legacy Gemini 3072-d (cloud-era rows).

## Rules

1. **Never search** across rows with different `(embedding_model, embedding_dim)`.
2. On embedder change, set `embedding = NULL` and reset backfill flags for affected tables.
3. `HybridEmbeddingClient` records model id + dimension on each write.
4. Default hybrid embedder: OpenAI-compatible `/embeddings` from `embedding_provider` in daemon settings (see [hybrid-provider-settings.md](hybrid-provider-settings.md)).

## Enabling hybrid embeddings

Desktop: `OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED=1` and configure `embedding_provider` on the daemon.

## Backfill

- `screenshot_embedding_backfill` migration_status row controls Rewind OCR embeddings.
- Task staged-task backfill: `TaskAssistant` / `EmbeddingService.backfillIfNeeded` after provider change.
