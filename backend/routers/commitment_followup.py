"""Authenticated due-event consumer; all task state remains canonical."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from database.action_items import get_action_item
from utils.commitment_followup_tasks import schedule_followup, verify_followup_task
from utils.executors import db_executor, run_blocking
from utils.proactivity_producers import produce_followup

router = APIRouter()


@router.post('/v1/commitment-followup-jobs/run', include_in_schema=False)
async def run_commitment_followup(request: Request, retry_count: int = Depends(verify_followup_task)):
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or set(payload) != {'uid', 'task_id', 'due_revision'}:
            return {'status': 'dropped'}
        if any(
            not isinstance(value, str) or not value or len(value) > 128 or '/' in value
            for key, value in payload.items()
            if key != 'due_revision'
        ):
            return {'status': 'dropped'}
        revision = payload['due_revision']
        if not isinstance(revision, str) or len(revision) > 64:
            return {'status': 'dropped'}
        due = datetime.fromisoformat(revision.replace('Z', '+00:00'))
        if due.tzinfo is None:
            return {'status': 'dropped'}
    except (ValueError, TypeError):
        return {'status': 'dropped'}
    uid, task_id = payload['uid'], payload['task_id']
    if due > datetime.now(timezone.utc):
        task = await run_blocking(db_executor, get_action_item, uid, task_id)
        current_due = task.get('due_at') if task else None
        if isinstance(current_due, str):
            current_due = datetime.fromisoformat(current_due.replace('Z', '+00:00'))
        if task and not task.get('completed') and task.get('status', 'active') == 'active' and current_due == due:
            await run_blocking(db_executor, schedule_followup, uid, task_id, due, retry_on_failure=True)
        return {'status': 'scheduled'}
    try:
        await produce_followup(uid, task_id, revision)
    except Exception as exc:
        raise HTTPException(status_code=503, detail='followup_unavailable') from exc
    return {'status': 'acked'}
