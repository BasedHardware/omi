from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
import logging
import math

from ..models.location import (
    LocationDB, 
    LocationResponse, 
    LocationContext, 
    OverlandPayload,
    MotionState
)
from ..core.database import get_db_context
from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LocationService:
    
    EARTH_RADIUS_KM = 6371
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return LocationService.EARTH_RADIUS_KM * c
    
    def _parse_motion(self, motion_data) -> str:
        if isinstance(motion_data, list):
            if not motion_data:
                return "unknown"
            priority = ["driving", "cycling", "running", "walking", "stationary"]
            for m in priority:
                if m in motion_data:
                    return m
            return motion_data[0] if motion_data else "unknown"
        elif isinstance(motion_data, str):
            return motion_data
        return "unknown"
    
    def _parse_overland_location(self, location: dict, user_id: str, device_id: Optional[str] = None) -> LocationDB:
        geometry = location.get("geometry", {})
        properties = location.get("properties", {})
        
        coordinates = geometry.get("coordinates", [0, 0])
        longitude = coordinates[0] if len(coordinates) > 0 else 0
        latitude = coordinates[1] if len(coordinates) > 1 else 0
        
        timestamp_str = properties.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()
        
        motion = self._parse_motion(properties.get("motion", []))
        
        battery_level = properties.get("battery_level")
        if battery_level is not None and battery_level > 1:
            battery_level = battery_level / 100
        
        return LocationDB(
            uid=user_id,
            device_id=device_id or properties.get("device_id"),
            latitude=latitude,
            longitude=longitude,
            altitude=properties.get("altitude"),
            speed=properties.get("speed"),
            horizontal_accuracy=properties.get("horizontal_accuracy"),
            vertical_accuracy=properties.get("vertical_accuracy"),
            motion=motion,
            activity=properties.get("activity"),
            battery_level=battery_level,
            battery_state=properties.get("battery_state"),
            wifi=properties.get("wifi"),
            timestamp=timestamp,
            raw_data=location
        )
    
    async def process_overland_batch(
        self,
        user_id: str,
        payload: OverlandPayload,
        device_id: Optional[str] = None
    ) -> int:
        locations_stored = 0
        
        with get_db_context() as db:
            for loc_data in payload.locations:
                try:
                    location = self._parse_overland_location(loc_data, user_id, device_id)
                    db.add(location)
                    locations_stored += 1
                except Exception as e:
                    logger.error(f"Error parsing location: {e}")
                    continue
            
            db.flush()
        
        logger.info(f"Stored {locations_stored} locations for user {user_id}")
        return locations_stored
    
    async def get_current(self, user_id: str) -> Optional[LocationResponse]:
        with get_db_context() as db:
            location = db.query(LocationDB).filter(
                LocationDB.uid == user_id
            ).order_by(desc(LocationDB.timestamp)).first()
            
            if location:
                return LocationResponse.model_validate(location)
            return None
    
    async def get_recent(
        self,
        user_id: str,
        hours: int = 24,
        limit: int = 100
    ) -> List[LocationResponse]:
        since = datetime.utcnow() - timedelta(hours=hours)
        
        with get_db_context() as db:
            locations = db.query(LocationDB).filter(
                and_(
                    LocationDB.uid == user_id,
                    LocationDB.timestamp >= since
                )
            ).order_by(desc(LocationDB.timestamp)).limit(limit).all()
            
            return [LocationResponse.model_validate(loc) for loc in locations]
    
    async def get_location_context(self, user_id: str) -> Optional[LocationContext]:
        current = await self.get_current(user_id)
        if not current:
            return None
        
        recent = await self.get_recent(user_id, hours=24, limit=50)
        
        is_at_home = self._check_if_at_home(current.latitude, current.longitude)
        is_traveling = self._check_if_traveling(recent)
        location_description = await self._get_location_description(
            current.latitude, 
            current.longitude
        )
        
        return LocationContext(
            current_latitude=current.latitude,
            current_longitude=current.longitude,
            current_motion=current.motion,
            current_speed=current.speed,
            battery_level=current.battery_level,
            battery_state=current.battery_state,
            last_updated=current.timestamp,
            location_description=location_description,
            is_at_home=is_at_home,
            is_traveling=is_traveling,
            recent_locations_count=len(recent)
        )
    
    def _check_if_at_home(self, lat: float, lon: float) -> bool:
        home_location = getattr(settings, 'home_location', None)
        if not home_location:
            return False
        
        try:
            home_lat, home_lon = map(float, home_location.split(','))
            distance = self.haversine_distance(lat, lon, home_lat, home_lon)
            return distance < 0.1
        except:
            return False
    
    def _check_if_traveling(self, recent_locations: List[LocationResponse]) -> bool:
        if len(recent_locations) < 2:
            return False
        
        driving_count = sum(1 for loc in recent_locations if loc.motion in ["driving", "cycling"])
        return driving_count / len(recent_locations) > 0.3
    
    async def _get_location_description(self, lat: float, lon: float) -> str:
        return f"Location: {lat:.4f}, {lon:.4f}"
    
    async def get_location_history(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        motion_filter: Optional[str] = None,
        limit: int = 500
    ) -> List[LocationResponse]:
        with get_db_context() as db:
            query = db.query(LocationDB).filter(LocationDB.uid == user_id)
            
            if start_date:
                query = query.filter(LocationDB.timestamp >= start_date)
            if end_date:
                query = query.filter(LocationDB.timestamp <= end_date)
            if motion_filter:
                query = query.filter(LocationDB.motion == motion_filter)
            
            locations = query.order_by(desc(LocationDB.timestamp)).limit(limit).all()
            
            return [LocationResponse.model_validate(loc) for loc in locations]
    
    async def get_motion_summary(
        self,
        user_id: str,
        hours: int = 24
    ) -> dict:
        since = datetime.utcnow() - timedelta(hours=hours)
        
        with get_db_context() as db:
            results = db.query(
                LocationDB.motion,
                func.count(LocationDB.id).label('count')
            ).filter(
                and_(
                    LocationDB.uid == user_id,
                    LocationDB.timestamp >= since
                )
            ).group_by(LocationDB.motion).all()
            
            summary = {r.motion: r.count for r in results}
            total = sum(summary.values())
            
            return {
                "summary": summary,
                "total_points": total,
                "hours_analyzed": hours,
                "dominant_motion": max(summary, key=summary.get) if summary else "unknown"
            }
    
    async def delete_old_locations(
        self,
        user_id: str,
        days_to_keep: int = 90
    ) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
        
        with get_db_context() as db:
            deleted = db.query(LocationDB).filter(
                and_(
                    LocationDB.uid == user_id,
                    LocationDB.timestamp < cutoff
                )
            ).delete()
            
            return deleted
