"""
Shopify Integration App for Omi

This app provides Shopify integration through OAuth authentication
and chat tools for analytics, orders, and customer management.
"""
import os
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    store_shopify_tokens,
    get_shopify_tokens,
    delete_shopify_tokens,
    store_default_store,
    get_default_store,
    get_user_settings,
)
from models import (
    ChatToolResponse,
    ShopifyOrder,
    ShopifyCustomer,
    ShopifyLineItem,
    ShopifyAnalytics,
    ShopifyShop,
)

load_dotenv()

# Shopify API Configuration
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
SHOPIFY_REDIRECT_URI = os.getenv("SHOPIFY_REDIRECT_URI", "http://localhost:8080/auth/shopify/callback")

# Shopify API version
SHOPIFY_API_VERSION = "2024-01"

# Required Shopify scopes
SHOPIFY_SCOPES = [
    "read_all_orders",
    "read_analytics",
    "read_customers",
    "write_customers",
    "write_draft_orders",
    "read_draft_orders",
    "read_orders",
    "write_orders",
]

app = FastAPI(
    title="Shopify Omi Integration",
    description="Shopify integration for Omi - Analytics, orders, and customer management",
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

def get_auth_header(access_token: str) -> Dict[str, str]:
    """Get authorization header for Shopify API requests."""
    return {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }


def shopify_api_request(
    uid: str,
    method: str,
    endpoint: str,
    params: Optional[Dict] = None,
    json_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """Make an authenticated request to Shopify API."""
    tokens = get_shopify_tokens(uid)
    if not tokens:
        return {"error": "User not authenticated with Shopify"}
    
    access_token = tokens["access_token"]
    shop_domain = tokens["shop_domain"]
    
    url = f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}{endpoint}"
    headers = get_auth_header(access_token)
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, params=params)
        else:
            return {"error": f"Unsupported HTTP method: {method}"}
        
        if response.status_code == 204:
            return {"success": True}
        elif response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("errors", f"API error: {response.status_code}")
            if isinstance(error_msg, dict):
                error_msg = str(error_msg)
            return {"error": error_msg}
        
        return response.json() if response.content else {"success": True}
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


def verify_shopify_hmac(query_string: str, hmac_value: str) -> bool:
    """Verify the HMAC signature from Shopify."""
    # Parse query string and remove hmac parameter
    params = urllib.parse.parse_qs(query_string)
    params.pop('hmac', None)
    
    # Sort and encode parameters
    sorted_params = sorted(params.items())
    encoded = urllib.parse.urlencode([(k, v[0]) for k, v in sorted_params])
    
    # Calculate HMAC
    digest = hmac.new(
        SHOPIFY_CLIENT_SECRET.encode('utf-8'),
        encoded.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(digest, hmac_value)


def format_currency(amount: str, currency: str = "USD") -> str:
    """Format currency amount."""
    try:
        value = float(amount)
        return f"${value:,.2f} {currency}"
    except (ValueError, TypeError):
        return f"${amount} {currency}"


def format_datetime(dt_string: str) -> str:
    """Format datetime string to readable format."""
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return dt_string


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
    
    tokens = get_shopify_tokens(uid)
    authenticated = tokens is not None
    
    # Get shop info if authenticated
    shop_info = None
    recent_orders = []
    
    if authenticated:
        shop_result = shopify_api_request(uid, "GET", "/shop.json")
        if "error" not in shop_result:
            shop_info = shop_result.get("shop", {})
        
        # Get recent orders count
        orders_result = shopify_api_request(uid, "GET", "/orders/count.json")
        if "error" not in orders_result:
            recent_orders = orders_result
    
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "uid": uid,
        "authenticated": authenticated,
        "shop_info": shop_info,
        "recent_orders": recent_orders,
        "shop_domain": tokens.get("shop_domain") if tokens else None,
    })


@app.get("/auth/shopify")
async def shopify_auth(uid: str, shop: Optional[str] = None):
    """Initiate Shopify OAuth flow."""
    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not shop:
        # Return a page to enter shop domain
        raise HTTPException(status_code=400, detail="Shop domain is required. Use /auth/shopify?uid=...&shop=your-store.myshopify.com")
    
    # Ensure shop domain is properly formatted
    if not shop.endswith('.myshopify.com'):
        shop = f"{shop}.myshopify.com"
    
    # Build OAuth URL
    scopes = ",".join(SHOPIFY_SCOPES)
    params = {
        "client_id": SHOPIFY_CLIENT_ID,
        "scope": scopes,
        "redirect_uri": SHOPIFY_REDIRECT_URI,
        "state": uid,  # Use uid as state to identify user on callback
    }
    
    auth_url = f"https://{shop}/admin/oauth/authorize?{urllib.parse.urlencode(params)}"
    print(f"🔐 SHOPIFY OAUTH - Redirecting to: {auth_url}")
    print(f"🔐 Client ID: {SHOPIFY_CLIENT_ID}")
    print(f"🔐 Redirect URI: {SHOPIFY_REDIRECT_URI}")
    print(f"🔐 Shop: {shop}")
    print(f"🔐 Scopes: {scopes}")
    return RedirectResponse(url=auth_url)


@app.get("/auth/shopify/callback", response_class=HTMLResponse)
async def shopify_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    shop: Optional[str] = None,
    hmac: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    """Handle Shopify OAuth callback."""
    if error:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": f"Authorization failed: {error_description or error}"
        })
    
    if not code or not state or not shop:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Invalid callback parameters"
        })
    
    uid = state
    
    # Exchange code for access token
    token_url = f"https://{shop}/admin/oauth/access_token"
    
    response = requests.post(
        token_url,
        json={
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
            "code": code,
        },
    )
    
    if response.status_code != 200:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Failed to exchange authorization code"
        })
    
    token_data = response.json()
    access_token = token_data.get("access_token")
    scope = token_data.get("scope", "")
    
    if not access_token:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "No access token received"
        })
    
    # Store tokens
    store_shopify_tokens(uid, access_token, shop, scope)
    
    # Get shop name and store as default
    headers = get_auth_header(access_token)
    shop_response = requests.get(
        f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/shop.json",
        headers=headers
    )
    if shop_response.status_code == 200:
        shop_data = shop_response.json().get("shop", {})
        store_default_store(uid, shop, shop_data.get("name", shop))
    
    # Redirect to home with uid
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/setup/shopify", tags=["setup"])
async def check_setup(uid: str):
    """Check if the user has completed Shopify setup (used by Omi)."""
    tokens = get_shopify_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect_shopify(uid: str):
    """Disconnect Shopify account."""
    delete_shopify_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ============================================
# Chat Tool Endpoints
# ============================================

def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats into datetime object."""
    if not date_str:
        return None
    
    # Try various date formats
    formats = [
        "%Y-%m-%d",           # 2024-11-28
        "%m/%d/%Y",           # 11/28/2024
        "%d/%m/%Y",           # 28/11/2024
        "%B %d, %Y",          # November 28, 2024
        "%b %d, %Y",          # Nov 28, 2024
        "%B %d %Y",           # November 28 2024
        "%b %d %Y",           # Nov 28 2024
        "%d %B %Y",           # 28 November 2024
        "%d %b %Y",           # 28 Nov 2024
        "%Y/%m/%d",           # 2024/11/28
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    return None


@app.post("/tools/get_analytics", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_analytics(request: Request):
    """
    Get store analytics.
    Chat tool for Omi - retrieves store analytics and sales data.
    Supports both preset periods and custom date ranges.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        period = body.get("period", "today")
        custom_start_date = body.get("start_date")  # Custom start date
        custom_end_date = body.get("end_date")      # Custom end date
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_shopify_tokens(uid):
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        # Calculate date range based on period or custom dates
        today = datetime.utcnow().date()
        period_text = ""
        
        # If custom dates are provided, use them
        if custom_start_date and custom_end_date:
            parsed_start = parse_date(custom_start_date)
            parsed_end = parse_date(custom_end_date)
            
            if not parsed_start or not parsed_end:
                return ChatToolResponse(error=f"Invalid date format. Please use formats like '2024-11-28', 'Nov 28, 2024', or '11/28/2024'.")
            
            start_date = parsed_start.date()
            end_date = parsed_end.date()
            period_text = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        elif custom_start_date:
            # Only start date provided - use today as end
            parsed_start = parse_date(custom_start_date)
            if not parsed_start:
                return ChatToolResponse(error=f"Invalid start date format. Please use formats like '2024-11-28', 'Nov 28, 2024', or '11/28/2024'.")
            start_date = parsed_start.date()
            end_date = today
            period_text = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        else:
            # Use preset period
            if period == "yesterday":
                start_date = today - timedelta(days=1)
                end_date = today - timedelta(days=1)
            elif period == "last_7_days":
                start_date = today - timedelta(days=7)
                end_date = today
            elif period == "last_30_days":
                start_date = today - timedelta(days=30)
                end_date = today
            elif period == "this_month":
                start_date = today.replace(day=1)
                end_date = today
            elif period == "last_month":
                first_of_this_month = today.replace(day=1)
                end_date = first_of_this_month - timedelta(days=1)
                start_date = end_date.replace(day=1)
            elif period == "this_year":
                start_date = today.replace(month=1, day=1)
                end_date = today
            else:  # today
                start_date = today
                end_date = today
            
            period_text = {
                "today": "Today",
                "yesterday": "Yesterday",
                "last_7_days": "Last 7 Days",
                "last_30_days": "Last 30 Days",
                "this_month": "This Month",
                "last_month": "Last Month",
                "this_year": "This Year"
            }.get(period, period)
        
        # Get orders - need to handle pagination for large date ranges
        all_orders = []
        params = {
            "status": "any",
            "created_at_min": f"{start_date}T00:00:00Z",
            "created_at_max": f"{end_date}T23:59:59Z",
            "limit": 250,  # Max per page
        }
        
        # Fetch first page
        orders_result = shopify_api_request(uid, "GET", "/orders.json", params=params)
        
        if "error" in orders_result:
            return ChatToolResponse(error=f"Failed to get analytics: {orders_result['error']}")
        
        all_orders.extend(orders_result.get("orders", []))
        
        # Fetch additional pages if needed (up to 1000 orders total)
        page_count = 1
        while len(orders_result.get("orders", [])) == 250 and page_count < 4:
            # Get the last order ID for pagination
            last_order_id = orders_result["orders"][-1]["id"]
            params["since_id"] = last_order_id
            orders_result = shopify_api_request(uid, "GET", "/orders.json", params=params)
            if "error" in orders_result:
                break
            all_orders.extend(orders_result.get("orders", []))
            page_count += 1
        
        orders = all_orders
        
        # Calculate detailed financial analytics
        total_orders = len(orders)
        
        # Gross sales (subtotal before discounts, taxes, shipping)
        gross_sales = sum(float(o.get("subtotal_price", 0)) for o in orders)
        
        # Total discounts applied
        total_discounts = sum(float(o.get("total_discounts", 0)) for o in orders)
        
        # Calculate refunds
        total_refunds = 0
        refunded_orders = 0
        for order in orders:
            refunds = order.get("refunds", [])
            if refunds:
                refunded_orders += 1
                for refund in refunds:
                    for transaction in refund.get("transactions", []):
                        total_refunds += float(transaction.get("amount", 0))
        
        # Net sales (gross - discounts - refunds)
        net_sales = gross_sales - total_discounts - total_refunds
        
        # Total collected (what was actually charged - includes tax & shipping)
        total_collected = sum(float(o.get("total_price", 0)) for o in orders)
        
        # Taxes and shipping
        total_tax = sum(float(o.get("total_tax", 0)) for o in orders)
        total_shipping = sum(
            float(o.get("total_shipping_price_set", {}).get("shop_money", {}).get("amount", 0))
            for o in orders
        )
        
        avg_order_value = total_collected / total_orders if total_orders > 0 else 0
        
        # Count unique customers
        customer_ids = set()
        new_customers = 0
        returning_customers = 0
        for order in orders:
            if order.get("customer"):
                customer_id = order["customer"].get("id")
                customer_ids.add(customer_id)
                # Check if new customer (orders_count == 1 at time of order)
                if order["customer"].get("orders_count", 0) <= 1:
                    new_customers += 1
                else:
                    returning_customers += 1
        
        # Get currency from first order or default
        currency = orders[0].get("currency", "USD") if orders else "USD"
        
        # Calculate additional metrics
        total_items = sum(
            sum(item.get("quantity", 0) for item in o.get("line_items", []))
            for o in orders
        )
        avg_items_per_order = total_items / total_orders if total_orders > 0 else 0
        
        # Discount rate
        discount_rate = (total_discounts / gross_sales * 100) if gross_sales > 0 else 0
        
        # Calculate COGS (Cost of Goods Sold) by fetching variant costs
        total_cogs = 0
        variant_costs = {}  # Cache variant costs to avoid repeated API calls
        cogs_available = True
        
        # Collect all unique variant IDs
        variant_ids = set()
        for order in orders:
            for item in order.get("line_items", []):
                variant_id = item.get("variant_id")
                if variant_id:
                    variant_ids.add(variant_id)
        
        # Fetch costs for variants (batch fetch products)
        if variant_ids:
            # Get unique product IDs
            product_ids = set()
            for order in orders:
                for item in order.get("line_items", []):
                    product_id = item.get("product_id")
                    if product_id:
                        product_ids.add(product_id)
            
            # Fetch products with variants to get inventory_item_ids
            inventory_item_ids = []
            for product_id in list(product_ids)[:50]:  # Limit to avoid too many API calls
                product_result = shopify_api_request(uid, "GET", f"/products/{product_id}.json")
                if "error" not in product_result:
                    product = product_result.get("product", {})
                    for variant in product.get("variants", []):
                        inv_item_id = variant.get("inventory_item_id")
                        if inv_item_id:
                            inventory_item_ids.append((variant["id"], inv_item_id))
            
            # Fetch inventory items to get costs (batch up to 100)
            if inventory_item_ids:
                inv_ids_str = ",".join(str(iid[1]) for iid in inventory_item_ids[:100])
                inv_result = shopify_api_request(
                    uid, "GET", "/inventory_items.json",
                    params={"ids": inv_ids_str}
                )
                if "error" not in inv_result:
                    for inv_item in inv_result.get("inventory_items", []):
                        inv_id = inv_item.get("id")
                        cost = inv_item.get("cost")
                        # Find matching variant
                        for var_id, iid in inventory_item_ids:
                            if iid == inv_id and cost:
                                variant_costs[var_id] = float(cost)
        
        # Calculate total COGS
        items_with_cost = 0
        items_without_cost = 0
        for order in orders:
            for item in order.get("line_items", []):
                variant_id = item.get("variant_id")
                quantity = item.get("quantity", 0)
                if variant_id and variant_id in variant_costs:
                    total_cogs += variant_costs[variant_id] * quantity
                    items_with_cost += quantity
                else:
                    items_without_cost += quantity
        
        # Calculate profit metrics
        gross_profit = net_sales - total_cogs
        profit_margin = (gross_profit / net_sales * 100) if net_sales > 0 else 0
        
        # Check if COGS data is complete
        cogs_note = ""
        if items_without_cost > 0:
            cogs_coverage = (items_with_cost / (items_with_cost + items_without_cost) * 100) if (items_with_cost + items_without_cost) > 0 else 0
            if cogs_coverage < 100:
                cogs_note = f" ({cogs_coverage:.0f}% of items have cost data)"
        
        result = f"""📊 **Store Analytics - {period_text}**

**💵 FINANCIAL SUMMARY**
━━━━━━━━━━━━━━━━━━━━━━
📈 **Gross Sales:** {format_currency(str(gross_sales), currency)}
🏷️ **Discounts:** -{format_currency(str(total_discounts), currency)} ({discount_rate:.1f}%)
↩️ **Refunds:** -{format_currency(str(total_refunds), currency)} ({refunded_orders} orders)
━━━━━━━━━━━━━━━━━━━━━━
💰 **Net Sales:** {format_currency(str(net_sales), currency)}

**📊 PROFIT & LOSS**
━━━━━━━━━━━━━━━━━━━━━━
💰 **Net Sales:** {format_currency(str(net_sales), currency)}
📦 **COGS:** -{format_currency(str(total_cogs), currency)}{cogs_note}
━━━━━━━━━━━━━━━━━━━━━━
💹 **Gross Profit:** {format_currency(str(gross_profit), currency)}
📈 **Profit Margin:** {profit_margin:.1f}%

**📦 ORDER METRICS**
━━━━━━━━━━━━━━━━━━━━━━
📦 **Total Orders:** {total_orders}
💵 **Avg Order Value:** {format_currency(str(avg_order_value), currency)}
🛒 **Items Sold:** {total_items}
📊 **Avg Items/Order:** {avg_items_per_order:.1f}

**👥 CUSTOMERS**
━━━━━━━━━━━━━━━━━━━━━━
👥 **Unique Customers:** {len(customer_ids)}
✨ **New Customers:** {new_customers}
🔄 **Returning:** {returning_customers}

**💳 COLLECTED**
━━━━━━━━━━━━━━━━━━━━━━
💳 **Total Collected:** {format_currency(str(total_collected), currency)}
🏛️ **Tax:** {format_currency(str(total_tax), currency)}
🚚 **Shipping:** {format_currency(str(total_shipping), currency)}"""
        
        # Add top products if we have orders
        if orders:
            product_sales = {}
            product_revenue = {}
            for order in orders:
                for item in order.get("line_items", []):
                    title = item.get("title", "Unknown")
                    qty = item.get("quantity", 0)
                    price = float(item.get("price", 0)) * qty
                    product_sales[title] = product_sales.get(title, 0) + qty
                    product_revenue[title] = product_revenue.get(title, 0) + price
            
            if product_sales:
                top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]
                result += "\n\n📈 **Top Products (by quantity):**"
                for i, (name, qty) in enumerate(top_products, 1):
                    revenue = product_revenue.get(name, 0)
                    result += f"\n{i}. {name} - {qty} sold ({format_currency(str(revenue), currency)})"
        
        return ChatToolResponse(result=result)
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get analytics: {str(e)}")


@app.post("/tools/get_orders", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_orders(request: Request):
    """
    Get recent orders.
    Chat tool for Omi - retrieves a list of recent orders.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        status = body.get("status", "any")
        financial_status = body.get("financial_status")
        limit = min(body.get("limit", 10), 50)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_shopify_tokens(uid):
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        params = {
            "status": status,
            "limit": limit,
        }
        if financial_status:
            params["financial_status"] = financial_status
        
        result = shopify_api_request(uid, "GET", "/orders.json", params=params)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get orders: {result['error']}")
        
        orders = result.get("orders", [])
        
        if not orders:
            return ChatToolResponse(result="📦 No orders found matching your criteria.")
        
        # Format results
        lines = [f"📦 **Recent Orders** ({len(orders)} found):\n"]
        
        for order in orders:
            order_name = order.get("name", f"#{order.get('order_number', 'N/A')}")
            total = format_currency(order.get("total_price", "0"), order.get("currency", "USD"))
            status_emoji = {
                "paid": "✅",
                "pending": "⏳",
                "refunded": "↩️",
                "partially_refunded": "↩️",
                "voided": "❌",
            }.get(order.get("financial_status", ""), "❓")
            
            fulfillment = order.get("fulfillment_status") or "unfulfilled"
            fulfillment_emoji = "📬" if fulfillment == "fulfilled" else "📦"
            
            customer_name = "Guest"
            if order.get("customer"):
                first = order["customer"].get("first_name", "")
                last = order["customer"].get("last_name", "")
                customer_name = f"{first} {last}".strip() or order["customer"].get("email", "Guest")
            
            created = format_datetime(order.get("created_at", ""))
            
            lines.append(f"**{order_name}** - {total} {status_emoji}")
            lines.append(f"   👤 {customer_name} | {fulfillment_emoji} {fulfillment.title()}")
            lines.append(f"   📅 {created}\n")
        
        return ChatToolResponse(result="\n".join(lines))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get orders: {str(e)}")


@app.post("/tools/get_order_details", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_order_details(request: Request):
    """
    Get details of a specific order.
    Chat tool for Omi - retrieves detailed information about an order.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        order_id = body.get("order_id")
        order_number = body.get("order_number")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not order_id and not order_number:
            return ChatToolResponse(error="Please provide an order ID or order number.")
        
        # Check authentication
        if not get_shopify_tokens(uid):
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        # If we have order number, search for it
        if order_number and not order_id:
            # Remove # if present
            order_number = str(order_number).lstrip('#')
            
            result = shopify_api_request(
                uid, "GET", "/orders.json",
                params={"name": f"#{order_number}", "status": "any"}
            )
            
            if "error" in result:
                return ChatToolResponse(error=f"Failed to find order: {result['error']}")
            
            orders = result.get("orders", [])
            if not orders:
                return ChatToolResponse(error=f"Order #{order_number} not found.")
            
            order_id = orders[0]["id"]
        
        # Get order details
        result = shopify_api_request(uid, "GET", f"/orders/{order_id}.json")
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get order: {result['error']}")
        
        order = result.get("order", {})
        
        if not order:
            return ChatToolResponse(error="Order not found.")
        
        # Format order details
        order_name = order.get("name", f"#{order.get('order_number', 'N/A')}")
        currency = order.get("currency", "USD")
        
        status_emoji = {
            "paid": "✅ Paid",
            "pending": "⏳ Pending",
            "refunded": "↩️ Refunded",
            "partially_refunded": "↩️ Partially Refunded",
            "voided": "❌ Voided",
        }.get(order.get("financial_status", ""), "❓ Unknown")
        
        fulfillment = order.get("fulfillment_status") or "unfulfilled"
        fulfillment_text = "📬 Fulfilled" if fulfillment == "fulfilled" else "📦 " + fulfillment.title()
        
        # Customer info
        customer_info = "👤 Guest checkout"
        if order.get("customer"):
            c = order["customer"]
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            email = c.get("email", "")
            customer_info = f"👤 {name or 'Customer'}"
            if email:
                customer_info += f" ({email})"
        
        # Line items
        items_text = ""
        for item in order.get("line_items", []):
            qty = item.get("quantity", 1)
            title = item.get("title", "Unknown")
            price = format_currency(item.get("price", "0"), currency)
            items_text += f"\n   • {qty}x {title} @ {price}"
        
        # Shipping address
        shipping_text = ""
        if order.get("shipping_address"):
            addr = order["shipping_address"]
            shipping_text = f"\n\n📍 **Shipping to:**\n   {addr.get('name', '')}\n   {addr.get('address1', '')}"
            if addr.get("address2"):
                shipping_text += f"\n   {addr['address2']}"
            shipping_text += f"\n   {addr.get('city', '')}, {addr.get('province', '')} {addr.get('zip', '')}\n   {addr.get('country', '')}"
        
        result_text = f"""📋 **Order {order_name}**

{status_emoji} | {fulfillment_text}
{customer_info}

📅 **Created:** {format_datetime(order.get('created_at', ''))}

🛒 **Items:**{items_text}

💰 **Subtotal:** {format_currency(order.get('subtotal_price', '0'), currency)}
📦 **Shipping:** {format_currency(order.get('total_shipping_price_set', {}).get('shop_money', {}).get('amount', '0'), currency)}
💵 **Tax:** {format_currency(order.get('total_tax', '0'), currency)}
**Total:** {format_currency(order.get('total_price', '0'), currency)}{shipping_text}"""
        
        if order.get("note"):
            result_text += f"\n\n📝 **Note:** {order['note']}"
        
        return ChatToolResponse(result=result_text)
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get order details: {str(e)}")


@app.post("/tools/create_order", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_order(request: Request):
    """
    Create a new order.
    Chat tool for Omi - creates a new order. Can search for customer by name or email.
    Automatically fetches product prices from store.
    """
    try:
        body = await request.json()
        print(f"🛒 CREATE ORDER - Received request: {body}")
        
        uid = body.get("uid")
        customer_email = body.get("customer_email")
        customer_name = body.get("customer_name", "")  # Can search by name
        customer_first_name = body.get("customer_first_name", "")
        customer_last_name = body.get("customer_last_name", "")
        customer_phone = body.get("customer_phone", "")
        customer_id_provided = body.get("customer_id")  # Direct customer ID selection
        line_items = body.get("line_items", [])
        shipping_address = body.get("shipping_address")
        note = body.get("note", "")
        tags = body.get("tags", "")
        send_receipt = body.get("send_receipt", True)
        financial_status = body.get("financial_status", "pending")
        discount_code = body.get("discount_code", "")  # Coupon/discount code
        free_shipping = body.get("free_shipping", False)  # Skip shipping charges
        
        # Check if discount code implies free shipping
        if discount_code and "freeshipping" in discount_code.lower().replace("_", "").replace("-", "").replace(" ", ""):
            free_shipping = True
            print(f"🆓 Free shipping detected from discount code: {discount_code}")
        
        # Address fields - can be passed individually
        address_line1 = body.get("address_line1", "") or body.get("address1", "") or body.get("street", "")
        address_line2 = body.get("address_line2", "") or body.get("address2", "")
        city = body.get("city", "")
        state = body.get("state", "") or body.get("province", "")
        zip_code = body.get("zip_code", "") or body.get("zip", "") or body.get("postal_code", "")
        country = body.get("country", "US")
        
        # Build shipping address from individual fields if not provided as object
        if not shipping_address and (address_line1 or city):
            shipping_address = {
                "first_name": customer_first_name or (customer_name.split()[0] if customer_name else ""),
                "last_name": customer_last_name or (customer_name.split()[-1] if customer_name and len(customer_name.split()) > 1 else ""),
                "address1": address_line1,
                "address2": address_line2,
                "city": city,
                "province": state,
                "zip": zip_code,
                "country": country,
                "phone": customer_phone,
            }
            print(f"📍 Built shipping address: {shipping_address}")
        
        
        print(f"🔍 DEBUG: uid={uid}, line_items={line_items}")
        
        if not uid:
            print(f"❌ No UID provided")
            return ChatToolResponse(error="User ID is required")
        
        if not line_items:
            print(f"❌ No line items provided")
            return ChatToolResponse(error="At least one line item is required. Please provide items with product name and quantity.")
        
        # Check authentication
        try:
            print(f"🔍 DEBUG: Getting tokens...")
            tokens = get_shopify_tokens(uid)
            print(f"🔍 DEBUG: tokens={tokens is not None}")
        except Exception as e:
            print(f"❌ Exception getting tokens: {e}")
            import traceback
            traceback.print_exc()
            return ChatToolResponse(error=f"Auth error: {str(e)}")
        
        if not tokens:
            print(f"❌ No Shopify tokens found")
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        customer_id = None
        customer_created = False
        customer_display_name = ""
        
        # If customer_id provided directly, use it
        if customer_id_provided:
            customer_id = customer_id_provided
            # Fetch customer details for display
            cust_result = shopify_api_request(uid, "GET", f"/customers/{customer_id}.json")
            if "error" not in cust_result and cust_result.get("customer"):
                c = cust_result["customer"]
                customer_display_name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                customer_email = c.get("email", "")
                customer_first_name = c.get("first_name", "")
                customer_last_name = c.get("last_name", "")
            print(f"🛒 Using provided customer ID: {customer_id}")
        
        # Search for customer by email first, then by name
        elif customer_email or customer_name:
            customers_found = []
            
            # Search by email if provided
            if customer_email:
                result = shopify_api_request(
                    uid, "GET", "/customers/search.json",
                    params={"query": f"email:{customer_email}"}
                )
                if "error" not in result:
                    customers_found = result.get("customers", [])
            
            # Search by name if no email or no results
            if not customers_found and customer_name:
                print(f"🔍 Searching for customer by name: {customer_name}")
                result = shopify_api_request(
                    uid, "GET", "/customers/search.json",
                    params={"query": customer_name}
                )
                if "error" not in result:
                    customers_found = result.get("customers", [])
            
            # Also try first/last name if provided
            if not customers_found and (customer_first_name or customer_last_name):
                search_term = f"{customer_first_name} {customer_last_name}".strip()
                if search_term:
                    print(f"🔍 Searching for customer by first/last name: {search_term}")
                    result = shopify_api_request(
                        uid, "GET", "/customers/search.json",
                        params={"query": search_term}
                    )
                    if "error" not in result:
                        customers_found = result.get("customers", [])
            
            if len(customers_found) > 1:
                # Multiple matches - ask user to choose
                lines = ["🔍 **Multiple customers found. Please specify which one:**\n"]
                for i, c in enumerate(customers_found[:10], 1):
                    name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "No name"
                    email = c.get("email", "No email")
                    orders_count = c.get("orders_count", 0)
                    lines.append(f"{i}. **{name}** - {email} ({orders_count} orders) [ID: {c['id']}]")
                lines.append("\n💡 Try again with: 'create order for [email] for 3 Omis'")
                lines.append("Or specify customer ID directly.")
                return ChatToolResponse(result="\n".join(lines))
            
            elif len(customers_found) == 1:
                # Exact match found
                c = customers_found[0]
                customer_id = c["id"]
                customer_email = c.get("email", customer_email)
                customer_first_name = c.get("first_name", customer_first_name)
                customer_last_name = c.get("last_name", customer_last_name)
                customer_display_name = f"{customer_first_name} {customer_last_name}".strip()
                print(f"🛒 Found customer: {customer_display_name} ({customer_id})")
            
            else:
                # No customer found - need email to create
                if not customer_email:
                    return ChatToolResponse(error=f"No customer found matching '{customer_name or customer_first_name + ' ' + customer_last_name}'. Please provide an email to create a new customer, or use a different name.")
                
                # Create new customer
                print(f"🛒 Creating new customer: {customer_email}")
                new_customer = {
                    "customer": {
                        "email": customer_email,
                        "first_name": customer_first_name or customer_name.split()[0] if customer_name else "",
                        "last_name": customer_last_name or (customer_name.split()[-1] if customer_name and len(customer_name.split()) > 1 else ""),
                        "phone": customer_phone,
                        "verified_email": True,
                        "send_email_welcome": False,
                    }
                }
                
                customer_create_result = shopify_api_request(
                    uid, "POST", "/customers.json",
                    json_data=new_customer
                )
                
                if "error" in customer_create_result:
                    print(f"🛒 Failed to create customer: {customer_create_result['error']}")
                else:
                    customer_id = customer_create_result.get("customer", {}).get("id")
                    customer_created = True
                    customer_display_name = f"{customer_first_name} {customer_last_name}".strip()
                    print(f"🛒 Created new customer: {customer_id}")
        else:
            return ChatToolResponse(error="Please provide a customer name or email.")
        
        # Fetch all products once for matching
        print(f"📦 Fetching all products from store...")
        all_products_result = shopify_api_request(uid, "GET", "/products.json", params={"limit": 250, "status": "active"})
        print(f"📦 Products API response: {all_products_result}")
        all_products = []
        if "error" in all_products_result:
            print(f"❌ Products API error: {all_products_result['error']}")
        else:
            all_products = all_products_result.get("products", [])
            print(f"📦 Found {len(all_products)} products in store")
            for p in all_products:
                print(f"   - {p.get('title')}")
        
        # If no products found, maybe need read_products scope - try alternate approach
        if not all_products:
            print(f"⚠️ No products returned. Trying to extract from recent orders...")
            # Get products from recent orders as fallback
            orders_result = shopify_api_request(uid, "GET", "/orders.json", params={"limit": 50, "status": "any"})
            if "error" not in orders_result:
                seen_products = {}
                for order in orders_result.get("orders", []):
                    for item in order.get("line_items", []):
                        variant_id = item.get("variant_id")
                        title = item.get("title", "")
                        price = item.get("price", "0")
                        if variant_id and title and variant_id not in seen_products:
                            seen_products[variant_id] = {
                                "title": title,
                                "variants": [{"id": variant_id, "price": price}]
                            }
                all_products = list(seen_products.values())
                print(f"📦 Extracted {len(all_products)} products from orders:")
                for p in all_products:
                    print(f"   - {p.get('title')} (variant: {p['variants'][0]['id']})")
        
        # Build order data - search for existing products
        order_line_items = []
        product_matches = []
        
        for item in line_items:
            title = item.get("title", "Custom Item")
            quantity = item.get("quantity", 1)
            provided_price = item.get("price")
            variant_id = item.get("variant_id")
            sku = item.get("sku")
            
            order_item = None
            matched_product = None
            
            # If variant_id is provided, use it directly
            if variant_id:
                order_item = {"variant_id": variant_id, "quantity": quantity}
                if provided_price:
                    order_item["price"] = str(provided_price)
            else:
                # Fuzzy search for the product by title
                print(f"🔍 Searching for product: '{title}'")
                search_title = title.lower().strip()
                found_variant = None
                
                # Try exact match first (case-insensitive)
                for product in all_products:
                    product_title = product.get("title", "").lower().strip()
                    if product_title == search_title:
                        if product.get("variants"):
                            found_variant = product["variants"][0]
                            matched_product = product["title"]
                            print(f"✅ Exact match: '{title}' → {product['title']}")
                            break
                
                # Try "contains" match - search term in product title
                if not found_variant:
                    for product in all_products:
                        product_title = product.get("title", "").lower()
                        if search_title in product_title:
                            if product.get("variants"):
                                found_variant = product["variants"][0]
                                matched_product = product["title"]
                                print(f"✅ Contains match: '{title}' found in '{product['title']}'")
                                break
                
                # Try reverse "contains" - product title in search term
                if not found_variant:
                    for product in all_products:
                        product_title = product.get("title", "").lower().strip()
                        if product_title in search_title:
                            if product.get("variants"):
                                found_variant = product["variants"][0]
                                matched_product = product["title"]
                                print(f"✅ Reverse match: product '{product['title']}' in search '{title}'")
                                break
                
                # Try word-by-word fuzzy match
                if not found_variant:
                    search_words = search_title.split()
                    for product in all_products:
                        product_title = product.get("title", "").lower()
                        # Check if any search word matches any word in product title
                        for word in search_words:
                            if len(word) >= 2 and word in product_title:
                                if product.get("variants"):
                                    found_variant = product["variants"][0]
                                    matched_product = product["title"]
                                    print(f"✅ Word match: '{word}' found in '{product['title']}'")
                                    break
                        if found_variant:
                            break
                
                if found_variant:
                    # Get product price from variant
                    product_price = found_variant.get("price", "0")
                    order_item = {
                        "variant_id": found_variant["id"],
                        "quantity": quantity
                    }
                    # Only override price if explicitly provided, otherwise use product price
                    if provided_price:
                        order_item["price"] = str(provided_price)
                        product_matches.append(f"'{title}' → **{matched_product}** @ ${provided_price} (custom price)")
                    else:
                        product_matches.append(f"'{title}' → **{matched_product}** @ ${product_price}")
                    print(f"✅ Using product: {matched_product} at ${product_price}/unit")
                else:
                    # No product found - show available products
                    print(f"⚠️ No product found for: '{title}'")
                    
                    if all_products:
                        lines = [f"❌ **Product '{title}' not found in your store.**\n"]
                        lines.append("📦 **Available products:**")
                        for p in all_products[:10]:
                            price = p.get("variants", [{}])[0].get("price", "0") if p.get("variants") else "0"
                            lines.append(f"   • {p['title']} - ${price}")
                        lines.append(f"\n💡 Try: 'create order for [customer] for 3 {all_products[0]['title']}'")
                        return ChatToolResponse(result="\n".join(lines))
                    
                    # Fall back to custom line item if price provided
                    if provided_price:
                        order_item = {
                            "title": title,
                            "quantity": quantity,
                            "price": str(provided_price),
                        }
                        if sku:
                            order_item["sku"] = sku
                        product_matches.append(f"'{title}' → ⚠️ Custom item @ ${provided_price}")
                    else:
                        return ChatToolResponse(error=f"Product '{title}' not found in your store and no price provided. Please use an existing product name.")
            
            order_line_items.append(order_item)
        
        order_data = {
            "order": {
                "email": customer_email,
                "line_items": order_line_items,
                "financial_status": financial_status,
                "send_receipt": send_receipt,
                "send_fulfillment_receipt": False,
            }
        }
        
        if customer_id:
            order_data["order"]["customer"] = {"id": customer_id}
        
        if note:
            order_data["order"]["note"] = note
        
        if tags:
            order_data["order"]["tags"] = tags
        
        if shipping_address:
            order_data["order"]["shipping_address"] = shipping_address
            order_data["order"]["billing_address"] = shipping_address
        
        # Use Draft Orders API if discount code OR shipping address (for proper shipping calculation)
        if discount_code or shipping_address:
            if discount_code:
                print(f"🏷️ Using Draft Orders API to apply discount: {discount_code}")
            if shipping_address:
                print(f"📦 Using Draft Orders API for shipping calculation")
            
            # Build draft order data
            draft_order_data = {
                "draft_order": {
                    "line_items": order_line_items,
                    "email": customer_email,
                }
            }
            
            # Only add note/tags if provided
            if note:
                draft_order_data["draft_order"]["note"] = note
            if tags:
                draft_order_data["draft_order"]["tags"] = tags
            
            if customer_id:
                draft_order_data["draft_order"]["customer"] = {"id": customer_id}
            
            if shipping_address:
                draft_order_data["draft_order"]["shipping_address"] = shipping_address
                draft_order_data["draft_order"]["billing_address"] = shipping_address
            
            # Create draft order
            print(f"🛒 Creating draft order...")
            draft_result = shopify_api_request(uid, "POST", "/draft_orders.json", json_data=draft_order_data)
            
            if "error" in draft_result:
                return ChatToolResponse(error=f"Failed to create draft order: {draft_result['error']}")
            
            draft_order = draft_result.get("draft_order", {})
            draft_order_id = draft_order.get("id")
            
            if not draft_order_id:
                return ChatToolResponse(error="Failed to create draft order - no ID returned")
            
            print(f"📝 Draft order created: {draft_order_id}")
            
            # Fetch and apply shipping rates if address provided (unless free shipping)
            if shipping_address and not free_shipping:
                print(f"📦 Calculating shipping rates...")
                
                # First, get shipping zones configured in the store
                shipping_zones_result = shopify_api_request(uid, "GET", "/shipping_zones.json")
                
                shipping_applied = False
                if "error" not in shipping_zones_result:
                    zones = shipping_zones_result.get("shipping_zones", [])
                    print(f"📦 Found {len(zones)} shipping zones")
                    
                    # Find applicable shipping rate for the destination country
                    dest_country = shipping_address.get("country", "US")
                    dest_province = shipping_address.get("province", "")
                    
                    for zone in zones:
                        # Check if this zone applies to the destination
                        zone_countries = zone.get("countries", [])
                        zone_applies = False
                        
                        for country in zone_countries:
                            if country.get("code") == dest_country:
                                # Check if it's a country-wide zone or has province restrictions
                                provinces = country.get("provinces", [])
                                if not provinces:  # Applies to whole country
                                    zone_applies = True
                                else:
                                    for prov in provinces:
                                        if prov.get("code") == dest_province:
                                            zone_applies = True
                                            break
                                break
                        
                        if zone_applies:
                            # Get weight-based or price-based rates from this zone
                            weight_rates = zone.get("weight_based_shipping_rates", [])
                            price_rates = zone.get("price_based_shipping_rates", [])
                            carrier_rates = zone.get("carrier_shipping_rate_providers", [])
                            
                            # Prefer weight-based rates, then price-based
                            available_rates = weight_rates + price_rates
                            
                            if available_rates:
                                # Pick the first available rate (usually standard shipping)
                                selected_rate = available_rates[0]
                                rate_name = selected_rate.get("name", "Standard Shipping")
                                rate_price = selected_rate.get("price", "0.00")
                                
                                print(f"📦 Found shipping rate: {rate_name} - ${rate_price}")
                                
                                # Update draft order with shipping line
                                shipping_update = {
                                    "draft_order": {
                                        "shipping_line": {
                                            "title": rate_name,
                                            "price": rate_price,
                                            "custom": True
                                        }
                                    }
                                }
                                update_result = shopify_api_request(
                                    uid, "PUT", f"/draft_orders/{draft_order_id}.json",
                                    json_data=shipping_update
                                )
                                
                                if "error" not in update_result:
                                    print(f"✅ Shipping applied: {rate_name} - ${rate_price}")
                                    draft_order = update_result.get("draft_order", draft_order)
                                    shipping_applied = True
                                else:
                                    print(f"⚠️ Failed to apply shipping: {update_result.get('error')}")
                                break
                            elif carrier_rates:
                                print(f"📦 Carrier-based shipping configured (requires checkout calculation)")
                else:
                    print(f"⚠️ Could not fetch shipping zones: {shipping_zones_result.get('error')}")
                
                if not shipping_applied:
                    print(f"⚠️ No shipping rate applied - may need manual shipping setup")
            elif shipping_address and free_shipping:
                print(f"🆓 Free shipping - skipping shipping charges")
            
            # Apply discount code to draft order if provided
            if discount_code:
                print(f"🏷️ Looking up discount code: {discount_code}")
                discount_result = shopify_api_request(
                    uid, "GET", "/price_rules.json", 
                    params={"limit": 250}
                )
                
                applied_discount = None
                if "error" not in discount_result:
                    price_rules = discount_result.get("price_rules", [])
                    for rule in price_rules:
                        # Get discount codes for this rule
                        codes_result = shopify_api_request(
                            uid, "GET", f"/price_rules/{rule['id']}/discount_codes.json"
                        )
                        if "error" not in codes_result:
                            for dc in codes_result.get("discount_codes", []):
                                if dc.get("code", "").upper() == discount_code.upper():
                                    # Found the discount code
                                    value_type = rule.get("value_type", "percentage")
                                    value = abs(float(rule.get("value", "0")))
                                    applied_discount = {
                                        "description": discount_code,
                                        "value_type": value_type,
                                        "value": str(value),
                                        "title": discount_code
                                    }
                                    print(f"✅ Found discount: {discount_code} = {value}{'%' if value_type == 'percentage' else ' off'}")
                                    break
                        if applied_discount:
                            break
                
                # Update draft order with discount
                if applied_discount:
                    update_data = {
                        "draft_order": {
                            "applied_discount": applied_discount
                        }
                    }
                    update_result = shopify_api_request(
                        uid, "PUT", f"/draft_orders/{draft_order_id}.json",
                        json_data=update_data
                    )
                    if "error" in update_result:
                        print(f"⚠️ Failed to apply discount: {update_result['error']}")
                    else:
                        print(f"✅ Discount applied to draft order")
                        draft_order = update_result.get("draft_order", draft_order)
                else:
                    print(f"⚠️ Discount code '{discount_code}' not found in store - creating order without discount")
            
            # Complete the draft order to create actual order (with retry for calculation delay)
            import time
            max_retries = 3
            complete_result = None
            
            for attempt in range(max_retries):
                print(f"🛒 Completing draft order... (attempt {attempt + 1}/{max_retries})")
                
                # Wait a bit for Shopify to finish calculating
                if attempt > 0:
                    time.sleep(2)
                
                complete_result = shopify_api_request(
                    uid, "PUT", f"/draft_orders/{draft_order_id}/complete.json",
                    params={"payment_pending": "true" if financial_status == "pending" else "false"}
                )
                
                if "error" not in complete_result:
                    print(f"✅ Draft order completed successfully")
                    break
                elif "not finished calculating" in complete_result.get("error", "").lower():
                    print(f"⏳ Order still calculating, waiting...")
                    time.sleep(2)
                else:
                    # Different error, don't retry
                    break
            
            print(f"📋 Complete result: {complete_result}")
            
            if "error" in complete_result:
                print(f"❌ Failed to complete draft order: {complete_result['error']}")
                return ChatToolResponse(error=f"Failed to complete draft order: {complete_result['error']}")
            
            order = complete_result.get("draft_order", {}).get("order", {})
            print(f"📋 Order from complete result: {order}")
            if not order:
                order = complete_result.get("draft_order", {})
            
            order_id = order.get("id") or draft_order.get("order_id")
            order_name = order.get("name", f"#{order.get('order_number', 'N/A')}")
            
            # If order_id still not found, fetch from draft
            if not order_id:
                draft_check = shopify_api_request(uid, "GET", f"/draft_orders/{draft_order_id}.json")
                if "error" not in draft_check:
                    order_id = draft_check.get("draft_order", {}).get("order_id")
                    if order_id:
                        order_fetch = shopify_api_request(uid, "GET", f"/orders/{order_id}.json")
                        if "error" not in order_fetch:
                            order = order_fetch.get("order", {})
                            order_name = order.get("name", order_name)
            
            print(f"✅ Order created from draft: {order_name} (ID: {order_id})")
            
            # Delete the draft order to keep things clean
            print(f"🗑️ Cleaning up draft order {draft_order_id}...")
            delete_result = shopify_api_request(uid, "DELETE", f"/draft_orders/{draft_order_id}.json")
            if "error" not in delete_result:
                print(f"✅ Draft order deleted")
            else:
                print(f"⚠️ Could not delete draft order: {delete_result.get('error')}")
        
        else:
            # No discount - use regular Orders API
            print(f"🛒 Creating order with data: {order_data}")
            
            result = shopify_api_request(uid, "POST", "/orders.json", json_data=order_data)
            
            if "error" in result:
                return ChatToolResponse(error=f"Failed to create order: {result['error']}")
            
            order = result.get("order", {})
            order_id = order.get("id")
            order_name = order.get("name", f"#{order.get('order_number', 'N/A')}")
        total = format_currency(order.get("total_price", "0"), order.get("currency", "USD"))
        
        # Get shop domain for admin link
        shop_domain = get_user_shop(uid)
        order_admin_url = f"https://{shop_domain}/admin/orders/{order_id}" if shop_domain and order_id else None
        
        # Build response
        display_name = customer_display_name or f"{customer_first_name} {customer_last_name}".strip() or "Customer"
        response_text = f"✅ **Order Created Successfully!**\n\n"
        response_text += f"📋 **Order:** {order_name}\n"
        response_text += f"💰 **Total:** {total}\n"
        response_text += f"👤 **Customer:** {display_name}"
        if customer_email:
            response_text += f" ({customer_email})"
        response_text += "\n"
        
        if customer_created:
            response_text += f"✨ New customer account created\n"
        
        response_text += f"\n🛒 **Items:**\n"
        for item in order.get("line_items", []):
            qty = item.get("quantity", 1)
            title = item.get("title", "Unknown")
            price = format_currency(item.get("price", "0"), order.get("currency", "USD"))
            variant_id = item.get("variant_id")
            if variant_id:
                response_text += f"   • {qty}x {title} @ {price} ✓\n"
            else:
                response_text += f"   • {qty}x {title} @ {price}\n"
        
        # Show discount if applied
        discount_codes = order.get("discount_codes", [])
        total_discounts = order.get("total_discounts", "0")
        if discount_codes or float(total_discounts) > 0:
            response_text += f"\n🏷️ **Discount Applied:**\n"
            for dc in discount_codes:
                response_text += f"   • Code: {dc.get('code', 'N/A')} (-{format_currency(dc.get('amount', '0'), order.get('currency', 'USD'))})\n"
            if float(total_discounts) > 0:
                response_text += f"   💸 Total Savings: {format_currency(total_discounts, order.get('currency', 'USD'))}\n"
        
        # Add product matching info
        if product_matches:
            response_text += f"\n🔍 **Product Matching:**\n"
            for match in product_matches:
                response_text += f"   {match}\n"
        
        if send_receipt:
            response_text += f"\n📧 Receipt sent to {customer_email}"
        
        # Add order admin link
        if order_admin_url:
            response_text += f"\n\n🔗 **View Order:** {order_admin_url}"
        
        print(f"🛒 SUCCESS: Created order {order_name}")
        return ChatToolResponse(result=response_text)
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create order: {str(e)}")


@app.post("/tools/get_customers", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_customers(request: Request):
    """
    Get customers.
    Chat tool for Omi - retrieves a list of customers, with optional search.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        query = body.get("query", "")
        limit = min(body.get("limit", 10), 50)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_shopify_tokens(uid):
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        if query:
            result = shopify_api_request(
                uid, "GET", "/customers/search.json",
                params={"query": query, "limit": limit}
            )
        else:
            result = shopify_api_request(
                uid, "GET", "/customers.json",
                params={"limit": limit}
            )
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get customers: {result['error']}")
        
        customers = result.get("customers", [])
        
        if not customers:
            return ChatToolResponse(result="👥 No customers found matching your criteria.")
        
        # Format results
        lines = [f"👥 **Customers** ({len(customers)} found):\n"]
        
        for c in customers:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Unknown"
            email = c.get("email", "No email")
            orders_count = c.get("orders_count", 0)
            total_spent = format_currency(c.get("total_spent", "0"), c.get("currency", "USD"))
            
            lines.append(f"**{name}**")
            lines.append(f"   📧 {email}")
            lines.append(f"   📦 {orders_count} orders | 💰 {total_spent} spent\n")
        
        return ChatToolResponse(result="\n".join(lines))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get customers: {str(e)}")


@app.post("/tools/create_customer", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_customer(request: Request):
    """
    Create a new customer.
    Chat tool for Omi - creates a new customer in the store.
    """
    try:
        body = await request.json()
        print(f"👤 CREATE CUSTOMER - Received request: {body}")
        
        uid = body.get("uid")
        email = body.get("email")
        first_name = body.get("first_name", "")
        last_name = body.get("last_name", "")
        phone = body.get("phone", "")
        tags = body.get("tags", "")
        note = body.get("note", "")
        accepts_marketing = body.get("accepts_marketing", False)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not email:
            return ChatToolResponse(error="Customer email is required")
        
        # Check authentication
        if not get_shopify_tokens(uid):
            return ChatToolResponse(error="Please connect your Shopify store first in the app settings.")
        
        # Check if customer already exists
        search_result = shopify_api_request(
            uid, "GET", "/customers/search.json",
            params={"query": f"email:{email}"}
        )
        
        if "error" not in search_result:
            existing = search_result.get("customers", [])
            if existing:
                c = existing[0]
                name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Unknown"
                return ChatToolResponse(
                    result=f"⚠️ Customer with email {email} already exists: **{name}** (ID: {c['id']})"
                )
        
        # Create customer
        customer_data = {
            "customer": {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "verified_email": True,
                "send_email_welcome": False,
                "accepts_marketing": accepts_marketing,
            }
        }
        
        if tags:
            customer_data["customer"]["tags"] = tags
        
        if note:
            customer_data["customer"]["note"] = note
        
        print(f"👤 Creating customer with data: {customer_data}")
        
        result = shopify_api_request(uid, "POST", "/customers.json", json_data=customer_data)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to create customer: {result['error']}")
        
        customer = result.get("customer", {})
        customer_id = customer.get("id")
        name = f"{first_name} {last_name}".strip() or "New Customer"
        
        response_text = f"""✅ **Customer Created Successfully!**

👤 **Name:** {name}
📧 **Email:** {email}
🆔 **Customer ID:** {customer_id}"""
        
        if phone:
            response_text += f"\n📱 **Phone:** {phone}"
        
        if tags:
            response_text += f"\n🏷️ **Tags:** {tags}"
        
        print(f"👤 SUCCESS: Created customer {customer_id}")
        return ChatToolResponse(result=response_text)
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create customer: {str(e)}")


# ============================================
# Omi Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    
    This endpoint returns the chat tools definitions that Omi will fetch
    when the app is created or updated in the Omi App Store.
    """
    return {
        "tools": [
            {
                "name": "get_analytics",
                "description": "Get store analytics and sales data from Shopify. Use this when the user asks about their store performance, sales, revenue, orders count, or analytics. Supports preset periods OR custom date ranges. For BFCM, specific dates like 'Nov 28 to Dec 2', or any custom range, use start_date and end_date parameters.",
                "endpoint": "/tools/get_analytics",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": "Preset time period: 'today', 'yesterday', 'last_7_days', 'last_30_days', 'this_month', 'last_month', 'this_year'. Ignored if start_date/end_date are provided."
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Custom start date for analytics. Formats: '2024-11-28', 'Nov 28, 2024', '11/28/2024'. Use with end_date for custom ranges like BFCM."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "Custom end date for analytics. Formats: '2024-12-02', 'Dec 2, 2024', '12/02/2024'. Use with start_date for custom ranges."
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Fetching store analytics..."
            },
            {
                "name": "get_orders",
                "description": "Get recent orders from the Shopify store. Use this when the user wants to see their orders, check recent sales, or list orders by status.",
                "endpoint": "/tools/get_orders",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Order status filter: 'any', 'open', 'closed', or 'cancelled'. Default is 'any'."
                        },
                        "financial_status": {
                            "type": "string",
                            "description": "Financial status filter: 'paid', 'pending', 'refunded', etc."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of orders to return (default: 10, max: 50)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Fetching orders..."
            },
            {
                "name": "get_order_details",
                "description": "Get detailed information about a specific order. Use this when the user asks about a specific order by its number (like #1001) or ID.",
                "endpoint": "/tools/get_order_details",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "The Shopify order ID"
                        },
                        "order_number": {
                            "type": "string",
                            "description": "The order number (e.g., '1001' or '#1001')"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Fetching order details..."
            },
            {
                "name": "create_order",
                "description": "Create a new order. ONLY include parameters the user explicitly provides. If user gives partial address (just street), ASK them for city, state, zip before creating order.",
                "endpoint": "/tools/create_order",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "Customer's full name (e.g., 'John Doe'). Will search existing customers."
                        },
                        "customer_email": {
                            "type": "string",
                            "description": "Customer's email address (required for new customers)"
                        },
                        "customer_phone": {
                            "type": "string",
                            "description": "Customer's phone number"
                        },
                        "line_items": {
                            "type": "array",
                            "description": "Array of items. Each item needs: title (product name), quantity (number). Example: [{\"title\": \"Omi\", \"quantity\": 3}]"
                        },
                        "discount_code": {
                            "type": "string",
                            "description": "Discount/coupon code to apply. IMPORTANT: Always pass this if user mentions a coupon/code."
                        },
                        "free_shipping": {
                            "type": "boolean",
                            "description": "Set to true if user mentions free shipping. Auto-detected if discount code contains 'freeshipping'."
                        },
                        "address_line1": {
                            "type": "string",
                            "description": "Street address. REQUIRED with city, state, zip_code for shipping."
                        },
                        "city": {
                            "type": "string",
                            "description": "City. REQUIRED if address_line1 is provided."
                        },
                        "state": {
                            "type": "string",
                            "description": "State/Province (e.g., 'IN'). REQUIRED if address_line1 is provided."
                        },
                        "zip_code": {
                            "type": "string",
                            "description": "ZIP/Postal code. REQUIRED if address_line1 is provided."
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code (default: 'US')"
                        },
                        "note": {
                            "type": "string",
                            "description": "Order note - only if user asks"
                        },
                        "tags": {
                            "type": "string",
                            "description": "Order tags - only if user asks"
                        },
                        "send_receipt": {
                            "type": "boolean",
                            "description": "Send order receipt email (default: true)"
                        },
                        "financial_status": {
                            "type": "string",
                            "description": "Financial status: 'pending' or 'paid' (default: 'pending')"
                        }
                    },
                    "required": ["line_items"]
                },
                "auth_required": True,
                "status_message": "Creating order..."
            },
            {
                "name": "get_customers",
                "description": "Get customers from the Shopify store. Use this when the user wants to see their customers, search for a specific customer, or list customers.",
                "endpoint": "/tools/get_customers",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - search by email, name, phone, etc."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of customers to return (default: 10, max: 50)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Fetching customers..."
            },
            {
                "name": "create_customer",
                "description": "Create a new customer in the Shopify store. Use this when the user wants to add a new customer. Email is required.",
                "endpoint": "/tools/create_customer",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Customer's email address (required)"
                        },
                        "first_name": {
                            "type": "string",
                            "description": "Customer's first name"
                        },
                        "last_name": {
                            "type": "string",
                            "description": "Customer's last name"
                        },
                        "phone": {
                            "type": "string",
                            "description": "Customer's phone number"
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated customer tags"
                        },
                        "note": {
                            "type": "string",
                            "description": "Internal note about the customer"
                        },
                        "accepts_marketing": {
                            "type": "boolean",
                            "description": "Whether customer accepts marketing emails (default: false)"
                        }
                    },
                    "required": ["email"]
                },
                "auth_required": True,
                "status_message": "Creating customer..."
            }
        ]
    }


# ============================================
# Health Check
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "shopify-omi-integration"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

