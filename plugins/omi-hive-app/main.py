"""
Hive Integration App for Omi

This app provides Hive project management integration through API key authentication
and chat tools for managing projects, tasks, actions, and searching.
"""
import os
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    store_hive_credentials,
    get_hive_credentials,
    delete_hive_credentials,
    is_connected,
    store_default_project,
    get_default_project,
    get_user_settings,
)
from models import (
    ChatToolResponse,
    HiveProject,
    HiveTask,
    HiveAction,
)

load_dotenv()

# Hive API Configuration
HIVE_GRAPHQL_URL = "https://prod-gql.hive.com/graphql"
HIVE_REST_API_BASE = "https://app.hive.com/api/v1"

app = FastAPI(
    title="Hive Omi Integration",
    description="Hive project management integration for Omi - Manage projects, tasks, and actions",
    version="1.0.0"
)

# Mount static files and templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
if os.path.exists(templates_dir):
    static_dir = os.path.join(templates_dir, "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


# ============================================
# Hive GraphQL Client
# ============================================

def hive_graphql_request(
    api_key: str,
    query: str,
    variables: Optional[Dict] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Make a GraphQL request to Hive's API.
    
    Args:
        api_key: User's Hive API key
        query: GraphQL query string
        variables: Optional variables for the query
        timeout: Request timeout in seconds
    
    Returns:
        Dict with 'data' key on success, or 'errors' key on failure
    """
    headers = {
        "Content-Type": "application/json",
        "api_key": api_key,
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    print(f"🐝 Hive GraphQL Request:")
    print(f"   URL: {HIVE_GRAPHQL_URL}")
    print(f"   API Key (first 8 chars): {api_key[:8]}...")
    print(f"   Query: {query[:100]}...")
    
    try:
        response = requests.post(
            HIVE_GRAPHQL_URL,
            headers=headers,
            json=payload,
            timeout=timeout
        )
        
        print(f"🐝 Hive Response: Status {response.status_code}")
        print(f"   Body: {response.text[:500]}")
        
        if response.status_code != 200:
            return {"errors": [{"message": f"HTTP {response.status_code}: {response.text}"}]}
        
        result = response.json()
        return result
        
    except requests.Timeout:
        print(f"🐝 Hive Request Timeout")
        return {"errors": [{"message": "Request timed out. Please try again."}]}
    except requests.RequestException as e:
        print(f"🐝 Hive Request Error: {e}")
        return {"errors": [{"message": f"Request failed: {str(e)}"}]}
    except Exception as e:
        print(f"🐝 Hive Unexpected Error: {e}")
        return {"errors": [{"message": f"Unexpected error: {str(e)}"}]}


def get_graphql_error(result: Dict) -> Optional[str]:
    """Extract error message from GraphQL result."""
    if "errors" in result and result["errors"]:
        errors = result["errors"]
        if isinstance(errors, list) and len(errors) > 0:
            return errors[0].get("message", "Unknown GraphQL error")
    return None


def hive_rest_request(uid: str, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Make authenticated REST request for a user."""
    credentials = get_hive_credentials(uid)
    if not credentials:
        return {"errors": [{"message": "User not connected to Hive"}]}
    
    api_key = credentials.get("api_key")
    hive_user_id = credentials.get("hive_user_id")
    
    headers = {
        "api_key": api_key,
        "Content-Type": "application/json"
    }
    
    # Ensure endpoint doesn't start with /
    endpoint = endpoint.lstrip("/")
    url = f"{HIVE_REST_API_BASE}/{endpoint}"
    
    # Add user_id to params for all requests
    if params is None:
        params = {}
    
    # Only add user_id for GET requests (required for some endpoints like workspaces)
    # Avoid adding it for POST/PUT/DELETE as strict APIs might reject unknown query params
    if hive_user_id and method.upper() == "GET":
        params["user_id"] = hive_user_id
        
    print(f"🐝 Hive REST Request: {method} {url}")
    print(f"   Params: {params}")
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data,
            timeout=30
        )
        
        print(f"🐝 Hive REST Response: Status {response.status_code}")
        
        if response.status_code >= 400:
            return {"errors": [{"message": f"HTTP {response.status_code}: {response.text}"}]}
            
        try:
            return response.json()
        except Exception:
            return {"data": response.text}
            
    except Exception as e:
        print(f"🐝 Hive REST Exception: {e}")
        return {"errors": [{"message": str(e)}]}


def hive_api_request(uid: str, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
    """Make authenticated GraphQL request for a user."""
    credentials = get_hive_credentials(uid)
    if not credentials:
        return {"errors": [{"message": "User not connected to Hive"}]}
    
    api_key = credentials.get("api_key")
    if not api_key:
        return {"errors": [{"message": "No API key found"}]}
    
    return hive_graphql_request(api_key, query, variables)


# ============================================
# GraphQL Queries and Mutations
# ============================================

GET_USER_QUERY = """
query GetUser {
    user {
        _id
        email
    }
}
"""

GET_WORKSPACES_QUERY = """
query GetWorkspaces {
    userWorkspaces {
        workspace {
            _id
            name
        }
    }
}
"""

GET_PROJECTS_QUERY = """
query GetProjects($workspaceId: ID!) {
    projects(workspaceId: $workspaceId) {
        _id
        name
        description
    }
}
"""

GET_ACTIONS_QUERY = """
query GetActions($projectId: ID!, $limit: Int) {
    actions(projectId: $projectId, limit: $limit) {
        _id
        title
        description
        status
        assignees {
            _id
            email
        }
        deadline
    }
}
"""

CREATE_ACTION_MUTATION = """
mutation CreateAction($input: CreateActionInput!) {
    createAction(input: $input) {
        _id
        title
        description
        status
    }
}
"""

SEARCH_ACTIONS_QUERY = """
query SearchActions($query: String!, $limit: Int) {
    searchActions(query: $query, limit: $limit) {
        _id
        title
        description
        status
        project {
            _id
            name
        }
    }
}
"""


# ============================================
# Helper Functions
# ============================================

def verify_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Verify an API key by fetching user info and workspaces."""
    print(f"🐝 Verifying API key...")
    result = hive_graphql_request(api_key, GET_USER_QUERY)
    
    print(f"🐝 Verify result: {result}")
    
    error = get_graphql_error(result)
    if error:
        print(f"🐝 GraphQL Error: {error}")
        return None
    
    data = result.get("data", {}).get("user")
    print(f"🐝 User data: {data}")
    
    if not data:
        return None
    
    # Try to get workspace ID from user object first
    workspace_id = data.get("workspaceId")
    
    if not workspace_id:
        # Fallback to REST API to fetch workspaces
        print(f"🐝 Fetching workspaces via REST API...")
        try:
            # Hive REST API often needs api_key and sometimes user_id
            headers = {"api_key": api_key}
            user_id = data.get("_id")
            if user_id:
                headers["user_id"] = user_id
                
            print(f"   REST Headers: {headers}")
            response = requests.get(
                f"{HIVE_REST_API_BASE}/workspaces",
                headers=headers,
                timeout=10
            )
            print(f"   REST Response Status: {response.status_code}")
            print(f"   REST Response Body: {response.text[:200]}")
            
            if response.status_code == 200:
                workspaces = response.json()
                if workspaces and len(workspaces) > 0:
                    # The REST API returns a list of workspace objects
                    workspace_id = workspaces[0].get("_id") or workspaces[0].get("id")
                    print(f"🐝 Using workspace from REST: {workspaces[0].get('name')} ({workspace_id})")
        except Exception as e:
            print(f"🐝 REST API error: {e}")
    
    return {
        "user_id": data.get("_id"),
        "email": data.get("email"),
        "workspace_id": workspace_id,
    }


def get_user_workspaces(uid: str) -> List[Dict]:
    """Get user's workspaces via REST API."""
    credentials = get_hive_credentials(uid)
    if not credentials:
        return []
    
    api_key = credentials.get("api_key")
    hive_user_id = credentials.get("hive_user_id")
    
    try:
        headers = {"api_key": api_key}
        if hive_user_id:
            headers["user_id"] = hive_user_id
            
        response = requests.get(
            f"{HIVE_REST_API_BASE}/workspaces",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"🐝 REST API error in get_user_workspaces: {e}")
    
    return []


def get_user_projects(uid: str, workspace_id: Optional[str] = None) -> List[HiveProject]:
    """Get user's projects."""
    # If no workspace_id provided, get it from stored credentials
    if not workspace_id:
        credentials = get_hive_credentials(uid)
        if credentials:
            workspace_id = credentials.get("workspace_id")
    
    if not workspace_id:
        print("🐝 Warning: No workspace ID available")
        return []
    
    # Use REST API: /workspaces/{workspaceId}/projects
    result = hive_rest_request(uid, "GET", f"workspaces/{workspace_id}/projects")
    
    if "errors" in result:
        return []
    
    projects_data = result if isinstance(result, list) else result.get("data", [])
    # If it's a dict with 'projects' key (some API versions)
    if isinstance(result, dict) and "projects" in result:
        projects_data = result["projects"]
        
    projects = []
    for p in projects_data or []:
        if not isinstance(p, dict):
            continue
            
        projects.append(HiveProject(
            id=p.get("id") or p.get("_id", ""),
            name=p.get("name", ""),
            description=p.get("description"),
            status=p.get("status"),
            workspace_id=workspace_id
        ))
    return projects


def find_project_by_name(uid: str, name: str) -> Optional[HiveProject]:
    """Find a project by name (case-insensitive partial match)."""
    projects = get_user_projects(uid)
    name_lower = name.lower()
    
    # First try exact match
    for project in projects:
        if project.name.lower() == name_lower:
            return project
    
    # Then try partial match
    for project in projects:
        if name_lower in project.name.lower():
            return project
    
    return None


def get_project_tasks(uid: str, project_id: str, limit: int = 20) -> List[HiveTask]:
    """Get tasks (actions) for a project via REST API."""
    # Get workspace ID from credentials
    credentials = get_hive_credentials(uid)
    workspace_id = credentials.get("workspace_id") if credentials else None
    
    if not workspace_id:
        print("⚠️ No workspace_id found, cannot get tasks via REST API")
        return []
    
    # Use workspace-scoped endpoint: /workspaces/{workspaceId}/actions
    # Note: Param is 'projectId' not 'project' per docs
    result = hive_rest_request(uid, "GET", f"workspaces/{workspace_id}/actions", params={"projectId": project_id, "limit": limit})
    
    if "errors" in result:
        return []
    
    # REST API returns a list of actions directly or in a list
    actions_data = result if isinstance(result, list) else result.get("data", [])
    if not isinstance(actions_data, list):
        actions_data = [result] if result.get("_id") else []
        
    tasks = []
    for a in actions_data or []:
        # REST API fields might differ slightly, handle both
        assignees = []
        if a.get("assignees"):
            assignees = [ass.get("email", "") for ass in a.get("assignees", []) if isinstance(ass, dict)]
            
        tasks.append(HiveTask(
            id=a.get("_id") or a.get("id", ""),
            name=a.get("title") or a.get("name", ""),
            description=a.get("description"),
            status=a.get("status"),
            project_id=project_id,
            assignees=assignees,
        ))
    return tasks


def search_tasks(uid: str, query: str, limit: int = 10) -> List[HiveTask]:
    """Search for tasks across all projects via REST API."""
    # Get workspace ID
    credentials = get_hive_credentials(uid)
    workspace_id = credentials.get("workspace_id") if credentials else None
    
    if not workspace_id:
        return []

    # Fetch recent actions from workspace and filter locally
    # The API doesn't support text search in 'Get actions'
    result = hive_rest_request(uid, "GET", f"workspaces/{workspace_id}/actions", params={"limit": 50})
    
    if "errors" in result:
        return []
        
    actions_data = result if isinstance(result, list) else result.get("data", [])
    if not isinstance(actions_data, list):
        actions_data = [result] if result.get("_id") else []
    
    query_lower = query.lower()
    tasks = []
    count = 0
    
    for a in actions_data or []:
        if count >= limit:
            break
            
        title = a.get("title") or a.get("name", "")
        desc = a.get("description", "")
        
        # Simple case-insensitive match
        if query_lower in title.lower() or (desc and query_lower in desc.lower()):
            project = a.get("project")
            project_id = ""
            project_name = ""
            if isinstance(project, dict):
                project_id = project.get("_id") or project.get("id", "")
                project_name = project.get("name", "")
            elif isinstance(project, str):
                project_id = project
                
            tasks.append(HiveTask(
                id=a.get("_id") or a.get("id", ""),
                name=title,
                description=desc,
                status=a.get("status"),
                project_id=project_id,
                project_name=project_name,
            ))
            count += 1
            
    return tasks


# ============================================
# Setup Endpoints
# ============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, uid: Optional[str] = None):
    """Home page / App settings page."""
    if not uid:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "connected": False,
            "error": "Missing user ID"
        })
    
    credentials = get_hive_credentials(uid)
    connected = credentials is not None
    
    # Get user info if connected
    user_info = None
    projects = []
    default_project = None
    
    if connected:
        user_info = {
            "email": credentials.get("hive_email"),
            "name": credentials.get("hive_name"),
            "user_id": credentials.get("hive_user_id"),
        }
        projects = get_user_projects(uid)
        default_project = get_default_project(uid)
    
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "uid": uid,
        "connected": connected,
        "user_info": user_info,
        "projects": projects,
        "default_project": default_project,
    })


@app.post("/settings/api-key")
async def connect_api_key(
    uid: str = Query(...),
    api_key: str = Form(...)
):
    """Connect Hive account using API key."""
    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    
    # Verify the API key
    user_info = verify_api_key(api_key.strip())
    
    if not user_info:
        # Return to setup page with error
        return RedirectResponse(
            url=f"/?uid={uid}&error=Invalid+API+key.+Please+check+and+try+again.",
            status_code=303
        )
    
    # Store credentials
    store_hive_credentials(
        uid=uid,
        api_key=api_key.strip(),
        hive_user_id=user_info.get("user_id", ""),
        hive_email=user_info.get("email"),
        workspace_id=user_info.get("workspace_id"),
    )
    
    return RedirectResponse(url=f"/?uid={uid}", status_code=303)


@app.get("/setup/hive", tags=["setup"])
async def check_setup(uid: str):
    """Check if the user has completed Hive setup (used by Omi)."""
    connected = is_connected(uid)
    return {"is_setup_completed": connected}


@app.post("/settings/default-project")
async def set_default_project(uid: str, project_id: str, project_name: str):
    """Set the default project for a user."""
    store_default_project(uid, project_id, project_name)
    return {"success": True, "message": f"Default project set to: {project_name}"}


@app.get("/disconnect")
async def disconnect_hive(uid: str):
    """Disconnect Hive account."""
    delete_hive_credentials(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/hive_get_projects", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_hive_get_projects(request: Request):
    """
    Get user's Hive projects.
    Chat tool for Omi - retrieves the user's projects.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check connection
        if not is_connected(uid):
            return ChatToolResponse(error="Please connect your Hive account first in the app settings.")
        
        projects = get_user_projects(uid)
        
        if not projects:
            return ChatToolResponse(result="You don't have any projects yet.")
        
        # Format results
        results = []
        for i, project in enumerate(projects[:limit], 1):
            status = f" ({project.status})" if project.status else ""
            results.append(f"{i}. **{project.name}**{status}")
        
        return ChatToolResponse(result=f"📋 Your Hive projects:\n\n" + "\n".join(results))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get projects: {str(e)}")


@app.post("/tools/hive_get_tasks", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_hive_get_tasks(request: Request):
    """
    Get tasks from a Hive project.
    Chat tool for Omi - retrieves tasks for a project.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        project_name = body.get("project_name")
        project_id = body.get("project_id")
        limit = body.get("limit", 10)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check connection
        if not is_connected(uid):
            return ChatToolResponse(error="Please connect your Hive account first in the app settings.")
        
        # Find project
        target_project = None
        if project_id:
            target_project = HiveProject(id=project_id, name=project_name or "Unknown")
        elif project_name:
            target_project = find_project_by_name(uid, project_name)
            if not target_project:
                return ChatToolResponse(error=f"Could not find project: {project_name}")
        else:
            # Use default project
            default = get_default_project(uid)
            if default:
                target_project = HiveProject(id=default["id"], name=default["name"])
            else:
                return ChatToolResponse(error="Please specify a project name or set a default project in app settings.")
        
        tasks = get_project_tasks(uid, target_project.id, limit)
        
        if not tasks:
            return ChatToolResponse(result=f"No tasks found in **{target_project.name}**.")
        
        # Format results
        results = []
        for i, task in enumerate(tasks[:limit], 1):
            status = f" [{task.status}]" if task.status else ""
            results.append(f"{i}. **{task.name}**{status}")
        
        return ChatToolResponse(
            result=f"📝 Tasks in **{target_project.name}**:\n\n" + "\n".join(results)
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get tasks: {str(e)}")


@app.post("/tools/hive_create_task", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_hive_create_task(request: Request):
    """
    Create a new task (Action) in Hive.
    Chat tool for Omi - creates a task in a project.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        task_name = body.get("task_name", "")
        project_name = body.get("project_name")
        project_id = body.get("project_id")
        description = body.get("description", "")
        due_date = body.get("due_date")
        parent_task_name = body.get("parent_task_name")
        parent_task_id = body.get("parent_task_id")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not task_name:
            return ChatToolResponse(error="Task name is required")
        
        # Check connection
        if not is_connected(uid):
            return ChatToolResponse(error="Please connect your Hive account first in the app settings.")
        
        # Find project
        target_project = None
        if project_id:
            target_project = HiveProject(id=project_id, name=project_name or "Unknown")
        elif project_name:
            target_project = find_project_by_name(uid, project_name)
            if not target_project:
                return ChatToolResponse(error=f"Could not find project: {project_name}")
        else:
            # Use default project
            default = get_default_project(uid)
            if default:
                target_project = HiveProject(id=default["id"], name=default["name"])
            else:
                return ChatToolResponse(error="Please specify a project name or set a default project in app settings.")
        
        # Get workspace ID from credentials
        credentials = get_hive_credentials(uid)
        workspace_id = credentials.get("workspace_id") if credentials else None
        
        if not workspace_id:
            return ChatToolResponse(error="Workspace ID not found. Please reconnect your Hive account.")

        # Handle parent task (for sub-actions)
        parent_id = parent_task_id
        if not parent_id and parent_task_name:
            # Search for the parent task to get its ID
            # searching limited to the target project if possible, or global
            # For now global search_tasks is what we have
            found_tasks = search_tasks(uid, parent_task_name, limit=5)
            
            # Filter by project if possible to be more accurate
            project_tasks = [t for t in found_tasks if t.project_id == target_project.id]
            
            if project_tasks:
                parent_id = project_tasks[0].id
            elif found_tasks:
                # If not found in project, maybe user meant a task in another project? 
                # But subtasks usually belong to the same project context implicitly. 
                # We'll use the best match.
                parent_id = found_tasks[0].id
            else:
                return ChatToolResponse(error=f"Could not find parent task: {parent_task_name}")
        
        # Create the task via REST API - endpoint is /actions/create
        # Body params: workspace, title, projectId, description
        create_data = {
            "workspace": workspace_id,
            "title": task_name,
            "projectId": target_project.id,
        }
        if description:
            create_data["description"] = description
            
        if due_date:
            create_data["deadline"] = due_date

        if parent_id:
            create_data["parentId"] = parent_id
        
        result = hive_rest_request(uid, "POST", "actions/create", data=create_data)
        
        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown error")
            return ChatToolResponse(error=f"Failed to create task: {error_msg}")
        
        success_msg = f"✅ Created task **{task_name}** in project **{target_project.name}**!"
        if parent_id:
            success_msg = f"✅ Created sub-task **{task_name}** under parent **{parent_task_name or parent_id}** in project **{target_project.name}**!"

        return ChatToolResponse(result=success_msg)
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create task: {str(e)}")


@app.post("/tools/hive_search", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_hive_search(request: Request):
    """
    Search for tasks and projects in Hive.
    Chat tool for Omi - searches across Hive.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        query = body.get("query", "")
        limit = body.get("limit", 10)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not query:
            return ChatToolResponse(error="Search query is required")
        
        # Check connection
        if not is_connected(uid):
            return ChatToolResponse(error="Please connect your Hive account first in the app settings.")
        
        tasks = search_tasks(uid, query, limit)
        
        if not tasks:
            return ChatToolResponse(result=f"No results found for '{query}'")
        
        # Format results
        results = []
        for i, task in enumerate(tasks, 1):
            project_info = f" (in {task.project_name})" if task.project_name else ""
            status = f" [{task.status}]" if task.status else ""
            results.append(f"{i}. **{task.name}**{status}{project_info}")
        
        return ChatToolResponse(
            result=f"🔍 Found {len(tasks)} results for '{query}':\n\n" + "\n".join(results)
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Search failed: {str(e)}")


@app.post("/tools/hive_update_task_status", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_hive_update_task_status(request: Request):
    """
    Update the status of a task in Hive.
    Chat tool for Omi - updates task status.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        task_name = body.get("task_name")
        task_id = body.get("task_id")
        status = body.get("status", "")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not task_name and not task_id:
            return ChatToolResponse(error="Task name or ID is required")
        
        if not status:
            return ChatToolResponse(error="Status is required (e.g., 'completed', 'in progress')")
        
        # Check connection
        if not is_connected(uid):
            return ChatToolResponse(error="Please connect your Hive account first in the app settings.")
            
        # If no task_id, find task by name
        if not task_id and task_name:
            tasks = search_tasks(uid, task_name, limit=5)
            if not tasks:
                return ChatToolResponse(error=f"Could not find task: {task_name}")
            
            # Find closest match
            best_match = None
            task_name_lower = task_name.lower()
            for t in tasks:
                if t.name.lower() == task_name_lower:
                    best_match = t
                    break
            
            if not best_match:
                best_match = tasks[0] # Use first result as fallback
                
            task_id = best_match.id
            task_name = best_match.name

        # Map status common terms to Hive status
        # Hive usually uses 'completed' or 'todo'
        hive_status = status.lower()
        if "done" in hive_status or "complete" in hive_status or "finished" in hive_status:
            hive_status = "completed"
        elif "todo" in hive_status or "not started" in hive_status:
            hive_status = "todo"
        elif "progress" in hive_status:
            hive_status = "in progress"

        # Update via REST API
        # Hive usually uses PUT /actions/{id}
        result = hive_rest_request(uid, "PUT", f"actions/{task_id}", data={"status": hive_status})
        
        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown error")
            return ChatToolResponse(error=f"Failed to update task: {error_msg}")
            
        return ChatToolResponse(
            result=f"✅ Updated task **{task_name}** status to **{hive_status}**!"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to update task: {str(e)}")


# ============================================
# Omi Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    
    This endpoint returns the chat tools definitions that Omi will fetch
    when the app is created or updated in the Omi App Store.
    """
    return {
        "tools": [
            {
                "name": "hive_get_projects",
                "description": "Get the user's Hive projects. Use this when the user wants to see their projects or check what projects they have in Hive.",
                "endpoint": "/tools/hive_get_projects",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of projects to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your Hive projects..."
            },
            {
                "name": "hive_get_tasks",
                "description": "Get tasks from a Hive project. Use this when the user wants to see tasks, to-dos, or action items in a specific project.",
                "endpoint": "/tools/hive_get_tasks",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Name of the project to get tasks from"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of tasks to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting tasks from Hive..."
            },
            {
                "name": "hive_create_task",
                "description": "Create a new task in Hive. Use this when the user wants to create a task, add a to-do, or add an action item to a project. Can also create sub-tasks if a parent task is specified.",
                "endpoint": "/tools/hive_create_task",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "task_name": {
                            "type": "string",
                            "description": "Name/title of the task to create"
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Name of the project to add the task to (uses default if not specified)"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description or details for the task"
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date for the task (format: YYYY-MM-DD)"
                        },
                        "parent_task_name": {
                            "type": "string",
                            "description": "Name of the parent task if this should be a sub-task"
                        }
                    },
                    "required": ["task_name"]
                },
                "auth_required": True,
                "status_message": "Creating task in Hive..."
            },
            {
                "name": "hive_search",
                "description": "Search for tasks and projects in Hive. Use this when the user wants to find or search for something in Hive.",
                "endpoint": "/tools/hive_search",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - what to look for"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)"
                        }
                    },
                    "required": ["query"]
                },
                "auth_required": True,
                "status_message": "Searching Hive..."
            },
            {
                "name": "hive_update_task_status",
                "description": "Update the status of a task in Hive. Use this when the user wants to complete a task, mark it as in progress, or change its status.",
                "endpoint": "/tools/hive_update_task_status",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "task_name": {
                            "type": "string",
                            "description": "Name of the task to update"
                        },
                        "task_id": {
                            "type": "string",
                            "description": "ID of the task to update (if known)"
                        },
                        "status": {
                            "type": "string",
                            "description": "New status for the task (e.g., 'completed', 'in progress', 'todo')"
                        }
                    },
                    "required": ["status"]
                },
                "auth_required": True,
                "status_message": "Updating task status in Hive..."
            }
        ]
    }


# ============================================
# Health Check
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "hive-omi-integration"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)

