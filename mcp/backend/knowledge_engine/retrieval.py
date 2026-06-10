# backend/knowledge_engine/retrieval.py
"""
Hybrid Retrieval Service
Combines vector search with optional citation graph
"""

from typing import List, Dict, Optional

from .embedding_service import EmbeddingService
from .vector_store import SupabaseVectorStore
from .graph_store import GraphStore


class HybridRetrieval:
    """
    Retrieval service combining vector search and citation graph
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: SupabaseVectorStore,
        graph_store: Optional[GraphStore] = None
    ):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.graph_store = graph_store

    def retrieve(
        self,
        query: str,
        top_k: int = 10,  # Increased from 5
        include_citations: bool = False,
        filter_paper_id: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> Dict:
        """
        Retrieve relevant chunks for a query.
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)
        
        print(f"🔍 RAG Search: query='{query[:50]}...'")
        print(f"   User ID: {user_id}")
        print(f"   Paper filter: {filter_paper_id}")

        # Vector search
        paper_id_filter = filter_paper_id[0] if filter_paper_id else None
        results = self.vector_store.search_similar(
            query_embedding,
            top_k=top_k,
            user_id=user_id,
            paper_id_filter=paper_id_filter,
        )
        
        print(f"   Found {len(results)} chunks")

        response = {
            "query": query,
            "chunks": [],
            "citations": {} if include_citations else None,
        }

        seen_papers = set()

        for result in results:
            chunk_data = {
                "text": result.get("chunk_text", ""),
                "score": result.get("similarity", 0.0),
                "metadata": result.get("metadata", {}),
                "paper_id": result.get("paper_id", ""),
                "chunk_index": result.get("chunk_index", 0)
            }
            response["chunks"].append(chunk_data)
            if result.get("paper_id"):
                seen_papers.add(result["paper_id"])

        # Add citation information if requested
        if include_citations and self.graph_store and self.graph_store.enabled:
            for paper_id in seen_papers:
                citations = self.graph_store.get_citations(paper_id)
                response["citations"][paper_id] = citations

        return response

    def get_all_resources(self, user_id: Optional[str] = None) -> List[Dict]:
        """
        Get list of all indexed resources.
        """
        papers = self.vector_store.get_all_papers(user_id=user_id)

        resources = []
        for paper in papers:
            resources.append({
                "paper_id": paper.get("id"),
                "filename": paper.get("filename", "unknown"),
                "upload_date": paper.get("upload_date"),
                "user_id": paper.get("user_id"),
            })

        return resources