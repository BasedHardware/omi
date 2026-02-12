"""
Linear Integration App for Omi

This app provides Linear integration through OAuth authentication
and chat tools for managing issues, projects, and workflows.
"""
import os
import base64
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (
    store_linear_tokens,
    get_linear_tokens,
    delete_linear_tokens,
    is_token_expired,
    store_default_team,
    get_default_team,
    get_user_settings,
)
from models import (
    ChatToolResponse,
    LinearIssue,
    LinearTeam,
    LinearProject,
    LinearComment,
    LinearUser,
    WorkflowState,
)

load_dotenv()

# Linear API Configuration
LINEAR_CLIENT_ID = os.getenv("LINEAR_CLIENT_ID", "")
LINEAR_CLIENT_SECRET = os.getenv("LINEAR_CLIENT_SECRET", "")
LINEAR_REDIRECT_URI = os.getenv("LINEAR_REDIRECT_URI", "http://localhost:8000/auth/linear/callback")

# Linear API endpoints
LINEAR_AUTH_URL = "https://linear.app/oauth/authorize"
LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_API_URL = "https://api.linear.app/graphql"

# Required Linear scopes
LINEAR_SCOPES = [
    "read",
    "write",
    "issues:create",
    "comments:create",
]

app = FastAPI(
    title="Linear Omi Integration",
    description="Linear integration for Omi - Manage issues, projects, and workflows with voice",
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
# Helper Functions
# ============================================

def get_auth_header(access_token: str) -> Dict[str, str]:
    """Get authorization header for Linear API requests."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh the Linear access token."""
    response = requests.post(
        LINEAR_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": LINEAR_CLIENT_ID,
            "client_secret": LINEAR_CLIENT_SECRET,
        },
    )
    
    if response.status_code == 200:
        return response.json()
    return None


def get_valid_access_token(uid: str) -> Optional[str]:
    """Get a valid access token, refreshing if necessary."""
    tokens = get_linear_tokens(uid)
    if not tokens:
        return None
    
    if is_token_expired(uid):
        # Refresh the token
        new_tokens = refresh_access_token(tokens["refresh_token"])
        if new_tokens:
            expires_at = int(datetime.utcnow().timestamp()) + new_tokens.get("expires_in", 315360000)
            store_linear_tokens(
                uid,
                new_tokens["access_token"],
                new_tokens.get("refresh_token", tokens["refresh_token"]),
                expires_at
            )
            return new_tokens["access_token"]
        return None
    
    return tokens["access_token"]


def linear_graphql_request(
    uid: str,
    query: str,
    variables: Optional[Dict] = None
) -> Dict[str, Any]:
    """Make an authenticated GraphQL request to Linear API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return {"error": "User not authenticated with Linear"}
    
    headers = get_auth_header(access_token)
    
    try:
        response = requests.post(
            LINEAR_API_URL,
            headers=headers,
            json={"query": query, "variables": variables or {}}
        )
        
        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            errors = error_data.get("errors", [])
            if errors:
                return {"error": errors[0].get("message", f"API error: {response.status_code}")}
            return {"error": f"API error: {response.status_code}"}
        
        result = response.json()
        if "errors" in result:
            return {"error": result["errors"][0].get("message", "GraphQL error")}
        
        return result.get("data", {})
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


def get_user_teams(uid: str) -> List[LinearTeam]:
    """Get teams the user belongs to."""
    query = """
    query {
        teams {
            nodes {
                id
                name
                key
                description
            }
        }
    }
    """
    result = linear_graphql_request(uid, query)
    
    if "error" in result:
        return []
    
    teams = []
    for team in result.get("teams", {}).get("nodes", []):
        teams.append(LinearTeam(
            id=team["id"],
            name=team["name"],
            key=team["key"],
            description=team.get("description") or ""
        ))
    return teams


def get_team_states(uid: str, team_id: str) -> List[WorkflowState]:
    """Get workflow states for a team."""
    query = """
    query($teamId: String!) {
        team(id: $teamId) {
            states {
                nodes {
                    id
                    name
                    type
                    color
                    position
                }
            }
        }
    }
    """
    result = linear_graphql_request(uid, query, {"teamId": team_id})
    
    if "error" in result:
        return []
    
    states = []
    for state in result.get("team", {}).get("states", {}).get("nodes", []):
        states.append(WorkflowState(
            id=state["id"],
            name=state["name"],
            type=state["type"],
            color=state.get("color", "#888"),
            position=state.get("position", 0)
        ))
    return sorted(states, key=lambda s: s.position)


def find_state_by_name(uid: str, team_id: str, state_name: str) -> Optional[WorkflowState]:
    """Find a workflow state by name (case-insensitive partial match)."""
    states = get_team_states(uid, team_id)
    state_name_lower = state_name.lower()
    
    # Map common names to Linear state types
    state_mapping = {
        "backlog": "backlog",
        "todo": "unstarted",
        "to do": "unstarted",
        "to-do": "unstarted",
        "in progress": "started",
        "in-progress": "started",
        "working": "started",
        "doing": "started",
        "done": "completed",
        "complete": "completed",
        "completed": "completed",
        "finished": "completed",
        "cancelled": "canceled",
        "canceled": "canceled",
    }
    
    # First try exact match
    for state in states:
        if state.name.lower() == state_name_lower:
            return state
    
    # Then try partial match
    for state in states:
        if state_name_lower in state.name.lower():
            return state
    
    # Then try type match
    mapped_type = state_mapping.get(state_name_lower)
    if mapped_type:
        for state in states:
            if state.type == mapped_type:
                return state
    
    return None


def get_user_profile(uid: str) -> Optional[LinearUser]:
    """Get the authenticated user's profile."""
    query = """
    query {
        viewer {
            id
            name
            email
            displayName
            avatarUrl
        }
    }
    """
    result = linear_graphql_request(uid, query)
    
    if "error" in result or not result.get("viewer"):
        return None
    
    viewer = result["viewer"]
    return LinearUser(
        id=viewer["id"],
        name=viewer["name"],
        email=viewer.get("email", ""),
        display_name=viewer.get("displayName", viewer["name"]),
        avatar_url=viewer.get("avatarUrl")
    )


# ============================================
# OAuth Endpoints
# ============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, uid: Optional[str] = None):
    """Home page / App settings page."""
    if not uid:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Missing user ID"
        })
    
    tokens = get_linear_tokens(uid)
    authenticated = tokens is not None
    
    # Get user profile if authenticated
    user_profile = None
    teams = []
    default_team = None
    
    if authenticated:
        user_profile = get_user_profile(uid)
        teams = get_user_teams(uid)
        default_team = get_default_team(uid)
    
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "uid": uid,
        "authenticated": authenticated,
        "user_profile": user_profile,
        "teams": teams,
        "default_team": default_team,
        "oauth_url": f"/auth/linear?uid={uid}"
    })


@app.get("/auth/linear")
async def linear_auth(uid: str):
    """Initiate Linear OAuth flow."""
    if not uid:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    params = {
        "client_id": LINEAR_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": LINEAR_REDIRECT_URI,
        "scope": ",".join(LINEAR_SCOPES),
        "state": uid,
        "prompt": "consent",
    }
    
    auth_url = f"{LINEAR_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/linear/callback", response_class=HTMLResponse)
async def linear_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Linear OAuth callback."""
    if error:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": f"Authorization failed: {error}"
        })
    
    if not code or not state:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Invalid callback parameters"
        })
    
    uid = state
    
    # Exchange code for tokens
    response = requests.post(
        LINEAR_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": LINEAR_REDIRECT_URI,
            "client_id": LINEAR_CLIENT_ID,
            "client_secret": LINEAR_CLIENT_SECRET,
        },
    )
    
    if response.status_code != 200:
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "authenticated": False,
            "error": "Failed to exchange authorization code"
        })
    
    token_data = response.json()
    # Linear tokens are long-lived (10 years), but we set a reasonable expiry
    expires_at = int(datetime.utcnow().timestamp()) + token_data.get("expires_in", 315360000)
    
    store_linear_tokens(
        uid,
        token_data["access_token"],
        token_data.get("refresh_token", ""),
        expires_at
    )
    
    # Redirect to home with uid
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/setup/linear", tags=["setup"])
async def check_setup(uid: str):
    """Check if the user has completed Linear setup (used by Omi)."""
    tokens = get_linear_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.post("/settings/default-team")
async def set_default_team(uid: str, team_id: str, team_name: str):
    """Set the default team for a user."""
    store_default_team(uid, team_id, team_name)
    return {"success": True, "message": f"Default team set to: {team_name}"}


@app.get("/disconnect")
async def disconnect_linear(uid: str):
    """Disconnect Linear account."""
    delete_linear_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/create_issue", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_issue(request: Request):
    """
    Create a new issue in Linear.
    Chat tool for Omi - creates issues with title, description, and priority.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        title = body.get("title", "")
        description = body.get("description", "")
        priority = body.get("priority")  # 0 = No priority, 1 = Urgent, 2 = High, 3 = Medium, 4 = Low
        team_id = body.get("team_id")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not title:
            return ChatToolResponse(error="Issue title is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Get team ID if not provided
        if not team_id:
            default = get_default_team(uid)
            if default:
                team_id = default["id"]
            else:
                # Use first team
                teams = get_user_teams(uid)
                if not teams:
                    return ChatToolResponse(error="No teams found in your Linear workspace.")
                team_id = teams[0].id
        
        # Map priority text to number
        priority_map = {
            "urgent": 1,
            "high": 2,
            "medium": 3,
            "normal": 3,
            "low": 4,
            "none": 0,
        }
        if isinstance(priority, str):
            priority = priority_map.get(priority.lower(), 0)
        
        # Create the issue
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                }
            }
        }
        """
        
        variables = {
            "input": {
                "teamId": team_id,
                "title": title,
            }
        }
        
        if description:
            variables["input"]["description"] = description
        if priority:
            variables["input"]["priority"] = priority
        
        result = linear_graphql_request(uid, mutation, variables)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to create issue: {result['error']}")
        
        issue_data = result.get("issueCreate", {})
        if not issue_data.get("success"):
            return ChatToolResponse(error="Failed to create issue")
        
        issue = issue_data.get("issue", {})
        identifier = issue.get("identifier", "")
        url = issue.get("url", "")
        state_name = issue.get("state", {}).get("name", "Unknown")
        
        return ChatToolResponse(
            result=f"✅ Created issue **{identifier}**: {title}\n\n"
                   f"Status: {state_name}\n"
                   f"🔗 {url}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create issue: {str(e)}")


@app.post("/tools/list_my_issues", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_my_issues(request: Request):
    """
    List issues assigned to the user.
    Chat tool for Omi - shows the user's assigned issues.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 10)
        status_filter = body.get("status")  # Optional: filter by status
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Build filter
        filter_clause = '{ assignee: { isMe: { eq: true } } }'
        if status_filter:
            status_lower = status_filter.lower()
            state_types = {
                "backlog": "backlog",
                "todo": "unstarted",
                "in progress": "started",
                "done": "completed",
                "cancelled": "canceled",
            }
            state_type = state_types.get(status_lower)
            if state_type:
                filter_clause = f'{{ assignee: {{ isMe: {{ eq: true }} }}, state: {{ type: {{ eq: "{state_type}" }} }} }}'
        
        query = f"""
        query {{
            issues(first: {limit}, filter: {filter_clause}, orderBy: updatedAt) {{
                nodes {{
                    id
                    identifier
                    title
                    priority
                    state {{
                        name
                        type
                    }}
                    url
                    updatedAt
                }}
            }}
        }}
        """
        
        result = linear_graphql_request(uid, query)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issues: {result['error']}")
        
        issues = result.get("issues", {}).get("nodes", [])
        
        if not issues:
            filter_msg = f" with status '{status_filter}'" if status_filter else ""
            return ChatToolResponse(result=f"📋 No issues assigned to you{filter_msg}.")
        
        # Format results with priority indicators
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for issue in issues:
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = issue.get("state", {}).get("name", "Unknown")
            results.append(
                f"{priority_icon} **{issue['identifier']}** - {issue['title']}\n"
                f"   └ Status: {state}"
            )
        
        return ChatToolResponse(
            result=f"📋 Your assigned issues:\n\n" + "\n\n".join(results)
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to list issues: {str(e)}")


@app.post("/tools/list_recent_issues", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_recent_issues(request: Request):
    """
    List recent issues in Linear workspace.
    Chat tool for Omi - shows recent issues regardless of assignee.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = body.get("limit", 5)
        team_key = body.get("team")  # Optional: filter by team key like "OMI", "ENG"
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Build query - get recent issues ordered by created date
        if team_key:
            query = f"""
            query {{
                issues(first: {limit}, orderBy: createdAt, filter: {{ team: {{ key: {{ eq: "{team_key.upper()}" }} }} }}) {{
                    nodes {{
                        id
                        identifier
                        title
                        priority
                        state {{
                            name
                        }}
                        assignee {{
                            name
                        }}
                        createdAt
                        url
                    }}
                }}
            }}
            """
        else:
            query = f"""
            query {{
                issues(first: {limit}, orderBy: createdAt) {{
                    nodes {{
                        id
                        identifier
                        title
                        priority
                        state {{
                            name
                        }}
                        assignee {{
                            name
                        }}
                        createdAt
                        url
                    }}
                }}
            }}
            """
        
        result = linear_graphql_request(uid, query)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issues: {result['error']}")
        
        issues = result.get("issues", {}).get("nodes", [])
        
        if not issues:
            return ChatToolResponse(result=f"📋 No recent issues found in Linear.")
        
        # Format results with priority indicators
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for issue in issues:
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = issue.get("state", {}).get("name", "Unknown")
            assignee = issue.get("assignee", {})
            assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
            results.append(
                f"{priority_icon} **{issue['identifier']}** - {issue['title']}\n"
                f"   └ {state} • {assignee_name}"
            )
        
        team_msg = f" in {team_key.upper()}" if team_key else ""
        return ChatToolResponse(
            result=f"📋 Latest {len(issues)} issues{team_msg} in Linear:\n\n" + "\n\n".join(results)
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to list issues: {str(e)}")


@app.post("/tools/update_issue_status", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_update_issue_status(request: Request):
    """
    Update the status of an issue.
    Chat tool for Omi - moves issues between workflow states.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        issue_identifier = body.get("issue_identifier", "")  # e.g., "ENG-123"
        new_status = body.get("new_status", "")  # e.g., "In Progress", "Done"
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not issue_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        if not new_status:
            return ChatToolResponse(error="New status is required (e.g., 'In Progress', 'Done')")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Search for the issue by identifier using searchIssues
        search_query = """
        query($term: String!) {
            searchIssues(term: $term, first: 1) {
                nodes {
                    id
                    identifier
                    title
                    team {
                        id
                    }
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, search_query, {
            "term": issue_identifier.upper()
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issues = result.get("searchIssues", {}).get("nodes", [])
        if not issues:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        issue = issues[0]
        team_id = issue["team"]["id"]
        issue_id = issue["id"]
        
        # Find the target state
        target_state = find_state_by_name(uid, team_id, new_status)
        if not target_state:
            states = get_team_states(uid, team_id)
            state_names = [s.name for s in states]
            return ChatToolResponse(
                error=f"Could not find status '{new_status}'. Available states: {', '.join(state_names)}"
            )
        
        # Update the issue
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    state {
                        name
                    }
                    url
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, mutation, {
            "id": issue_id,
            "input": {"stateId": target_state.id}
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to update issue: {result['error']}")
        
        update_data = result.get("issueUpdate", {})
        if not update_data.get("success"):
            return ChatToolResponse(error="Failed to update issue status")
        
        updated_issue = update_data.get("issue", {})
        new_state = updated_issue.get("state", {}).get("name", target_state.name)
        
        return ChatToolResponse(
            result=f"✅ Updated **{issue['identifier']}** to **{new_state}**\n\n"
                   f"{issue['title']}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to update issue: {str(e)}")


@app.post("/tools/search_issues", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_search_issues(request: Request):
    """
    Search for issues in Linear.
    Chat tool for Omi - searches issues by text query.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        query_text = body.get("query", "")
        limit = body.get("limit", 5)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not query_text:
            return ChatToolResponse(error="Search query is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        query = """
        query($term: String!, $first: Int!) {
            searchIssues(term: $term, first: $first) {
                nodes {
                    id
                    identifier
                    title
                    priority
                    state {
                        name
                    }
                    assignee {
                        name
                    }
                    url
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, query, {
            "term": query_text,
            "first": limit
        })
        
        if "error" in result:
            # Fall back to filter-based search
            filter_query = """
            query($filter: IssueFilter!, $first: Int!) {
                issues(filter: $filter, first: $first) {
                    nodes {
                        id
                        identifier
                        title
                        priority
                        state {
                            name
                        }
                        assignee {
                            name
                        }
                        url
                    }
                }
            }
            """
            result = linear_graphql_request(uid, filter_query, {
                "filter": {"title": {"containsIgnoreCase": query_text}},
                "first": limit
            })
            
            if "error" in result:
                return ChatToolResponse(error=f"Search failed: {result['error']}")
            
            issues = result.get("issues", {}).get("nodes", [])
        else:
            issues = result.get("searchIssues", {}).get("nodes", [])
        
        if not issues:
            return ChatToolResponse(result=f"🔍 No issues found for '{query_text}'")
        
        # Format results
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for i, issue in enumerate(issues, 1):
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = issue.get("state", {}).get("name", "Unknown")
            assignee = issue.get("assignee", {})
            assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
            results.append(
                f"{i}. {priority_icon} **{issue['identifier']}** - {issue['title']}\n"
                f"   └ {state} • Assigned to: {assignee_name}"
            )
        
        return ChatToolResponse(
            result=f"🔍 Found {len(issues)} issue(s) for '{query_text}':\n\n" + "\n\n".join(results)
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Search failed: {str(e)}")


@app.post("/tools/get_issue", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_issue(request: Request):
    """
    Get details of a specific issue.
    Chat tool for Omi - retrieves full issue details.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        issue_identifier = body.get("issue_identifier", "")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not issue_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        query = """
        query($term: String!) {
            searchIssues(term: $term, first: 1) {
                nodes {
                    id
                    identifier
                    title
                    description
                    priority
                    estimate
                    state {
                        name
                        type
                    }
                    assignee {
                        name
                    }
                    creator {
                        name
                    }
                    team {
                        name
                    }
                    project {
                        name
                    }
                    labels {
                        nodes {
                            name
                        }
                    }
                    url
                    createdAt
                    updatedAt
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, query, {
            "term": issue_identifier.upper()
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issue: {result['error']}")
        
        issues = result.get("searchIssues", {}).get("nodes", [])
        if not issues:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        issue = issues[0]
        
        # Format the issue details
        priority_map = {0: "No priority", 1: "🔴 Urgent", 2: "🟠 High", 3: "🟡 Medium", 4: "🔵 Low"}
        priority = priority_map.get(issue.get("priority", 0), "No priority")
        
        state = issue.get("state", {}).get("name", "Unknown")
        assignee = issue.get("assignee", {})
        assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
        creator = issue.get("creator", {})
        creator_name = creator.get("name", "Unknown") if creator else "Unknown"
        team = issue.get("team", {}).get("name", "")
        project = issue.get("project", {})
        project_name = project.get("name", "No project") if project else "No project"
        
        labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
        labels_str = ", ".join(labels) if labels else "None"
        
        description = issue.get("description", "")
        if description and len(description) > 300:
            description = description[:300] + "..."
        
        details = [
            f"📋 **{issue['identifier']}**: {issue['title']}",
            f"",
            f"**Status:** {state}",
            f"**Priority:** {priority}",
            f"**Assignee:** {assignee_name}",
            f"**Team:** {team}",
            f"**Project:** {project_name}",
            f"**Labels:** {labels_str}",
            f"**Created by:** {creator_name}",
        ]
        
        if issue.get("estimate"):
            details.append(f"**Estimate:** {issue['estimate']} points")
        
        if description:
            details.append(f"\n**Description:**\n{description}")
        
        details.append(f"\n🔗 {issue['url']}")
        
        return ChatToolResponse(result="\n".join(details))
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get issue: {str(e)}")


@app.post("/tools/add_comment", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_add_comment(request: Request):
    """
    Add a comment to an issue.
    Chat tool for Omi - adds comments to existing issues.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        issue_identifier = body.get("issue_identifier", "")
        comment_body = body.get("comment", "")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not issue_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        if not comment_body:
            return ChatToolResponse(error="Comment text is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # First, get the issue ID using search
        query = """
        query($term: String!) {
            searchIssues(term: $term, first: 1) {
                nodes {
                    id
                    identifier
                    title
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, query, {
            "term": issue_identifier.upper()
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issues = result.get("searchIssues", {}).get("nodes", [])
        if not issues:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        issue = issues[0]
        
        # Add the comment
        mutation = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment {
                    id
                    body
                    createdAt
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, mutation, {
            "input": {
                "issueId": issue["id"],
                "body": comment_body
            }
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to add comment: {result['error']}")
        
        comment_data = result.get("commentCreate", {})
        if not comment_data.get("success"):
            return ChatToolResponse(error="Failed to add comment")
        
        return ChatToolResponse(
            result=f"💬 Added comment to **{issue['identifier']}**:\n\n"
                   f"> {comment_body[:200]}{'...' if len(comment_body) > 200 else ''}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to add comment: {str(e)}")


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
                "name": "linear_create_issue",
                "description": "Create a new issue in Linear. Use this when the user wants to create a Linear task, ticket, issue, or bug report.",
                "endpoint": "/tools/create_issue",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the Linear issue"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the Linear issue"
                        },
                        "priority": {
                            "type": "string",
                            "description": "Priority level: 'urgent', 'high', 'medium', 'low', or 'none'"
                        }
                    },
                    "required": ["title"]
                },
                "auth_required": True,
                "status_message": "Creating Linear issue..."
            },
            {
                "name": "linear_list_my_issues",
                "description": "List Linear issues assigned to the user. Use this when the user wants to see their Linear tasks, tickets, or assigned work.",
                "endpoint": "/tools/list_my_issues",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of Linear issues to return (default: 10)"
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status: 'backlog', 'todo', 'in progress', 'done', 'cancelled'"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your Linear issues..."
            },
            {
                "name": "linear_list_recent_issues",
                "description": "List recent Linear issues in the workspace regardless of assignee. Use this when the user wants to see latest issues, recent tickets, or all new Linear issues.",
                "endpoint": "/tools/list_recent_issues",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of Linear issues to return (default: 5)"
                        },
                        "team": {
                            "type": "string",
                            "description": "Optional team key to filter by (e.g., 'OMI', 'ENG')"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting recent Linear issues..."
            },
            {
                "name": "linear_update_issue_status",
                "description": "Update the status of a Linear issue. Use this when the user wants to move a Linear task to a different status like 'In Progress' or 'Done'.",
                "endpoint": "/tools/update_issue_status",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_identifier": {
                            "type": "string",
                            "description": "Linear issue identifier (e.g., 'ENG-123', 'OMI-456')"
                        },
                        "new_status": {
                            "type": "string",
                            "description": "New status for the Linear issue (e.g., 'In Progress', 'Done', 'Backlog')"
                        }
                    },
                    "required": ["issue_identifier", "new_status"]
                },
                "auth_required": True,
                "status_message": "Updating Linear issue status..."
            },
            {
                "name": "linear_search_issues",
                "description": "Search for issues in Linear. Use this when the user wants to find specific Linear issues or tasks by keyword.",
                "endpoint": "/tools/search_issues",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - Linear issue title, description, or identifier"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 5)"
                        }
                    },
                    "required": ["query"]
                },
                "auth_required": True,
                "status_message": "Searching Linear..."
            },
            {
                "name": "linear_get_issue",
                "description": "Get detailed information about a specific Linear issue. Use this when the user asks about a particular Linear issue or wants to know its details.",
                "endpoint": "/tools/get_issue",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_identifier": {
                            "type": "string",
                            "description": "Linear issue identifier (e.g., 'ENG-123', 'OMI-456')"
                        }
                    },
                    "required": ["issue_identifier"]
                },
                "auth_required": True,
                "status_message": "Getting Linear issue details..."
            },
            {
                "name": "linear_add_comment",
                "description": "Add a comment to an existing Linear issue. Use this when the user wants to comment on, note, or add information to a Linear issue.",
                "endpoint": "/tools/add_comment",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_identifier": {
                            "type": "string",
                            "description": "Linear issue identifier (e.g., 'ENG-123', 'OMI-456')"
                        },
                        "comment": {
                            "type": "string",
                            "description": "Comment text to add to the Linear issue"
                        }
                    },
                    "required": ["issue_identifier", "comment"]
                },
                "auth_required": True,
                "status_message": "Adding comment to Linear issue..."
            }
        ]
    }


# ============================================
# Health Check
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "linear-omi-integration"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

