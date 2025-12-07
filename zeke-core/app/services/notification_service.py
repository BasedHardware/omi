from typing import List, Optional, TYPE_CHECKING
from datetime import datetime, time
from dataclasses import dataclass
import logging
import asyncio

from ..core.config import get_settings
from ..integrations.twilio import TwilioClient

if TYPE_CHECKING:
    from ..core.auth import AuthContext, Scope

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class Notification:
    message: str
    priority: str = "normal"
    channel: str = "sms"
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class NotificationPermissionError(Exception):
    def __init__(self, message: str = "Permission denied to send notifications"):
        self.message = message
        super().__init__(self.message)


class NotificationService:
    def __init__(self, twilio_client: Optional[TwilioClient] = None):
        self.twilio = twilio_client or TwilioClient()
        self._queue: List[Notification] = []
        self._batch_interval = 300
        self._allowed_senders: set = set()
    
    def check_permission(self, auth_context: Optional["AuthContext"] = None, source: Optional[str] = None) -> bool:
        if auth_context is None:
            return True
        
        if auth_context.is_internal:
            return True
        
        from ..core.auth import Scope
        
        if auth_context.has_scope(Scope.NOTIFICATIONS_SEND):
            return True
        
        if auth_context.has_scope(Scope.ADMIN):
            return True
        
        return False
    
    def require_permission(self, auth_context: Optional["AuthContext"] = None, source: Optional[str] = None) -> None:
        if not self.check_permission(auth_context, source):
            key_info = f" (key: {auth_context.key_name})" if auth_context and auth_context.key_name else ""
            logger.warning(f"Notification permission denied{key_info}")
            raise NotificationPermissionError(
                f"API key does not have 'notifications:send' scope required to send notifications"
            )
    
    def is_quiet_hours(self) -> bool:
        from zoneinfo import ZoneInfo
        
        tz = ZoneInfo(settings.user_timezone)
        now = datetime.now(tz)
        current_hour = now.hour
        
        start = settings.quiet_hours_start
        end = settings.quiet_hours_end
        
        if start > end:
            return current_hour >= start or current_hour < end
        else:
            return start <= current_hour < end
    
    async def queue(
        self, 
        message: str, 
        priority: str = "normal",
        auth_context: Optional["AuthContext"] = None
    ):
        self.require_permission(auth_context)
        
        notification = Notification(message=message, priority=priority)
        
        if priority == "urgent":
            await self._send_immediately(notification)
        else:
            self._queue.append(notification)
    
    async def _send_immediately(self, notification: Notification):
        if self.is_quiet_hours() and notification.priority != "urgent":
            logger.info("Quiet hours - queueing notification")
            self._queue.append(notification)
            return
        
        await self.twilio.send_to_user(notification.message)
    
    async def flush_queue(self, auth_context: Optional["AuthContext"] = None):
        self.require_permission(auth_context)
        
        if not self._queue:
            return
        
        if self.is_quiet_hours():
            logger.info("Quiet hours - skipping queue flush")
            return
        
        if len(self._queue) == 1:
            notification = self._queue.pop(0)
            await self.twilio.send_to_user(notification.message)
        else:
            messages = [n.message for n in self._queue]
            combined = "\n\n".join(messages)
            
            if len(combined) > 1500:
                combined = combined[:1500] + "..."
            
            await self.twilio.send_to_user(f"Updates:\n\n{combined}")
            self._queue.clear()
    
    async def send_task_reminder(
        self, 
        task_title: str, 
        due_at: datetime,
        auth_context: Optional["AuthContext"] = None
    ):
        self.require_permission(auth_context)
        message = f"Reminder: \"{task_title}\" is due soon."
        await self._queue_internal(message, priority="normal")
    
    async def send_weather_alert(
        self, 
        alert_message: str,
        auth_context: Optional["AuthContext"] = None
    ):
        self.require_permission(auth_context)
        await self._queue_internal(f"Weather Alert: {alert_message}", priority="urgent")
    
    async def send_daily_briefing(
        self, 
        briefing: str,
        auth_context: Optional["AuthContext"] = None
    ):
        self.require_permission(auth_context)
        await self._send_immediately(Notification(
            message=f"Good morning! Here's your briefing:\n\n{briefing}",
            priority="normal"
        ))
    
    async def _queue_internal(self, message: str, priority: str = "normal"):
        notification = Notification(message=message, priority=priority)
        
        if priority == "urgent":
            await self._send_immediately(notification)
        else:
            self._queue.append(notification)
    
    async def flush_queue_internal(self):
        if not self._queue:
            return
        
        if self.is_quiet_hours():
            logger.info("Quiet hours - skipping queue flush")
            return
        
        if len(self._queue) == 1:
            notification = self._queue.pop(0)
            await self.twilio.send_to_user(notification.message)
        else:
            messages = [n.message for n in self._queue]
            combined = "\n\n".join(messages)
            
            if len(combined) > 1500:
                combined = combined[:1500] + "..."
            
            await self.twilio.send_to_user(f"Updates:\n\n{combined}")
            self._queue.clear()
