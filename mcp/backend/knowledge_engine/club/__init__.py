"""
Club RAG Knowledge Engine — Supabase backend

All public objects are exposed through lazy accessors so that missing env
vars or credentials do NOT crash the app at import time.  The real objects
are only constructed on first attribute access.
"""

from knowledge_engine.club.config import ClubKnowledgeConfig, club_config
from knowledge_engine.club.vector_store import (
    ClubVectorStore,
    club_vector_store,
    get_club_vector_store,
)
from knowledge_engine.club.embedding_generator import (
    ClubEmbeddingGenerator,
    embedding_generator,
    get_embedding_generator,
)
from knowledge_engine.club.ingestion import (
    ClubKnowledgeIngestion,
    ingestion,
    get_ingestion,
)
from knowledge_engine.club.retrieval import (
    ClubKnowledgeRetriever,
    club_retriever,
    get_club_retriever,
)

__all__ = [
    # Config
    "ClubKnowledgeConfig",
    "club_config",
    # Vector store
    "ClubVectorStore",
    "club_vector_store",
    "get_club_vector_store",
    # Embedding generator
    "ClubEmbeddingGenerator",
    "embedding_generator",
    "get_embedding_generator",
    # Ingestion
    "ClubKnowledgeIngestion",
    "ingestion",
    "get_ingestion",
    # Retrieval
    "ClubKnowledgeRetriever",
    "club_retriever",
    "get_club_retriever",
]
