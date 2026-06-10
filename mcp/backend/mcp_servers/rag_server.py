"""
MCP Server for Research RAG with Supabase Integration
Provides retrieval-only access to the knowledge base
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Any, Dict, List

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from mcp.types import (
    Resource, 
    Tool, 
    TextContent,
    ListToolsResult,
    CallToolResult
)
from dotenv import load_dotenv

from knowledge_engine.embedding_service import EmbeddingService
from knowledge_engine.vector_store import SupabaseVectorStore
from knowledge_engine.graph_store import GraphStore
from knowledge_engine.retrieval import HybridRetrieval

# Load environment variables
load_dotenv()

# Initialize MCP server
server = Server("research-rag")

# Initialize knowledge engine components
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY"))
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Check for required Supabase configuration
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in environment variables", file=sys.stderr)
    print("The server will start but retrieval will fail until these are configured", file=sys.stderr)

# Initialize services
try:
    embedding_service = EmbeddingService(embedding_dim=EMBEDDING_DIM)
    print(f"✅ Embedding service initialized (dim={EMBEDDING_DIM})", file=sys.stderr)
except Exception as e:
    print(f"❌ Failed to initialize embedding service: {e}", file=sys.stderr)
    embedding_service = None

# Initialize Supabase vector store
vector_store = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        vector_store = SupabaseVectorStore(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY,
            embedding_dim=EMBEDDING_DIM
        )
        print("✅ Supabase vector store initialized", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize Supabase vector store: {e}", file=sys.stderr)

# Initialize graph store (optional)
graph_store = None
if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
    try:
        graph_store = GraphStore(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE
        )
        print("✅ Neo4j graph store initialized", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize Neo4j graph store: {e}", file=sys.stderr)
        graph_store = None

# Initialize retrieval service
retrieval_service = None
if embedding_service and vector_store:
    try:
        retrieval_service = HybridRetrieval(
            embedding_service=embedding_service,
            vector_store=vector_store,
            graph_store=graph_store
        )
        print("✅ Retrieval service initialized", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize retrieval service: {e}", file=sys.stderr)


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List all indexed research papers as resources"""
    if not vector_store:
        return []
    
    try:
        resources = vector_store.get_all_papers()
        
        return [
            Resource(
                uri=f"paper://{r['id']}",
                name=r['filename'],
                mimeType="application/pdf",
                description=f"Research paper: {r['filename']} (Uploaded: {r.get('upload_date', 'unknown')})"
            )
            for r in resources
        ]
    except Exception as e:
        print(f"Error listing resources: {e}", file=sys.stderr)
        return []


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """
    List available RAG tools
    """
    tools = [
        Tool(
            name="retrieve_context",
            description="""Retrieve relevant context from indexed user resources. 
Returns top-k text chunks that are most relevant to the query.
Use this when you need to find information from the knowledge base.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or question"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    },
                    "include_citations": {
                        "type": "boolean",
                        "description": "Include citation graph information (requires Neo4j)",
                        "default": False
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID for filtering resources (optional)",
                        "default": None
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_resources_info",
            description="Get information about all indexed resources including counts and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User ID for filtering resources (optional)",
                        "default": None
                    },
                    "detailed": {
                        "type": "boolean",
                        "description": "Return detailed resource information",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="get_system_stats",
            description="Get statistics about the RAG system including document and chunk counts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User ID for filtering stats (optional)",
                        "default": None
                    }
                }
            }
        )
    ]
    
    return tools


@server.call_tool()
async def handle_call_tool(name: str, arguments: Optional[dict] = None) -> list[TextContent]:
    """
    Handle tool calls
    """
    arguments = arguments or {}
    
    if name == "retrieve_context":
        return await handle_retrieve_context(arguments)
    elif name == "list_resources_info":
        return await handle_list_resources_info(arguments)
    elif name == "get_system_stats":
        return await handle_get_system_stats(arguments)
    else:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Unknown tool: {name}"
            }, indent=2)
        )]


async def handle_retrieve_context(arguments: dict) -> list[TextContent]:
    """Handle retrieve_context tool call"""
    query = arguments.get("query", "")
    top_k = arguments.get("top_k", 5)
    include_citations = arguments.get("include_citations", False)
    user_id = arguments.get("user_id")
    
    if not query:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Query cannot be empty"
            }, indent=2)
        )]
    
    # Check if retrieval service is available
    if not retrieval_service:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Retrieval service not available. Please check Supabase configuration.",
                "query": query,
                "num_results": 0,
                "chunks": []
            }, indent=2)
        )]
    
    try:
        # Perform retrieval
        results = retrieval_service.retrieve(
            query=query,
            top_k=top_k,
            user_id=user_id,
            include_citations=include_citations,
        )
        
        # Format response
        response = {
            "query": query,
            "num_results": len(results.get("chunks", [])),
            "chunks": [
                {
                    "text": chunk["text"],
                    "score": chunk["score"],
                    "source": chunk["metadata"].get("filename", "unknown"),
                    "paper_id": chunk.get("paper_id"),
                    "chunk_index": chunk.get("metadata", {}).get("chunk_id", -1)
                }
                for chunk in results.get("chunks", [])
            ]
        }
        
        # Add citations if requested and available
        if include_citations and results.get("citations"):
            response["citations"] = results["citations"]
        
        return [TextContent(
            type="text",
            text=json.dumps(response, indent=2)
        )]
        
    except Exception as e:
        print(f"Retrieval error: {e}", file=sys.stderr)
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Retrieval failed: {str(e)}",
                "query": query,
                "num_results": 0,
                "chunks": []
            }, indent=2)
        )]


async def handle_list_resources_info(arguments: dict) -> list[TextContent]:
    """Handle list_resources_info tool call"""
    if not vector_store:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Vector store not available",
                "total_resources": 0,
                "resources": []
            }, indent=2)
        )]
    
    try:
        user_id = arguments.get("user_id")
        detailed = arguments.get("detailed", False)
        
        resources = vector_store.get_all_papers(user_id=user_id)
        
        if detailed:
            response = {
                "total_resources": len(resources),
                "resources": resources
            }
        else:
            response = {
                "total_resources": len(resources),
                "resources": [
                    {
                        "id": r["id"],
                        "filename": r["filename"],
                        "upload_date": r.get("upload_date"),
                        "chunk_count": r.get("chunk_count", "unknown")
                    }
                    for r in resources
                ]
            }
        
        return [TextContent(
            type="text",
            text=json.dumps(response, indent=2)
        )]
        
    except Exception as e:
        print(f"Error listing resources: {e}", file=sys.stderr)
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Failed to list resources: {str(e)}"
            }, indent=2)
        )]


async def handle_get_system_stats(arguments: dict) -> list[TextContent]:
    """Handle get_system_stats tool call"""
    if not vector_store:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Vector store not available",
                "stats": {
                    "document_count": 0,
                    "chunk_count": 0
                },
                "vector_store": "Supabase PostgreSQL",
                "embedding_dimension": EMBEDDING_DIM,
                "graph_store_enabled": graph_store is not None
            }, indent=2)
        )]
    
    try:
        user_id = arguments.get("user_id")
        stats = vector_store.get_stats(user_id=user_id)
        
        response = {
            "stats": stats,
            "vector_store": "Supabase PostgreSQL",
            "embedding_dimension": EMBEDDING_DIM,
            "graph_store_enabled": graph_store is not None
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(response, indent=2)
        )]
        
    except Exception as e:
        print(f"Error getting stats: {e}", file=sys.stderr)
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Failed to get system stats: {str(e)}"
            }, indent=2)
        )]


async def main():
    """Run the MCP server using stdio transport"""
    print("Starting Research RAG MCP Server...", file=sys.stderr)
    print(f"Vector Store: {'Supabase PostgreSQL' if vector_store else 'Not initialized'}", file=sys.stderr)
    print(f"Embedding Dimension: {EMBEDDING_DIM}", file=sys.stderr)
    print(f"Graph Store: {'Enabled' if graph_store else 'Disabled'}", file=sys.stderr)
    print(f"Retrieval Service: {'Available' if retrieval_service else 'Not available'}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="research-rag",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())