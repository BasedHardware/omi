import logging
from typing import Any, Dict
from arq import cron

logger = logging.getLogger(__name__)


async def process_conversation(ctx: Dict[str, Any], conversation_id: str, user_id: str):
    from app.services.memory_service import MemoryService
    from app.services.conversation_service import ConversationService
    
    logger.info(f"Processing conversation {conversation_id} for user {user_id}")
    
    try:
        conversation_service = ConversationService()
        memory_service = MemoryService()
        
        conversation = await conversation_service.get_by_id(conversation_id)
        if not conversation or not conversation.overview:
            logger.warning(f"Conversation {conversation_id} not found or has no overview")
            return {"status": "skipped", "reason": "no_overview"}
        
        transcript = conversation_service.get_transcript_text(conversation)
        
        memories = await memory_service.extract_from_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            transcript=transcript,
            overview=conversation.overview
        )
        
        logger.info(f"Extracted {len(memories)} memories from conversation {conversation_id}")
        return {"status": "success", "memories_extracted": len(memories)}
        
    except Exception as e:
        logger.error(f"Error processing conversation {conversation_id}: {e}")
        raise


async def send_scheduled_reminder(ctx: Dict[str, Any], task_id: str, user_id: str, message: str):
    from app.integrations.twilio import TwilioClient
    from app.core.config import get_settings
    
    logger.info(f"Sending scheduled reminder for task {task_id}")
    
    try:
        settings = get_settings()
        twilio = TwilioClient()
        
        if settings.user_phone_number:
            await twilio.send_to_user(f"Reminder: {message}")
            logger.info(f"Sent reminder SMS for task {task_id}")
            return {"status": "sent", "method": "sms"}
        else:
            logger.warning("No phone number configured for reminders")
            return {"status": "skipped", "reason": "no_phone"}
            
    except Exception as e:
        logger.error(f"Error sending reminder for task {task_id}: {e}")
        raise


async def check_due_tasks(ctx: Dict[str, Any], user_id: str = "default_user"):
    from app.services.task_service import TaskService
    from app.services.notification_service import NotificationService
    from app.core.config import get_settings
    from datetime import datetime
    
    logger.info("Checking for due tasks")
    
    try:
        settings = get_settings()
        task_service = TaskService()
        notification_service = NotificationService()
        
        if notification_service.is_quiet_hours():
            logger.info("In quiet hours, skipping task notifications")
            return {"status": "skipped", "reason": "quiet_hours"}
        
        tasks = await task_service.get_due_soon(user_id=user_id, hours=1)
        
        if not tasks:
            return {"status": "success", "notifications_sent": 0}
        
        notifications_sent = 0
        for task in tasks:
            await notification_service.queue(f"Task due soon: {task.title}")
            notifications_sent += 1
        
        await notification_service.flush_queue()
        
        logger.info(f"Sent {notifications_sent} task notifications")
        return {"status": "success", "notifications_sent": notifications_sent}
        
    except Exception as e:
        logger.error(f"Error checking due tasks: {e}")
        raise


async def flush_notification_queue(ctx: Dict[str, Any]):
    from app.services.notification_service import NotificationService
    
    logger.info("Flushing notification queue")
    
    try:
        notification_service = NotificationService()
        await notification_service.flush_queue()
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error flushing notification queue: {e}")
        raise


class WorkerSettings:
    functions = [
        process_conversation,
        send_scheduled_reminder,
        check_due_tasks,
        flush_notification_queue,
    ]
    
    cron_jobs = [
        cron(check_due_tasks, minute={0, 15, 30, 45}),
        cron(flush_notification_queue, minute={5, 20, 35, 50}),
    ]
    
    max_jobs = 10
    job_timeout = 300
    keep_result = 3600
    
    @staticmethod
    def redis_settings():
        from app.core.redis import get_redis_settings
        return get_redis_settings()
