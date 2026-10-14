"""Conservative reads of the same consumers invoked by listen/pusher fanout."""

import os

from database.notifications import get_mentor_notification_frequency
from database.redis_db import get_user_webhook_db, user_webhook_status_db
from models.users import WebhookType, webhook_url_from_setting
from utils import proactivity_flags
from utils.apps import get_available_apps
from utils.executors import db_executor, run_blocking
from utils.mentor_admission import mentor_plan_allows_evaluation


async def realtime_consumer_active(uid: str) -> bool:
    if os.getenv('MENTOR_PIPELINE') == 'cohort':
        frequency = await run_blocking(db_executor, get_mentor_notification_frequency, uid)
        # Match the producer's opt-out and paid admission. Buffered context
        # and cohort/flag uncertainty must never be mistaken for inactivity.
        if frequency != 0 and await run_blocking(db_executor, mentor_plan_allows_evaluation, uid):
            lane = await run_blocking(db_executor, proactivity_flags.mentor_pipeline, uid)
            if lane == 'v2':
                return True
    apps = await run_blocking(db_executor, get_available_apps, uid)
    if any(app.enabled and (app.triggers_realtime() or app.triggers_realtime_audio_bytes()) for app in apps):
        return True
    for kind in (WebhookType.realtime_transcript, WebhookType.audio_bytes):
        if await run_blocking(db_executor, user_webhook_status_db, uid, kind):
            setting = await run_blocking(db_executor, get_user_webhook_db, uid, kind)
            if webhook_url_from_setting(kind, setting):
                return True
    return False
