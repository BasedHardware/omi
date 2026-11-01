"""Conservative reads of the same consumers invoked by listen/pusher fanout."""

from database.redis_db import get_user_webhook_db, user_webhook_status_db
from models.users import WebhookType, webhook_url_from_setting
from utils.apps import get_available_apps
from utils.executors import db_executor, run_blocking


async def realtime_consumer_active(uid: str) -> bool:
    apps = await run_blocking(db_executor, get_available_apps, uid)
    if any(app.enabled and (app.triggers_realtime() or app.triggers_realtime_audio_bytes()) for app in apps):
        return True
    for kind in (WebhookType.realtime_transcript, WebhookType.audio_bytes):
        if await run_blocking(db_executor, user_webhook_status_db, uid, kind):
            setting = await run_blocking(db_executor, get_user_webhook_db, uid, kind)
            if webhook_url_from_setting(kind, setting):
                return True
    return False
