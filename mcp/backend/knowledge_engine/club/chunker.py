"""
Document Chunker for Club Knowledge
Chunks documents for embedding and retrieval
"""
from typing import List, Dict, Any
from pathlib import Path

from knowledge_engine.club.config import club_config
from utils.logger import logger


class ClubDocumentChunker:
    """
    Chunk documents for club knowledge base
    
    Uses same strategy as your existing RAG system:
    - Fixed chunk size with overlap
    - Preserves metadata
    """
    
    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ):
        self.chunk_size = chunk_size or club_config.CLUB_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or club_config.CLUB_CHUNK_OVERLAP
        
        logger.info(f"ClubDocumentChunker initialized: size={self.chunk_size}, overlap={self.chunk_overlap}")
    
    def chunk_document(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Chunk a document into smaller pieces
        
        Args:
            content: Full document text
            metadata: Document metadata
            
        Returns:
            List of chunks:
            [
                {
                    "text": str,
                    "metadata": {
                        ...original_metadata,
                        "chunk_index": int,
                        "total_chunks": int
                    }
                },
                ...
            ]
        """
        if not content or not content.strip():
            logger.warning(f"Empty content for {metadata.get('source', 'unknown')}")
            return []
        
        # Split into chunks
        chunks = self._split_text(content)
        
        # Add metadata to each chunk
        chunked_docs = []
        total_chunks = len(chunks)
        
        for idx, chunk_text in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                "chunk_index": idx,
                "total_chunks": total_chunks
            }
            
            chunked_docs.append({
                "text": chunk_text,
                "metadata": chunk_metadata
            })
        
        logger.debug(f"Chunked {metadata.get('source', 'unknown')} into {total_chunks} chunks")
        
        return chunked_docs
    
    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap
        
        Simple character-based splitting (same as your existing system)
        """
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            # Get chunk
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary if possible
            if end < text_len:
                # Look for period, question mark, or exclamation within last 100 chars
                last_part = chunk[-100:] if len(chunk) > 100 else chunk
                for sep in ['. ', '? ', '! ', '\n\n']:
                    last_sep = last_part.rfind(sep)
                    if last_sep != -1:
                        # Found a good break point
                        chunk = chunk[:len(chunk) - len(last_part) + last_sep + len(sep)]
                        break
            
            chunks.append(chunk.strip())
            
            # Move start forward (with overlap)
            start = end - self.chunk_overlap
            
            # Prevent infinite loop
            if start <= chunks[-1].__len__() - self.chunk_size + self.chunk_overlap:
                start = end
        
        return [c for c in chunks if c]  # Filter empty chunks
    
    def chunk_multiple_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Chunk multiple documents
        
        Args:
            documents: List of {"content": str, "metadata": dict}
            
        Returns:
            Flattened list of all chunks
        """
        all_chunks = []
        
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            
            chunks = self.chunk_document(content, metadata)
            all_chunks.extend(chunks)
        
        logger.info(f"Chunked {len(documents)} documents into {len(all_chunks)} chunks")
        
        return all_chunks


# Singleton
chunker = ClubDocumentChunker()