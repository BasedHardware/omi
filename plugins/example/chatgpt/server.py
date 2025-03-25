import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import sys
from datetime import datetime

# Helper function for logging with timestamps
def log_with_timestamp(message: str):
    """Log a message with the current timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Millisecond precision
    print(f"[{timestamp}] {message}")

# Add parent directory to path for imports to work
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)
if current_dir not in sys.path:
    sys.path.append(current_dir)

from memory_handler import router as memory_handler_router

# Create a FastAPI app
app = FastAPI(
    title="OMI ChatGPT Integration",
    description="API for integrating OMI conversations with ChatGPT",
    version="1.0.0"
)

# Mount templates directory from the chatgpt folder if it exists
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
static_dir = os.path.join(templates_dir, "static")
if os.path.exists(static_dir):
    app.mount("/templates/static", StaticFiles(directory=static_dir), name="templates_static")

# Include our router
app.include_router(memory_handler_router)

# Default route
@app.get("/")
async def root():
    return {
        "message": "OMI ChatGPT Integration API",
        "documentation": "/docs",
        "setup": "/chatgpt/setup?uid=test_user_123"
    }

# Run the server when the script is executed directly
if __name__ == "__main__":
    log_with_timestamp("Starting OMI ChatGPT Integration server...")
    
    # Load environment variables from .env file if it exists
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        from dotenv import load_dotenv
        log_with_timestamp(f"Loading environment from {env_file}")
        load_dotenv(env_file)
    
    # Generate random client ID and secret if not set
    if not os.getenv('OPENAI_CLIENT_ID'):
        import secrets
        client_id = f"omi_app_{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        os.environ['OPENAI_CLIENT_ID'] = client_id
        os.environ['OPENAI_CLIENT_SECRET'] = client_secret
        log_with_timestamp("\nGenerated random client credentials:")
        log_with_timestamp(f"OPENAI_CLIENT_ID={client_id}")
        log_with_timestamp(f"OPENAI_CLIENT_SECRET={client_secret}")
    
    # Print OAuth configuration
    log_with_timestamp("\nOAuth Configuration for ChatGPT Actions:")
    log_with_timestamp(f"Authorization URL: http://localhost:8000/chatgpt/oauth/authorize")
    log_with_timestamp(f"Token URL: http://localhost:8000/chatgpt/oauth/token")
    log_with_timestamp(f"Client ID: {os.getenv('OPENAI_CLIENT_ID')}")
    log_with_timestamp(f"Scope: read:memories")
    
    # Print webhook information
    log_with_timestamp("\nWebhook Information:")
    log_with_timestamp(f"Webhook URL: http://localhost:8000/chatgpt/webhook/memory?uid=test_user")
    log_with_timestamp("Set this URL in OMI app's developer settings for Memory Creation Triggers")
    
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port=8000) 