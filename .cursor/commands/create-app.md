# Create App

Scaffold a new Omi app structure.

## Purpose

Create a new Omi app with webhook endpoints and proper integration setup.

## App Types

### Prompt-Based App
No server required - just define prompts.

### Integration App
Requires server endpoint for webhooks.

## Quick Start

1. **Test with webhook.site**
   - Go to https://webhook.site
   - Copy your unique URL

2. **Create app in Omi app**
   - Open Omi app
   - Navigate to Explore → Create an App
   - Select capability
   - Paste webhook URL
   - Install app

3. **Start speaking**
   - Watch real-time data appear on webhook.site

## Creating a Full App

### Python App

1. **Set up FastAPI server**
   ```bash
   mkdir my-omi-app
   cd my-omi-app
   python -m venv venv
   source venv/bin/activate
   pip install fastapi uvicorn
   ```

2. **Create main.py**
   ```python
   from fastapi import FastAPI
   app = FastAPI()

   @app.post("/webhook/memory-created")
   async def memory_created(webhook: dict):
       # Process memory
       return {"status": "processed"}
   ```

3. **Run server**
   ```bash
   uvicorn main:app --reload
   ```

4. **Expose via Ngrok**
   ```bash
   ngrok http 8000
   ```

5. **Register webhook URL in Omi app**

### JavaScript App

1. **Set up Express server**
   ```bash
   mkdir my-omi-app
   cd my-omi-app
   npm init -y
   npm install express
   ```

2. **Create index.js**
   ```javascript
   const express = require('express');
   const app = express();
   app.use(express.json());

   app.post('/webhook/memory-created', (req, res) => {
     // Process memory
     res.json({ status: 'processed' });
   });

   app.listen(3000);
   ```

3. **Run server and expose via Ngrok**

## App Capabilities

- **Memory triggers**: Webhook when memory created
- **Real-time transcript**: Live transcript processing
- **Chat tools**: Custom tools for LangGraph
- **Audio streaming**: Raw audio processing
- **Prompts**: Customize AI behavior

## Related Documentation

- App Introduction: `docs/doc/developer/apps/Introduction.mdx`
- Integrations: `docs/doc/developer/apps/Integrations.mdx`
- Chat Tools: `docs/doc/developer/apps/ChatTools.mdx`
- Plugin Development: `.cursor/rules/plugin-development.mdc`
