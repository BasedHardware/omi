from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import io
import base64
import logging
from datetime import datetime

router = APIRouter(
    prefix="/chatgpt",
    tags=["chatgpt"],
)

# Get the absolute path to the templates directory
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Setup logging
logger = logging.getLogger("chatgpt_integration")

@router.get("/", response_class=HTMLResponse)
async def chatgpt_page(request: Request, uid: str = ""):
    """
    Renders a simple redirect page to ChatGPT with the UID
    """
    try:
        if not uid or uid.strip() == "":
            # If no UID is provided, log the error
            logger.warning("ChatGPT integration accessed without UID")
            return RedirectResponse(
                url="/",  # Redirect to home page if no UID
                status_code=302
            )
        
        # Log the access for analytics
        logger.info(f"ChatGPT integration page accessed with UID: {uid}")
        
        # Return the template with the UID
        return templates.TemplateResponse(
            "chatgpt/index.html", 
            {
                "request": request, 
                "uid": uid.strip(),
                "page_title": "Redirecting to Omi for ChatGPT"
            }
        )
    except Exception as e:
        logger.error(f"Error in redirect: {str(e)}")
        return RedirectResponse(
            url="/",  # Redirect to home page on error
            status_code=302
        )

@router.get("/stats", response_class=JSONResponse)
async def get_stats(request: Request):
    """
    Returns usage statistics for the ChatGPT integration
    Admin-only endpoint
    """
    # This would be expanded with actual stats in a production environment
    return JSONResponse({
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "message": "Stats endpoint is working"
    })
