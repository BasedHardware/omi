-- =============================================================================
-- Supabase Migration — Shared RAG Schema (User + Club)
-- Run this ONCE in your Supabase SQL editor (Dashboard → SQL Editor → New query)
-- =============================================================================

-- 1. Enable pgvector extension (once per project)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Papers table (shared by user RAG and club RAG)
--    source = 'user' for user-uploaded docs
--    source = 'club' for club knowledge (Drive-synced)
--    user_id = NULL for club docs
CREATE TABLE IF NOT EXISTS papers (
    id          TEXT        PRIMARY KEY,
    filename    TEXT        NOT NULL,
    user_id     TEXT,                                    -- NULL for club docs
    source      TEXT        NOT NULL DEFAULT 'user',     -- 'user' | 'club'
    processed   BOOLEAN     NOT NULL DEFAULT FALSE,
    upload_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS papers_user_id_idx ON papers (user_id);
CREATE INDEX IF NOT EXISTS papers_source_idx  ON papers (source);

-- 3. Document chunks table
--    embedding VECTOR(384) matches EMBEDDING_DIM = 384 in .env
CREATE TABLE IF NOT EXISTS document_chunks (
    id          BIGSERIAL   PRIMARY KEY,
    paper_id    TEXT        NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_text  TEXT        NOT NULL,
    chunk_index INT         NOT NULL DEFAULT 0,
    start_char  INT         NOT NULL DEFAULT 0,
    end_char    INT         NOT NULL DEFAULT 0,
    embedding   VECTOR(384),
    metadata    JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS chunks_paper_id_idx ON document_chunks (paper_id);

-- 4. Vector similarity search function
--    Called by both user RAG (SupabaseVectorStore.search) and
--    club RAG (ClubVectorStore.search) with different filter combinations.
--
--    Filter logic (all filters are optional / NULL = no filter):
--      user_id_filter   → scope to one user's docs
--      paper_id_filter  → scope to one specific paper
--      source_filter    → 'user' or 'club'
--      category_filter  → metadata->>'category' (events | announcements | coordinators)
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding  VECTOR(384),
    match_count      INT     DEFAULT 5,
    user_id_filter   TEXT    DEFAULT NULL,
    paper_id_filter  TEXT    DEFAULT NULL,
    source_filter    TEXT    DEFAULT NULL,
    category_filter  TEXT    DEFAULT NULL
)
RETURNS TABLE (
    id          BIGINT,
    paper_id    TEXT,
    chunk_text  TEXT,
    metadata    JSONB,
    similarity  FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.paper_id,
        dc.chunk_text,
        dc.metadata,
        (1 - (dc.embedding <=> query_embedding))::FLOAT AS similarity
    FROM document_chunks dc
    JOIN papers p ON p.id = dc.paper_id
    WHERE
        (user_id_filter   IS NULL OR p.user_id               = user_id_filter)
        AND (paper_id_filter IS NULL OR dc.paper_id           = paper_id_filter)
        AND (source_filter   IS NULL OR p.source              = source_filter)
        AND (category_filter IS NULL OR dc.metadata->>'category' = category_filter)
    ORDER BY dc.embedding <=> query_embedding   -- cosine distance ASC = similarity DESC
    LIMIT match_count;
END;
$$;

-- 5. (Optional) IVFFlat ANN index — uncomment once you have 1 000+ rows.
--    Rule of thumb: lists ≈ sqrt(total_rows).  Rebuild after bulk inserts.
--
-- CREATE INDEX IF NOT EXISTS chunks_embedding_ivfflat_idx
--     ON document_chunks
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- =============================================================================
-- Quick smoke-test — paste these after running the migration to verify.
-- =============================================================================
-- SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
-- SELECT table_name FROM information_schema.tables
--     WHERE table_schema = 'public'
--       AND table_name IN ('papers', 'document_chunks');
-- SELECT proname, pronargs FROM pg_proc WHERE proname = 'match_document_chunks';
