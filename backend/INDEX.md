# Backend Module Index

Quick reference guide to backend modules and their purposes.

## Module Hierarchy

**Import Order (lowest to highest)**:
1. `database/` - Data access layer
2. `utils/` - Business logic and utilities
3. `routers/` - API endpoints
4. `main.py` - Application entry

## Database Layer (`database/`)

### Core Modules

- `conversations.py` - Firestore conversation operations
- `memories.py` - Memory storage and retrieval
- `vector_db.py` - Pinecone vector operations
- `redis_db.py` - Redis caching
- `action_items.py` - Task management
- `users.py` - User data operations
- `apps.py` - App/plugin data

### Supporting Modules

- `auth.py` - Authentication data
- `dev_api_key.py` - Developer API key management
- `mcp_api_key.py` - MCP API key management
- `notifications.py` - Notification data
- `calendar_meetings.py` - Calendar event storage
- `folders.py` - Conversation folder management
- `goals.py` - User goals
- `knowledge_graph.py` - Knowledge graph operations
- `wrapped.py` - Year-end summary data
- `trends.py` - Analytics data
- `cache.py` / `cache_manager.py` - Caching utilities

## Utils Layer (`utils/`)

### LLM Processing (`utils/llm/`)

- `clients.py` - LLM client configurations
- `conversation_processing.py` - Conversation analysis
- `chat.py` - Chat-related processing

### Retrieval System (`utils/retrieval/`)

- `graph.py` - LangGraph agentic system
- `rag.py` - Retrieval-Augmented Generation
- `tools/` - LangGraph tools

### Conversation Processing (`utils/conversations/`)

- `process_conversation.py` - Main processing pipeline
- `postprocess_conversation.py` - Post-processing
- `memories.py` - Memory extraction
- `search.py` - Conversation search

### Speech-to-Text (`utils/stt/`)

- `streaming.py` - Real-time STT processing
- `pre_recorded.py` - Pre-recorded transcription
- `vad.py` - Voice Activity Detection

## Routers Layer (`routers/`)

### Core Endpoints

- `transcribe.py` - Audio streaming
- `conversations.py` - Conversation management
- `chat.py` - Chat system
- `memories.py` - Memory operations
- `action_items.py` - Task management

### Developer & Integration

- `developer.py` - Developer API
- `mcp.py` / `mcp_sse.py` - MCP server
- `apps.py` - App management

### Authentication

- `auth.py` - Core authentication
- `oauth.py` - OAuth callbacks
- `custom_auth.py` - Custom auth flows

## Main Application

- `main.py` - FastAPI app setup and configuration

## Related Documentation

- Backend Components: `.cursor/BACKEND_COMPONENTS.md`
- Backend Architecture: `.cursor/rules/backend-architecture.mdc`
- Backend Deep Dive: `docs/doc/developer/backend/backend_deepdive.mdx`
