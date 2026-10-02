"""
Pydantic models for the ShipBob Omi plugin.
"""

from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel

from omi_plugin_sdk.models import Conversation, EndpointResponse, Structured, TranscriptSegment


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


class GetInventoryRequest(BaseModel):
    """Request model for get_inventory."""

    uid: str
    product_name: Optional[str] = None
    limit: Optional[int] = 10


class GetProductsRequest(BaseModel):
    """Request model for get_products."""

    uid: str
    limit: Optional[int] = 10
    search: Optional[str] = None


class CreateWroRequest(BaseModel):
    """Request model for create_wro."""

    uid: str
    product_name: str
    quantity: int
    fulfillment_center_id: Optional[int] = None
    expected_arrival_date: Optional[str] = None
    tracking_number: Optional[str] = None
    purchase_order_number: Optional[str] = None
    packaging_type: Optional[str] = "EverythingInOneBox"
    package_type: Optional[str] = "Package"


class GetWrosRequest(BaseModel):
    """Request model for get_wros."""

    uid: str
    limit: Optional[int] = 10
    status: Optional[str] = None


class CancelWroRequest(BaseModel):
    """Request model for cancel_wro."""

    uid: str
    wro_id: str


class GetOrdersRequest(BaseModel):
    """Request model for get_orders."""

    uid: str
    limit: Optional[int] = 10
    status: Optional[str] = None


class GetFulfillmentCentersRequest(BaseModel):
    """Request model for get_fulfillment_centers."""

    uid: str


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
