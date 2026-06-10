# backend/api/routes/knowledge.py
#
# FIX: Removed `= Depends(get_current_user)` from all route signatures.
# CurrentUser already embeds the Depends via Annotated — adding it again
# as a default value causes FastAPI's AssertionError at startup.

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, Optional
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

from knowledge_engine.embedding_service import EmbeddingService
from knowledge_engine.vector_store import SupabaseVectorStore
from knowledge_engine.graph_store import GraphStore
from knowledge_engine.chunking import DocumentChunker
from knowledge_engine.ingestion import DocumentIngestion
from knowledge_engine.retrieval import HybridRetrieval

from auth.dependencies import CurrentUser   # ← no get_current_user import needed

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "UserDocs")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")

_services_initialized = False
_embedding_service: Optional[EmbeddingService] = None
_vector_store: Optional[SupabaseVectorStore] = None
_graph_store: Optional[GraphStore] = None
_chunker: Optional[DocumentChunker] = None
_ingestion_service: Optional[DocumentIngestion] = None
_retrieval_service: Optional[HybridRetrieval] = None
_processing_status: Dict[str, Dict] = {}


def get_services() -> Dict:
    global _services_initialized
    global _embedding_service, _vector_store, _graph_store
    global _chunker, _ingestion_service, _retrieval_service

    if _services_initialized:
        return {
            "embedding": _embedding_service,
            "vector_store": _vector_store,
            "graph_store": _graph_store,
            "chunker": _chunker,
            "ingestion": _ingestion_service,
            "retrieval": _retrieval_service,
        }

    _embedding_service = EmbeddingService(embedding_dim=EMBEDDING_DIM)
    _vector_store = SupabaseVectorStore(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        embedding_dim=EMBEDDING_DIM,
    )

    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if neo4j_uri and neo4j_user and neo4j_password:
        _graph_store = GraphStore(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )

    _chunker = DocumentChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    _ingestion_service = DocumentIngestion(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        supabase_bucket=SUPABASE_BUCKET,
        embedding_service=_embedding_service,
        chunker=_chunker,
        graph_store=_graph_store,
    )
    _retrieval_service = HybridRetrieval(
        embedding_service=_embedding_service,
        vector_store=_vector_store,
        graph_store=_graph_store,
    )

    _services_initialized = True
    return {
        "embedding": _embedding_service,
        "vector_store": _vector_store,
        "graph_store": _graph_store,
        "chunker": _chunker,
        "ingestion": _ingestion_service,
        "retrieval": _retrieval_service,
    }


# ── Routes — note: just `user: CurrentUser`, no = Depends() ───────────────

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,   # ✅ correct — Annotated carries the Depends
):
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    services = get_services()
    task_id = str(uuid.uuid4())
    paper_id = str(uuid.uuid4())
    storage_path = f"{current_user.get('user_id')}/{paper_id}/{file.filename}"

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 10MB)")

        _processing_status[task_id] = {
            "status": "queued",
            "progress": 0,
            "filename": file.filename,
            "paper_id": paper_id,
            "storage_path": storage_path,
            "user_id": current_user.get("user_id"),
            "message": "Queued for processing",
        }

        background_tasks.add_task(
            _process_document_background,
            task_id, content, file.filename, paper_id,
            storage_path, current_user.get("user_id"), services["ingestion"],
        )

        return JSONResponse({
            "task_id": task_id,
            "paper_id": paper_id,
            "filename": file.filename,
            "message": "Upload successful, processing started",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


async def _process_document_background(
    task_id, file_bytes, filename, paper_id, storage_path, user_id, ingestion_service
):
    def _progress(status, progress):
        _processing_status[task_id] = {
            "status": "processing", "progress": progress,
            "filename": filename, "paper_id": paper_id,
            "user_id": user_id, "message": status,
        }
    try:
        result = ingestion_service.process_pdf(
            file_bytes=file_bytes, filename=filename,
            progress_callback=_progress, user_id=user_id,
            paper_id=paper_id, storage_path=storage_path,
        )
        _processing_status[task_id] = {
            "status": "completed" if result["success"] else "failed",
            "progress": 100 if result["success"] else 0,
            "filename": filename, "paper_id": paper_id, "user_id": user_id,
            "chunks_created": result.get("chunks_created", 0),
            "message": result.get("message", ""),
            "error": result.get("error"),
        }
    except Exception as e:
        _processing_status[task_id] = {
            "status": "failed", "progress": 0, "filename": filename,
            "paper_id": paper_id, "user_id": user_id,
            "error": str(e), "message": f"Processing failed: {e}",
        }


@router.get("/status/{task_id}")
async def get_processing_status(
    task_id: str,
    current_user: CurrentUser,          # ✅ no = Depends()
):
    if task_id not in _processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _processing_status[task_id]
    if task.get("user_id") and task["user_id"] != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Not authorized to view this task")
    return task


@router.get("/resources")
async def list_resources(
    current_user: CurrentUser,          # ✅ no = Depends()
):
    services = get_services()
    papers = services["vector_store"].get_all_papers(user_id=current_user.get("user_id"))
    return {
        "resources": [
            {
                "paper_id": p.get("id"),
                "filename": p.get("filename"),
                "upload_date": p.get("upload_date"),
                "user_id": p.get("user_id"),
                "storage_path": p.get("storage_path"),
            }
            for p in papers
        ],
        "total": len(papers),
        "user_id": current_user.get("user_id"),
    }


@router.delete("/resources/{paper_id}")
async def delete_resource(
    paper_id: str,
    current_user: CurrentUser,          # ✅ no = Depends()
):
    try:
        uuid.UUID(paper_id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID format.")

    services = get_services()
    papers = services["vector_store"].get_all_papers(user_id=current_user.get("user_id"))
    paper = next((p for p in papers if p.get("id") == paper_id), None)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found or no permission")

    result = services["ingestion"].delete_document(paper_id, paper.get("storage_path"))
    if result.get("success"):
        return {"success": True, "paper_id": paper_id, "message": result.get("message")}
    raise HTTPException(status_code=500, detail=result.get("message", "Deletion failed"))


@router.get("/stats")
async def get_stats(
    current_user: CurrentUser,          # ✅ no = Depends()
):
    services = get_services()
    stats = services["vector_store"].get_stats(user_id=current_user.get("user_id"))
    stats["storage_backend"] = "Supabase PostgreSQL + Supabase Storage"
    stats["storage_bucket"] = SUPABASE_BUCKET
    stats["neo4j_enabled"] = (
        services["graph_store"] is not None and services["graph_store"].enabled
    )
    stats["user_id"] = current_user.get("user_id")
    return stats


@router.post("/search")
async def search_documents(
    query: str,
    top_k: int = 5,
    include_citations: bool = False,
    current_user: CurrentUser = None,   # ✅ File() and Query params need = None here
):
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    services = get_services()
    try:
        results = services["retrieval"].retrieve(
            query=query,
            top_k=top_k,
            user_id=current_user.get("user_id"),
            include_citations=include_citations,
        )
        return {
            "query": query,
            "num_results": len(results.get("chunks", [])),
            "chunks": results.get("chunks", []),
            "citations": results.get("citations"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/system/info")
async def get_system_info():
    # Public — no auth needed
    return {
        "supabase_enabled": True,
        "supabase_url": SUPABASE_URL,
        "supabase_bucket": SUPABASE_BUCKET,
        "embedding_dim": EMBEDDING_DIM,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
