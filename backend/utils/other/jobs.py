import time

from utils.executors import db_executor, run_blocking
from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.task_intelligence.chat_first_materialization_health import run_scheduled_check
from utils.x_connector import should_run_x_sync_job, run_x_sync_job


async def start_job():
    job_started_at = time.monotonic()
    # Notification
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # Weekly and read-only. Keep the collection-group scan off the event loop;
    # its bounded aggregate log is the source for the routed Cloud Monitoring alarm.
    await run_blocking(db_executor, run_scheduled_check)

    # X (Twitter) connector — incremental background sync every few hours.
    if should_run_x_sync_job():
        await run_x_sync_job(job_started_at=job_started_at)
