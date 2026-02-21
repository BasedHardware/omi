"""
Pydantic models for the ShipBob Omi plugin.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# Omi Chat Tool Models
class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""
    uid: str
    app_id: str
    tool_name: str


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


# ShipBob Data Models
class ShipBobUser(BaseModel):
    """ShipBob user information."""
    id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None


class ShipBobChannel(BaseModel):
    """ShipBob channel information."""
    id: int
    name: str


class FulfillmentCenter(BaseModel):
    """ShipBob fulfillment center."""
    id: int
    name: str


class InventoryItem(BaseModel):
    """ShipBob inventory item."""
    id: int
    name: str
    sku: Optional[str] = None
    total_fulfillable_quantity: int = 0
    total_onhand_quantity: int = 0
    total_committed_quantity: int = 0
    total_sellable_quantity: int = 0
    total_awaiting_quantity: int = 0
    total_exception_quantity: int = 0


class Product(BaseModel):
    """ShipBob product."""
    id: int
    reference_id: Optional[str] = None
    name: str
    sku: Optional[str] = None
    inventory_id: Optional[int] = None


class BoxItem(BaseModel):
    """Box item for WRO."""
    inventory_id: int
    quantity: int
    lot_number: Optional[str] = None
    lot_date: Optional[str] = None


class WROBox(BaseModel):
    """Box for WRO."""
    tracking_number: Optional[str] = None
    box_items: List[BoxItem]


class WarehouseReceivingOrder(BaseModel):
    """ShipBob Warehouse Receiving Order."""
    id: int
    status: str
    purchase_order_number: Optional[str] = None
    expected_arrival_date: Optional[str] = None
    fulfillment_center_id: Optional[int] = None
    insert_date: Optional[str] = None


class Order(BaseModel):
    """ShipBob order."""
    id: int
    order_number: Optional[str] = None
    status: str
    created_date: Optional[str] = None
    shipping_method: Optional[str] = None


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
