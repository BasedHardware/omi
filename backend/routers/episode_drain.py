"""Internal OIDC-only episode wake. No in-process sleeping or paid work."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.firestore_read_origin import read_origin
from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.episodes.log import worker
from utils.executors import db_executor, run_blocking

router = APIRouter(tags=['internal-episodes'])


@router.post('/v2/episode-drain/run', include_in_schema=False)
@read_origin('job:episode_drain')
async def drain_episode_user(request: Request, _retry_count: int = Depends(verify_cloud_tasks_oidc)):
    payload = await request.json()
    uid = payload.get('uid') if isinstance(payload, dict) else None
    if not isinstance(uid, str) or not uid or len(uid) > 128 or '/' in uid:
        return JSONResponse(status_code=400, content={'status': 'invalid_uid'})
    outcome = await run_blocking(db_executor, worker.drain, uid)
    return {'status': outcome}
