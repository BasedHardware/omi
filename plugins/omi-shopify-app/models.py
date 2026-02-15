"""
Pydantic models for the Shopify Omi plugin.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class ShopifyCustomer(BaseModel):
    """Shopify customer information."""
    id: Optional[int] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    orders_count: int = 0
    total_spent: str = "0.00"
    created_at: Optional[str] = None
    tags: Optional[str] = None


class ShopifyAddress(BaseModel):
    """Shopify address information."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None


class ShopifyLineItem(BaseModel):
    """Shopify order line item."""
    id: Optional[int] = None
    title: str
    quantity: int
    price: str
    sku: Optional[str] = None
    variant_id: Optional[int] = None
    product_id: Optional[int] = None


class ShopifyOrder(BaseModel):
    """Shopify order information."""
    id: Optional[int] = None
    order_number: Optional[int] = None
    name: Optional[str] = None  # e.g., "#1001"
    email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    financial_status: Optional[str] = None  # paid, pending, refunded
    fulfillment_status: Optional[str] = None  # fulfilled, partial, null
    total_price: str = "0.00"
    subtotal_price: str = "0.00"
    total_tax: str = "0.00"
    currency: str = "USD"
    customer: Optional[ShopifyCustomer] = None
    line_items: List[ShopifyLineItem] = []
    shipping_address: Optional[ShopifyAddress] = None
    billing_address: Optional[ShopifyAddress] = None
    note: Optional[str] = None
    tags: Optional[str] = None


class ShopifyAnalytics(BaseModel):
    """Shopify store analytics."""
    total_sales: str = "0.00"
    total_orders: int = 0
    average_order_value: str = "0.00"
    total_customers: int = 0
    new_customers: int = 0
    returning_customers: int = 0
    top_products: List[Dict[str, Any]] = []
    period: str = "today"


class ShopifyShop(BaseModel):
    """Shopify store information."""
    id: int
    name: str
    email: str
    domain: str
    myshopify_domain: str
    currency: str
    money_format: str
    timezone: str
    plan_name: str


# Omi Chat Tool Models
class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""
    uid: str
    app_id: str
    tool_name: str


class GetAnalyticsRequest(ChatToolRequest):
    """Request model for getting analytics."""
    period: str = "today"  # today, yesterday, last_7_days, last_30_days


class GetOrdersRequest(ChatToolRequest):
    """Request model for getting orders."""
    status: Optional[str] = None  # any, open, closed, cancelled
    financial_status: Optional[str] = None  # paid, pending, refunded
    limit: int = 10


class GetOrderDetailsRequest(ChatToolRequest):
    """Request model for getting order details."""
    order_id: Optional[str] = None  # Can be order ID or order number
    order_number: Optional[str] = None


class CreateOrderRequest(ChatToolRequest):
    """Request model for creating an order."""
    customer_email: str
    customer_first_name: Optional[str] = None
    customer_last_name: Optional[str] = None
    customer_phone: Optional[str] = None
    line_items: List[Dict[str, Any]]  # [{title, quantity, price}]
    shipping_address: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    tags: Optional[str] = None
    send_receipt: bool = True
    financial_status: str = "pending"


class GetCustomersRequest(ChatToolRequest):
    """Request model for getting customers."""
    query: Optional[str] = None  # Search by email, name, etc.
    limit: int = 10


class CreateCustomerRequest(ChatToolRequest):
    """Request model for creating a customer."""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    tags: Optional[str] = None
    note: Optional[str] = None
    accepts_marketing: bool = False


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


# Omi Conversation Models (for future memory/webhook integrations)
class TranscriptSegment(BaseModel):
    """Transcript segment from Omi conversation."""
    text: str
    speaker: Optional[str] = "SPEAKER_00"
    is_user: bool
    start: float
    end: float


class Structured(BaseModel):
    """Structured conversation data."""
    title: str
    overview: str
    emoji: str = ""
    category: str = "other"


class Conversation(BaseModel):
    """Omi conversation model."""
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    structured: Structured
    discarded: bool


class EndpointResponse(BaseModel):
    """Standard endpoint response for Omi webhooks."""
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default="")

