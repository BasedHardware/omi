import logging

import httpx

from app.config import OMI_API_URL, OMI_APP_ID, OMI_APP_API_KEY

log = logging.getLogger('uvicorn.error')


_http = httpx.AsyncClient(base_url=OMI_API_URL, timeout=15.0)
_headers = {'Authorization': f'Bearer {OMI_APP_API_KEY}', 'Content-Type': 'application/json'}


async def create_task(uid: str, description: str, due_at: str | None = None) -> bool:
    if not OMI_APP_ID or not OMI_APP_API_KEY:
        log.warning(f'Skipping task creation (OMI_APP_ID/OMI_APP_API_KEY not set): {description}')
        return False

    body = {'description': description, 'completed': False}
    if due_at:
        body['due_at'] = due_at

    try:
        resp = await _http.post(
            f'/v2/integrations/{OMI_APP_ID}/user/action-items',
            params={'uid': uid},
            headers=_headers,
            json=body,
        )
        if resp.status_code < 300:
            log.info(f'Task created for {uid}: {description}')
            return True
        log.warning(f'Task creation failed ({resp.status_code}): {resp.text}')
    except Exception as e:
        log.error(f'Task creation error: {e}')
    return False


async def create_memory(uid: str, content: str, tags: list[str] | None = None) -> bool:
    if not OMI_APP_ID or not OMI_APP_API_KEY:
        log.warning(f'Skipping memory creation (OMI_APP_ID/OMI_APP_API_KEY not set): {content}')
        return False

    body = {
        'text_source': 'other',
        'text_source_spec': 'sandbox_plugin',
        'memories': [{'content': content, 'tags': tags or []}],
    }

    try:
        resp = await _http.post(
            f'/v2/integrations/{OMI_APP_ID}/user/memories',
            params={'uid': uid},
            headers=_headers,
            json=body,
        )
        if resp.status_code < 300:
            log.info(f'Memory created for {uid}: {content}')
            return True
        log.warning(f'Memory creation failed ({resp.status_code}): {resp.text}')
    except Exception as e:
        log.error(f'Memory creation error: {e}')
    return False


async def close():
    await _http.aclose()
