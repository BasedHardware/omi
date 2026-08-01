import logging

from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.projections.scheduler import should_run_job as should_run_projection_job
from utils.projections.scheduler import start_cron_job as start_cron_projection_job
from utils.x_connector import should_run_x_sync_job, run_x_sync_job

logger = logging.getLogger(__name__)


async def start_job():
    # Notification
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # Projection generation — daily at 08:xx local time for the explicit rollout cohort.
    if should_run_projection_job():
        try:
            await start_cron_projection_job()
        except Exception:
            logger.exception('projection generation failed; continuing shared hourly jobs')

    # X (Twitter) connector — incremental background sync every few hours.
    if should_run_x_sync_job():
        await run_x_sync_job()
