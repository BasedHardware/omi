---
name: omi-api-integration
description: "Omi API integration Developer API MCP server webhook OAuth authentication rate limiting API keys"
---

# Omi API Integration Skill

This skill provides guidance for integrating with Omi APIs, including Developer API, MCP server, and webhook integrations.

## When to Use

Use this skill when:
- Building integrations with Omi
- Using the Developer API
- Setting up MCP server
- Creating webhook integrations
- Working with OAuth flows

## Key Patterns

### Developer API

**Base URL**: `https://api.omi.me/v1/dev`

**Authentication**: Bearer token with `omi_dev_` prefix

#### Getting API Key

1. Open Omi app
2. Settings → Developer → Create Key
3. Copy key immediately (won't be shown again)

#### Making Requests

```python
import requests

headers = {
    "Authorization": "Bearer omi_dev_your_key_here"
}

# Get memories
response = requests.get(
    "https://api.omi.me/v1/dev/user/memories",
    headers=headers,
    params={"limit": 10}
)

memories = response.json()
```

#### Available Endpoints

- `GET /v1/dev/user/memories` - Get memories
- `POST /v1/dev/user/memories` - Create memory
- `POST /v1/dev/user/memories/batch` - Create up to 25 memories
- `GET /v1/dev/user/conversations` - Get conversations
- `POST /v1/dev/user/conversations` - Create conversation
- `GET /v1/dev/user/action-items` - Get action items
- `POST /v1/dev/user/action-items` - Create action item

### MCP Server

**Purpose**: Enable AI assistants (like Claude) to interact with Omi data

#### Hosted MCP Server (SSE)

**URL**: `https://api.omi.me/v1/mcp/sse`

**Authentication**: Bearer token with `omi_mcp_` prefix

#### Available Tools

- `get_memories` - Retrieve memories
- `create_memory` - Create a memory
- `edit_memory` - Edit a memory
- `delete_memory` - Delete a memory
- `get_conversations` - Retrieve conversations

#### Configuration

```json
{
  "mcpServers": {
    "omi": {
      "url": "https://api.omi.me/v1/mcp/sse",
      "apiKey": "omi_mcp_your_key_here"
    }
  }
}
```

### Webhook Integrations

#### Memory Creation Webhook

**Trigger**: When a memory is created

**Endpoint**: `POST /webhook/memory-created`

**Payload**:
```json
{
  "id": "memory_id",
  "content": "Memory content",
  "category": "personal",
  "user_id": "user_uid",
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Real-time Transcript Webhook

**Trigger**: As transcript segments arrive

**Endpoint**: `POST /webhook/transcript`

**Payload**:
```json
{
  "text": "Transcript segment",
  "timestamp": 1234567890,
  "conversation_id": "conv_id",
  "user_id": "user_uid"
}
```

### OAuth Integration

#### Google OAuth

1. Create OAuth 2.0 Client in Google Cloud Console
2. Configure authorized origins and redirect URIs
3. Use client ID and secret in app

#### Apple OAuth

1. Create App ID with Sign In with Apple
2. Create Services ID
3. Create private key (.p8 file)
4. Configure in Firebase Console

## Common Tasks

### Creating an Integration

1. Set up webhook endpoint
2. Register webhook URL in app configuration
3. Handle webhook payloads
4. Process and react to events

### Using Developer API

1. Generate API key in Omi app
2. Store key securely (environment variable)
3. Make authenticated requests
4. Handle rate limits (100/min, 10,000/day)

### Setting Up MCP

1. Generate MCP API key in Omi app
2. Configure MCP client (Claude Desktop, etc.)
3. Use tools to interact with Omi data

## Related Documentation

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **API Overview**: `docs/doc/developer/api/overview.mdx` - [View online](https://docs.omi.me/doc/developer/api/overview)
- **API Endpoints**: `docs/api-reference/` - [View online](https://docs.omi.me/api-reference/)
- **Memories API**: `docs/doc/developer/api/memories.mdx` - [View online](https://docs.omi.me/doc/developer/api/memories)
- **Conversations API**: `docs/doc/developer/api/conversations.mdx` - [View online](https://docs.omi.me/doc/developer/api/conversations)
- **Action Items API**: `docs/doc/developer/api/action-items.mdx` - [View online](https://docs.omi.me/doc/developer/api/action-items)
- **MCP**: `docs/doc/developer/MCP.mdx` - [View online](https://docs.omi.me/doc/developer/MCP)
- **Plugin Development**: `docs/doc/developer/apps/Introduction.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Introduction)
- **OAuth**: `docs/doc/developer/apps/Oauth.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Oauth)

## Related Cursor Resources

### Rules
- `.cursor/rules/backend-api-patterns.mdc` - Backend API patterns
- `.cursor/rules/backend-architecture.mdc` - Backend architecture
- `.cursor/rules/plugin-development.mdc` - Plugin development patterns
- `.cursor/rules/web-nextjs-patterns.mdc` - Web API integration

### Subagents
- `.cursor/agents/backend-api-developer/` - Uses this skill for API development
- `.cursor/agents/plugin-developer/` - Uses this skill for plugin integration
- `.cursor/agents/web-developer/` - Uses this skill for web integration
- `.cursor/agents/sdk-developer/` - Uses this skill for SDK development

### Commands
- `/backend-setup` - Uses this skill for API setup
- `/create-plugin` - Uses this skill for plugin integration
- `/update-api-docs` - Uses this skill for API documentation
