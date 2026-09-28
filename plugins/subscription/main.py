from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging
import re
from datetime import datetime
from urllib.parse import quote

router = APIRouter(
    prefix="/subscription",
    tags=["subscription"],
)

# Get the absolute path to the templates directory
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Setup logging
logger = logging.getLogger("subscription_integration")


def _sanitize_uid(uid: str) -> str:
    """
    Sanitize and validate uid to prevent Reflected XSS and injection attacks.
    Only allows alphanumeric characters, underscores, and hyphens (up to 128 chars).
    """
    if not uid:
        return ""
    cleaned = str(uid).strip()
    if re.fullmatch(r"^[a-zA-Z0-9_-]{1,128}$", cleaned):
        return cleaned
    return ""


@router.get("/", response_class=HTMLResponse)
async def subscription_page(request: Request, uid: str = ""):
    """
    Renders the subscription pricing page with monthly and annual plans
    """
    safe_uid = _sanitize_uid(uid)
    # Log the access for analytics
    if safe_uid:
        logger.info(f"Subscription page accessed with UID: {safe_uid}")
    else:
        if uid:
            logger.warning("Subscription page accessed with invalid/untrusted UID format")
        else:
            logger.warning("Subscription page accessed without UID")

    return templates.TemplateResponse(
        "subscription/index.html", {"request": request, "uid": safe_uid, "page_title": "Upgrade to Unlimited"}
    )
