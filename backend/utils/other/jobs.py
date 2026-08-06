from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job


async def start_job():
    # Notification / daily summary only. X connector sync lives on x-connector-sync-job.
    if should_run_daily_notification_job():
        await start_cron_notification_job()
