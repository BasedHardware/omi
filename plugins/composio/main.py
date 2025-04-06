import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from the correct path
env_path = Path(__file__).parent / '.env'
logger.info(f"Loading environment variables from: {env_path}")
load_dotenv(env_path)

# Log environment variable status (without exposing secrets)
logger.info("Environment variables loaded:")
logger.info(f"OMI_APP_ID present: {'Yes' if os.getenv('OMI_APP_ID') else 'No'}")
logger.info(f"OMI_API_KEY present: {'Yes' if os.getenv('OMI_API_KEY') else 'No'}")
logger.info(f"NOTION_CLIENT_ID present: {'Yes' if os.getenv('NOTION_CLIENT_ID') else 'No'}")
logger.info(f"NOTION_CLIENT_SECRET present: {'Yes' if os.getenv('NOTION_CLIENT_SECRET') else 'No'}")

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from src.notion import router as notion_router, init_notion_credentials
from src.omi_api import router as omi_router
from src.db import create_db_tables

# Initialize FastAPI app
app = FastAPI(title="OMI-Composio Integration")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Initialize Notion credentials
init_notion_credentials(
    client_id=os.getenv("NOTION_CLIENT_ID", ""),
    client_secret=os.getenv("NOTION_CLIENT_SECRET", ""),
    redirect_uri=os.getenv("NOTION_REDIRECT_URI", "")
)

# Include routers
app.include_router(notion_router)
app.include_router(omi_router)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_db_tables()

# Home route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Run the app
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 