"""
Document Ingestion Service
Handles PDF processing, chunking, and indexing into Supabase (no local storage)
"""

import uuid
import io
from typing import Dict, Optional, Callable
import PyPDF2
from supabase import create_client

from .embedding_service import EmbeddingService
from .vector_store import SupabaseVectorStore
from .graph_store import GraphStore
from .chunking import DocumentChunker


class DocumentIngestion:
    """
    Full ingestion pipeline: PDF -> chunks -> embeddings -> Supabase
    No local file storage - everything goes to Supabase
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        supabase_bucket: str,
        embedding_service: EmbeddingService,
        chunker: DocumentChunker,
        graph_store: Optional[GraphStore] = None,
    ):
        self.supabase = create_client(supabase_url, supabase_key)
        self.supabase_bucket = supabase_bucket

        self.vector_store = SupabaseVectorStore(
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            embedding_dim=embedding_service.get_embedding_dimension(),
        )

        self.embedding_service = embedding_service
        self.chunker = chunker
        self.graph_store = graph_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_pdf(
        self,
        file_bytes: bytes,
        filename: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        user_id: Optional[str] = None,
        paper_id: Optional[str] = None,
        storage_path: Optional[str] = None,
    ) -> Dict:
        """
        Process a PDF file and store it in Supabase.

        Args:
            file_bytes: PDF file content as bytes
            filename: Original filename
            progress_callback: Optional callback(status, progress_percent)
            user_id: Owner of this document (Supabase per-user filtering)
            paper_id: Pre-generated UUID; auto-generated if omitted
            storage_path: Path in Supabase Storage where file will be stored

        Returns:
            Result dict with keys: success, paper_id, filename, chunks_created, message
        """
        if paper_id is None:
            paper_id = str(uuid.uuid4())

        try:
            if progress_callback:
                progress_callback("Extracting text from PDF", 10)

            text = self._extract_text_from_bytes(file_bytes)
            if not text or len(text.strip()) < 100:
                raise ValueError("PDF contains insufficient text")

            if progress_callback:
                progress_callback("Chunking document", 30)

            metadata = {"filename": filename, "paper_id": paper_id}
            chunks = self.chunker.chunk_text(text, metadata)
            if not chunks:
                raise ValueError("No chunks created from PDF")

            if progress_callback:
                progress_callback("Generating embeddings", 50)

            chunk_texts = [c["text"] for c in chunks]
            embeddings = self.embedding_service.embed_texts(chunk_texts)

            if progress_callback:
                progress_callback("Adding to vector store", 70)

            self.vector_store.add_documents(embeddings, chunks, paper_id, user_id=user_id)

            if progress_callback:
                progress_callback("Saving to Supabase Storage", 85)

            # Upload to Supabase Storage
            if storage_path:
                try:
                    self.supabase.storage.from_(self.supabase_bucket).upload(
                        storage_path,
                        file_bytes,
                        {"content-type": "application/pdf"}
                    )
                    print(f"✅ File uploaded to storage: {storage_path}")
                except Exception as e:
                    print(f"⚠️ Storage upload warning: {e}")

            if self.graph_store and self.graph_store.enabled:
                if progress_callback:
                    progress_callback("Adding to citation graph", 95)
                self.graph_store.add_paper(paper_id, filename, metadata)

            if progress_callback:
                progress_callback("Complete", 100)

            return {
                "success": True,
                "paper_id": paper_id,
                "filename": filename,
                "chunks_created": len(chunks),
                "message": f"Successfully processed {filename}",
            }

        except Exception as e:
            if progress_callback:
                progress_callback(f"Error: {str(e)}", 0)
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to process {filename}: {str(e)}",
            }

    def delete_document(self, paper_id: str, storage_path: Optional[str] = None) -> Dict:
        """Delete a document and all its chunks from Supabase."""
        try:
            self.vector_store.delete_paper(paper_id)

            if self.graph_store and self.graph_store.enabled:
                self.graph_store.delete_paper(paper_id)

            # Delete from Supabase Storage
            if storage_path:
                try:
                    self.supabase.storage.from_(self.supabase_bucket).remove([storage_path])
                except Exception as e:
                    print(f"Failed to delete from storage: {e}")

            return {
                "success": True,
                "paper_id": paper_id,
                "message": f"Successfully deleted document {paper_id}",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to delete document {paper_id}: {str(e)}",
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_text_from_bytes(self, file_bytes: bytes) -> str:
        text = ""
        try:
            with io.BytesIO(file_bytes) as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
            return text.strip()
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")