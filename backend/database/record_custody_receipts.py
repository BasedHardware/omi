"""Short-lived finish receipts; the active repair CronJob owns their expiry."""

from datetime import datetime, timezone

from google.cloud.firestore_v1 import FieldFilter

from database.firestore_read_origin import read_origin

# A receipt outlives any backend-sync request and all its ambiguous-commit
# retries. Expiry deletes metadata only, never audio or recovery obligations.
RETENTION_SECONDS = 24 * 60 * 60
PAGE_SIZE = 128
MAX_PER_RUN = 10000


def expires_at(now):
    return datetime.fromtimestamp(now + RETENTION_SECONDS, timezone.utc)


@read_origin('job:record_custody_receipts:expired_page')
def expired_page(client, *, now, budget):
    # Every pre-fix receipt already has recorded_at; no backfill is needed.
    return list(
        client.collection_group('record_custody_recoveries')
        .where(filter=FieldFilter('recorded_at', '<=', now - RETENTION_SECONDS))
        .order_by('recorded_at')
        .limit(PAGE_SIZE)
        .stream(timeout=min(10, budget.timeout()), retry=None)
    )


def prune(client, *, now, budget):
    """Bound each pass and every RPC; a saturated page resumes next CronJob."""
    deleted = 0
    while deleted < MAX_PER_RUN:
        budget.check()
        page = expired_page(client, now=now, budget=budget)
        if not page:
            break
        page = page[: MAX_PER_RUN - deleted]
        batch = client.batch()
        for doc in page:
            batch.delete(doc.reference)
        batch.commit(timeout=min(10, budget.timeout()), retry=None)
        deleted += len(page)
        if len(page) < PAGE_SIZE:
            break
    return deleted
