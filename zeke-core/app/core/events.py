from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "zeke-core"


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._async_handlers: Dict[str, List[Callable]] = {}
    
    def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def subscribe_async(self, event_type: str, handler: Callable):
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []
        self._async_handlers[event_type].append(handler)
    
    def publish(self, event: Event):
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.type}: {e}")
        
        handlers = self._handlers.get("*", [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in wildcard handler: {e}")
    
    async def publish_async(self, event: Event):
        self.publish(event)
        
        async_handlers = self._async_handlers.get(event.type, [])
        tasks = []
        for handler in async_handlers:
            tasks.append(asyncio.create_task(handler(event)))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


event_bus = EventBus()


class EventTypes:
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_PROCESSED = "conversation.processed"
    MEMORY_EXTRACTED = "memory.extracted"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    CHAT_MESSAGE_RECEIVED = "chat.message.received"
    CHAT_RESPONSE_SENT = "chat.response.sent"
    SMS_RECEIVED = "sms.received"
    SMS_SENT = "sms.sent"
    NOTIFICATION_QUEUED = "notification.queued"
    AUTOMATION_TRIGGERED = "automation.triggered"
