import logging
import time

from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.other.screen_activity_cleanup import purge_retired_screen_activity_copies
from utils.x_connector import should_run_x_sync_job, run_x_sync_job

logger = logging.getLogger(__name__)


async def start_job():
    job_started_at = time.monotonic()
    # Notification
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # X (Twitter) connector — incremental background sync every few hours.
    if should_run_x_sync_job():
        await run_x_sync_job(job_started_at=job_started_at)

    # Retired screen-activity sync: drain the historical cloud copies (Firestore
    # rows + Pinecone vectors) left behind by pre-rollout users. Bounded per run;
    # a failed user is retried on the next pass because its documents survive.
    try:
        await purge_retired_screen_activity_copies()
    except Exception:
        logger.exception("screen_activity cloud purge pass crashed")
