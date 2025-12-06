from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Float, DateTime, Boolean, JSON, Index
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class MotionState(str, Enum):
    stationary = "stationary"
    walking = "walking"
    running = "running"
    cycling = "cycling"
    driving = "driving"
    unknown = "unknown"


class BatteryState(str, Enum):
    charging = "charging"
    full = "full"
    unplugged = "unplugged"
    unknown = "unknown"


class LocationDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "locations"
    
    uid: str = Column(String(64), nullable=False, index=True)
    device_id: Optional[str] = Column(String(128), nullable=True, index=True)
    
    latitude: float = Column(Float, nullable=False)
    longitude: float = Column(Float, nullable=False)
    altitude: Optional[float] = Column(Float, nullable=True)
    
    speed: Optional[float] = Column(Float, nullable=True)
    horizontal_accuracy: Optional[float] = Column(Float, nullable=True)
    vertical_accuracy: Optional[float] = Column(Float, nullable=True)
    
    motion: str = Column(String(64), default="unknown")
    activity: Optional[str] = Column(String(64), nullable=True)
    
    battery_level: Optional[float] = Column(Float, nullable=True)
    battery_state: Optional[str] = Column(String(32), nullable=True)
    
    wifi: Optional[str] = Column(String(128), nullable=True)
    
    timestamp: datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    
    raw_data: Optional[dict] = Column(JSON, nullable=True)
    
    trip_id: Optional[str] = Column(String(64), nullable=True, index=True)
    
    __table_args__ = (
        Index('ix_locations_uid_timestamp', 'uid', 'timestamp'),
    )


class OverlandLocation(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime
    altitude: Optional[float] = None
    speed: Optional[float] = None
    horizontal_accuracy: Optional[float] = None
    vertical_accuracy: Optional[float] = None
    motion: List[str] = Field(default_factory=list)
    activity: Optional[str] = None
    battery_level: Optional[float] = None
    battery_state: Optional[str] = None
    wifi: Optional[str] = None
    device_id: Optional[str] = None


class OverlandPayload(BaseModel):
    locations: List[dict]
    trip: Optional[dict] = None
    current: Optional[dict] = None


class LocationResponse(BaseModel):
    id: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    motion: str = "unknown"
    activity: Optional[str] = None
    battery_level: Optional[float] = None
    battery_state: Optional[str] = None
    timestamp: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class LocationContext(BaseModel):
    current_latitude: float
    current_longitude: float
    current_motion: str
    current_speed: Optional[float] = None
    battery_level: Optional[float] = None
    battery_state: Optional[str] = None
    last_updated: datetime
    location_description: Optional[str] = None
    is_at_home: bool = False
    is_traveling: bool = False
    recent_locations_count: int = 0
