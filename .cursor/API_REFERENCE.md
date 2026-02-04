# Omi API Reference

Quick reference for all API endpoints in the Omi backend.

## Base URLs

- **Production**: `https://api.omi.me`
- **Development**: Use ngrok or local backend URL

## Authentication

Most endpoints require Firebase authentication via `uid` parameter or Bearer token.

### Developer API Authentication
```
Authorization: Bearer omi_dev_your_api_key_here
```

### MCP Authentication
```
Authorization: Bearer omi_mcp_your_api_key_here
```

## Core Endpoints

### Transcription & Audio

#### `POST /v4/listen` (WebSocket)
Real-time audio streaming and transcription.

**Parameters**:
- `uid` (query): Firebase user ID
- `language` (query, optional): Language code (e.g., "en", "es")

**Returns**: WebSocket connection with bidirectional audio/transcript streaming

**Usage**: See `routers/transcribe.py`

---

### Conversations

#### `POST /v1/conversations`
Create or finalize a conversation after recording.

**Body**: `{}` (empty - conversation created during WebSocket)

**Returns**: Conversation object with structured data

**Usage**: Called after recording ends to trigger processing

#### `GET /v1/conversations`
List user conversations.

**Query Parameters**:
- `limit` (int): Number of conversations to return
- `include_discarded` (bool): Include discarded conversations
- `start_date` (datetime): Filter by start date
- `end_date` (datetime): Filter by end date

**Returns**: List of conversation objects

#### `GET /v1/conversations/{conversation_id}`
Get a specific conversation.

**Returns**: Full conversation with transcript segments

#### `DELETE /v1/conversations/{conversation_id}`
Delete a conversation.

---

### Chat

#### `POST /v2/messages`
Send a chat message and get AI response.

**Body**:
```json
{
  "message": "What did I discuss yesterday?",
  "conversation_id": "optional_conversation_id"
}
```

**Returns**: Streaming response with citations

**Routing**: 
- Simple questions → Direct LLM response
- Context needed → LangGraph agentic path with tool calls
- Persona questions → Persona app path

**Usage**: See `routers/chat.py` and `utils/retrieval/graph.py`

---

### Memories

#### `GET /v1/memories`
Get user memories.

**Query Parameters**:
- `limit` (int): Number of memories
- `offset` (int): Pagination offset
- `categories` (array): Filter by categories

**Returns**: List of memory objects

#### `POST /v1/memories`
Create a memory.

**Body**:
```json
{
  "content": "User prefers morning workouts",
  "category": "health"
}
```

#### `PUT /v1/memories/{memory_id}`
Update a memory.

#### `DELETE /v1/memories/{memory_id}`
Delete a memory.

---

### Action Items

#### `GET /v1/action-items`
Get user action items (tasks).

**Query Parameters**:
- `status` (string): Filter by status (pending, completed)
- `limit` (int): Number of items

**Returns**: List of action item objects

#### `POST /v1/action-items`
Create an action item.

#### `PUT /v1/action-items/{action_item_id}`
Update an action item (e.g., mark complete).

---

### Apps/Plugins

#### `GET /v1/apps`
List available apps/plugins.

**Returns**: List of app objects

#### `POST /v1/apps/{app_id}/install`
Install an app for the user.

#### `DELETE /v1/apps/{app_id}/uninstall`
Uninstall an app.

#### `GET /v1/apps/{app_id}/tools`
Get chat tools provided by an app.

---

### Developer API

**Base Path**: `/v1/dev`

#### `GET /v1/dev/user/memories`
Get user memories (Developer API).

**Authentication**: Bearer token with `omi_dev_` prefix

#### `POST /v1/dev/user/memories`
Create a memory (Developer API).

#### `POST /v1/dev/user/memories/batch`
Create up to 25 memories at once.

#### `GET /v1/dev/user/conversations`
Get user conversations (Developer API).

#### `POST /v1/dev/user/conversations`
Create conversation from text (Developer API).

#### `GET /v1/dev/user/action-items`
Get user action items (Developer API).

#### `POST /v1/dev/user/action-items`
Create action item (Developer API).

#### `GET /v1/dev/keys`
List all API keys for the user.

#### `POST /v1/dev/keys`
Create a new API key.

#### `DELETE /v1/dev/keys/{key_id}`
Revoke an API key.

**Usage**: See `routers/developer.py`

---

### MCP Server

**Base Path**: `/v1/mcp`

#### `GET /v1/mcp/sse` (Server-Sent Events)
MCP server endpoint for SSE connections.

**Authentication**: Bearer token with `omi_mcp_` prefix

**Tools Available**:
- `get_memories` - Retrieve memories
- `create_memory` - Create a memory
- `edit_memory` - Edit a memory
- `delete_memory` - Delete a memory
- `get_conversations` - Retrieve conversations

**Usage**: See `routers/mcp_sse.py` and `docs/doc/developer/MCP.mdx`

---

### Webhooks (App Integrations)

#### `POST /v1/apps/{app_id}/webhook/memory-created`
Webhook endpoint for memory creation triggers.

**Body**: Memory object

**Usage**: Apps can register webhooks to receive notifications when memories are created.

#### `POST /v1/apps/{app_id}/webhook/transcript`
Webhook endpoint for real-time transcript processing.

**Body**: Transcript segment

**Usage**: Apps can process live transcripts as conversations happen.

**Usage**: See `docs/doc/developer/apps/Integrations.mdx`

---

### OAuth

#### `GET /v1/auth/callback/google`
Google OAuth callback.

#### `GET /v1/auth/callback/apple`
Apple OAuth callback.

**Usage**: See `routers/oauth.py` and `docs/doc/developer/apps/Oauth.mdx`

---

## Router Organization

All routers are in `backend/routers/`:

- `transcribe.py` - Audio streaming and transcription
- `conversations.py` - Conversation management
- `chat.py` - Chat system
- `memories.py` - Memory operations
- `action_items.py` - Task management
- `apps.py` - App/plugin management
- `developer.py` - Developer API
- `mcp.py` - MCP server (stdio)
- `mcp_sse.py` - MCP server (SSE)
- `oauth.py` - OAuth callbacks
- `auth.py` - Core authentication
- `integrations.py` - External integrations
- `notifications.py` - Push notifications
- `speech_profile.py` - Speech profile management
- `firmware.py` - Firmware updates
- `users.py` - User management
- `trends.py` - Analytics and trends
- `wrapped.py` - Year-end summaries
- `folders.py` - Conversation folders
- `goals.py` - User goals
- `knowledge_graph.py` - Knowledge graph operations

## Error Responses

All endpoints return consistent error formats:

```json
{
  "detail": "Error message here"
}
```

**HTTP Status Codes**:
- `200 OK` - Success
- `204 No Content` - Success with no body
- `400 Bad Request` - Invalid parameters
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

## Rate Limits

- **Developer API**: 100 requests/minute per API key, 10,000 requests/day per user
- **Chat API**: Varies by subscription tier
- **Transcription**: Based on Deepgram usage limits

## Related Documentation

- API Overview: `docs/doc/developer/api/overview.mdx`
- Memories API: `docs/doc/developer/api/memories.mdx`
- Conversations API: `docs/doc/developer/api/conversations.mdx`
- Action Items API: `docs/doc/developer/api/action-items.mdx`
- Keys API: `docs/doc/developer/api/keys.mdx`
- MCP: `docs/doc/developer/MCP.mdx`
- Plugin Development: `docs/doc/developer/apps/Introduction.mdx`
