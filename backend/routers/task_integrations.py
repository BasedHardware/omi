from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import secrets
import ast
from datetime import datetime, timedelta, timezone
import httpx

import database.users as users_db
import database.redis_db as redis_db
from utils.other import endpoints as auth

router = APIRouter()

# OAuth state management
OAUTH_STATE_EXPIRY = 600  # 10 minutes

http_client: Optional[httpx.AsyncClient] = None

# Templates
templates = Jinja2Templates(directory="templates")

# OAuth provider configurations
OAUTH_CONFIGS = {
    'todoist': {'name': 'Todoist'},
    'asana': {'name': 'Asana'},
    'google_tasks': {'name': 'Google Tasks'},
    'clickup': {'name': 'ClickUp'},
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


def render_oauth_response(
    request: Request,
    app_key: str,
    success: bool = True,
    redirect_url: Optional[str] = None,
    error_type: Optional[str] = None,
) -> HTMLResponse:
    """
    Render OAuth callback response using template.

    Args:
        request: FastAPI request object
        app_key: Integration app key (todoist, asana, etc.)
        success: Whether the OAuth flow was successful
        redirect_url: Deep link URL to redirect to (for success case)
        error_type: Type of error (missing_code, invalid_state, config_error, server_error)
    """
    # Use a single, default gradient in the template (template now hardcodes it).
    config = OAUTH_CONFIGS.get(app_key, {'name': app_key.title()})

    if success:
        context = {
            'request': request,
            'title': f"{config['name']} Auth",
            'icon': '✓',
            'message': 'Authentication Successful!',
            'description': 'Redirecting back to Omi...',
            'redirect_url': redirect_url or f'omi://{app_key}/callback?error=unknown',
            'show_spinner': True,
        }
    else:
        error_messages = {
            'missing_code': 'No authorization code received from {}.'.format(config['name']),
            'invalid_state': 'Invalid or expired authentication request.',
            'config_error': '{} OAuth not properly configured.'.format(config['name']),
            'server_error': 'An error occurred during authentication.',
        }

        context = {
            'request': request,
            'title': f"{config['name']} Auth Error",
            'icon': '❌',
            'message': f"{'Security' if error_type == 'invalid_state' else 'Configuration' if error_type == 'config_error' else 'Authentication'} Error",
            'description': error_messages.get(error_type, 'An error occurred.'),
            'redirect_url': f'omi://{app_key}/callback?error={error_type or "unknown"}',
            'show_spinner': False,
        }

    return templates.TemplateResponse('oauth_callback.html', context)


def validate_and_consume_oauth_state(state_token: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Validate OAuth state token and return associated data.
    Deletes the state token after validation to prevent replay attacks.

    Returns:
        Dict with 'uid' and 'app_key' if valid, None if invalid/expired
    """
    if not state_token:
        return None

    state_key = f"oauth_state:{state_token}"
    state_data_str = redis_db.r.get(state_key)

    if not state_data_str:
        return None

    # Delete immediately to prevent replay
    redis_db.r.delete(state_key)

    try:
        state_data = ast.literal_eval(state_data_str.decode() if isinstance(state_data_str, bytes) else state_data_str)
        return state_data
    except Exception as e:
        print(f"Error parsing state data: {e}")
        return None


# Request/Response models
class TaskIntegrationData(BaseModel):
    """Data for a task integration connection"""

    # Common fields
    connected: bool = True
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

    # Asana-specific fields
    user_gid: Optional[str] = None
    workspace_gid: Optional[str] = None
    workspace_name: Optional[str] = None
    project_gid: Optional[str] = None
    project_name: Optional[str] = None

    # Google Tasks-specific fields
    default_list_id: Optional[str] = None
    default_list_title: Optional[str] = None

    # ClickUp-specific fields
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    space_id: Optional[str] = None
    space_name: Optional[str] = None
    list_id: Optional[str] = None
    list_name: Optional[str] = None


class TaskIntegrationsResponse(BaseModel):
    """Response containing all task integrations"""

    integrations: Dict[str, Any] = Field(description="Map of app_key to connection details")
    default_app: Optional[str] = Field(description="Default task integration app key")


class DefaultTaskIntegrationRequest(BaseModel):
    """Request to set default task integration"""

    app_key: str = Field(description="Task integration app key (e.g., 'asana', 'todoist')")


class DefaultTaskIntegrationResponse(BaseModel):
    """Response for default task integration"""

    default_app: Optional[str] = Field(description="Default task integration app key")


# *****************************
# ********** ROUTES ***********
# *****************************


@router.get("/v1/task-integrations", response_model=TaskIntegrationsResponse, tags=['task-integrations'])
def get_task_integrations(uid: str = Depends(auth.get_current_user_uid)):
    """Get all task integration connections for the current user."""
    integrations = users_db.get_task_integrations(uid)
    default_app = users_db.get_default_task_integration(uid)

    return TaskIntegrationsResponse(integrations=integrations, default_app=default_app)


@router.get("/v1/task-integrations/default", response_model=DefaultTaskIntegrationResponse, tags=['task-integrations'])
def get_default_task_integration(uid: str = Depends(auth.get_current_user_uid)):
    """Get the user's default task integration app."""
    default_app = users_db.get_default_task_integration(uid)
    return DefaultTaskIntegrationResponse(default_app=default_app)


@router.put("/v1/task-integrations/default", response_model=DefaultTaskIntegrationResponse, tags=['task-integrations'])
def set_default_task_integration(request: DefaultTaskIntegrationRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Set the user's default task integration app."""
    users_db.set_default_task_integration(uid, request.app_key)
    return DefaultTaskIntegrationResponse(default_app=request.app_key)


@router.put("/v1/task-integrations/{app_key}", tags=['task-integrations'])
def save_task_integration(app_key: str, data: TaskIntegrationData, uid: str = Depends(auth.get_current_user_uid)):
    """Save or update a task integration connection."""
    # Convert Pydantic model to dict, excluding None values
    integration_data = data.model_dump(exclude_none=True)

    users_db.set_task_integration(uid, app_key, integration_data)

    return {"status": "ok", "app_key": app_key}


@router.delete("/v1/task-integrations/{app_key}", status_code=204, tags=['task-integrations'])
def delete_task_integration(app_key: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete a task integration connection."""
    success = users_db.delete_task_integration(uid, app_key)

    if not success:
        raise HTTPException(status_code=404, detail="Task integration not found")

    # If this was the default, clear it
    default_app = users_db.get_default_task_integration(uid)
    if default_app == app_key:
        users_db.set_default_task_integration(uid, '')

    return {"status": "ok"}


# *****************************
# ****** OAuth Initiation *****
# *****************************


class OAuthUrlResponse(BaseModel):
    """Response containing OAuth authorization URL"""

    auth_url: str = Field(description="OAuth authorization URL to open in browser")


@router.get("/v1/task-integrations/{app_key}/oauth-url", response_model=OAuthUrlResponse, tags=['task-integrations'])
def get_oauth_url(app_key: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get OAuth authorization URL for a task integration.
    Frontend opens this URL in browser to start OAuth flow.
    Uses secure random state tokens to prevent CSRF attacks.
    """
    base_url = os.getenv('BASE_API_URL')
    if not base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")
    # Normalize base_url: remove trailing slash to prevent redirect URI mismatches
    base_url = base_url.rstrip('/')

    # Generate cryptographically secure random state token
    state_token = secrets.token_urlsafe(32)

    # Store state mapping in Redis with expiry
    state_key = f"oauth_state:{state_token}"
    state_data = {'uid': uid, 'app_key': app_key, 'created_at': datetime.now(timezone.utc).isoformat()}
    redis_db.r.setex(state_key, OAUTH_STATE_EXPIRY, str(state_data))

    if app_key == 'todoist':
        client_id = os.getenv('TODOIST_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Todoist not configured")

        base_url = base_url.rstrip('/')
        redirect_uri = f'{base_url}/v2/integrations/todoist/callback'
        auth_url = f'https://todoist.com/oauth/authorize?client_id={client_id}&scope=data:read_write&state={state_token}&redirect_uri={redirect_uri}'

    elif app_key == 'asana':
        client_id = os.getenv('ASANA_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Asana not configured")

        base_url = base_url.rstrip('/')
        redirect_uri = f'{base_url}/v2/integrations/asana/callback'
        scopes = 'tasks:read tasks:write workspaces:read projects:read users:read'
        from urllib.parse import quote

        auth_url = f'https://app.asana.com/-/oauth_authorize?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&state={state_token}&scope={quote(scopes)}'

    elif app_key == 'google_tasks':
        client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Google Tasks not configured")

        base_url = base_url.rstrip('/')
        redirect_uri = f'{base_url}/v2/integrations/google-tasks/callback'
        scope = 'https://www.googleapis.com/auth/tasks'
        from urllib.parse import quote

        auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&scope={quote(scope)}&access_type=offline&prompt=consent&state={state_token}'

    elif app_key == 'clickup':
        client_id = os.getenv('CLICKUP_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="ClickUp not configured")

        base_url = base_url.rstrip('/')
        redirect_uri = f'{base_url}/v2/integrations/clickup/callback'
        from urllib.parse import quote

        auth_url = (
            f'https://app.clickup.com/api?client_id={client_id}&redirect_uri={quote(redirect_uri)}&state={state_token}'
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported integration: {app_key}")

    return OAuthUrlResponse(auth_url=auth_url)


# *****************************
# ****** Token Refresh ******
# *****************************


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


async def refresh_oauth_token(uid: str, app_key: str, integration: dict) -> dict:
    name = OAUTH_CONFIGS.get(app_key, {'name': app_key}).get('name', app_key)
    refresh_token = integration.get('refresh_token')
    if not refresh_token:
        raise HTTPException(status_code=401, detail=f"No refresh token available for {name}")
    try:
        req = _build_refresh_request(app_key, refresh_token)
        client = get_http_client()
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
            updated_integration = integration.copy()
            updated_integration['access_token'] = new_access_token
            if new_refresh_token:
                updated_integration['refresh_token'] = new_refresh_token
            if expires_in:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                updated_integration['expires_at'] = expires_at.isoformat()
            users_db.set_task_integration(uid, app_key, updated_integration)
            return updated_integration
        else:
            error_text = token_response.text
            print(f'{app_key}: Token refresh failed with HTTP {token_response.status_code}: {error_text}')
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
                    updated_integration = integration.copy()
                    updated_integration['connected'] = False
                    users_db.set_task_integration(uid, app_key, updated_integration)
            raise HTTPException(status_code=401, detail=f"Failed to refresh {name} token")
    except HTTPException:
        raise
    except Exception as e:
        print(f'{app_key}: Error refreshing token: {e}')
        raise HTTPException(status_code=500, detail=f"Error refreshing token: {str(e)}")


async def ensure_valid_oauth_token(
    uid: str, app_key: str, integration: dict, refresh_if_missing_expires_at: bool = False
) -> dict:
    supports_refresh = app_key in ['google_tasks', 'asana']
    if not supports_refresh:
        return integration
    expires_at_str = integration.get('expires_at')
    if not expires_at_str:
        if refresh_if_missing_expires_at or integration.get('refresh_token'):
            return await refresh_oauth_token(uid, app_key, integration)
        return integration
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        buffer_time = timedelta(minutes=5)
        if datetime.now(timezone.utc) + buffer_time >= expires_at:
            if integration.get('refresh_token'):
                return await refresh_oauth_token(uid, app_key, integration)
            updated_integration = integration.copy()
            updated_integration['connected'] = False
            users_db.set_task_integration(uid, app_key, updated_integration)
            return updated_integration
    except Exception:
        if integration.get('refresh_token'):
            return await refresh_oauth_token(uid, app_key, integration)
    return integration


async def perform_request_with_token_retry(
    uid: str,
    app_key: str,
    integration: dict,
    request_fn,
):
    client = get_http_client()
    access_token = integration.get('access_token') or ''
    response = await request_fn(client, access_token)
    if response.status_code == 401:
        if app_key in ['google_tasks', 'asana']:
            try:
                integration = await refresh_oauth_token(uid, app_key, integration)
                new_access_token = integration.get('access_token') or ''
                response = await request_fn(client, new_access_token)
            except Exception as e:
                print(f'{app_key}: Token refresh failed during retry: {e}')
                return response, integration, e
    return response, integration, None


# *****************************
# ****** Task Operations ******
# *****************************


async def _create_task_internal(
    uid: str,
    app_key: str,
    integration: dict,
    title: str,
    description: Optional[str] = None,
    due_date: Optional[datetime] = None,
) -> dict:
    """
    Internal function to create task in external service.
    Used by both API endpoint and auto-sync.

    Args:
        uid: User ID
        app_key: Integration key (todoist, asana, google_tasks, clickup)
        integration: Integration config dict with access_token etc.
        title: Task title
        description: Optional task description/notes
        due_date: Optional due date

    Returns:
        dict: {"success": bool, "external_task_id": str, "error": str, "error_code": str}

        Error codes:
        - token_refresh_failed: OAuth token refresh failed
        - no_access_token: No access token available
        - no_workspace: Asana workspace not configured
        - no_list: Task list not configured (Google Tasks, ClickUp)
        - api_error: External API returned an error
        - unsupported: Unsupported integration
    """
    if app_key in ['google_tasks', 'asana']:
        integration = await ensure_valid_oauth_token(
            uid, app_key, integration, refresh_if_missing_expires_at=(app_key == 'google_tasks')
        )
        if not integration.get('connected'):
            name = OAUTH_CONFIGS.get(app_key, {'name': app_key}).get('name', app_key)
            return {"success": False, "error": f"{name} token refresh failed", "error_code": "token_refresh_failed"}

    access_token = integration.get('access_token')
    if not access_token:
        return {"success": False, "error": f"No access token for {app_key}", "error_code": "no_access_token"}

    try:
        client = get_http_client()

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
                return {"success": True, "external_task_id": str(task_data.get('id'))}
            else:
                if response.status_code == 401:
                    integration['connected'] = False
                    users_db.set_task_integration(uid, 'todoist', integration)
                return {
                    "success": False,
                    "error": f"Todoist API error: {response.status_code}",
                    "error_code": "api_error",
                }

        elif app_key == 'asana':
            workspace_gid = integration.get('workspace_gid')
            project_gid = integration.get('project_gid')
            user_gid = integration.get('user_gid')

            if not workspace_gid:
                return {"success": False, "error": "No workspace configured", "error_code": "no_workspace"}

            task_data = {'name': title, 'workspace': workspace_gid}
            if description:
                task_data['notes'] = description
            if due_date:
                task_data['due_on'] = due_date.strftime('%Y-%m-%d')
            if user_gid:
                task_data['assignee'] = user_gid
            if project_gid:
                task_data['projects'] = [project_gid]

            response = await client.post(
                'https://app.asana.com/api/1.0/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json={'data': task_data},
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return {"success": True, "external_task_id": result.get('data', {}).get('gid')}
            else:
                return {
                    "success": False,
                    "error": f"Asana API error: {response.status_code}",
                    "error_code": "api_error",
                }

        elif app_key == 'google_tasks':
            list_id = integration.get('default_list_id')
            if not list_id:
                return {"success": False, "error": "No task list configured", "error_code": "no_list"}

            task_data = {'title': title}
            if description:
                task_data['notes'] = description
            if due_date:
                task_data['due'] = due_date.strftime('%Y-%m-%dT00:00:00.000Z')

            response = await client.post(
                f'https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json=task_data,
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return {"success": True, "external_task_id": result.get('id')}
            else:
                return {
                    "success": False,
                    "error": f"Google Tasks API error: {response.status_code}",
                    "error_code": "api_error",
                }

        elif app_key == 'clickup':
            list_id = integration.get('list_id')
            if not list_id:
                return {"success": False, "error": "No list configured", "error_code": "no_list"}

            task_data = {'name': title}
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
                return {"success": True, "external_task_id": result.get('id')}
            else:
                return {
                    "success": False,
                    "error": f"ClickUp API error: {response.status_code}",
                    "error_code": "api_error",
                }

        else:
            return {"success": False, "error": f"Unsupported integration: {app_key}", "error_code": "unsupported"}

    except Exception as e:
        print(f"Error creating task in {app_key}: {e}")
        return {"success": False, "error": str(e)}


class CreateTaskRequest(BaseModel):
    """Request to create a task in an integration"""

    title: str = Field(description="Task title/name")
    description: Optional[str] = Field(default=None, description="Task description/notes")
    due_date: Optional[str] = Field(default=None, description="Due date in ISO format")


class CreateTaskResponse(BaseModel):
    """Response for task creation"""

    success: bool
    external_task_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/v1/task-integrations/{app_key}/tasks", response_model=CreateTaskResponse, tags=['task-integrations'])
async def create_task_via_integration(
    app_key: str, request: CreateTaskRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Create a task in the specified integration using stored credentials."""

    # Get integration details
    integration = users_db.get_task_integration(uid, app_key)
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=404, detail=f"Not connected to {app_key}")

    # Validate access token exists
    if not integration.get('access_token'):
        raise HTTPException(status_code=401, detail=f"No access token for {app_key}")

    # Parse due date if provided
    due_date = None
    if request.due_date:
        due_date = datetime.fromisoformat(request.due_date.replace('Z', '+00:00'))

    result = await _create_task_internal(
        uid=uid,
        app_key=app_key,
        integration=integration,
        title=request.title,
        description=request.description,
        due_date=due_date,
    )

    if not result.get("success"):
        error_code = result.get("error_code")
        error_msg = result.get("error", "Unknown error")

        if error_code == "token_refresh_failed":
            name = OAUTH_CONFIGS.get(app_key, {'name': app_key}).get('name', app_key)
            raise HTTPException(status_code=401, detail=f"{name} token refresh failed. Please reconnect.")
        if error_code == "no_access_token":
            raise HTTPException(status_code=401, detail=error_msg)

    return CreateTaskResponse(
        success=result.get("success", False),
        external_task_id=result.get("external_task_id"),
        error=result.get("error"),
    )


# *****************************
# ****** Data Fetching APIs ****
# *****************************


@router.get("/v1/task-integrations/asana/workspaces", tags=['task-integrations'])
async def get_asana_workspaces(uid: str = Depends(auth.get_current_user_uid)):
    """Get user's Asana workspaces"""
    data = users_db.get_task_integration(uid, 'asana')

    if not data:
        raise HTTPException(status_code=404, detail="Asana integration not found")

    data = await ensure_valid_oauth_token(uid, 'asana', data)
    if not data.get('connected'):
        raise HTTPException(status_code=401, detail="Asana token refresh failed. Please reconnect.")

    access_token = data.get('access_token')

    if not access_token:
        raise HTTPException(status_code=401, detail="Asana not authenticated")

    try:

        async def _request(client, token):
            return await client.get(
                'https://app.asana.com/api/1.0/workspaces',
                headers={'Authorization': f'Bearer {token}'},
            )

        response, data, err = await perform_request_with_token_retry(uid, 'asana', data, _request)
        if err:
            raise HTTPException(status_code=401, detail="Asana authentication expired. Please reconnect.")

        if response.status_code == 200:
            result = response.json()
            return {'workspaces': result.get('data', [])}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Asana workspaces")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching workspaces: {str(e)}")


@router.get("/v1/task-integrations/asana/projects/{workspace_gid}", tags=['task-integrations'])
async def get_asana_projects(workspace_gid: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get projects in an Asana workspace"""
    data = users_db.get_task_integration(uid, 'asana')

    if not data:
        raise HTTPException(status_code=404, detail="Asana integration not found")

    data = await ensure_valid_oauth_token(uid, 'asana', data)
    if not data.get('connected'):
        raise HTTPException(status_code=401, detail="Asana token refresh failed. Please reconnect.")

    access_token = data.get('access_token')

    if not access_token:
        raise HTTPException(status_code=401, detail="Asana not authenticated")

    try:

        async def _request(client, token):
            return await client.get(
                f'https://app.asana.com/api/1.0/projects?workspace={workspace_gid}&archived=false&opt_fields=name,gid,owner',
                headers={'Authorization': f'Bearer {token}'},
            )

        response, data, err = await perform_request_with_token_retry(uid, 'asana', data, _request)
        if err:
            raise HTTPException(status_code=401, detail="Asana authentication expired. Please reconnect.")

        if response.status_code == 200:
            result = response.json()
            return {'projects': result.get('data', [])}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Asana projects")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching projects: {str(e)}")


@router.get("/v1/task-integrations/clickup/teams", tags=['task-integrations'])
async def get_clickup_teams(uid: str = Depends(auth.get_current_user_uid)):
    """Get user's ClickUp teams"""
    data = users_db.get_task_integration(uid, 'clickup')

    if not data:
        raise HTTPException(status_code=404, detail="ClickUp integration not found")

    data = await ensure_valid_oauth_token(uid, 'clickup', data)
    if not data.get('connected'):
        raise HTTPException(status_code=401, detail="ClickUp token refresh failed. Please reconnect.")

    access_token = data.get('access_token')

    if not access_token:
        raise HTTPException(status_code=401, detail="ClickUp not authenticated")

    try:

        async def _request(client, token):
            return await client.get(
                'https://api.clickup.com/api/v2/team',
                headers={'Authorization': token},
            )

        response, data, err = await perform_request_with_token_retry(uid, 'clickup', data, _request)
        if err:
            raise HTTPException(status_code=401, detail="ClickUp authentication expired. Please reconnect.")

        if response.status_code == 200:
            result = response.json()
            return {'teams': result.get('teams', [])}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch ClickUp teams")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching teams: {str(e)}")


@router.get("/v1/task-integrations/clickup/spaces/{team_id}", tags=['task-integrations'])
async def get_clickup_spaces(team_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get spaces in a ClickUp team"""
    data = users_db.get_task_integration(uid, 'clickup')

    if not data:
        raise HTTPException(status_code=404, detail="ClickUp integration not found")

    data = await ensure_valid_oauth_token(uid, 'clickup', data)
    if not data.get('connected'):
        raise HTTPException(status_code=401, detail="ClickUp token refresh failed. Please reconnect.")

    access_token = data.get('access_token')

    if not access_token:
        raise HTTPException(status_code=401, detail="ClickUp not authenticated")

    try:

        async def _request(client, token):
            return await client.get(
                f'https://api.clickup.com/api/v2/team/{team_id}/space?archived=false',
                headers={'Authorization': token},
            )

        response, data, err = await perform_request_with_token_retry(uid, 'clickup', data, _request)
        if err:
            raise HTTPException(status_code=401, detail="ClickUp authentication expired. Please reconnect.")

        if response.status_code == 200:
            result = response.json()
            return {'spaces': result.get('spaces', [])}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch ClickUp spaces")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching spaces: {str(e)}")


@router.get("/v1/task-integrations/clickup/lists/{space_id}", tags=['task-integrations'])
async def get_clickup_lists(space_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get lists in a ClickUp space"""
    data = users_db.get_task_integration(uid, 'clickup')

    if not data:
        raise HTTPException(status_code=404, detail="ClickUp integration not found")

    data = await ensure_valid_oauth_token(uid, 'clickup', data)
    if not data.get('connected'):
        raise HTTPException(status_code=401, detail="ClickUp token refresh failed. Please reconnect.")

    access_token = data.get('access_token')

    if not access_token:
        raise HTTPException(status_code=401, detail="ClickUp not authenticated")

    try:

        async def _request(client, token):
            return await client.get(
                f'https://api.clickup.com/api/v2/space/{space_id}/list?archived=false',
                headers={'Authorization': token},
            )

        response, data, err = await perform_request_with_token_retry(uid, 'clickup', data, _request)
        if err:
            raise HTTPException(status_code=401, detail="ClickUp authentication expired. Please reconnect.")

        if response.status_code == 200:
            result = response.json()
            return {'lists': result.get('lists', [])}
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch ClickUp lists")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching lists: {str(e)}")


# *****************************
# ******* OAuth Callbacks *****
# *****************************


class OAuthProviderConfig(BaseModel):
    """Configuration for OAuth provider-specific logic"""

    token_endpoint: str
    token_request_type: str = "form"
    token_request_data: Dict[str, Any]
    additional_headers: Dict[str, str] = {}

    async def fetch_additional_data(self, client: httpx.AsyncClient, access_token: str) -> Dict[str, Any]:
        """Hook for fetching provider-specific data after token exchange"""
        return {}


async def handle_oauth_callback(
    request: Request,
    app_key: str,
    code: Optional[str],
    state: Optional[str],
    provider_config: OAuthProviderConfig,
) -> HTMLResponse:
    """
    Generic OAuth callback handler that works for all providers.

    Args:
        request: FastAPI request object
        app_key: Integration app key (todoist, asana, google_tasks, clickup)
        code: Authorization code from OAuth provider
        state: State token for CSRF protection
        provider_config: Provider-specific configuration

    Returns:
        HTMLResponse with OAuth callback page
    """
    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    try:
        client = get_http_client()

        if provider_config.token_request_type == "form":
            token_response = await client.post(
                provider_config.token_endpoint,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    **provider_config.additional_headers,
                },
                data=provider_config.token_request_data,
            )
        else:  # params
            token_response = await client.post(
                provider_config.token_endpoint,
                params=provider_config.token_request_data,
                headers=provider_config.additional_headers,
            )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in')  # Seconds until expiry

            if not access_token:
                print(f'{app_key}: No access token received in response')
                deep_link = f'omi://{app_key}/callback?error=no_access_token'
                return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

            integration_data = {
                'connected': True,
                'access_token': access_token,
            }

            supports_refresh = app_key in ['google_tasks', 'asana']
            if refresh_token and supports_refresh:
                integration_data['refresh_token'] = refresh_token

            if expires_in and supports_refresh:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                integration_data['expires_at'] = expires_at.isoformat()

            try:
                additional_data = await provider_config.fetch_additional_data(client, access_token)
                integration_data.update(additional_data)
            except Exception as e:
                print(f'{app_key}: Error fetching additional data: {e}')

            # Store in Firebase
            try:
                users_db.set_task_integration(uid, app_key, integration_data)
                print(f'{app_key}: Successfully stored tokens for user {uid}')
            except Exception as e:
                print(f'{app_key}: Error storing tokens in Firebase: {e}')
                deep_link = f'omi://{app_key}/callback?error=storage_failed'
                return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

            requires_setup = 'requires_setup=true' if app_key in ['asana', 'clickup'] else ''
            deep_link = f'omi://{app_key}/callback?success=true{"&" + requires_setup if requires_setup else ""}'

            return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)
        else:
            print(f'{app_key}: Token exchange failed with HTTP {token_response.status_code}')
            deep_link = f'omi://{app_key}/callback?error=token_exchange_failed'
            return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

    except Exception as e:
        print(f'{app_key}: Unexpected error during OAuth callback: {e}')
        deep_link = f'omi://{app_key}/callback?error=server_error'
        return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


@router.get(
    '/v2/integrations/todoist/callback',
    response_class=HTMLResponse,
    tags=['task-integrations', 'oauth'],
)
async def todoist_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Todoist integration."""
    client_id = os.getenv('TODOIST_CLIENT_ID')
    client_secret = os.getenv('TODOIST_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return render_oauth_response(request, 'todoist', success=False, error_type='config_error')

    config = OAuthProviderConfig(
        token_endpoint='https://todoist.com/oauth/access_token',
        token_request_type='form',
        token_request_data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
        },
    )

    return await handle_oauth_callback(request, 'todoist', code, state, config)


@router.get(
    '/v2/integrations/asana/callback',
    response_class=HTMLResponse,
    tags=['task-integrations', 'oauth'],
)
async def asana_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Asana integration."""
    client_id = os.getenv('ASANA_CLIENT_ID')
    client_secret = os.getenv('ASANA_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'asana', success=False, error_type='config_error')

    # Normalize base_url: remove trailing slash to prevent redirect URI mismatches
    base_url = base_url.rstrip('/')
    redirect_uri = f'{base_url}/v2/integrations/asana/callback'

    class AsanaConfig(OAuthProviderConfig):
        async def fetch_additional_data(self, client: httpx.AsyncClient, access_token: str) -> Dict[str, Any]:
            """Fetch Asana user GID"""
            try:
                user_response = await client.get(
                    'https://app.asana.com/api/1.0/users/me',
                    headers={'Authorization': f'Bearer {access_token}'},
                )
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    user_gid = user_data.get('data', {}).get('gid')
                    return {'user_gid': user_gid} if user_gid else {}
            except Exception as e:
                print(f'asana: Failed to fetch user GID: {e}')
            return {}

    config = AsanaConfig(
        token_endpoint='https://app.asana.com/-/oauth_token',
        token_request_type='form',
        token_request_data={
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'code': code,
        },
    )

    return await handle_oauth_callback(request, 'asana', code, state, config)


@router.get(
    '/v2/integrations/google-tasks/callback',
    response_class=HTMLResponse,
    tags=['task-integrations', 'oauth'],
)
async def google_tasks_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Google Tasks integration."""
    client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_TASKS_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'google_tasks', success=False, error_type='config_error')

    # Normalize base_url: remove trailing slash to prevent redirect URI mismatches
    base_url = base_url.rstrip('/')
    redirect_uri = f'{base_url}/v2/integrations/google-tasks/callback'

    class GoogleTasksConfig(OAuthProviderConfig):
        async def fetch_additional_data(self, client: httpx.AsyncClient, access_token: str) -> Dict[str, Any]:
            """Fetch default Google Tasks list"""
            try:
                lists_response = await client.get(
                    'https://tasks.googleapis.com/tasks/v1/users/@me/lists',
                    headers={'Authorization': f'Bearer {access_token}'},
                )
                if lists_response.status_code == 200:
                    lists_data = lists_response.json()
                    items = lists_data.get('items', [])
                    if items:
                        return {
                            'default_list_id': items[0].get('id'),
                            'default_list_title': items[0].get('title'),
                        }
            except Exception as e:
                print(f'google_tasks: Failed to fetch task lists: {e}')
            return {}

    config = GoogleTasksConfig(
        token_endpoint='https://oauth2.googleapis.com/token',
        token_request_type='form',
        token_request_data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
    )

    return await handle_oauth_callback(request, 'google_tasks', code, state, config)


@router.get(
    '/v2/integrations/clickup/callback',
    response_class=HTMLResponse,
    tags=['task-integrations', 'oauth'],
)
async def clickup_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for ClickUp integration."""
    client_id = os.getenv('CLICKUP_CLIENT_ID')
    client_secret = os.getenv('CLICKUP_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return render_oauth_response(request, 'clickup', success=False, error_type='config_error')

    config = OAuthProviderConfig(
        token_endpoint='https://api.clickup.com/api/v2/oauth/token',
        token_request_type='params',
        token_request_data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
        },
    )

    return await handle_oauth_callback(request, 'clickup', code, state, config)


@router.on_event("shutdown")
async def shutdown_http_client():
    """Cleanup HTTP client on app shutdown."""
    await close_http_client()
