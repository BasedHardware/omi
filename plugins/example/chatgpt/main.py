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
    Renders the simplified ChatGPT integration page with direct link to OmiGPT
    """
    # Log the access for analytics
    if uid:
        logger.info(f"ChatGPT integration page accessed with UID: {uid}")
    else:
        logger.warning("ChatGPT integration page accessed without UID")

    return templates.TemplateResponse(
        "chatgpt/index.html", {"request": request, "uid": uid, "page_title": "Connect Omi with ChatGPT"}
    )


@router.get("/redirect", response_class=RedirectResponse)
async def redirect_to_chatgpt(uid: str = ""):
    """
    Redirects to ChatGPT with UID as a URL parameter
    """
    try:
        if not uid or uid.strip() == "":
            # If no UID is provided, redirect to the main page with an error
            logger.warning("Redirect attempted without UID")
            return RedirectResponse(url="/chatgpt?error=missing_uid", status_code=302)

        # Log the redirect for analytics
        logger.info(f"Redirecting to ChatGPT with UID: {uid}")

        # Encode the UID for URL safety
        from urllib.parse import quote

        encoded_uid = quote(uid.strip())

        # Redirect to ChatGPT with UID in the prompt parameter
        chatgpt_url = f"https://chatgpt.com/g/g-67e2772d0af081919a5baddf4a12aacf-omi?prompt=here%20is%20my%20omi%20uid%20{encoded_uid}"
        return RedirectResponse(url=chatgpt_url, status_code=302)
    except Exception as e:
        logger.error(f"Error in redirect: {str(e)}")
        return RedirectResponse(url="/chatgpt?error=redirect_failed", status_code=302)


@router.get("/stats", response_class=JSONResponse)
async def get_stats(request: Request):
    """
    Returns usage statistics for the ChatGPT integration
    Admin-only endpoint
    """
    # This would be expanded with actual stats in a production environment
    return JSONResponse(
        {"status": "success", "timestamp": datetime.now().isoformat(), "message": "Stats endpoint is working"}
    )
