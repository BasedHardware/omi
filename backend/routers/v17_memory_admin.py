import os
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query

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
