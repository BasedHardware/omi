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
        "subscription/index.html", 
        {
            "request": request, 
            "uid": uid,
            "page_title": "Upgrade to Unlimited"
        }
    )

@router.get("/redirect/monthly", response_class=RedirectResponse)
async def redirect_to_monthly_payment(uid: str = ""):
    """
    Redirects to Stripe payment for monthly plan
    """
    try:
        if not uid or uid.strip() == "":
            logger.warning("Monthly payment redirect attempted without UID")
            return RedirectResponse(
                url="/subscription?error=missing_uid",
                status_code=302
            )
        
        logger.info(f"Redirecting to monthly payment with UID: {uid}")
        
        # Encode the UID for URL safety
        encoded_uid = quote(uid.strip())
        
        # Monthly plan Stripe URL
        stripe_url = f"https://buy.stripe.com/bJedR1bG4bpcbwiahI6wE1G?client_reference_id={encoded_uid}"
        return RedirectResponse(
            url=stripe_url,
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error in monthly payment redirect: {str(e)}")
        return RedirectResponse(
            url="/subscription?error=redirect_failed",
            status_code=302
        )

@router.get("/redirect/annual", response_class=RedirectResponse)
async def redirect_to_annual_payment(uid: str = ""):
    """
    Redirects to Stripe payment for annual plan
    """
    try:
        if not uid or uid.strip() == "":
            logger.warning("Annual payment redirect attempted without UID")
            return RedirectResponse(
                url="/subscription?error=missing_uid",
                status_code=302
            )
        
        logger.info(f"Redirecting to annual payment with UID: {uid}")
        
        # Encode the UID for URL safety
        encoded_uid = quote(uid.strip())
        
        # Annual plan Stripe URL (using same URL for demo, you can change this)
        stripe_url = f"https://buy.stripe.com/bJedR1bG4bpcbwiahI6wE1G?client_reference_id={encoded_uid}"
        return RedirectResponse(
            url=stripe_url,
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error in annual payment redirect: {str(e)}")
        return RedirectResponse(
            url="/subscription?error=redirect_failed",
            status_code=302
        )

@router.get("/stats", response_class=JSONResponse)
async def get_subscription_stats(request: Request):
    """
    Returns subscription statistics
    Admin-only endpoint
    """
    return JSONResponse({
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "message": "Subscription stats endpoint is working"
    })
