# Backend Components Reference

Quick reference guide to backend modules and their purposes.

## Module Hierarchy

**Import Order (lowest to highest)**:
1. `database/` - Data access layer
2. `utils/` - Business logic and utilities
3. `routers/` - API endpoints
4. `main.py` - Application entry

## Database Layer (`database/`)

### Core Data Access

#### `conversations.py`
**Purpose**: Firestore operations for conversations

**Key Functions**:
- `upsert_conversation()` - Create or update conversation
- `get_conversation()` - Get single conversation
- `get_conversations()` - List conversations with filters
- `delete_conversation()` - Soft delete conversation
- `get_conversation_photos()` - Get photos for conversation

**Firestore Structure**: `users/{uid}/conversations/{conversation_id}`

#### `memories.py`
**Purpose**: Memory storage and retrieval

**Key Functions**:
- `save_memories()` - Save extracted memories
- `get_memories()` - Get user memories with filters
- `update_memory()` - Update memory content
- `delete_memory()` - Delete memory

**Firestore Structure**: `users/{uid}/memories/{memory_id}`

#### `vector_db.py`
**Purpose**: Pinecone vector operations

**Key Functions**:
- `upsert_vector()` - Store conversation embedding
- `upsert_vectors()` - Batch store embeddings
- `query_vectors()` - Semantic similarity search
- `delete_vector()` - Remove embedding

**Usage**: Semantic search for conversations

#### `redis_db.py`
**Purpose**: Redis caching and metadata

**Key Functions**:
- `set_speech_profile_duration()` - Cache profile duration
- `get_speech_profile_duration()` - Get cached duration
- `enable_app()` / `disable_app()` - Manage app state
- `get_enabled_apps()` - Get user's enabled apps
- `cache_user_name()` / `get_cached_user_name()` - User name cache

**Note**: Redis is optional but recommended for performance

#### `action_items.py`
**Purpose**: Task/to-do management

**Key Functions**:
- `save_action_items()` - Save action items
- `get_action_items()` - Get user's action items
- `update_action_item()` - Update task status
- `delete_action_item()` - Delete task

### Supporting Modules

- `users.py` - User data operations
- `apps.py` - App/plugin data
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
- `helpers.py` - Database helper functions

## Utils Layer (`utils/`)

### LLM Processing (`utils/llm/`)

#### `clients.py`
**Purpose**: LLM client configurations

**Key Components**:
- OpenAI client setup
- Embedding model configuration (`text-embedding-3-large`)
- Model selection logic

#### `conversation_processing.py`
**Purpose**: Conversation analysis and structuring

**Key Functions**:
- `_get_structured()` - Extract title, overview, action items, events
- `_should_discard()` - Determine if conversation should be discarded
- `_extract_memories()` - Extract user facts from conversation
- `_save_action_items()` - Save extracted action items

#### `chat.py`
**Purpose**: Chat-related LLM processing

**Key Functions**:
- `generate_initial_message()` - First message in chat
- `requires_context()` - Determine if question needs context
- `extract_topics_and_dates()` - Extract query metadata

### Retrieval System (`utils/retrieval/`)

#### `graph.py`
**Purpose**: LangGraph agentic system

**Key Components**:
- `requires_context()` - Route questions to appropriate path
- LangGraph router configuration
- Tool system integration

**Paths**:
- Simple: Direct LLM response
- Agentic: Full tool access with LangGraph
- Persona: Persona app responses

#### `rag.py`
**Purpose**: Retrieval-Augmented Generation

**Key Functions**:
- Vector search in Pinecone
- Context retrieval from Firestore
- Memory retrieval

#### `tools/` Directory
**Purpose**: LangGraph tools for agentic system

**Available Tools**:
- `conversation_tools.py` - Conversation retrieval
- `memory_tools.py` - Memory operations
- `action_item_tools.py` - Task management
- `calendar_tools.py` - Google Calendar integration
- `gmail_tools.py` - Gmail integration
- `github_tools.py` - GitHub integration
- `notion_tools.py` - Notion integration
- `whoop_tools.py` - Whoop health data
- `twitter_tools.py` - Twitter/X integration
- `perplexity_tools.py` - Web search
- `app_tools.py` - Dynamic app tools

### Conversation Processing (`utils/conversations/`)

#### `process_conversation.py`
**Purpose**: Main conversation processing pipeline

**Flow**:
1. Check if should discard
2. Extract structured data
3. Extract memories
4. Save action items
5. Store in Firestore
6. Generate and store embedding
7. Run enabled apps

#### `postprocess_conversation.py`
**Purpose**: Post-processing after conversation saved

#### `memories.py`
**Purpose**: Memory extraction from conversations

#### `search.py`
**Purpose**: Conversation search functionality

#### `merge_conversations.py`
**Purpose**: Merge related conversations

#### `location.py`
**Purpose**: Geolocation processing

### Speech-to-Text (`utils/stt/`)

#### `streaming.py`
**Purpose**: Real-time STT processing

**Key Functions**:
- `process_audio_dg()` - Deepgram processing
- `process_audio_soniox()` - Soniox processing
- `process_audio_speechmatics()` - Speechmatics processing
- `get_stt_service_for_language()` - Service selection

#### `pre_recorded.py`
**Purpose**: Pre-recorded audio transcription

#### `vad.py`
**Purpose**: Voice Activity Detection

#### `speech_profile.py`
**Purpose**: Speech profile management

#### `speaker_embedding.py`
**Purpose**: Speaker identification

### Other Utilities (`utils/other/`)

#### `storage.py`
**Purpose**: Google Cloud Storage operations

**Key Functions**:
- `upload_profile_audio()` - Upload speech profile
- `get_profile_audio_if_exists()` - Retrieve profile

#### `webhooks.py`
**Purpose**: Webhook processing for apps

#### `notifications.py`
**Purpose**: Push notification handling

#### `timeout.py`
**Purpose**: Request timeout middleware

### Supporting Utilities

- `apps.py` - App/plugin utilities
- `app_integrations.py` - Integration management
- `audio.py` - Audio processing
- `chat.py` - Chat utilities
- `encryption.py` - Data encryption
- `analytics.py` - Analytics tracking
- `onboarding.py` - User onboarding
- `subscription.py` - Subscription management
- `stripe.py` - Stripe payment integration
- `translation.py` - Translation utilities
- `text_utils.py` - Text processing

## Routers Layer (`routers/`)

### Core Endpoints

#### `transcribe.py`
**Purpose**: Real-time audio transcription

**Endpoints**:
- `POST /v4/listen` (WebSocket) - Audio streaming

**Key Functions**:
- `websocket_endpoint()` - WebSocket handler
- Audio processing and forwarding to STT services

#### `conversations.py`
**Purpose**: Conversation management

**Endpoints**:
- `POST /v1/conversations` - Create/finalize conversation
- `GET /v1/conversations` - List conversations
- `GET /v1/conversations/{id}` - Get conversation
- `DELETE /v1/conversations/{id}` - Delete conversation

#### `chat.py`
**Purpose**: Chat system

**Endpoints**:
- `POST /v2/messages` - Send message, get response

**Key Functions**:
- Routes to LangGraph system
- Handles streaming responses

#### `memories.py`
**Purpose**: Memory operations

**Endpoints**:
- `GET /v1/memories` - List memories
- `POST /v1/memories` - Create memory
- `PUT /v1/memories/{id}` - Update memory
- `DELETE /v1/memories/{id}` - Delete memory

#### `action_items.py`
**Purpose**: Task management

**Endpoints**:
- `GET /v1/action-items` - List action items
- `POST /v1/action-items` - Create action item
- `PUT /v1/action-items/{id}` - Update action item

### Developer & Integration

#### `developer.py`
**Purpose**: Developer API

**Endpoints**:
- `GET /v1/dev/user/memories` - Get memories
- `POST /v1/dev/user/memories` - Create memory
- `POST /v1/dev/user/memories/batch` - Batch create
- `GET /v1/dev/user/conversations` - Get conversations
- `POST /v1/dev/user/conversations` - Create conversation
- `GET /v1/dev/user/action-items` - Get action items
- `POST /v1/dev/user/action-items` - Create action item
- `GET /v1/dev/keys` - List API keys
- `POST /v1/dev/keys` - Create API key
- `DELETE /v1/dev/keys/{id}` - Revoke key

#### `mcp.py` & `mcp_sse.py`
**Purpose**: Model Context Protocol server

**Endpoints**:
- `GET /v1/mcp/sse` - SSE endpoint for MCP

#### `apps.py`
**Purpose**: App/plugin management

**Endpoints**:
- `GET /v1/apps` - List apps
- `POST /v1/apps/{id}/install` - Install app
- `DELETE /v1/apps/{id}/uninstall` - Uninstall app
- `GET /v1/apps/{id}/tools` - Get app tools

### Authentication & OAuth

#### `auth.py`
**Purpose**: Core authentication

#### `oauth.py`
**Purpose**: OAuth callbacks

**Endpoints**:
- `GET /v1/auth/callback/google` - Google OAuth
- `GET /v1/auth/callback/apple` - Apple OAuth

#### `custom_auth.py`
**Purpose**: Custom authentication flows

### Supporting Routers

- `integrations.py` - External integrations
- `notifications.py` - Push notifications
- `speech_profile.py` - Speech profile management
- `firmware.py` - Firmware updates
- `users.py` - User management
- `trends.py` - Analytics
- `wrapped.py` - Year-end summaries
- `folders.py` - Conversation folders
- `goals.py` - User goals
- `knowledge_graph.py` - Knowledge graph
- `workflow.py` - Workflow automation
- `imports.py` - Data imports
- `payment.py` - Payment processing
- `sync.py` - Data synchronization
- `updates.py` - App updates
- `task_integrations.py` - Task integrations
- `calendar_meetings.py` - Calendar management
- `agents.py` - Agent management
- `plugins.py` - Plugin management
- `other.py` - Miscellaneous endpoints
- `onboarding.py` - User onboarding
- `announcements.py` - Announcements

## Main Application (`main.py`)

**Purpose**: FastAPI application setup

**Key Components**:
- FastAPI app initialization
- Router registration
- Middleware setup (timeout)
- Firebase initialization
- Modal deployment configuration

## Models (`models/`)

Data models for request/response validation:

- `conversation.py` - Conversation models
- `memories.py` - Memory models
- `chat.py` - Chat models
- `app.py` - App models
- `users.py` - User models
- `task.py` - Action item models
- `shared.py` - Shared models

## Related Documentation

- Architecture: `.cursor/ARCHITECTURE.md`
- API Reference: `.cursor/API_REFERENCE.md`
- Data Flow: `.cursor/DATA_FLOW.md`
- Backend Deep Dive: `docs/doc/developer/backend/backend_deepdive.mdx`
- Chat System: `docs/doc/developer/backend/chat_system.mdx`
