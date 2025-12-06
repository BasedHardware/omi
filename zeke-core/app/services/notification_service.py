from typing import List, Optional
from datetime import datetime, time
from dataclasses import dataclass
import logging
import asyncio

from ..core.config import get_settings
from ..integrations.twilio import TwilioClient

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


class NotificationService:
    def __init__(self, twilio_client: Optional[TwilioClient] = None):
        self.twilio = twilio_client or TwilioClient()
        self._queue: List[Notification] = []
        self._batch_interval = 300
    
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
    
    async def queue(self, message: str, priority: str = "normal"):
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
    
    async def flush_queue(self):
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
    
    async def send_task_reminder(self, task_title: str, due_at: datetime):
        message = f"Reminder: \"{task_title}\" is due soon."
        await self.queue(message, priority="normal")
    
    async def send_weather_alert(self, alert_message: str):
        await self.queue(f"Weather Alert: {alert_message}", priority="urgent")
    
    async def send_daily_briefing(self, briefing: str):
        await self._send_immediately(Notification(
            message=f"Good morning! Here's your briefing:\n\n{briefing}",
            priority="normal"
        ))
