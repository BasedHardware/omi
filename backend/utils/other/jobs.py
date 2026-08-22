from utils.executors import db_executor, run_blocking
from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.task_intelligence.chat_first_materialization_health import run_scheduled_check


async def start_job():
    # Notification / daily summary only. X connector sync lives on x-connector-sync-job.
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # Weekly and read-only. Keep the collection-group scan off the event loop;
    # its bounded aggregate log is the source for the routed Cloud Monitoring alarm.
    await run_blocking(db_executor, run_scheduled_check)
