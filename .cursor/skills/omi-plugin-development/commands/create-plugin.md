# Create Plugin

Scaffold a new Omi plugin/app structure.

## Purpose

Create a new Omi plugin/app with proper structure and configuration.

## Plugin Types

### 1. Prompt-Based App (No Server)

Just define prompts - no server required.

**Capabilities**:
- Chat prompts: Customize AI personality
- Memory prompts: Customize memory extraction

### 2. Integration App (Requires Server)

Requires a server endpoint for webhooks.

**Capabilities**:
- Memory triggers: Webhook on memory creation
- Real-time transcript: Webhook for live transcripts
- Chat tools: Custom tools for LangGraph
- Audio streaming: Raw audio processing

## Creating a Python Plugin

1. **Create plugin directory**
   ```bash
   mkdir -p plugins/my-plugin
   cd plugins/my-plugin
   ```

2. **Create main.py**
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
       return {"status": "processed"}
   ```

3. **Create requirements.txt**
   ```
   fastapi>=0.100.0
   uvicorn>=0.27.0
   ```

4. **Test with webhook.site**
   - Go to https://webhook.site
   - Copy your unique URL
   - Register in Omi app
   - Test webhook

## Creating a JavaScript Plugin

1. **Create plugin directory**
   ```bash
   mkdir -p plugins/my-plugin
   cd plugins/my-plugin
   ```

2. **Initialize Node.js project**
   ```bash
   npm init -y
   npm install express
   ```

3. **Create index.js**
   ```javascript
   const express = require('express');
   const app = express();

   app.use(express.json());

   app.post('/webhook/memory-created', (req, res) => {
     const { id, content, category, user_id } = req.body;
     // Process memory
     res.json({ status: 'processed' });
   });

   app.listen(3000, () => {
     console.log('Plugin running on port 3000');
   });
   ```

## Next Steps

1. Implement webhook handlers
2. Test with webhook.site
3. Register plugin in Omi app
4. Deploy plugin server
5. Submit to Omi app store (optional)

## Related Documentation

- Plugin Development: `docs/doc/developer/apps/Introduction.mdx`
- Integrations: `docs/doc/developer/apps/Integrations.mdx`
- Chat Tools: `docs/doc/developer/apps/ChatTools.mdx`
- Plugin Patterns: `.cursor/rules/plugin-development.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/plugin-development.mdc` - Plugin development patterns
- `.cursor/rules/plugin-apps-js.mdc` - JavaScript plugin patterns
- `.cursor/rules/backend-api-patterns.mdc` - Backend API patterns

### Skills
- `.cursor/skills/omi-plugin-development/` - Plugin development workflows
- `.cursor/skills/omi-api-integration/` - API integration patterns

### Subagents
- `.cursor/agents/plugin-developer/` - Plugin development specialist

### Commands
- `/test-integration` - Test plugin after creation
