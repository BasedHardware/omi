from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.other.purge_trashed import purge_expired_trashed_conversations, should_run_purge_trashed_job


async def start_job():
    # Notification
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    if should_run_purge_trashed_job():
        purge_expired_trashed_conversations()
