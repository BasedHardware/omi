from celery import Celery
from celery.schedules import crontab
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
REDIS_URL = settings.redis_url

celery_app = Celery(
    "zeke_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.core.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="zeke_default",
    task_routes={
        "app.core.tasks.process_conversation": {"queue": "zeke_processing"},
        "app.core.tasks.run_memory_curation": {"queue": "zeke_curation"},
        "app.core.tasks.send_scheduled_reminder": {"queue": "zeke_notifications"},
        "app.core.tasks.check_due_tasks": {"queue": "zeke_notifications"},
    },
    task_annotations={
        "app.core.tasks.process_conversation": {
            "rate_limit": "10/m",
            "max_retries": 3,
            "default_retry_delay": 60,
        },
        "app.core.tasks.run_memory_curation": {
            "rate_limit": "2/m",
            "max_retries": 2,
        },
    },
    beat_schedule={
        "check-due-tasks-every-15-minutes": {
            "task": "app.core.tasks.check_due_tasks",
            "schedule": crontab(minute="*/15"),
            "args": ("default_user",),
        },
        "flush-notifications-every-15-minutes": {
            "task": "app.core.tasks.flush_notification_queue",
            "schedule": crontab(minute="5,20,35,50"),
        },
        "run-curation-4x-daily": {
            "task": "app.core.tasks.run_memory_curation",
            "schedule": crontab(hour="0,6,12,18", minute=30),
            "args": ("default_user",),
        },
    },
)

logger.info(f"Celery app configured with broker: {REDIS_URL}")
