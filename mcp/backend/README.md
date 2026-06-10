# Agentic Chatbot Backend

FastAPI backend with LangChain agent and MCP server integration for Gmail, Google Drive, and Google Calendar.

## 🏗️ Architecture

```
Frontend (React) → FastAPI → LangChain Agent → MCP Servers → Google APIs
                             ↓
                          Groq LLM
```

## 📦 Components

### Core (`backend/core/`)
- **`config.py`**: Configuration management with Pydantic
- **`agent.py`**: LangChain agent lifecycle management
- **`mcp_client.py`**: MCP client wrapper (if needed)

### API (`backend/api/`)
- **`main.py`**: FastAPI application entry point
- **`routes/`**: API endpoints
  - `chat.py`: Chat endpoints (streaming & non-streaming)
  - `health.py`: Health checks
  - `tools.py`: Tool management
- **`models/`**: Pydantic request/response models

### MCP Servers (`backend/mcp_servers/`)
- `gmail_server.py`: Gmail integration
- `google_drive_server.py`: Drive integration
- `google_calendar_server.py`: Calendar integration

## 🚀 Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Run setup script
python backend/scripts/setup.py

# Edit .env with your API keys
nano backend/.env  # or use your favorite editor
```

Required environment variables:
- `GROQ_API_KEY`: Get from [Groq Console](https://console.groq.com/keys)
- `credentials.json`: Google OAuth credentials

### 3. Google API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable APIs:
   - Gmail API
   - Google Drive API
   - Google Calendar API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download as `backend/credentials/credentials.json`
6. Run token generation:
   ```bash
   python backend/scripts/generate_tokens.py
   ```

### 4. Start Server

```bash
# Development (with auto-reload)
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Or simply
python -m backend.api.main
```

Server will start at: `http://localhost:8001`

## 📚 API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔌 API Endpoints

### Health

```bash
# Check server health
GET /api/health

# Readiness check
GET /api/health/ready

# Liveness check
GET /api/health/live
```

### Chat

```bash
# Non-streaming chat
POST /api/chat
{
  "message": "What's on my calendar today?",
  "conversation_id": "optional_id",
  "stream": false
}

# Streaming chat
POST /api/chat/stream
{
  "message": "Show me my recent emails",
  "stream": true
}

# Get conversation history
GET /api/chat/history/{conversation_id}

# Delete conversation
DELETE /api/chat/history/{conversation_id}
```

### Tools

```bash
# List all tools
GET /api/tools

# List MCP servers
GET /api/tools/servers

# Get tool info
GET /api/tools/{tool_name}

# Execute tool directly
POST /api/tools/execute
{
  "tool_name": "gmail_get_messages",
  "arguments": {"max_results": 5}
}
```

## 🧪 Testing

```bash
# Test individual MCP servers
python backend/scripts/test_servers.py

# Run pytest (if you write tests)
pytest backend/tests/
```

## 🔧 Configuration Options

Edit `backend/.env`:

```bash
# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# LLM
LLM_MODEL=llama-3.1-8b-instant
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048

# Enable/disable servers
ENABLE_GMAIL=true
ENABLE_GOOGLE_DRIVE=true
ENABLE_GOOGLE_CALENDAR=true

# CORS (add your frontend URL)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## 📖 Key Concepts

### 1. **Pydantic Models**
Define data structure and validation:
```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
```

### 2. **Dependency Injection**
FastAPI automatically provides dependencies:
```python
@app.get("/health")
async def health(request: Request):
    # request is injected automatically
```

### 3. **Async/Await**
Non-blocking operations for better performance:
```python
async def chat(message: str):
    result = await agent.ainvoke(...)
```

### 4. **Streaming Responses**
Real-time data with Server-Sent Events:
```python
async def event_generator():
    async for chunk in agent.stream_chat(...):
        yield f"data: {chunk.json()}\n\n"
```

### 5. **Lifespan Events**
Initialize/cleanup on startup/shutdown:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await agent_manager.initialize()
    yield
    # Shutdown
    await agent_manager.shutdown()
```

## 🐛 Troubleshooting

### Agent not initialized
**Error**: `Agent not initialized`
**Solution**: Wait a few seconds after starting server. Check logs for initialization errors.

### Missing credentials
**Error**: `credentials.json not found`
**Solution**: Follow Google API Setup steps above.

### Import errors
**Error**: `ModuleNotFoundError`
**Solution**: Ensure virtual environment is activated and dependencies installed.

### CORS errors from frontend
**Error**: `CORS policy blocked`
**Solution**: Add frontend URL to `CORS_ORIGINS` in `.env`

### MCP server connection failed
**Error**: `Failed to connect to MCP server`
**Solution**: 
1. Check `token.json` exists (run `generate_tokens.py`)
2. Verify Google API is enabled
3. Check credentials are valid

## 📝 Development Tips

### 1. Hot Reload
Use `--reload` flag for automatic restarts:
```bash
uvicorn backend.api.main:app --reload
```

### 2. Debug Logging
Set `LOG_LEVEL=DEBUG` in `.env` for detailed logs.

### 3. Test Tools Individually
```bash
python backend/scripts/test_servers.py
```

### 4. API Documentation
FastAPI auto-generates docs at `/docs` - very helpful for testing!

### 5. Type Hints
Use type hints everywhere - catches bugs early:
```python
async def process_message(message: str) -> ChatResponse:
    ...
```

## 🔐 Security Notes

- Never commit `.env` or `credentials.json` to git
- Use environment variables for secrets
- Validate all user inputs (Pydantic does this automatically)
- Implement rate limiting for production
- Use HTTPS in production

## 📈 Performance Tips

- Use `async/await` for I/O operations
- Stream responses for better UX
- Cache LLM results when appropriate
- Monitor token usage
- Consider connection pooling for databases

## 🚀 Production Deployment

```bash
# Install production server
pip install gunicorn

# Run with gunicorn
gunicorn backend.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

Or use Docker:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangChain Documentation](https://python.langchain.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Uvicorn Documentation](https://www.uvicorn.org/)

## 🤝 Contributing

1. Follow PEP 8 style guide
2. Add type hints to all functions
3. Write docstrings for public APIs
4. Test your changes
5. Update documentation

## 📄 License

MIT