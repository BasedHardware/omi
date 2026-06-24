from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
    should_run_canonical_short_term_maintenance_cron,
)
from utils.other.notifications import should_run_job as should_run_daily_notification_job
from utils.other.notifications import start_cron_job as start_cron_notification_job
from utils.x_connector import should_run_x_sync_job, run_x_sync_job


async def start_job():
    # Notification
    if should_run_daily_notification_job():
        await start_cron_notification_job()

    # X (Twitter) connector — incremental background sync every few hours.
    if should_run_x_sync_job():
        await run_x_sync_job()

    # Canonical short-term TTL audit + batch-or-daily promotion (cohort whitelist only).
    if should_run_canonical_short_term_maintenance_cron():
        await run_canonical_short_term_maintenance_cron()
