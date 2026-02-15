"""
ShipBob Integration App for Omi

This app provides ShipBob integration through OAuth2 authentication
and chat tools for managing inventory, WROs, and orders.
"""
import os
import sys
import secrets
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    store_shipbob_tokens,
    get_shipbob_tokens,
    delete_shipbob_tokens,
    store_oauth_state,
    get_oauth_state,
    delete_oauth_state,
    update_shipbob_channel,
    get_user_settings,
)
from models import ChatToolResponse


def log(msg: str):
    """Print and flush immediately for Railway logging."""
    print(msg)
    sys.stdout.flush()


load_dotenv()

# ShipBob API Configuration
SHIPBOB_CLIENT_ID = os.getenv("SHIPBOB_CLIENT_ID", "")
SHIPBOB_CLIENT_SECRET = os.getenv("SHIPBOB_CLIENT_SECRET", "")
SHIPBOB_REDIRECT_URI = os.getenv("SHIPBOB_REDIRECT_URI", "http://localhost:8080/auth/shipbob/callback")

# ShipBob API URLs
SHIPBOB_AUTH_URL = os.getenv("SHIPBOB_AUTH_URL", "https://auth.shipbob.com/connect/authorize")
SHIPBOB_TOKEN_URL = os.getenv("SHIPBOB_TOKEN_URL", "https://auth.shipbob.com/connect/token")
SHIPBOB_API_URL = os.getenv("SHIPBOB_API_URL", "https://api.shipbob.com")

# For sandbox testing, use:
# SHIPBOB_AUTH_URL = "https://authstage.shipbob.com/connect/authorize"
# SHIPBOB_TOKEN_URL = "https://authstage.shipbob.com/connect/token"
# SHIPBOB_API_URL = "https://sandbox-api.shipbob.com"

# OAuth2 Scopes
SHIPBOB_SCOPES = "openid offline_access channels_read inventory_read inventory_write products_read products_write receiving_read receiving_write orders_read locations_read"

app = FastAPI(
    title="ShipBob Omi Integration",
    description="ShipBob integration for Omi - Manage inventory and fulfillment with voice",
    version="1.0.0"
)

# Mount static files and templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
if os.path.exists(templates_dir):
    static_dir = os.path.join(templates_dir, "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


# ============================================
# Helper Functions
# ============================================

def get_shipbob_headers(uid: str) -> Optional[Dict[str, str]]:
    """Get headers for ShipBob API requests."""
    tokens = get_shipbob_tokens(uid)
    if not tokens:
        return None

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type": "application/json"
    }

    # Add channel ID if available
    if tokens.get("channel_id"):
        headers["shipbob_channel_id"] = str(tokens["channel_id"])

    return headers


def refresh_token_if_needed(uid: str) -> bool:
    """Refresh the access token if it's expired or about to expire."""
    tokens = get_shipbob_tokens(uid)
    if not tokens or not tokens.get("refresh_token"):
        return False

    # Check if token needs refresh (ShipBob tokens last 1 hour)
    updated_at = tokens.get("updated_at")
    if updated_at:
        updated_time = datetime.fromisoformat(updated_at)
        # Refresh if token is older than 50 minutes
        if datetime.utcnow() - updated_time < timedelta(minutes=50):
            return True  # Token still valid

    # Refresh the token
    try:
        response = requests.post(
            SHIPBOB_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": SHIPBOB_CLIENT_ID,
                "client_secret": SHIPBOB_CLIENT_SECRET
            }
        )

        if response.status_code == 200:
            token_data = response.json()
            store_shipbob_tokens(
                uid,
                token_data["access_token"],
                token_data.get("refresh_token", tokens["refresh_token"]),
                token_data.get("token_type", "Bearer"),
                token_data.get("expires_in"),
                tokens.get("channel_id")
            )
            log(f"Token refreshed for user {uid}")
            return True
        else:
            log(f"Token refresh failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        log(f"Token refresh error: {e}")
        return False


def make_shipbob_request(
    uid: str,
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    params: Optional[Dict] = None
) -> Optional[Dict]:
    """Make an authenticated request to ShipBob API."""
    refresh_token_if_needed(uid)

    headers = get_shipbob_headers(uid)
    if not headers:
        return None

    url = f"{SHIPBOB_API_URL}{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return None

        if response.status_code in [200, 201]:
            return response.json()
        else:
            log(f"ShipBob API error: {response.status_code} - {response.text[:200]}")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        log(f"ShipBob API exception: {e}")
        return {"error": str(e)}


def get_channels(uid: str) -> List[Dict]:
    """Get user's ShipBob channels."""
    result = make_shipbob_request(uid, "GET", "/1.0/channel")
    if isinstance(result, list):
        return result
    if result and isinstance(result, dict) and not result.get("error"):
        return []
    return []


def get_fulfillment_centers(uid: str) -> List[Dict]:
    """Get available fulfillment centers."""
    result = make_shipbob_request(uid, "GET", "/1.0/fulfillmentCenter")
    if isinstance(result, list):
        return result
    if result and isinstance(result, dict) and not result.get("error"):
        return []
    return []


def get_inventory(uid: str, page: int = 1, limit: int = 50) -> List[Dict]:
    """Get inventory items."""
    params = {"Page": page, "Limit": limit}
    result = make_shipbob_request(uid, "GET", "/1.0/inventory", params=params)
    if isinstance(result, list):
        return result
    if result and isinstance(result, dict) and not result.get("error"):
        return []
    return []


def get_products(uid: str, page: int = 1, limit: int = 50) -> List[Dict]:
    """Get products."""
    params = {"Page": page, "Limit": limit}
    result = make_shipbob_request(uid, "GET", "/1.0/product", params=params)
    if isinstance(result, list):
        return result
    if result and isinstance(result, dict) and not result.get("error"):
        return []
    return []


def search_product_by_name(uid: str, name: str) -> Optional[Dict]:
    """Search for a product by name."""
    # Try products endpoint first
    products = get_products(uid, limit=100)
    name_lower = name.lower()

    for product in products:
        product_name = product.get("name", "").lower()
        if name_lower in product_name or product_name in name_lower:
            return product

    return None


def search_inventory_by_name(uid: str, name: str) -> Optional[Dict]:
    """Search for an inventory item by name."""
    inventory = get_inventory(uid, limit=100)
    name_lower = name.lower()

    for item in inventory:
        item_name = item.get("name", "").lower()
        if name_lower in item_name or item_name in name_lower:
            return item

    return None


def get_inventory_by_product(uid: str, product_name: str) -> Optional[Dict]:
    """Get inventory levels for a specific product."""
    product = search_product_by_name(uid, product_name)
    if not product:
        return None

    inventory_id = None
    # Get inventory ID from product's inventory items
    if "fulfillable_inventory_items" in product:
        items = product["fulfillable_inventory_items"]
        if items:
            inventory_id = items[0].get("id")

    if inventory_id:
        result = make_shipbob_request(uid, "GET", f"/1.0/inventory/{inventory_id}")
        if result and isinstance(result, dict) and not result.get("error"):
            result["product"] = product
            return result

    return {"product": product, "inventory": None}


# ============================================
# OAuth Endpoints
# ============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, uid: Optional[str] = None):
    """Home page / App settings page."""
    if not uid:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Missing user ID"
        })

    tokens = get_shipbob_tokens(uid)
    authenticated = tokens is not None

    channels = []
    selected_channel = None
    if authenticated:
        channels = get_channels(uid)
        if tokens.get("channel_id"):
            for ch in channels:
                if ch.get("id") == tokens["channel_id"]:
                    selected_channel = ch
                    break

    return templates.TemplateResponse("setup.html", {
        "request": request,
        "uid": uid,
        "authenticated": authenticated,
        "channels": channels,
        "selected_channel": selected_channel,
    })


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "shipbob-omi"}


@app.get("/auth/shipbob")
async def shipbob_auth(uid: str):
    """Initiate ShipBob OAuth2 flow."""
    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")

    if not SHIPBOB_CLIENT_ID or not SHIPBOB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="ShipBob credentials not configured")

    # Generate state for CSRF protection
    state = f"{uid}:{secrets.token_urlsafe(32)}"
    store_oauth_state(uid, state)

    # Build authorization URL
    params = {
        "client_id": SHIPBOB_CLIENT_ID,
        "response_type": "code",
        "response_mode": "query",
        "redirect_uri": SHIPBOB_REDIRECT_URI,
        "scope": SHIPBOB_SCOPES,
        "state": state,
        "integration_name": "Omi Voice Assistant"
    }

    auth_url = f"{SHIPBOB_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/shipbob/callback")
@app.post("/auth/shipbob/callback")
async def handle_shipbob_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    """Handle ShipBob OAuth2 callback (supports both GET and POST for form_post mode)."""
    # For POST requests, extract from form data
    if request.method == "POST":
        form_data = await request.form()
        code = code or form_data.get("code")
        state = state or form_data.get("state")
        error = error or form_data.get("error")
        error_description = error_description or form_data.get("error_description")

    if error:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": f"Authorization failed: {error_description or error}"
        })

    if not code or not state:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Invalid callback parameters"
        })

    # Extract uid from state
    try:
        uid, _ = state.split(":", 1)
    except ValueError:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Invalid state parameter"
        })

    # Verify state matches what we stored
    stored_state = get_oauth_state(uid)
    if stored_state != state:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "State mismatch - possible CSRF attack"
        })

    # Clean up state
    delete_oauth_state(uid)

    # Exchange code for access token
    try:
        response = requests.post(
            SHIPBOB_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SHIPBOB_REDIRECT_URI,
                "client_id": SHIPBOB_CLIENT_ID,
                "client_secret": SHIPBOB_CLIENT_SECRET
            }
        )

        if response.status_code != 200:
            log(f"Token exchange failed: {response.status_code} - {response.text}")
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "authenticated": False,
                "error": f"Failed to exchange authorization code: {response.text}"
            })

        token_data = response.json()

        # Store tokens
        store_shipbob_tokens(
            uid,
            token_data["access_token"],
            token_data.get("refresh_token"),
            token_data.get("token_type", "Bearer"),
            token_data.get("expires_in")
        )

        # Try to get and store the first channel
        try:
            channels = get_channels(uid)
            if channels and isinstance(channels, list) and len(channels) > 0:
                # Find a channel with write access
                for ch in channels:
                    if isinstance(ch, dict):
                        if "_write" in ch.get("name", "").lower() or ch.get("scopes"):
                            update_shipbob_channel(uid, ch["id"])
                            break
                else:
                    # Just use the first channel
                    if isinstance(channels[0], dict):
                        update_shipbob_channel(uid, channels[0]["id"])
        except Exception as ch_err:
            log(f"Channel selection error (non-fatal): {ch_err}")

        # Redirect to home with uid
        return RedirectResponse(url=f"/?uid={uid}")

    except Exception as e:
        log(f"OAuth error: {e}")
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": f"Failed to exchange authorization code: {str(e)}"
        })


@app.get("/setup/shipbob", tags=["setup"])
async def check_setup(uid: str):
    """Check if the user has completed ShipBob setup (used by Omi)."""
    tokens = get_shipbob_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect_shipbob(uid: str):
    """Disconnect ShipBob account."""
    delete_shipbob_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


@app.post("/select-channel")
async def select_channel(request: Request):
    """Select a channel for the user."""
    body = await request.json()
    uid = body.get("uid")
    channel_id = body.get("channel_id")

    if not uid or not channel_id:
        raise HTTPException(status_code=400, detail="Missing uid or channel_id")

    update_shipbob_channel(uid, int(channel_id))
    return {"success": True}


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/get_inventory", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_inventory(request: Request):
    """
    Get inventory levels for all items or a specific product.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        product_name = body.get("product_name")
        limit = body.get("limit", 10)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        if product_name:
            # Search inventory directly by name
            inv = search_inventory_by_name(uid, product_name)
            if not inv:
                return ChatToolResponse(error=f"Could not find inventory item '{product_name}'")

            result_parts = [
                f"**Inventory for: {inv.get('name', 'Unknown')}**",
                "",
                f"**SKU:** {inv.get('sku', 'N/A')}",
                f"**Fulfillable Quantity:** {inv.get('fulfillable_quantity', 'N/A')}",
                f"**On Hand:** {inv.get('onhand_quantity', 'N/A')}",
                f"**Committed:** {inv.get('committed_quantity', 'N/A')}",
                f"**Awaiting:** {inv.get('awaiting_quantity', 'N/A')}",
            ]

            return ChatToolResponse(result="\n".join(result_parts))
        else:
            # Get all inventory
            inventory = get_inventory(uid, limit=limit)
            if not inventory:
                return ChatToolResponse(result="No inventory items found.")

            result_parts = [f"**Inventory Items ({len(inventory)})**", ""]
            for item in inventory[:limit]:
                name = item.get("name", "Unknown")
                sku = item.get("sku", "N/A")
                fulfillable = item.get("fulfillable_quantity", item.get("total_fulfillable_quantity", 0))
                result_parts.append(f"- **{name}** (SKU: {sku}) - {fulfillable} fulfillable")

            return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting inventory: {e}")
        return ChatToolResponse(error=f"Failed to get inventory: {str(e)}")


@app.post("/tools/get_products", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_products(request: Request):
    """
    Get list of products.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        search = body.get("search")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        products = get_products(uid, limit=100 if search else limit)

        if search:
            search_lower = search.lower()
            products = [p for p in products if search_lower in p.get("name", "").lower()]

        if not products:
            return ChatToolResponse(result="No products found.")

        result_parts = [f"**Products ({len(products[:limit])})**", ""]
        for product in products[:limit]:
            name = product.get("name", "Unknown")
            sku = product.get("sku", "N/A")
            ref_id = product.get("reference_id", "")
            result_parts.append(f"- **{name}** (SKU: {sku})")
            if ref_id:
                result_parts[-1] += f" [Ref: {ref_id}]"

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting products: {e}")
        return ChatToolResponse(error=f"Failed to get products: {str(e)}")


@app.post("/tools/create_wro", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_wro(request: Request):
    """
    Create a Warehouse Receiving Order (WRO).
    """
    try:
        body = await request.json()
        log(f"=== CREATE_WRO START ===")
        log(f"Request: {body}")

        uid = body.get("uid")
        product_name = body.get("product_name")
        quantity = body.get("quantity")
        fulfillment_center_id = body.get("fulfillment_center_id")
        expected_arrival_date = body.get("expected_arrival_date")
        tracking_number = body.get("tracking_number")
        purchase_order_number = body.get("purchase_order_number")
        packaging_type = body.get("packaging_type", "EverythingInOneBox")
        package_type = body.get("package_type", "Package")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not product_name:
            return ChatToolResponse(error="Product name is required")

        if not quantity or int(quantity) <= 0:
            return ChatToolResponse(error="Quantity must be greater than zero")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        # Find the product and get inventory_id
        product = search_product_by_name(uid, product_name)
        if not product:
            return ChatToolResponse(error=f"Could not find product '{product_name}'. Please check the product name.")

        # Get inventory_id from product
        inventory_id = None
        if "fulfillable_inventory_items" in product:
            items = product["fulfillable_inventory_items"]
            if items:
                inventory_id = items[0].get("id")

        if not inventory_id:
            # Try to get from inventory list
            inventory = get_inventory(uid, limit=100)
            product_name_lower = product.get("name", "").lower()
            for inv in inventory:
                if inv.get("name", "").lower() == product_name_lower:
                    inventory_id = inv.get("id")
                    break

        if not inventory_id:
            return ChatToolResponse(error=f"Could not find inventory ID for product '{product_name}'")

        # Get fulfillment center if not provided
        if not fulfillment_center_id:
            fcs = get_fulfillment_centers(uid)
            if fcs:
                fulfillment_center_id = fcs[0].get("id")
            else:
                return ChatToolResponse(error="No fulfillment centers available. Please specify a fulfillment_center_id.")

        # Parse expected arrival date
        if not expected_arrival_date:
            # Default to 7 days from now
            arrival_date = datetime.utcnow() + timedelta(days=7)
            expected_arrival_date = arrival_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif not expected_arrival_date.endswith("Z"):
            # Try to parse and format
            try:
                parsed = datetime.strptime(expected_arrival_date, "%Y-%m-%d")
                expected_arrival_date = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
            except:
                pass

        # Build WRO request
        wro_data = {
            "fulfillment_center": {"id": int(fulfillment_center_id)},
            "package_type": package_type,
            "box_packaging_type": packaging_type,
            "expected_arrival_date": expected_arrival_date,
            "boxes": [
                {
                    "tracking_number": tracking_number or "",
                    "box_items": [
                        {
                            "inventory_id": inventory_id,
                            "quantity": int(quantity)
                        }
                    ]
                }
            ]
        }

        if purchase_order_number:
            wro_data["purchase_order_number"] = purchase_order_number

        log(f"Creating WRO: {wro_data}")

        # Create WRO using 2.0 API
        result = make_shipbob_request(uid, "POST", "/2.0/receiving", data=wro_data)

        if not result:
            return ChatToolResponse(error="Failed to create WRO - no response from ShipBob")

        if isinstance(result, dict) and result.get("error"):
            return ChatToolResponse(error=f"Failed to create WRO: {result.get('error')}")

        wro_id = result.get("id", "Unknown")
        status = result.get("status", "Unknown")

        result_parts = [
            "**WRO Created Successfully!**",
            "",
            f"**WRO ID:** {wro_id}",
            f"**Status:** {status}",
            f"**Product:** {product.get('name', product_name)}",
            f"**Quantity:** {quantity}",
            f"**Expected Arrival:** {expected_arrival_date[:10]}",
        ]

        if purchase_order_number:
            result_parts.append(f"**PO Number:** {purchase_order_number}")

        if result.get("box_labels_uri"):
            result_parts.append(f"\n**Box Labels:** {result['box_labels_uri']}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        import traceback
        log(f"Error creating WRO: {e}")
        log(traceback.format_exc())
        return ChatToolResponse(error=f"Failed to create WRO: {str(e)}")


@app.post("/tools/get_wros", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_wros(request: Request):
    """
    Get Warehouse Receiving Orders.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        status_filter = body.get("status")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        params = {"Limit": limit}
        if status_filter:
            params["Status"] = status_filter

        result = make_shipbob_request(uid, "GET", "/2.0/receiving", params=params)

        if not result:
            return ChatToolResponse(result="No WROs found.")

        if isinstance(result, dict) and result.get("error"):
            return ChatToolResponse(error=f"Failed to get WROs: {result.get('error')}")

        wros = result if isinstance(result, list) else (result.get("data", []) if isinstance(result, dict) else [])

        if not wros:
            return ChatToolResponse(result="No Warehouse Receiving Orders found.")

        result_parts = [f"**Warehouse Receiving Orders ({len(wros)})**", ""]
        for wro in wros[:limit]:
            wro_id = wro.get("id", "Unknown")
            status = wro.get("status", "Unknown")
            po_num = wro.get("purchase_order_number", "N/A")
            arrival = wro.get("expected_arrival_date", "N/A")
            if arrival and len(arrival) > 10:
                arrival = arrival[:10]

            result_parts.append(f"- **WRO #{wro_id}** - Status: {status}")
            if po_num != "N/A":
                result_parts[-1] += f" (PO: {po_num})"
            result_parts.append(f"  Expected: {arrival}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting WROs: {e}")
        return ChatToolResponse(error=f"Failed to get WROs: {str(e)}")


@app.post("/tools/cancel_wro", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_cancel_wro(request: Request):
    """
    Cancel a Warehouse Receiving Order.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        wro_id = body.get("wro_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not wro_id:
            return ChatToolResponse(error="WRO ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        result = make_shipbob_request(uid, "POST", f"/2.0/receiving/{wro_id}/cancel")

        if result and isinstance(result, dict) and result.get("error"):
            return ChatToolResponse(error=f"Failed to cancel WRO: {result.get('error')}")

        return ChatToolResponse(result=f"**WRO #{wro_id} has been cancelled.**")

    except Exception as e:
        log(f"Error cancelling WRO: {e}")
        return ChatToolResponse(error=f"Failed to cancel WRO: {str(e)}")


@app.post("/tools/get_orders", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_orders(request: Request):
    """
    Get recent orders.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        status = body.get("status")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        params = {"Limit": limit}
        if status:
            params["Status"] = status

        # Try with explicit channel in params if available
        tokens = get_shipbob_tokens(uid)
        if tokens and tokens.get("channel_id"):
            params["ChannelId"] = tokens["channel_id"]

        result = make_shipbob_request(uid, "GET", "/1.0/order", params=params)
        log(f"Orders API: channel={tokens.get('channel_id') if tokens else 'N/A'}, result_type={type(result).__name__}, len={len(result) if isinstance(result, list) else 'N/A'}")

        if not result:
            return ChatToolResponse(result="No orders found.")

        if isinstance(result, dict) and result.get("error"):
            return ChatToolResponse(error=f"Failed to get orders: {result.get('error')}")

        orders = result if isinstance(result, list) else []

        if not orders:
            return ChatToolResponse(result="No orders found. (API returned empty list)")

        result_parts = [f"**Recent Orders ({len(orders)})**", ""]
        for order in orders[:limit]:
            order_id = order.get("id", "Unknown")
            order_num = order.get("order_number", order_id)
            status = order.get("status", "Unknown")
            created = order.get("created_date", "N/A")
            if created and len(created) > 10:
                created = created[:10]

            result_parts.append(f"- **Order #{order_num}** - {status} ({created})")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting orders: {e}")
        return ChatToolResponse(error=f"Failed to get orders: {str(e)}")


@app.post("/tools/get_fulfillment_centers", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_fulfillment_centers(request: Request):
    """
    Get available fulfillment centers.
    """
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        headers = get_shipbob_headers(uid)
        if not headers:
            return ChatToolResponse(error="Please connect your ShipBob account first in the app settings.")

        fcs = get_fulfillment_centers(uid)

        if not fcs:
            return ChatToolResponse(result="No fulfillment centers found.")

        result_parts = [f"**Fulfillment Centers ({len(fcs)})**", ""]
        for fc in fcs:
            fc_id = fc.get("id", "Unknown")
            name = fc.get("name", "Unknown")
            address = fc.get("address", {})
            city = address.get("city", "")
            state = address.get("state", "")
            location = f"{city}, {state}" if city else ""

            result_parts.append(f"- **{name}** (ID: {fc_id})")
            if location:
                result_parts[-1] += f" - {location}"

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting fulfillment centers: {e}")
        return ChatToolResponse(error=f"Failed to get fulfillment centers: {str(e)}")


# ============================================
# Omi Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    """
    return {
        "tools": [
            {
                "name": "get_inventory",
                "description": "Get inventory levels from ShipBob. Use this when the user wants to check stock, inventory quantities, fulfillable quantity, or how much of a product is available. Can get all inventory or search for a specific product.",
                "endpoint": "/tools/get_inventory",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "product_name": {
                            "type": "string",
                            "description": "Name of a specific product to check inventory for. If not provided, returns all inventory items."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of items to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Checking inventory levels..."
            },
            {
                "name": "get_products",
                "description": "Get list of products from ShipBob. Use this when the user wants to see their products, search for products, or find product information.",
                "endpoint": "/tools/get_products",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "search": {
                            "type": "string",
                            "description": "Search term to filter products by name"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of products to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting products..."
            },
            {
                "name": "create_wro",
                "description": "Create a Warehouse Receiving Order (WRO) in ShipBob. Use this when the user wants to send inventory to ShipBob, create a receiving order, or notify ShipBob about incoming stock.",
                "endpoint": "/tools/create_wro",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "product_name": {
                            "type": "string",
                            "description": "Name of the product being received. Required."
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Quantity of units being sent. Required."
                        },
                        "expected_arrival_date": {
                            "type": "string",
                            "description": "Expected arrival date (YYYY-MM-DD format). Defaults to 7 days from now."
                        },
                        "tracking_number": {
                            "type": "string",
                            "description": "Tracking number for the shipment (optional)"
                        },
                        "purchase_order_number": {
                            "type": "string",
                            "description": "Purchase order number for reference (optional)"
                        },
                        "fulfillment_center_id": {
                            "type": "integer",
                            "description": "ID of the fulfillment center. If not provided, uses the first available FC."
                        },
                        "packaging_type": {
                            "type": "string",
                            "description": "Box packaging type: 'EverythingInOneBox', 'OneSkuPerBox', or 'MultipleSkuPerBox'. Default: 'EverythingInOneBox'"
                        }
                    },
                    "required": ["product_name", "quantity"]
                },
                "auth_required": True,
                "status_message": "Creating Warehouse Receiving Order..."
            },
            {
                "name": "get_wros",
                "description": "Get Warehouse Receiving Orders from ShipBob. Use this when the user wants to check WRO status, see incoming inventory, or view receiving orders.",
                "endpoint": "/tools/get_wros",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status: 'Awaiting', 'PartiallyArrived', 'Processing', 'Completed'"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of WROs to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting Warehouse Receiving Orders..."
            },
            {
                "name": "cancel_wro",
                "description": "Cancel a Warehouse Receiving Order. Use this when the user wants to cancel an incoming shipment or receiving order. Note: Cannot cancel WROs that have partially arrived, are being processed, or are completed.",
                "endpoint": "/tools/cancel_wro",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "wro_id": {
                            "type": "integer",
                            "description": "The WRO ID to cancel. Required."
                        }
                    },
                    "required": ["wro_id"]
                },
                "auth_required": True,
                "status_message": "Cancelling WRO..."
            },
            {
                "name": "get_orders",
                "description": "Get recent orders from ShipBob. Use this when the user wants to check order status, see recent orders, or view fulfillment status.",
                "endpoint": "/tools/get_orders",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by order status"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of orders to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting orders..."
            },
            {
                "name": "get_fulfillment_centers",
                "description": "Get available ShipBob fulfillment centers. Use this when the user wants to see warehouse locations, FC options, or needs a fulfillment center ID for creating WROs.",
                "endpoint": "/tools/get_fulfillment_centers",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting fulfillment centers..."
            }
        ]
    }


# ============================================
# Run Server
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
