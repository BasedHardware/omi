from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

import database.users as users_db
from utils.other import endpoints as auth

router = APIRouter()


# Request/Response models
class TaskIntegrationData(BaseModel):
    """Data for a task integration connection"""

    # Common fields
    connected: bool = True

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
