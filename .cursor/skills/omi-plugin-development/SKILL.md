---
name: omi-plugin-development
description: "Omi plugin app development webhook patterns chat tools OAuth flows prompt-based apps integration apps FastAPI Express"
---

# Omi Plugin Development Skill

This skill provides guidance for developing Omi plugins/apps, including webhook patterns, chat tools, and OAuth flows.

## When to Use

Use this skill when:
- Creating new Omi plugins/apps
- Implementing webhook handlers
- Adding chat tools for LangGraph
- Setting up OAuth integrations
- Building prompt-based apps

## Key Patterns

### Plugin Types

#### 1. Prompt-Based Apps
**No server required** - Just define prompts

- **Chat prompts**: Customize AI personality
- **Memory prompts**: Customize memory extraction

#### 2. Integration Apps
**Requires server endpoint** - Webhook-based

- **Memory triggers**: Webhook on memory creation
- **Real-time transcript**: Webhook for live transcripts
- **Chat tools**: Custom tools for LangGraph
- **Audio streaming**: Raw audio processing

### Webhook Patterns

#### Memory Creation Webhook

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class MemoryWebhook(BaseModel):
    id: str
    content: str
    category: str
    user_id: str

@app.post("/webhook/memory-created")
async def memory_created(webhook: MemoryWebhook):
    """Called when a memory is created."""
    # Process memory
    # Can create new memories via API
    # Can trigger actions
    return {"status": "processed"}
```

#### Real-time Transcript Webhook

```python
@app.post("/webhook/transcript")
async def transcript_segment(segment: dict):
    """Called with live transcript segments."""
    text = segment.get("text")
    
    # Process in real-time
    if "hey omi" in text.lower():
        await trigger_action()
    
    return {"status": "received"}
```

### Chat Tools

#### Creating a Chat Tool

```python
from langchain.tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """Description of what this tool does.
    
    Args:
        query: The search query
        
    Returns:
        Results as a string
    """
    result = perform_search(query)
    return json.dumps(result)

# Register in app configuration
CHAT_TOOLS = [my_custom_tool]
```

**Usage**: Tool becomes available in agentic chat path when app is enabled

### OAuth Integration

#### Setting Up OAuth

```python
from authlib.integrations.fastapi_oauth2 import OAuth2

oauth = OAuth2(
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
)

@app.get("/auth")
async def auth():
    return await oauth.google.authorize_redirect(
        redirect_uri="https://your-app.com/callback"
    )
```

### Plugin Configuration

#### App Manifest

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "description": "Plugin description",
  "capabilities": [
    "memory_trigger",
    "real_time_transcript",
    "chat_tools"
  ],
  "webhook_url": "https://your-app.com/webhook"
}
```

## Common Tasks

### Creating a New Plugin

1. Choose plugin type (prompt-based or integration)
2. Set up server (if integration app)
3. Implement webhook handlers
4. Register plugin in Omi app
5. Test with webhook.site first

### Adding Chat Tools

1. Create tool function with `@tool` decorator
2. Write clear tool description
3. Register in app configuration
4. Tool becomes available when app enabled

### Setting Up OAuth

1. Create OAuth app in provider (Google, Apple, etc.)
2. Configure redirect URIs
3. Implement OAuth flow in plugin
4. Store tokens securely

## Best Practices

1. **Error Handling**: Handle webhook errors gracefully
2. **Idempotency**: Make webhooks idempotent
3. **Rate Limiting**: Implement rate limiting
4. **Security**: Verify webhook signatures
5. **Documentation**: Document your plugin API
6. **Testing**: Test with webhook.site first

## Related Documentation

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **Plugin Introduction**: `docs/doc/developer/apps/Introduction.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Introduction)
- **Integrations**: `docs/doc/developer/apps/Integrations.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Integrations)
- **Chat Tools**: `docs/doc/developer/apps/ChatTools.mdx` - [View online](https://docs.omi.me/doc/developer/apps/ChatTools)
- **OAuth**: `docs/doc/developer/apps/Oauth.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Oauth)
- **Prompt-Based Apps**: `docs/doc/developer/apps/PromptBased.mdx` - [View online](https://docs.omi.me/doc/developer/apps/PromptBased)
- **Audio Streaming**: `docs/doc/developer/apps/AudioStreaming.mdx` - [View online](https://docs.omi.me/doc/developer/apps/AudioStreaming)
- **Submitting Apps**: `docs/doc/developer/apps/Submitting.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Submitting)
- **Plugin Development**: `.cursor/rules/plugin-development.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/plugin-development.mdc` - Plugin development patterns
- `.cursor/rules/plugin-apps-js.mdc` - JavaScript plugin patterns
- `.cursor/rules/backend-api-patterns.mdc` - Backend API patterns
- `.cursor/rules/backend-architecture.mdc` - Backend architecture

### Subagents
- `.cursor/agents/plugin-developer/` - Uses this skill for plugin development

### Commands
- `/create-plugin` - Uses this skill for plugin scaffolding
- `/create-app` - Uses this skill for app creation
