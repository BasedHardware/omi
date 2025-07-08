"""
Comprehensive monitoring and analytics system for Google Calendar integration.
Tracks performance, errors, and usage patterns across different platforms.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import json
import uuid
from database.redis_db import get_redis_client
from utils.calendar_error_handling import CalendarError, ErrorCategory, ErrorSeverity


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class EventType(Enum):
    OAUTH_INITIATED = "oauth_initiated"
    OAUTH_COMPLETED = "oauth_completed"
    OAUTH_FAILED = "oauth_failed"
    TOKEN_REFRESH = "token_refresh"
    EVENT_CREATED = "event_created"
    EVENT_RETRIEVED = "event_retrieved"
    ERROR_OCCURRED = "error_occurred"
    USER_DISCONNECTED = "user_disconnected"
    BACKGROUND_REFRESH = "background_refresh"


@dataclass
class CalendarMetric:
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime
    platform: Optional[str] = None
    user_id: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class CalendarEvent:
    event_type: EventType
    timestamp: datetime
    user_id: Optional[str] = None
    platform: Optional[str] = None
    session_id: Optional[str] = None
    duration_ms: Optional[int] = None
    success: bool = True
    error_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CalendarMonitoringService:
    def __init__(self):
        self.redis_client = get_redis_client()
        self.metrics_buffer = []
        self.events_buffer = []
        self.buffer_size = 100
        self.last_flush = time.time()
        self.flush_interval = 30  # seconds
        
    async def record_metric(self, 
                          name: str, 
                          value: float, 
                          metric_type: MetricType,
                          platform: str = None,
                          user_id: str = None,
                          tags: Dict[str, str] = None):
        """Record a metric for monitoring."""
        metric = CalendarMetric(
            name=name,
            value=value,
            metric_type=metric_type,
            timestamp=datetime.utcnow(),
            platform=platform,
            user_id=user_id,
            tags=tags or {}
        )
        
        self.metrics_buffer.append(metric)
        await self._flush_if_needed()
    
    async def record_event(self,
                         event_type: EventType,
                         user_id: str = None,
                         platform: str = None,
                         session_id: str = None,
                         duration_ms: int = None,
                         success: bool = True,
                         error_code: str = None,
                         metadata: Dict[str, Any] = None):
        """Record an event for monitoring."""
        event = CalendarEvent(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            platform=platform,
            session_id=session_id,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            metadata=metadata or {}
        )
        
        self.events_buffer.append(event)
        await self._flush_if_needed()
    
    async def record_oauth_flow(self,
                              user_id: str,
                              platform: str,
                              session_id: str,
                              stage: str,
                              success: bool = True,
                              error_code: str = None,
                              duration_ms: int = None):
        """Record OAuth flow metrics and events."""
        # Record event
        event_type = EventType.OAUTH_COMPLETED if success else EventType.OAUTH_FAILED
        if stage == "initiated":
            event_type = EventType.OAUTH_INITIATED
        
        await self.record_event(
            event_type=event_type,
            user_id=user_id,
            platform=platform,
            session_id=session_id,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            metadata={"stage": stage}
        )
        
        # Record platform-specific metrics
        await self.record_metric(
            name=f"oauth_{stage}_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform,
            tags={"success": str(success)}
        )
        
        if duration_ms:
            await self.record_metric(
                name=f"oauth_{stage}_duration",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                platform=platform
            )
    
    async def record_token_operation(self,
                                   operation: str,
                                   user_id: str,
                                   platform: str,
                                   success: bool = True,
                                   error_code: str = None,
                                   duration_ms: int = None):
        """Record token operations (store, retrieve, refresh)."""
        await self.record_event(
            event_type=EventType.TOKEN_REFRESH,
            user_id=user_id,
            platform=platform,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            metadata={"operation": operation}
        )
        
        await self.record_metric(
            name=f"token_{operation}_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform,
            tags={"success": str(success)}
        )
    
    async def record_calendar_operation(self,
                                      operation: str,
                                      user_id: str,
                                      platform: str = None,
                                      success: bool = True,
                                      error_code: str = None,
                                      duration_ms: int = None,
                                      metadata: Dict[str, Any] = None):
        """Record calendar operations (create event, get events, etc.)."""
        event_type = EventType.EVENT_CREATED if operation == "create_event" else EventType.EVENT_RETRIEVED
        
        await self.record_event(
            event_type=event_type,
            user_id=user_id,
            platform=platform,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            metadata=metadata
        )
        
        await self.record_metric(
            name=f"calendar_{operation}_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform,
            tags={"success": str(success)}
        )
        
        if duration_ms:
            await self.record_metric(
                name=f"calendar_{operation}_duration",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                platform=platform
            )
    
    async def record_error(self,
                         calendar_error: CalendarError,
                         user_id: str = None,
                         platform: str = None,
                         context: Dict[str, Any] = None):
        """Record error metrics and events."""
        await self.record_event(
            event_type=EventType.ERROR_OCCURRED,
            user_id=user_id,
            platform=platform or calendar_error.platform,
            success=False,
            error_code=calendar_error.code,
            metadata={
                "category": calendar_error.category.value,
                "severity": calendar_error.severity.value,
                "message": calendar_error.message,
                "context": context or {}
            }
        )
        
        # Error count by category
        await self.record_metric(
            name="calendar_errors_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform or calendar_error.platform,
            tags={
                "category": calendar_error.category.value,
                "severity": calendar_error.severity.value,
                "error_code": calendar_error.code
            }
        )
    
    async def record_user_action(self,
                               action: str,
                               user_id: str,
                               platform: str = None,
                               success: bool = True,
                               metadata: Dict[str, Any] = None):
        """Record user actions (connect, disconnect, configure)."""
        if action == "disconnect":
            event_type = EventType.USER_DISCONNECTED
        else:
            # Use a generic event type for other actions
            event_type = EventType.OAUTH_COMPLETED  # Could add more specific types
        
        await self.record_event(
            event_type=event_type,
            user_id=user_id,
            platform=platform,
            success=success,
            metadata={"action": action, **(metadata or {})}
        )
        
        await self.record_metric(
            name=f"user_{action}_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform,
            tags={"success": str(success)}
        )
    
    async def record_background_operation(self,
                                        operation: str,
                                        user_id: str = None,
                                        platform: str = None,
                                        success: bool = True,
                                        duration_ms: int = None,
                                        processed_count: int = None):
        """Record background operations (token refresh, event sync)."""
        await self.record_event(
            event_type=EventType.BACKGROUND_REFRESH,
            user_id=user_id,
            platform=platform,
            duration_ms=duration_ms,
            success=success,
            metadata={
                "operation": operation,
                "processed_count": processed_count
            }
        )
        
        await self.record_metric(
            name=f"background_{operation}_count",
            value=1,
            metric_type=MetricType.COUNTER,
            platform=platform,
            tags={"success": str(success)}
        )
        
        if processed_count:
            await self.record_metric(
                name=f"background_{operation}_processed",
                value=processed_count,
                metric_type=MetricType.GAUGE,
                platform=platform
            )
    
    async def get_platform_health_metrics(self, platform: str, time_range_hours: int = 24) -> Dict[str, Any]:
        """Get health metrics for a specific platform."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)
        
        metrics = await self._get_metrics_in_range(start_time, end_time, platform)
        events = await self._get_events_in_range(start_time, end_time, platform)
        
        # Calculate success rates
        oauth_events = [e for e in events if e.event_type in [EventType.OAUTH_COMPLETED, EventType.OAUTH_FAILED]]
        oauth_success_rate = self._calculate_success_rate(oauth_events)
        
        calendar_events = [e for e in events if e.event_type in [EventType.EVENT_CREATED, EventType.EVENT_RETRIEVED]]
        calendar_success_rate = self._calculate_success_rate(calendar_events)
        
        error_events = [e for e in events if e.event_type == EventType.ERROR_OCCURRED]
        error_breakdown = self._analyze_errors(error_events)
        
        # Calculate average response times
        avg_oauth_time = self._calculate_avg_duration(oauth_events)
        avg_calendar_time = self._calculate_avg_duration(calendar_events)
        
        return {
            "platform": platform,
            "time_range_hours": time_range_hours,
            "oauth_success_rate": oauth_success_rate,
            "calendar_success_rate": calendar_success_rate,
            "average_oauth_duration_ms": avg_oauth_time,
            "average_calendar_duration_ms": avg_calendar_time,
            "total_events": len(events),
            "error_count": len(error_events),
            "error_breakdown": error_breakdown,
            "active_users": len(set(e.user_id for e in events if e.user_id))
        }
    
    async def get_overall_health_status(self) -> Dict[str, Any]:
        """Get overall health status across all platforms."""
        platforms = ["ios", "android", "windows", "macos", "web"]
        overall_metrics = {}
        
        for platform in platforms:
            try:
                platform_metrics = await self.get_platform_health_metrics(platform, 1)  # Last hour
                overall_metrics[platform] = platform_metrics
            except Exception as e:
                overall_metrics[platform] = {"error": str(e)}
        
        # Calculate overall health score
        health_score = self._calculate_health_score(overall_metrics)
        
        return {
            "overall_health_score": health_score,
            "platform_metrics": overall_metrics,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy" if health_score > 0.8 else "degraded" if health_score > 0.5 else "unhealthy"
        }
    
    async def get_usage_analytics(self, time_range_hours: int = 168) -> Dict[str, Any]:  # 1 week default
        """Get usage analytics for calendar integration."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=time_range_hours)
        
        events = await self._get_events_in_range(start_time, end_time)
        
        # Platform distribution
        platform_usage = {}
        for event in events:
            if event.platform:
                platform_usage[event.platform] = platform_usage.get(event.platform, 0) + 1
        
        # Daily active users
        daily_users = {}
        for event in events:
            if event.user_id:
                day = event.timestamp.date().isoformat()
                if day not in daily_users:
                    daily_users[day] = set()
                daily_users[day].add(event.user_id)
        
        daily_user_counts = {day: len(users) for day, users in daily_users.items()}
        
        # Event type distribution
        event_type_counts = {}
        for event in events:
            event_type_counts[event.event_type.value] = event_type_counts.get(event.event_type.value, 0) + 1
        
        # Success rates by event type
        success_rates = {}
        for event_type in EventType:
            type_events = [e for e in events if e.event_type == event_type]
            if type_events:
                success_rates[event_type.value] = self._calculate_success_rate(type_events)
        
        return {
            "time_range_hours": time_range_hours,
            "total_events": len(events),
            "unique_users": len(set(e.user_id for e in events if e.user_id)),
            "platform_distribution": platform_usage,
            "daily_active_users": daily_user_counts,
            "event_type_distribution": event_type_counts,
            "success_rates_by_type": success_rates,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _flush_if_needed(self):
        """Flush buffers if they're full or enough time has passed."""
        current_time = time.time()
        
        if (len(self.metrics_buffer) >= self.buffer_size or 
            len(self.events_buffer) >= self.buffer_size or
            current_time - self.last_flush >= self.flush_interval):
            await self._flush_buffers()
    
    async def _flush_buffers(self):
        """Flush metrics and events to Redis."""
        try:
            # Flush metrics
            if self.metrics_buffer:
                metrics_data = []
                for metric in self.metrics_buffer:
                    metrics_data.append({
                        "id": str(uuid.uuid4()),
                        "data": asdict(metric),
                        "timestamp": metric.timestamp.isoformat()
                    })
                
                await self.redis_client.lpush(
                    "calendar_metrics",
                    *[json.dumps(m) for m in metrics_data]
                )
                
                # Set expiry (keep for 30 days)
                await self.redis_client.expire("calendar_metrics", 30 * 24 * 3600)
                
                self.metrics_buffer.clear()
            
            # Flush events
            if self.events_buffer:
                events_data = []
                for event in self.events_buffer:
                    event_dict = asdict(event)
                    event_dict['timestamp'] = event.timestamp.isoformat()
                    event_dict['event_type'] = event.event_type.value
                    
                    events_data.append({
                        "id": str(uuid.uuid4()),
                        "data": event_dict
                    })
                
                await self.redis_client.lpush(
                    "calendar_events",
                    *[json.dumps(e) for e in events_data]
                )
                
                # Set expiry (keep for 30 days)
                await self.redis_client.expire("calendar_events", 30 * 24 * 3600)
                
                self.events_buffer.clear()
            
            self.last_flush = time.time()
        
        except Exception as e:
            print(f"Error flushing monitoring data: {e}")
    
    async def _get_metrics_in_range(self, start_time: datetime, end_time: datetime, platform: str = None) -> List[CalendarMetric]:
        """Get metrics within a time range."""
        try:
            raw_metrics = await self.redis_client.lrange("calendar_metrics", 0, -1)
            metrics = []
            
            for raw_metric in raw_metrics:
                try:
                    metric_data = json.loads(raw_metric)
                    metric_timestamp = datetime.fromisoformat(metric_data['timestamp'])
                    
                    if start_time <= metric_timestamp <= end_time:
                        if platform is None or metric_data['data'].get('platform') == platform:
                            metric = CalendarMetric(
                                name=metric_data['data']['name'],
                                value=metric_data['data']['value'],
                                metric_type=MetricType(metric_data['data']['metric_type']),
                                timestamp=metric_timestamp,
                                platform=metric_data['data'].get('platform'),
                                user_id=metric_data['data'].get('user_id'),
                                tags=metric_data['data'].get('tags', {})
                            )
                            metrics.append(metric)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
            
            return metrics
        except Exception:
            return []
    
    async def _get_events_in_range(self, start_time: datetime, end_time: datetime, platform: str = None) -> List[CalendarEvent]:
        """Get events within a time range."""
        try:
            raw_events = await self.redis_client.lrange("calendar_events", 0, -1)
            events = []
            
            for raw_event in raw_events:
                try:
                    event_data = json.loads(raw_event)
                    event_timestamp = datetime.fromisoformat(event_data['data']['timestamp'])
                    
                    if start_time <= event_timestamp <= end_time:
                        if platform is None or event_data['data'].get('platform') == platform:
                            event = CalendarEvent(
                                event_type=EventType(event_data['data']['event_type']),
                                timestamp=event_timestamp,
                                user_id=event_data['data'].get('user_id'),
                                platform=event_data['data'].get('platform'),
                                session_id=event_data['data'].get('session_id'),
                                duration_ms=event_data['data'].get('duration_ms'),
                                success=event_data['data'].get('success', True),
                                error_code=event_data['data'].get('error_code'),
                                metadata=event_data['data'].get('metadata', {})
                            )
                            events.append(event)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
            
            return events
        except Exception:
            return []
    
    def _calculate_success_rate(self, events: List[CalendarEvent]) -> float:
        """Calculate success rate for a list of events."""
        if not events:
            return 1.0
        
        successful = sum(1 for e in events if e.success)
        return successful / len(events)
    
    def _calculate_avg_duration(self, events: List[CalendarEvent]) -> float:
        """Calculate average duration for events that have duration."""
        durations = [e.duration_ms for e in events if e.duration_ms is not None]
        return sum(durations) / len(durations) if durations else 0
    
    def _analyze_errors(self, error_events: List[CalendarEvent]) -> Dict[str, Any]:
        """Analyze error events to provide breakdown."""
        if not error_events:
            return {}
        
        error_codes = {}
        categories = {}
        
        for event in error_events:
            if event.error_code:
                error_codes[event.error_code] = error_codes.get(event.error_code, 0) + 1
            
            category = event.metadata.get('category', 'unknown')
            categories[category] = categories.get(category, 0) + 1
        
        return {
            "by_error_code": error_codes,
            "by_category": categories,
            "total_errors": len(error_events)
        }
    
    def _calculate_health_score(self, platform_metrics: Dict[str, Any]) -> float:
        """Calculate overall health score based on platform metrics."""
        scores = []
        
        for platform, metrics in platform_metrics.items():
            if "error" in metrics:
                scores.append(0.0)
                continue
            
            oauth_rate = metrics.get('oauth_success_rate', 1.0)
            calendar_rate = metrics.get('calendar_success_rate', 1.0)
            error_count = metrics.get('error_count', 0)
            total_events = metrics.get('total_events', 1)
            
            # Calculate platform score
            error_rate = error_count / max(total_events, 1)
            platform_score = (oauth_rate + calendar_rate) / 2 * (1 - error_rate)
            scores.append(max(0.0, min(1.0, platform_score)))
        
        return sum(scores) / len(scores) if scores else 0.0


# Global monitoring service instance
calendar_monitoring = CalendarMonitoringService()