from utils.executors import db_executor, run_blocking
from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.redis_memory_health import run_scheduled_check as run_redis_memory_check


async def start_job():
    # Notification / daily summary only. X connector sync lives on x-connector-sync-job.
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # Read-only Redis INFO. Log line is the Cloud Monitoring 90% used_memory alarm.
    await run_blocking(db_executor, run_redis_memory_check)
