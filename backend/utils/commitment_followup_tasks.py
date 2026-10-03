"""One-shot due wakes through the existing Cloud Tasks transport; no cron."""

import hashlib
import logging
import math
import os
from datetime import datetime, timedelta, timezone

from fastapi import Request

from utils import cloud_tasks
from utils.proactivity_flags import enabled

logger = logging.getLogger(__name__)


def schedule_followup(uid: str, task_id: str, due_at: datetime | str, *, retry_on_failure: bool = False) -> None:
    """No task mutation; stale wakes are fenced by canonical due revision at execution."""
    queue = os.getenv('COMMITMENT_FOLLOWUP_TASKS_QUEUE', '')
    url = os.getenv('COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL', '')
    invoker = os.getenv('COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA', '')
    if not all([queue, url, invoker]):
        return
    try:
        if not enabled(uid):
            return
        due = datetime.fromisoformat(due_at.replace('Z', '+00:00')) if isinstance(due_at, str) else due_at
        if due.tzinfo is None:
            return
        due = due.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        # Cloud Tasks accepts at most 30 days ahead. For longer commitments, each
        # one-shot wake schedules the next bounded hop, with the same source revision.
        hop_seconds = int(timedelta(days=28).total_seconds())
        hops = max(0, math.ceil((due - now).total_seconds() / hop_seconds) - 1)
        wake = max(now, due - timedelta(seconds=hops * hop_seconds))
        revision = due.isoformat()
        identity = hashlib.sha256(f'{uid}:{task_id}:{revision}:{hops}'.encode()).hexdigest()
        cloud_tasks.enqueue_named_task(
            queue,
            url,
            f'commitment-{identity}',
            {'uid': uid, 'task_id': task_id, 'due_revision': revision},
            audience=url,
            invoker_sa=invoker,
            schedule_at=math.ceil(wake.timestamp()),
        )
    except Exception:
        logger.info('commitment_followup scheduling_unavailable')
        if retry_on_failure:
            raise


def verify_followup_task(request: Request) -> int:
    return cloud_tasks.verify_configured_cloud_tasks_oidc(
        request,
        audience=os.getenv('COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL', ''),
        invoker_sa=os.getenv('COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA', ''),
    )
