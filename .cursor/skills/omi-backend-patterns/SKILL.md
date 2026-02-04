---
name: omi-backend-patterns
description: "Omi backend patterns conversation processing memory extraction chat system LangGraph FastAPI Firestore Pinecone Redis"
---

# Omi Backend Patterns Skill

This skill provides guidance for working with the Omi backend, including conversation processing, memory extraction, chat system, and LangGraph integration.

## When to Use

Use this skill when:
- Working on backend Python code in `backend/`
- Implementing new API endpoints
- Processing conversations or extracting memories
- Working with the LangGraph chat system
- Integrating with Firestore, Pinecone, or Redis

## Key Patterns

### Conversation Processing

The conversation processing pipeline follows this flow:

1. **Audio arrives via WebSocket** (`/v4/listen`)
2. **Transcription** via Deepgram/Soniox/Speechmatics
3. **Conversation creation** in Firestore (status: "in_progress")
4. **Processing trigger** via `POST /v1/conversations` or timeout
5. **LLM extraction** of structured data:
   - Title and overview
   - Action items
   - Calendar events
   - Memories (user facts)
6. **Storage** in Firestore and Pinecone

**Key Function**: `utils/conversations/process_conversation.py::process_conversation()`

### Memory Extraction

Memories are extracted from conversations using LLM:

```python
from utils.llm.conversation_processing import _extract_memories

memories = await _extract_memories(
    transcript=transcript,
    existing_memories=existing_memories,
)
```

**Categories**: personal, health, work, relationships, preferences

### Chat System Architecture

The chat system uses LangGraph for routing:

1. **Classification**: `requires_context()` determines path
2. **Simple Path**: Direct LLM response (no context needed)
3. **Agentic Path**: Full tool access with LangGraph ReAct agent
4. **Persona Path**: Persona app responses

**Key File**: `utils/retrieval/graph.py`

### Module Hierarchy

**CRITICAL**: Always follow the import hierarchy:

1. `database/` - Data access (lowest)
2. `utils/` - Business logic
3. `routers/` - API endpoints
4. `main.py` - Application entry

**Never import from higher levels in lower levels!**

### Database Patterns

- **Firestore**: Primary database for conversations, memories, users
- **Pinecone**: Vector embeddings for semantic search
- **Redis**: Caching (speech profiles, enabled apps, user names)
- **GCS**: Binary files (audio, photos, speech profiles)

### API Endpoint Patterns

- Use FastAPI routers in `routers/`
- Keep routers thin - business logic in `utils/`
- Use dependency injection for auth
- Return consistent error formats

## Common Tasks

### Adding a New API Endpoint

1. Create router function in appropriate `routers/*.py`
2. Add business logic in `utils/`
3. Use database functions from `database/`
4. Follow error handling patterns
5. Add to router in `main.py`

### Processing Conversations

1. Use `process_conversation()` from `utils/conversations/process_conversation.py`
2. Handle extraction results
3. Store in Firestore and Pinecone
4. Trigger app webhooks if needed

### Adding a Chat Tool

1. Create tool function in `utils/retrieval/tools/`
2. Use `@tool` decorator from LangChain
3. Add to tool loading in `utils/retrieval/tools/app_tools.py`
4. Tool will be available in agentic chat path

## Related Documentation

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **Backend Deep Dive**: `docs/doc/developer/backend/backend_deepdive.mdx` - [View online](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- **Chat System**: `docs/doc/developer/backend/chat_system.mdx` - [View online](https://docs.omi.me/doc/developer/backend/chat_system)
- **Data Storage**: `docs/doc/developer/backend/StoringConversations.mdx` - [View online](https://docs.omi.me/doc/developer/backend/StoringConversations)
- **Transcription**: `docs/doc/developer/backend/transcription.mdx` - [View online](https://docs.omi.me/doc/developer/backend/transcription)
- **Backend Setup**: `docs/doc/developer/backend/Backend_Setup.mdx` - [View online](https://docs.omi.me/doc/developer/backend/Backend_Setup)
- **Backend Architecture**: `.cursor/rules/backend-architecture.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/backend-architecture.mdc` - System architecture and module hierarchy
- `.cursor/rules/backend-api-patterns.mdc` - FastAPI router patterns
- `.cursor/rules/backend-database-patterns.mdc` - Database storage patterns
- `.cursor/rules/backend-llm-patterns.mdc` - LLM integration patterns
- `.cursor/rules/backend-testing.mdc` - Testing patterns
- `.cursor/rules/backend-imports.mdc` - Import rules
- `.cursor/rules/memory-management.mdc` - Memory management

### Subagents
- `.cursor/agents/backend-api-developer/` - Uses this skill for API development
- `.cursor/agents/backend-llm-engineer/` - Uses this skill for LLM integration
- `.cursor/agents/backend-database-engineer/` - Uses this skill for database work

### Commands
- `/backend-setup` - Uses this skill for setup guidance
- `/backend-test` - Uses this skill for testing patterns
- `/backend-deploy` - Uses this skill for deployment patterns
