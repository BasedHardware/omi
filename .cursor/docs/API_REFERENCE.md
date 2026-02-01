# Omi API Reference

Quick reference for API endpoints in the Omi backend. **Two distinct APIs** use different auth and paths.

## Base URLs

- **Production**: `https://api.omi.me`
- **Development**: Use ngrok or local backend URL

---

## Authentication

### User/App API (Firebase)

Used by the Omi app. Most endpoints require Firebase authentication via `uid` (from Firebase ID token) or session.

- **Typical use**: Mobile app, web app
- **Auth**: Firebase ID token / Bearer token from Firebase Auth

### Developer API (`/v1/dev/*`)

Used for programmatic access to a user’s data (memories, conversations, action items). Create keys in **Settings → Developer → Create Key** in the Omi app.

```
Authorization: Bearer omi_dev_your_api_key_here
```

- **Typical use**: Integrations, scripts, third-party apps
- **Full docs**: `docs/doc/developer/api/overview.mdx`, `memories.mdx`, `conversations.mdx`, `action-items.mdx`, `keys.mdx`

### MCP API (`/v1/mcp/*`)

For MCP (Model Context Protocol) consumers.

```
Authorization: Bearer omi_mcp_your_api_key_here
```

- **Full docs**: `docs/doc/developer/MCP.mdx`

---

## User/App API (Firebase auth)

Endpoints used by the Omi app. Authenticate with Firebase.

### Transcription & Audio

#### `WS /v4/listen` (WebSocket)

Real-time audio streaming and transcription.

- **Parameters**: `uid` (query), `language` (query, optional)
- **Usage**: `routers/transcribe.py`

### Conversations

- `POST /v1/conversations` – Create/finalize conversation after recording
- `GET /v1/conversations` – List conversations (`limit`, `include_discarded`, `start_date`, `end_date`)
- `GET /v1/conversations/{id}` – Get one conversation
- `PATCH /v1/conversations/{id}/title`, `.../visibility`, `.../starred`, `.../action-items`, `.../events`
- `DELETE /v1/conversations/{id}` – Delete conversation
- `POST /v1/conversations/search`, `POST /v1/conversations/merge`, etc.

**Usage**: `routers/conversations.py`

### Memories

- `GET /v3/memories` – List memories (`limit`, `offset`)
- `POST /v3/memories` – Create memory
- `PATCH /v3/memories/{id}`, `PATCH /v3/memories/{id}/visibility`
- `DELETE /v3/memories/{id}`, `DELETE /v3/memories`

**Usage**: `routers/memories.py`

### Action Items

- `GET /v1/action-items` – List action items
- `GET /v1/action-items/{id}` – Get one
- `POST /v1/action-items`, `POST /v1/action-items/batch`
- `PATCH /v1/action-items/{id}`, `PATCH /v1/action-items/{id}/completed`
- `DELETE /v1/action-items/{id}`
- `GET /v1/conversations/{id}/action-items`, `DELETE /v1/conversations/{id}/action-items`

**Usage**: `routers/action_items.py`

### Chat

- `POST /v2/messages` – Send message, receive streaming AI response
- `GET /v2/messages`, `DELETE /v2/messages`, `POST /v2/initial-message`
- `POST /v2/voice-messages`, `POST /v2/voice-message/transcribe`
- `POST /v2/files`, `POST /v1/files`

**Usage**: `routers/chat.py`, `utils/retrieval/graph.py`

### Goals

- `GET /v1/goals` – Get current active goal
- `GET /v1/goals/all` – Get all active goals (up to 3)
- `POST /v1/goals` – Create goal
- `PATCH /v1/goals/{goal_id}` – Update goal
- `PATCH /v1/goals/{goal_id}/progress` – Update goal progress
- `GET /v1/goals/{goal_id}/history` – Get goal history
- `DELETE /v1/goals/{goal_id}` – Delete goal
- `GET /v1/goals/suggest` – Get goal suggestions
- `GET /v1/goals/{goal_id}/advice` – Get advice for specific goal
- `GET /v1/goals/advice` – Get general goal advice
- `POST /v1/goals/extract-progress` – Extract progress from conversation

**Usage**: `routers/goals.py`

### Folders

- `GET /v1/folders` – List all folders
- `POST /v1/folders` – Create folder
- `GET /v1/folders/{folder_id}` – Get folder
- `PATCH /v1/folders/{folder_id}` – Update folder
- `DELETE /v1/folders/{folder_id}` – Delete folder
- `POST /v1/folders/reorder` – Reorder folders
- `GET /v1/folders/{folder_id}/conversations` – Get conversations in folder
- `PATCH /v1/conversations/{conversation_id}/folder` – Move conversation to folder
- `POST /v1/folders/{folder_id}/conversations/bulk-move` – Bulk move conversations

**Usage**: `routers/folders.py`

### Knowledge Graph

- `GET /v1/knowledge-graph` – Get knowledge graph
- `POST /v1/knowledge-graph/rebuild` – Rebuild knowledge graph
- `DELETE /v1/knowledge-graph` – Delete knowledge graph

**Usage**: `routers/knowledge_graph.py`

### Calendar Meetings

- `POST /v1/calendar/meetings` – Store calendar meeting context
- `GET /v1/calendar/meetings/{meeting_id}` – Get meeting context
- `GET /v1/calendar/meetings` – List meetings

**Usage**: `routers/calendar_meetings.py`

### Workflow

- `POST /v1/workflow/...` – Workflow automation endpoints
- `GET /v1/workflow/...` – Workflow status endpoints

**Usage**: `routers/workflow.py`

### Agents

- `POST /v1/agents/hume/callback` – Hume AI callback endpoint

**Usage**: `routers/agents.py`

### Users, Apps, Integrations, etc.

- `routers/users.py` – Profile, webhooks, people, language, etc.
- `routers/apps.py` – Apps/plugins
- `routers/integrations.py`, `routers/task_integrations.py`, `routers/oauth.py`
- `routers/notifications.py`, `routers/firmware.py`, `routers/updates.py`, etc.

---

## Developer API (`/v1/dev/*`)

**Auth**: `Authorization: Bearer omi_dev_<key>`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/dev/keys` | List API keys |
| POST | `/v1/dev/keys` | Create API key |
| DELETE | `/v1/dev/keys/{key_id}` | Revoke API key |
| GET | `/v1/dev/user/memories` | List memories (`limit`, `offset`, `categories`) |
| POST | `/v1/dev/user/memories` | Create memory |
| POST | `/v1/dev/user/memories/batch` | Create up to 25 memories |
| PATCH | `/v1/dev/user/memories/{id}` | Update memory |
| DELETE | `/v1/dev/user/memories/{id}` | Delete memory |
| GET | `/v1/dev/user/conversations` | List conversations (`limit`, `offset`, `start_date`, `end_date`, `categories`, `include_transcript`) |
| GET | `/v1/dev/user/conversations/{id}` | Get one conversation |
| POST | `/v1/dev/user/conversations` | Create conversation from text |
| POST | `/v1/dev/user/conversations/from-segments` | Create from transcript segments |
| PATCH | `/v1/dev/user/conversations/{id}` | Update conversation |
| DELETE | `/v1/dev/user/conversations/{id}` | Delete conversation |
| GET | `/v1/dev/user/action-items` | List action items |
| POST | `/v1/dev/user/action-items` | Create action item |
| POST | `/v1/dev/user/action-items/batch` | Create up to 50 action items |
| PATCH | `/v1/dev/user/action-items/{id}` | Update action item |
| DELETE | `/v1/dev/user/action-items/{id}` | Delete action item |

**Usage**: `routers/developer.py`  
**Docs**: `docs/doc/developer/api/overview.mdx`, `memories.mdx`, `conversations.mdx`, `action-items.mdx`, `keys.mdx`

---

## MCP Server (`/v1/mcp/*`)

**Auth**: `Authorization: Bearer omi_mcp_<key>`

### SSE Endpoints (MCP Protocol)

- `POST /v1/mcp/sse` – SSE streamable HTTP (main MCP endpoint)
- `GET /v1/mcp/sse` – SSE connection for server-initiated messages
- `DELETE /v1/mcp/sse` – Delete/terminate session
- `GET /v1/mcp/sse/info` – Get server information

**Usage**: `routers/mcp_sse.py`

### REST API Endpoints

- `GET /v1/mcp/keys` – List MCP API keys
- `POST /v1/mcp/keys` – Create MCP API key
- `DELETE /v1/mcp/keys/{key_id}` – Revoke MCP API key
- `GET /v1/mcp/memories` – List memories
- `POST /v1/mcp/memories` – Create memory
- `PATCH /v1/mcp/memories/{memory_id}` – Edit memory
- `DELETE /v1/mcp/memories/{memory_id}` – Delete memory
- `GET /v1/mcp/conversations` – List conversations

**Usage**: `routers/mcp.py`, `routers/mcp_sse.py`  
**Docs**: `docs/doc/developer/MCP.mdx`

---

## Router Overview

| Router | Purpose |
|--------|---------|
| `transcribe.py` | Audio streaming, transcription |
| `conversations.py` | User conversations (app) |
| `memories.py` | User memories (app, `/v3/memories`) |
| `action_items.py` | Action items (app) |
| `chat.py` | Chat, messages |
| `developer.py` | Developer API (`/v1/dev/*`) |
| `mcp_sse.py` | MCP over SSE |
| `mcp.py` | MCP REST API (keys, memories, conversations) |
| `users.py` | User profile, webhooks, people, language, etc. |
| `apps.py` | Apps/plugins |
| `oauth.py` | OAuth callbacks |
| `auth.py` | Authentication |
| `integrations.py` | Integrations |
| `task_integrations.py` | Task management integrations (Asana, ClickUp, etc.) |
| `goals.py` | Goals and progress tracking |
| `folders.py` | Conversation folders/organization |
| `knowledge_graph.py` | Knowledge graph operations |
| `workflow.py` | Workflow automation |
| `calendar_meetings.py` | Calendar meeting integration |
| `agents.py` | AI agents |
| `notifications.py` | Push notifications |
| `firmware.py` | Firmware management |
| `updates.py` | App updates |
| `trends.py` | Analytics and trends |
| Others | Additional routers for specific features |

---

## Error Responses

```json
{ "detail": "Error message" }
```

Common status codes: `200`, `204`, `400`, `401`, `403`, `404`, `422`, `429`, `500`.

---

## Related Documentation

- Developer API: `docs/doc/developer/api/overview.mdx`, `memories.mdx`, `conversations.mdx`, `action-items.mdx`, `keys.mdx`
- MCP: `docs/doc/developer/MCP.mdx`
- Apps: `docs/doc/developer/apps/Introduction.mdx`, `Integrations.mdx`, `Oauth.mdx`
