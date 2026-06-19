import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from database._client import db
from jobs.v17_short_term_lifecycle_worker import ShortTermLifecycleWorkerReport, run_short_term_lifecycle_firestore
from utils.memory.v17_non_active_route_report import fetch_non_active_route_audit_report

router = APIRouter()


def _parse_expected_source_ids(expected_source_ids: Optional[str]) -> Optional[List[str]]:
    if expected_source_ids is None:
        return None
    parsed = [source_id.strip() for source_id in expected_source_ids.split(',') if source_id.strip()]
    return parsed or None


def _require_admin_key(secret_key: str) -> None:
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')


def _parse_evaluated_at(evaluated_at: Optional[str]) -> datetime:
    if evaluated_at is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(evaluated_at.replace('Z', '+00:00'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='evaluated_at must be an ISO-8601 timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(status_code=400, detail='evaluated_at must include a timezone')
    return parsed.astimezone(timezone.utc)


def _validate_lifecycle_run_inputs(run_id: str, limit: int) -> None:
    if not run_id or not run_id.strip():
        raise HTTPException(status_code=400, detail='run_id must be non-empty')
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail='limit must be between 1 and 1000')


def _short_term_lifecycle_response(
    *, uid: str, run_id: str, evaluated_at: datetime, report: ShortTermLifecycleWorkerReport
) -> dict:
    transition_count = report.created_count + report.existing_count
    return {
        'uid': uid,
        'run_id': run_id,
        'evaluated_at': evaluated_at.isoformat(),
        'evaluated_count': transition_count + report.skipped_count,
        'created_count': report.created_count,
        'existing_count': report.existing_count,
        'skipped_count': report.skipped_count,
        'transition_count': transition_count,
        'skipped_memory_ids': list(report.skipped_memory_ids),
        'default_access_allowed': False,
        'archive_default_visible': False,
    }


@router.get('/v17/admin/users/{uid}/non-active-route-report', tags=['admin', 'v17'])
def get_v17_non_active_route_report(
    uid: str,
    run_id: Optional[str] = Query(None),
    expected_source_ids: Optional[str] = Query(None),
    secret_key: str = Header(...),
):
    """Surface V17 non-active route accounting for admin/no-silent-loss audits.

    Reads only `users/{uid}/non_active_memory_routes` through the shared report
    fetcher. It does not query default Long-term `memory_items`; `context_only`
    stays internal/audit-only and Archive remains an explicit product tier.
    """

    _require_admin_key(secret_key)
    report = fetch_non_active_route_audit_report(
        uid,
        run_id=run_id,
        expected_source_ids=_parse_expected_source_ids(expected_source_ids),
    )
    return report.model_dump(mode='json')


@router.post('/v17/admin/users/{uid}/short-term-lifecycle/run', tags=['admin', 'v17'])
def post_v17_short_term_lifecycle_run(
    uid: str,
    run_id: str = Query(...),
    evaluated_at: Optional[str] = Query(None),
    limit: int = Query(500),
    secret_key: str = Header(...),
):
    """Run the V17 Short-term lifecycle worker for one user.

    The endpoint is an explicit admin/job entrypoint around the concrete
    Firestore runner. It evaluates only authoritative Short-term `memory_items`,
    persists idempotent lifecycle transition/audit records, and returns counts;
    it does not expose Archive or stale Short-term through default reads.
    """

    _require_admin_key(secret_key)
    _validate_lifecycle_run_inputs(run_id, limit)
    evaluated_time = _parse_evaluated_at(evaluated_at)
    report = run_short_term_lifecycle_firestore(
        uid=uid,
        db_client=db,
        run_id=run_id,
        now=evaluated_time,
        limit=limit,
        dispositions=None,
    )
    return _short_term_lifecycle_response(uid=uid, run_id=run_id, evaluated_at=evaluated_time, report=report)
