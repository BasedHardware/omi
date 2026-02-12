from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging
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


@router.get("/", response_class=HTMLResponse)
async def subscription_page(request: Request, uid: str = ""):
    """
    Renders the subscription pricing page with monthly and annual plans
    """
    # Log the access for analytics
    if uid:
        logger.info(f"Subscription page accessed with UID: {uid}")
    else:
        logger.warning("Subscription page accessed without UID")

    return templates.TemplateResponse(
        "subscription/index.html", {"request": request, "uid": uid, "page_title": "Upgrade to Unlimited"}
    )
