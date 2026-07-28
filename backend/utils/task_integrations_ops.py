"""Task integration operations — external API calls and OAuth token management.

Lives in utils/ so auto-sync (task_sync) and the HTTP router share one implementation
without violating the utils → routers import hierarchy.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Tuple

import httpx
from fastapi import HTTPException

import database.users as users_db
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize
import logging

logger = logging.getLogger(__name__)

OAUTH_CONFIGS = {
    'todoist': {'name': 'Todoist'},
    'asana': {'name': 'Asana'},
    'google_tasks': {'name': 'Google Tasks'},
    'clickup': {'name': 'ClickUp'},
}

http_client: Optional[httpx.AsyncClient] = None


def _provider_create_success(external_task_id: Any) -> dict:
    task_id = str(external_task_id).strip() if external_task_id is not None else ''
    if not task_id:
        return {
            'success': False,
            'error': 'Provider response omitted task identity',
            'error_code': 'invalid_provider_response',
            'retryable': False,
            'ambiguous': True,
        }
    return {'success': True, 'external_task_id': task_id}


def _provider_create_http_failure(provider: str, status_code: int) -> dict:
    if 200 <= status_code < 300:
        return {
            'success': False,
            'error': f'{provider} response did not contain a completed task',
            'error_code': 'invalid_provider_response',
            'status_code': status_code,
            'retryable': False,
            'ambiguous': True,
        }
    ambiguous = status_code in {408, 425} or status_code >= 500
    return {
        'success': False,
        'error': f'{provider} API error: {status_code}',
        'error_code': 'api_error',
        'status_code': status_code,
        'retryable': status_code == 429,
        'ambiguous': ambiguous,
    }


def _provider_create_transport_failure(error: httpx.TransportError) -> dict:
    safe_before_send = isinstance(error, (httpx.PoolTimeout, httpx.ConnectTimeout, httpx.ConnectError))
    return {
        'success': False,
        'error': type(error).__name__,
        'error_code': 'transport_error',
        'retryable': safe_before_send,
        'ambiguous': not safe_before_send,
    }


def get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client instance."""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=10.0)
    return http_client


async def close_http_client():
    """Close the HTTP client and cleanup resources."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None


def _build_refresh_request(app_key: str, refresh_token: str) -> dict:
    name = OAUTH_CONFIGS.get(app_key, {'name': app_key}).get('name', app_key)
    if app_key == 'google_tasks':
        client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_TASKS_CLIENT_SECRET')
        if not all([client_id, client_secret]):
            raise HTTPException(status_code=500, detail=f"{name} not configured")
        return {
            'url': 'https://oauth2.googleapis.com/token',
            'type': 'form',
            'headers': {'Content-Type': 'application/x-www-form-urlencoded'},
            'data': {
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            },
        }
    if app_key == 'asana':
        client_id = os.getenv('ASANA_CLIENT_ID')
        client_secret = os.getenv('ASANA_CLIENT_SECRET')
        if not all([client_id, client_secret]):
            raise HTTPException(status_code=500, detail=f"{name} not configured")
        return {
            'url': 'https://app.asana.com/-/oauth_token',
            'type': 'form',
            'headers': {'Content-Type': 'application/x-www-form-urlencoded'},
            'data': {
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
            },
        }
    raise HTTPException(status_code=400, detail=f"Unsupported integration: {app_key}")


async def refresh_oauth_token(
    uid: str, app_key: str, integration: dict, client: Optional[httpx.AsyncClient] = None
) -> dict:
    name = OAUTH_CONFIGS.get(app_key, {'name': app_key}).get('name', app_key)
    refresh_token = integration.get('refresh_token')
    if not refresh_token:
        raise HTTPException(status_code=401, detail=f"No refresh token available for {name}")
    try:
        req = _build_refresh_request(app_key, refresh_token)
        client = client or get_http_client()
        if req['type'] == 'form':
            token_response = await client.post(req['url'], headers=req.get('headers', {}), data=req.get('data', {}))
        else:
            token_response = await client.post(req['url'], headers=req.get('headers', {}), params=req.get('params', {}))
        if token_response.status_code == 200:
            token_data = token_response.json()
            new_access_token = token_data.get('access_token')
            new_refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in')
            if not new_access_token:
                raise HTTPException(status_code=401, detail=f"Failed to refresh {name} token")
            # Narrow update payload — only write the fields that changed so a
            # stale snapshot doesn't clobber concurrent changes to workspace_gid,
            # project_gid, etc. via Firestore set(merge=True).
            update_payload: dict = {
                'access_token': new_access_token,
                'connected': True,
            }
            if new_refresh_token:
                update_payload['refresh_token'] = new_refresh_token
            if expires_in:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                update_payload['expires_at'] = expires_at.isoformat()
            await run_blocking(db_executor, users_db.set_task_integration, uid, app_key, update_payload)
            return {**integration, **update_payload}
        else:
            error_text = token_response.text
            logger.error(
                f'{app_key}: Token refresh failed with HTTP {token_response.status_code}: {sanitize(error_text)}'
            )
            if token_response.status_code == 400:
                should_disconnect = False
                try:
                    err_json = token_response.json()
                except Exception:
                    err_json = None
                if err_json:
                    err_code = str(err_json.get('error', '')).lower()
                    err_desc = str(err_json.get('error_description', '')).lower()
                    if (
                        'invalid_grant' in err_code
                        or 'invalid_refresh_token' in err_code
                        or 'invalid_grant' in err_desc
                        or 'invalid_refresh_token' in err_desc
                    ):
                        should_disconnect = True
                else:
                    lower_text = error_text.lower()
                    if 'invalid_grant' in lower_text or 'invalid_refresh_token' in lower_text:
                        should_disconnect = True
                if should_disconnect:
                    disconnect_payload = {'connected': False}
                    await run_blocking(db_executor, users_db.set_task_integration, uid, app_key, disconnect_payload)
            raise HTTPException(status_code=401, detail=f"Failed to refresh {name} token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'{app_key}: Error refreshing token: {e}')
        raise HTTPException(status_code=500, detail=f"Error refreshing token: {str(e)}")


async def ensure_valid_oauth_token(
    uid: str,
    app_key: str,
    integration: dict,
    refresh_if_missing_expires_at: bool = False,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    supports_refresh = app_key in ['google_tasks', 'asana']
    if not supports_refresh:
        return integration
    expires_at_str = integration.get('expires_at')
    if not expires_at_str:
        if refresh_if_missing_expires_at or integration.get('refresh_token'):
            return await refresh_oauth_token(uid, app_key, integration, client=client)
        return integration
    # Parse/compare the expiry — a malformed timestamp should trigger a refresh,
    # but refresh_oauth_token failures must propagate (not be caught and retried
    # with a stale dict that may have already rotated the refresh token).
    need_refresh = False
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        buffer_time = timedelta(minutes=5)
        if datetime.now(timezone.utc) + buffer_time >= expires_at:
            need_refresh = True
    except (ValueError, TypeError):
        need_refresh = True
    if need_refresh:
        if integration.get('refresh_token'):
            return await refresh_oauth_token(uid, app_key, integration, client=client)
        disconnect_payload = {'connected': False}
        await run_blocking(db_executor, users_db.set_task_integration, uid, app_key, disconnect_payload)
        return {**integration, 'connected': False}
    return integration


def _task_create_configuration_failure(app_key: str, integration: dict) -> Optional[dict]:
    if app_key not in OAUTH_CONFIGS:
        return {
            'success': False,
            'error': f'Unsupported integration: {app_key}',
            'error_code': 'unsupported',
            'retryable': False,
            'ambiguous': False,
        }
    if integration.get('connected') is False:
        name = OAUTH_CONFIGS[app_key]['name']
        return {
            'success': False,
            'error': f'{name} token refresh failed',
            'error_code': 'token_refresh_failed',
            'retryable': False,
            'ambiguous': False,
        }
    if not integration.get('access_token'):
        return {
            'success': False,
            'error': f'No access token for {app_key}',
            'error_code': 'no_access_token',
            'retryable': False,
            'ambiguous': False,
        }
    required_field = {
        'asana': ('workspace_gid', 'No workspace configured', 'no_workspace'),
        'google_tasks': ('default_list_id', 'No task list configured', 'no_list'),
        'clickup': ('list_id', 'No list configured', 'no_list'),
    }.get(app_key)
    if required_field and not integration.get(required_field[0]):
        return {
            'success': False,
            'error': required_field[1],
            'error_code': required_field[2],
            'retryable': False,
            'ambiguous': False,
        }
    return None


async def perform_request_with_token_retry(
    uid: str,
    app_key: str,
    integration: dict,
    request_fn: Callable,
    client: Optional[httpx.AsyncClient] = None,
) -> Tuple[Any, dict, Optional[Exception]]:
    client = client or get_http_client()
    access_token = integration.get('access_token') or ''
    response = await request_fn(client, access_token)
    if response.status_code == 401:
        if app_key in ['google_tasks', 'asana']:
            try:
                integration = await refresh_oauth_token(uid, app_key, integration, client=client)
                new_access_token = integration.get('access_token') or ''
                response = await request_fn(client, new_access_token)
            except Exception as e:
                logger.error(f'{app_key}: Token refresh failed during retry: {e}')
                return response, integration, e
    return response, integration, None


async def create_task_internal(
    uid: str,
    app_key: str,
    integration: dict,
    title: str,
    description: Optional[str] = None,
    due_date: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """
    Create task in external service. Used by API endpoint and auto-sync.

    Returns:
        dict: {"success": bool, "external_task_id": str, "error": str, "error_code": str}
    """
    if app_key in {'google_tasks', 'asana'}:
        integration = await ensure_valid_oauth_token(
            uid,
            app_key,
            integration,
            refresh_if_missing_expires_at=(app_key == 'google_tasks'),
            client=client,
        )
    preflight_error = _task_create_configuration_failure(app_key, integration)
    if preflight_error is not None:
        return preflight_error

    try:
        client = client or get_http_client()
        access_token = str(integration['access_token'])

        if app_key == 'todoist':
            body = {'content': title, 'priority': 2}
            if description:
                body['description'] = description
            if due_date:
                body['due_string'] = due_date.strftime('%Y-%m-%d')

            response = await client.post(
                'https://api.todoist.com/rest/v2/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json=body,
            )

            if response.status_code in [200, 201]:
                task_data = response.json()
                return _provider_create_success(task_data.get('id'))
            else:
                if response.status_code == 401:
                    await run_blocking(
                        db_executor,
                        users_db.set_task_integration,
                        uid,
                        'todoist',
                        {'connected': False},
                    )
                return _provider_create_http_failure('Todoist', response.status_code)

        elif app_key == 'asana':
            workspace_gid = str(integration['workspace_gid'])
            project_gid = integration.get('project_gid')
            user_gid = integration.get('user_gid')

            task_data = {'name': title, 'workspace': workspace_gid}
            if description:
                task_data['notes'] = description
            if due_date:
                task_data['due_on'] = due_date.strftime('%Y-%m-%d')
            if user_gid:
                task_data['assignee'] = user_gid
            if project_gid:
                task_data['projects'] = [project_gid]

            async def _asana_post(c, token):
                return await c.post(
                    'https://app.asana.com/api/1.0/tasks',
                    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                    json={'data': task_data},
                )

            response, integration, retry_err = await perform_request_with_token_retry(
                uid, app_key, integration, _asana_post, client=client
            )
            if retry_err:
                return {
                    "success": False,
                    "error": "Asana token refresh failed",
                    "error_code": "token_refresh_failed",
                    "retryable": False,
                }

            if response.status_code in [200, 201]:
                result = response.json()
                return _provider_create_success(result.get('data', {}).get('gid'))
            else:
                return _provider_create_http_failure('Asana', response.status_code)

        elif app_key == 'google_tasks':
            list_id = str(integration['default_list_id'])

            task_data = {'title': title}
            if description:
                task_data['notes'] = description
            if due_date:
                task_data['due'] = due_date.strftime('%Y-%m-%dT00:00:00.000Z')

            async def _google_tasks_post(c, token):
                return await c.post(
                    f'https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks',
                    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                    json=task_data,
                )

            response, integration, retry_err = await perform_request_with_token_retry(
                uid, app_key, integration, _google_tasks_post, client=client
            )
            if retry_err:
                return {
                    "success": False,
                    "error": "Google Tasks token refresh failed",
                    "error_code": "token_refresh_failed",
                    "retryable": False,
                }

            if response.status_code in [200, 201]:
                result = response.json()
                return _provider_create_success(result.get('id'))
            else:
                return _provider_create_http_failure('Google Tasks', response.status_code)

        elif app_key == 'clickup':
            list_id = str(integration['list_id'])

            task_data: dict[str, Any] = {'name': title}
            if description:
                task_data['description'] = description
            if due_date:
                task_data['due_date'] = int(due_date.timestamp() * 1000)

            response = await client.post(
                f'https://api.clickup.com/api/v2/list/{list_id}/task',
                headers={'Authorization': access_token, 'Content-Type': 'application/json'},
                json=task_data,
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return _provider_create_success(result.get('id'))
            else:
                return _provider_create_http_failure('ClickUp', response.status_code)
        else:
            return {
                'success': False,
                'error': f'Unsupported integration: {app_key}',
                'error_code': 'unsupported',
                'retryable': False,
                'ambiguous': False,
            }

    except httpx.TransportError as e:
        logger.error(f"Error creating task in {app_key}: {e}")
        return _provider_create_transport_failure(e)
    except Exception as e:
        logger.error(f"Error creating task in {app_key}: {e}")
        return {
            "success": False,
            "error": type(e).__name__,
            "error_code": "internal_error",
            "retryable": False,
            "ambiguous": True,
        }
