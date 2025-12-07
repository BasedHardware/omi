import logging
from typing import Any, Dict

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async_task(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(name="app.core.tasks.process_conversation", bind=True, max_retries=3)
def process_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
    from app.services.memory_service import MemoryService
    from app.services.conversation_service import ConversationService
    
    logger.info(f"Processing conversation {conversation_id} for user {user_id}")
    
    async def _process():
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
    
    return run_async_task(_process())


@celery_app.task(name="app.core.tasks.send_scheduled_reminder", bind=True, max_retries=2)
def send_scheduled_reminder(self, task_id: str, user_id: str, message: str) -> Dict[str, Any]:
    from app.integrations.twilio import TwilioClient
    from app.core.config import get_settings
    
    logger.info(f"Sending scheduled reminder for task {task_id}")
    
    async def _send():
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
    
    return run_async_task(_send())


@celery_app.task(name="app.core.tasks.check_due_tasks", bind=True)
def check_due_tasks(self, user_id: str = "default_user") -> Dict[str, Any]:
    from app.services.task_service import TaskService
    from app.services.notification_service import NotificationService
    
    logger.info("Checking for due tasks")
    
    async def _check():
        try:
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
    
    return run_async_task(_check())


@celery_app.task(name="app.core.tasks.flush_notification_queue", bind=True)
def flush_notification_queue(self) -> Dict[str, Any]:
    from app.services.notification_service import NotificationService
    
    logger.info("Flushing notification queue")
    
    async def _flush():
        try:
            notification_service = NotificationService()
            await notification_service.flush_queue()
            return {"status": "success"}
            
        except Exception as e:
            logger.error(f"Error flushing notification queue: {e}")
            raise
    
    return run_async_task(_flush())


@celery_app.task(name="app.core.tasks.run_memory_curation", bind=True, max_retries=2)
def run_memory_curation(self, user_id: str = "default_user") -> Dict[str, Any]:
    from app.services.curation_service import MemoryCurationService
    
    logger.info(f"Running memory curation for user {user_id}")
    
    async def _curate():
        try:
            curation_service = MemoryCurationService()
            
            result = await curation_service.run_curation(
                user_id=user_id,
                batch_size=20,
                auto_delete=False,
                reprocess_all=False
            )
            
            logger.info(
                f"Curation completed: processed={result.memories_processed}, "
                f"updated={result.memories_updated}, flagged={result.memories_flagged}"
            )
            
            return {
                "status": result.status,
                "processed": result.memories_processed,
                "updated": result.memories_updated,
                "flagged": result.memories_flagged,
                "deleted": result.memories_deleted
            }
            
        except Exception as e:
            logger.error(f"Error running memory curation: {e}")
            raise
    
    return run_async_task(_curate())


@celery_app.task(name="app.core.tasks.update_knowledge_graph", bind=True, max_retries=2)
def update_knowledge_graph(self, user_id: str, conversation_id: str, transcript: str) -> Dict[str, Any]:
    logger.info(f"Updating knowledge graph for conversation {conversation_id}")
    return {"status": "pending", "message": "GraphRAG will be implemented in Phase 3"}
