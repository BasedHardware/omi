from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os

import database.users as users_db
from utils.other import endpoints as auth

router = APIRouter()


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
    """
    base_url = os.getenv('BASE_API_URL')
    if not base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

    if app_key == 'todoist':
        client_id = os.getenv('TODOIST_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Todoist not configured")

        redirect_uri = f'{base_url}v2/integrations/todoist/callback'
        auth_url = f'https://todoist.com/oauth/authorize?client_id={client_id}&scope=data:read_write&state={uid}&redirect_uri={redirect_uri}'

    elif app_key == 'asana':
        client_id = os.getenv('ASANA_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Asana not configured")

        redirect_uri = f'{base_url}v2/integrations/asana/callback'
        scopes = 'tasks:read tasks:write workspaces:read projects:read users:read'
        from urllib.parse import quote

        auth_url = f'https://app.asana.com/-/oauth_authorize?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&state={uid}&scope={quote(scopes)}'

    elif app_key == 'google_tasks':
        client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="Google Tasks not configured")

        redirect_uri = f'{base_url}v2/integrations/google-tasks/callback'
        scope = 'https://www.googleapis.com/auth/tasks'
        from urllib.parse import quote

        auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&scope={quote(scope)}&access_type=offline&prompt=consent&state={uid}'

    elif app_key == 'clickup':
        client_id = os.getenv('CLICKUP_CLIENT_ID')
        if not client_id:
            raise HTTPException(status_code=500, detail="ClickUp not configured")

        redirect_uri = f'{base_url}v2/integrations/clickup/callback'
        from urllib.parse import quote

        auth_url = f'https://app.clickup.com/api?client_id={client_id}&redirect_uri={quote(redirect_uri)}&state={uid}'

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
    import requests
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

            response = requests.post(
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

            response = requests.post(
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

            response = requests.post(
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

            response = requests.post(
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
