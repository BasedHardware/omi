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

        redirect_uri = f'{base_url}v2/integrations/todoist/callback'
        auth_url = f'https://todoist.com/oauth/authorize?client_id={client_id}&scope=data:read_write&state={state_token}&redirect_uri={redirect_uri}'

    elif app_key == 'asana':
        client_id = os.getenv('ASANA_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Asana not configured")

        redirect_uri = f'{base_url}v2/integrations/asana/callback'
        scopes = 'tasks:read tasks:write workspaces:read projects:read users:read'
        from urllib.parse import quote

        auth_url = f'https://app.asana.com/-/oauth_authorize?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&state={state_token}&scope={quote(scopes)}'

    elif app_key == 'google_tasks':
        client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Google Tasks not configured")

        redirect_uri = f'{base_url}v2/integrations/google-tasks/callback'
        scope = 'https://www.googleapis.com/auth/tasks'
        from urllib.parse import quote

        auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&scope={quote(scope)}&access_type=offline&prompt=consent&state={state_token}'

    elif app_key == 'clickup':
        client_id = os.getenv('CLICKUP_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="ClickUp not configured")

        redirect_uri = f'{base_url}v2/integrations/clickup/callback'
        from urllib.parse import quote

        auth_url = (
            f'https://app.clickup.com/api?client_id={client_id}&redirect_uri={quote(redirect_uri)}&state={state_token}'
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported integration: {app_key}")

    return OAuthUrlResponse(auth_url=auth_url)


# *****************************
# ****** Task Operations ******
# *****************************


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
    from datetime import datetime

    # Get integration details
    integration = users_db.get_task_integration(uid, app_key)
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=404, detail=f"Not connected to {app_key}")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=401, detail=f"No access token for {app_key}")

    try:
        if app_key == 'todoist':
            # Create task in Todoist
            body = {
                'content': request.title,
                'priority': 2,
            }
            if request.description:
                body['description'] = request.description
            if request.due_date:
                due = datetime.fromisoformat(request.due_date.replace('Z', '+00:00'))
                body['due_string'] = due.strftime('%Y-%m-%d')

            client = get_http_client()
            response = await client.post(
                'https://api.todoist.com/rest/v2/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json=body,
            )

            if response.status_code in [200, 201]:
                task_data = response.json()
                return CreateTaskResponse(success=True, external_task_id=task_data.get('id'))
            else:
                return CreateTaskResponse(success=False, error=f"Todoist API error: {response.status_code}")

        elif app_key == 'asana':
            # Create task in Asana
            workspace_gid = integration.get('workspace_gid')
            project_gid = integration.get('project_gid')
            user_gid = integration.get('user_gid')

            if not workspace_gid:
                return CreateTaskResponse(success=False, error="No workspace configured")

            task_data = {
                'name': request.title,
                'workspace': workspace_gid,
            }
            if request.description:
                task_data['notes'] = request.description
            if request.due_date:
                due = datetime.fromisoformat(request.due_date.replace('Z', '+00:00'))
                task_data['due_on'] = due.strftime('%Y-%m-%d')
            if user_gid:
                task_data['assignee'] = user_gid
            if project_gid:
                task_data['projects'] = [project_gid]

            client = get_http_client()
            response = await client.post(
                'https://app.asana.com/api/1.0/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json={'data': task_data},
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return CreateTaskResponse(success=True, external_task_id=result.get('data', {}).get('gid'))
            else:
                return CreateTaskResponse(success=False, error=f"Asana API error: {response.status_code}")

        elif app_key == 'google_tasks':
            # Create task in Google Tasks
            list_id = integration.get('default_list_id')
            if not list_id:
                return CreateTaskResponse(success=False, error="No task list configured")

            task_data = {'title': request.title}
            if request.description:
                task_data['notes'] = request.description
            if request.due_date:
                due = datetime.fromisoformat(request.due_date.replace('Z', '+00:00'))
                task_data['due'] = due.strftime('%Y-%m-%dT00:00:00.000Z')

            client = get_http_client()
            response = await client.post(
                f'https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                json=task_data,
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return CreateTaskResponse(success=True, external_task_id=result.get('id'))
            else:
                return CreateTaskResponse(success=False, error=f"Google Tasks API error: {response.status_code}")

        elif app_key == 'clickup':
            # Create task in ClickUp
            list_id = integration.get('list_id')
            if not list_id:
                return CreateTaskResponse(success=False, error="No list configured")

            task_data = {'name': request.title}
            if request.description:
                task_data['description'] = request.description
            if request.due_date:
                due = datetime.fromisoformat(request.due_date.replace('Z', '+00:00'))
                task_data['due_date'] = int(due.timestamp() * 1000)

            client = get_http_client()
            response = await client.post(
                f'https://api.clickup.com/api/v2/list/{list_id}/task',
                headers={'Authorization': access_token, 'Content-Type': 'application/json'},
                json=task_data,
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return CreateTaskResponse(success=True, external_task_id=result.get('id'))
            else:
                return CreateTaskResponse(success=False, error=f"ClickUp API error: {response.status_code}")

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported integration: {app_key}")

    except Exception as e:
        print(f"Error creating task in {app_key}: {e}")
        return CreateTaskResponse(success=False, error=str(e))


# *****************************
# ******* OAuth Callbacks *****
# *****************************


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
    """
    OAuth callback endpoint for Todoist integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    app_key = 'todoist'

    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    # Exchange code for tokens using backend credentials
    import requests

    client_id = os.getenv('TODOIST_CLIENT_ID')
    client_secret = os.getenv('TODOIST_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return render_oauth_response(request, app_key, success=False, error_type='config_error')

    try:
        # Exchange code for tokens
        client = get_http_client()
        token_response = await client.post(
            'https://todoist.com/oauth/access_token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')

            # Store token in Firebase
            if access_token and uid:
                try:
                    users_db.set_task_integration(
                        uid,
                        app_key,
                        {
                            'connected': True,
                            'access_token': access_token,
                        },
                    )
                    print(f'✓ Stored {app_key} token in Firebase for user {uid}')
                except Exception as e:
                    print(f'Error storing {app_key} token: {e}')

            # Create deep link for success (no token in URL)
            deep_link = f'omi://{app_key}/callback?success=true'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://{app_key}/callback?error=token_exchange_failed'
    except Exception as e:
        print(f'Error exchanging {app_key} code: {e}')
        deep_link = f'omi://{app_key}/callback?error=server_error'

    return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


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
    """
    OAuth callback endpoint for Asana integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    app_key = 'asana'

    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    # Exchange code for tokens using backend credentials
    import requests

    client_id = os.getenv('ASANA_CLIENT_ID')
    client_secret = os.getenv('ASANA_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, app_key, success=False, error_type='config_error')

    redirect_uri = f'{base_url}v2/integrations/asana/callback'

    try:
        # Exchange code for tokens
        client = get_http_client()
        token_response = await client.post(
            'https://app.asana.com/-/oauth_token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'authorization_code',
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'code': code,
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token', '')

            # Fetch user info and store everything in Firebase
            if access_token and uid:
                try:
                    # Fetch user GID from Asana
                    user_response = await client.get(
                        'https://app.asana.com/api/1.0/users/me', headers={'Authorization': f'Bearer {access_token}'}
                    )
                    user_gid = None
                    if user_response.status_code == 200:
                        user_data = user_response.json()
                        user_gid = user_data.get('data', {}).get('gid')

                    # Store in Firebase
                    users_db.set_task_integration(
                        uid,
                        app_key,
                        {
                            'connected': True,
                            'access_token': access_token,
                            'refresh_token': refresh_token,
                            'user_gid': user_gid,
                        },
                    )
                    print(f'✓ Stored {app_key} tokens in Firebase for user {uid}')
                except Exception as e:
                    print(f'Error storing {app_key} tokens: {e}')

            # Create deep link for success (no tokens in URL)
            deep_link = f'omi://{app_key}/callback?success=true&requires_setup=true'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://{app_key}/callback?error=token_exchange_failed'
    except Exception as e:
        print(f'Error exchanging {app_key} code: {e}')
        deep_link = f'omi://{app_key}/callback?error=server_error'

    return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


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
    """
    OAuth callback endpoint for Google Tasks integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    app_key = 'google_tasks'

    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    # Exchange code for tokens using backend credentials
    import requests

    client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_TASKS_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, app_key, success=False, error_type='config_error')

    redirect_uri = f'{base_url}v2/integrations/google-tasks/callback'

    try:
        # Exchange code for tokens
        client = get_http_client()
        token_response = await client.post(
            'https://oauth2.googleapis.com/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token', '')

            # Fetch task lists and store in Firebase
            if access_token and uid:
                try:
                    # Fetch default task list
                    lists_response = await client.get(
                        'https://tasks.googleapis.com/tasks/v1/users/@me/lists',
                        headers={'Authorization': f'Bearer {access_token}'},
                    )
                    default_list_id = None
                    default_list_title = None
                    if lists_response.status_code == 200:
                        lists_data = lists_response.json()
                        items = lists_data.get('items', [])
                        if items:
                            default_list_id = items[0].get('id')
                            default_list_title = items[0].get('title')

                    # Store in Firebase
                    users_db.set_task_integration(
                        uid,
                        app_key,
                        {
                            'connected': True,
                            'access_token': access_token,
                            'refresh_token': refresh_token,
                            'default_list_id': default_list_id,
                            'default_list_title': default_list_title,
                        },
                    )
                    print(f'✓ Stored {app_key} tokens in Firebase for user {uid}')
                except Exception as e:
                    print(f'Error storing {app_key} tokens: {e}')

            # Create deep link for success (no tokens in URL)
            deep_link = 'omi://google-tasks/callback?success=true'
        else:
            # Failed to exchange, return error
            deep_link = 'omi://google-tasks/callback?error=token_exchange_failed'
    except Exception as e:
        print(f'Error exchanging {app_key} code: {e}')
        deep_link = 'omi://google-tasks/callback?error=server_error'

    return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


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
    """
    OAuth callback endpoint for ClickUp integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    app_key = 'clickup'

    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    # Exchange code for tokens using backend credentials
    import requests

    client_id = os.getenv('CLICKUP_CLIENT_ID')
    client_secret = os.getenv('CLICKUP_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return render_oauth_response(request, app_key, success=False, error_type='config_error')

    try:
        # Exchange code for tokens
        client = get_http_client()
        token_response = await client.post(
            'https://api.clickup.com/api/v2/oauth/token',
            params={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')

            # Store token in Firebase
            if access_token and uid:
                try:
                    users_db.set_task_integration(
                        uid,
                        app_key,
                        {
                            'connected': True,
                            'access_token': access_token,
                        },
                    )
                    print(f'✓ Stored {app_key} token in Firebase for user {uid}')
                except Exception as e:
                    print(f'Error storing {app_key} token: {e}')

            # Create deep link for success (no token in URL)
            deep_link = f'omi://{app_key}/callback?success=true&requires_setup=true'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://{app_key}/callback?error=token_exchange_failed'
    except Exception as e:
        print(f'Error exchanging {app_key} code: {e}')
        deep_link = f'omi://{app_key}/callback?error=server_error'

    return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


@router.on_event("shutdown")
async def shutdown_http_client():
    """Cleanup HTTP client on app shutdown."""
    await close_http_client()
