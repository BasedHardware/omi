"""
Linear Integration App for Omi

This app provides Linear integration through OAuth authentication
and chat tools for managing issues, projects, and workflows.
"""
import os
import base64
import re
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

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
        errors = result.get("errors")
        if errors:
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                return {"error": errors[0].get("message", "GraphQL error")}
            return {"error": "GraphQL error"}
        
        return result.get("data", {})
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}


_LINEAR_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")


def sanitize_issue_identifier(raw: Any) -> Optional[str]:
    """Normalize a Linear identifier without treating caller text as GraphQL.

    Voice callers commonly say ``issue: #ENG-123`` or paste a Linear issue
    URL.  Only the identifier portion is accepted; arbitrary objects, blank
    values, slugs, and malformed strings are rejected before any API call.
    """
    if not isinstance(raw, str):
        return None

    value = raw.strip()
    if not value:
        return None

    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and parsed.netloc:
        parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
        try:
            issue_index = next(i for i, part in enumerate(parts) if part.casefold() == "issue")
            value = parts[issue_index + 1]
        except (StopIteration, IndexError):
            return None

    value = urllib.parse.unquote(value).strip()
    # Voice transcription may wrap an identifier in opening punctuation, but
    # a team key literally named ISSUE must not be mistaken for the word
    # "issue" and have its first segment stripped.
    value = value.lstrip("([{<").strip()
    value = re.sub(r"^(?:linear\s+)?issue(?:\s*[:#]\s*|\s+)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^#\s*", "", value)
    value = value.rstrip(".,;:)]}>").strip()
    if not _LINEAR_IDENTIFIER_RE.fullmatch(value):
        return None
    return value.upper()


def get_issue_by_identifier(uid: str, issue_identifier: str) -> Dict[str, Any]:
    """Resolve an exact shorthand identifier, never a ranked search result."""
    identifier = sanitize_issue_identifier(issue_identifier)
    if identifier is None:
        return {"error": "Invalid Linear issue identifier"}

    query = """
    query($id: String!) {
        issue(id: $id) {
            id
            identifier
            title
            description
            priority
            estimate
            state { name type }
            assignee { name }
            creator { name }
            team { id name }
            project { name }
            labels { nodes { name } }
            url
            createdAt
            updatedAt
        }
    }
    """
    return linear_graphql_request(uid, query, {"id": identifier})


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
    
    teams_data = result.get("teams") or {}
    nodes = teams_data.get("nodes") if isinstance(teams_data, dict) else []
    teams = []
    for team in nodes if isinstance(nodes, list) else []:
        if not isinstance(team, dict):
            continue
        team_id = team.get("id")
        team_name = team.get("name")
        team_key = team.get("key")
        if not all(isinstance(value, str) and value.strip() for value in (team_id, team_name, team_key)):
            continue
        teams.append(LinearTeam(
            id=team_id,
            name=team_name,
            key=team_key,
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
    
    team_data = result.get("team") or {}
    states_data = team_data.get("states") if isinstance(team_data, dict) else {}
    nodes = states_data.get("nodes") if isinstance(states_data, dict) else []
    states = []
    for state in nodes if isinstance(nodes, list) else []:
        if not isinstance(state, dict):
            continue
        state_id = state.get("id")
        state_name = state.get("name")
        state_type = state.get("type")
        if not all(isinstance(value, str) and value.strip() for value in (state_id, state_name, state_type)):
            continue
        color = state.get("color")
        position = state.get("position")
        states.append(WorkflowState(
            id=state_id,
            name=state_name,
            type=state_type,
            color=color if isinstance(color, str) and color else "#888",
            position=position if isinstance(position, (int, float)) else 0
        ))
    return sorted(states, key=lambda s: s.position)


STATE_TYPE_ALIASES = {
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


def _unique_teams(teams: List[LinearTeam]) -> List[LinearTeam]:
    """Deduplicate team candidates while preserving Linear's order."""
    unique: List[LinearTeam] = []
    seen = set()
    for team in teams:
        if team.id not in seen:
            seen.add(team.id)
            unique.append(team)
    return unique


def resolve_team(uid: str, team_target: Any = None) -> Tuple[Optional[LinearTeam], List[LinearTeam]]:
    """Resolve a team without silently choosing the first workspace team.

    Resolution tiers are intentionally ordered: UUID, exact key/name, then
    substring key/name.  Any tier producing multiple candidates is returned
    as an ambiguity so callers can ask the user instead of mutating the wrong
    team.  With no target, a saved default is honored; otherwise one team is
    safe and multiple teams require an explicit target.
    """
    teams = get_user_teams(uid)
    if not teams:
        return None, []

    if team_target is None or (isinstance(team_target, str) and not team_target.strip()):
        default = get_default_team(uid)
        if isinstance(default, dict):
            default_id = default.get("id")
            if isinstance(default_id, str) and default_id.strip():
                matches = _unique_teams([team for team in teams if team.id.casefold() == default_id.strip().casefold()])
                if len(matches) == 1:
                    return matches[0], matches
        if len(teams) == 1:
            return teams[0], [teams[0]]
        return None, _unique_teams(teams)

    if not isinstance(team_target, str):
        return None, []
    target = team_target.strip()
    if not target:
        return resolve_team(uid, None)
    target_folded = target.casefold()

    uuid_matches = _unique_teams([team for team in teams if team.id.casefold() == target_folded])
    if uuid_matches:
        return (uuid_matches[0], uuid_matches) if len(uuid_matches) == 1 else (None, uuid_matches)

    exact_matches = _unique_teams([
        team for team in teams
        if team.key.casefold() == target_folded or team.name.casefold() == target_folded
    ])
    if exact_matches:
        return (exact_matches[0], exact_matches) if len(exact_matches) == 1 else (None, exact_matches)

    partial_matches = _unique_teams([
        team for team in teams
        if target_folded in team.key.casefold() or target_folded in team.name.casefold()
    ])
    if len(partial_matches) == 1:
        return partial_matches[0], partial_matches
    return None, partial_matches


def find_state_by_name(uid: str, team_id: str, state_name: str) -> Tuple[Optional[WorkflowState], List[WorkflowState]]:
    """Find a workflow state by name.

    Returns (state, candidates). A single unambiguous match at any tier
    (exact name, workflow type alias, partial name) wins. Multiple matches
    at a tier are ambiguous: candidates lists them for the caller and the
    weaker tiers below are not tried, so an issue is never silently moved
    to whichever state a team happens to have listed first. A Linear team
    can have more than one state of the same type (two "started" columns,
    for example), so the type alias tier needs the same check the name
    tiers already needed.
    """
    if not isinstance(state_name, str) or not state_name.strip():
        return None, []

    states = get_team_states(uid, team_id)
    state_name_lower = state_name.strip().casefold()

    exact = [s for s in states if isinstance(s.name, str) and s.name.casefold() == state_name_lower]
    if len(exact) == 1:
        return exact[0], exact
    if len(exact) > 1:
        return None, exact

    mapped_type = STATE_TYPE_ALIASES.get(state_name_lower)
    if mapped_type:
        typed = [s for s in states if s.type == mapped_type]
        if len(typed) == 1:
            return typed[0], typed
        if len(typed) > 1:
            return None, typed

    partial = [s for s in states if isinstance(s.name, str) and state_name_lower in s.name.casefold()]
    if len(partial) == 1:
        return partial[0], partial
    return None, partial


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
        team_target = body.get("team") or body.get("team_id")
        status_target = body.get("status") if "status" in body else body.get("state")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not isinstance(title, str) or not title.strip():
            return ChatToolResponse(error="Issue title is required")
        if not isinstance(description, str):
            description = ""
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        team, team_candidates = resolve_team(uid, team_target)
        if not team:
            if not team_candidates:
                return ChatToolResponse(error="No teams found in your Linear workspace.")
            target_label = str(team_target).strip() if team_target is not None else ""
            if target_label:
                return ChatToolResponse(
                    error=f"Team '{target_label}' is ambiguous or was not found. "
                          f"Choose one of: {_format_team_candidates(team_candidates)}"
                )
            return ChatToolResponse(
                error=f"Multiple Linear teams found; specify a team key, name, or UUID: "
                      f"{_format_team_candidates(team_candidates)}"
            )
        team_id = team.id

        priority = coerce_priority(priority)
        target_state = None
        if status_target is not None:
            if not isinstance(status_target, str) or not status_target.strip():
                return ChatToolResponse(error="Status must be a non-empty workflow state name.")
            target_state, state_candidates = find_state_by_name(uid, team_id, status_target)
            if not target_state:
                if state_candidates:
                    return ChatToolResponse(
                        error=f"Status '{status_target}' is ambiguous; choose one of "
                              f"{_format_state_candidates(state_candidates)}."
                    )
                available_states = get_team_states(uid, team_id)
                available = _format_state_candidates(available_states) or "none"
                return ChatToolResponse(
                    error=f"Could not find status '{status_target}' for {team.name}. Available states: {available}"
                )
        
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
        if target_state:
            variables["input"]["stateId"] = target_state.id
        
        result = linear_graphql_request(uid, mutation, variables)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to create issue: {result['error']}")
        
        issue_data = result.get("issueCreate", {})
        if not issue_data.get("success"):
            return ChatToolResponse(error="Failed to create issue")
        
        issue = issue_data.get("issue", {})
        identifier = issue.get("identifier", "")
        url = issue.get("url", "")
        state_name = _nested_name(issue.get("state"), "Unknown")
        
        return ChatToolResponse(
            result=f"✅ Created issue **{identifier}**: {title}\n\n"
                   f"Status: {state_name}\n"
                   f"🔗 {url}"
        )
    
    except Exception as e:
        return ChatToolResponse(error=f"Failed to create issue: {str(e)}")


def coerce_limit(value: Any, default: int = 10, min_val: int = 1, max_val: int = 50) -> int:
    """Coerce a caller-supplied limit to an int clamped between min_val and max_val.

    Chat tool parameters arrive as loosely-typed JSON (null when the backend
    omits an optional parameter, or strings like "10" from LLM callers), so
    anything that is not numeric falls back to default.
    """
    if value is None:
        return default
    try:
        val = int(value)
    except (ValueError, TypeError, OverflowError):
        return default
    if val < min_val:
        return min_val
    if val > max_val:
        return max_val
    return val


def coerce_priority(value: Any) -> int:
    """Normalize Linear priority names and numeric JSON/string values."""
    priority_map = {
        "urgent": 1,
        "high": 2,
        "medium": 3,
        "normal": 3,
        "low": 4,
        "none": 0,
    }
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().casefold()
        if cleaned in priority_map:
            return priority_map[cleaned]
        if cleaned.isdigit():
            value = int(cleaned)
        else:
            return 0
    if isinstance(value, int) and 0 <= value <= 4:
        return value
    return 0


def _format_team_candidates(candidates: List[LinearTeam]) -> str:
    """Format safe team choices for an ambiguity response."""
    return ", ".join(f"{team.name} ({team.key})" for team in candidates)


def _format_state_candidates(candidates: List[WorkflowState]) -> str:
    return ", ".join(f"'{state.name}'" for state in candidates)


def _nested_name(value: Any, default: str) -> str:
    """Read an optional GraphQL object's name without assuming its shape."""
    if not isinstance(value, dict):
        return default
    name = value.get("name")
    return name if isinstance(name, str) and name else default


def _nodes_from(result: Any, key: str) -> List[Dict[str, Any]]:
    """Return only object nodes from a nullable GraphQL connection."""
    if not isinstance(result, dict):
        return []
    container = result.get(key) or {}
    if not isinstance(container, dict):
        return []
    nodes = container.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


@app.post("/tools/list_my_issues", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_my_issues(request: Request):
    """
    List issues assigned to the user.
    Chat tool for Omi - shows the user's assigned issues.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        limit = coerce_limit(body.get("limit"), default=10, min_val=1, max_val=50)
        status_filter = body.get("status")  # Optional: filter by status
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Build filter as a structured variables object, never interpolated text
        filter_obj: Dict[str, Any] = {"assignee": {"isMe": {"eq": True}}}
        if status_filter:
            status_lower = str(status_filter).lower()
            state_types = {
                "backlog": "backlog",
                "todo": "unstarted",
                "in progress": "started",
                "done": "completed",
                "cancelled": "canceled",
            }
            state_type = state_types.get(status_lower)
            if state_type:
                filter_obj["state"] = {"type": {"eq": state_type}}
        
        query = """
        query($first: Int!, $filter: IssueFilter) {
            issues(first: $first, filter: $filter, orderBy: updatedAt) {
                nodes {
                    id
                    identifier
                    title
                    priority
                    state {
                        name
                        type
                    }
                    url
                    updatedAt
                }
            }
        }
        """
        
        result = linear_graphql_request(uid, query, {"first": limit, "filter": filter_obj})
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issues: {result['error']}")
        
        issues = _nodes_from(result, "issues")
        
        if not issues:
            filter_msg = f" with status '{status_filter}'" if status_filter else ""
            return ChatToolResponse(result=f"📋 No issues assigned to you{filter_msg}.")
        
        # Format results with priority indicators
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for issue in issues:
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = _nested_name(issue.get("state"), "Unknown")
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
        limit = coerce_limit(body.get("limit"), default=5, min_val=1, max_val=50)
        team_key = body.get("team")  # Optional: filter by team key like "OMI", "ENG"
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Build query - get recent issues ordered by created date.
        # The team key travels as a structured filter variable, never as
        # interpolated GraphQL text, so quotes/braces stay inert data.
        clean_team = team_key.strip().upper() if isinstance(team_key, str) and team_key.strip() else None
        if clean_team:
            query = """
            query($first: Int!, $filter: IssueFilter) {
                issues(first: $first, orderBy: createdAt, filter: $filter) {
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
                        createdAt
                        url
                    }
                }
            }
            """
            variables = {"first": limit, "filter": {"team": {"key": {"eq": clean_team}}}}
        else:
            query = """
            query($first: Int!) {
                issues(first: $first, orderBy: createdAt) {
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
                        createdAt
                        url
                    }
                }
            }
            """
            variables = {"first": limit}
        
        result = linear_graphql_request(uid, query, variables)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issues: {result['error']}")
        
        issues = _nodes_from(result, "issues")
        
        if not issues:
            return ChatToolResponse(result=f"📋 No recent issues found in Linear.")
        
        # Format results with priority indicators
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for issue in issues:
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = _nested_name(issue.get("state"), "Unknown")
            assignee_name = _nested_name(issue.get("assignee"), "Unassigned")
            results.append(
                f"{priority_icon} **{issue['identifier']}** - {issue['title']}\n"
                f"   └ {state} • {assignee_name}"
            )
        
        team_msg = f" in {clean_team}" if clean_team else ""
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
        
        normalized_identifier = sanitize_issue_identifier(issue_identifier)
        if not normalized_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        if not isinstance(new_status, str) or not new_status.strip():
            return ChatToolResponse(error="New status is required (e.g., 'In Progress', 'Done')")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        result = get_issue_by_identifier(uid, normalized_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        team = issue.get("team") or {}
        team_id = team.get("id") if isinstance(team, dict) else None
        if not isinstance(team_id, str) or not team_id:
            return ChatToolResponse(error=f"Issue {issue.get('identifier', issue_identifier)} has no team; status cannot be updated.")
        issue_id = issue.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            return ChatToolResponse(error=f"Issue {issue.get('identifier', issue_identifier)} has no Linear ID; status cannot be updated.")
        
        # Find the target state
        target_state, candidates = find_state_by_name(uid, team_id, new_status)
        if not target_state:
            if candidates:
                names = ", ".join(f"'{s.name}'" for s in candidates)
                return ChatToolResponse(
                    error=f"'{new_status}' matches more than one status: {names}. Say the full status name."
                )
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
        new_state = _nested_name(updated_issue.get("state"), target_state.name)
        
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
            
            issues = _nodes_from(result, "issues")
        else:
            issues = _nodes_from(result, "searchIssues")
        
        if not issues:
            return ChatToolResponse(result=f"🔍 No issues found for '{query_text}'")
        
        # Format results
        priority_icons = {0: "⚪", 1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}
        results = []
        for i, issue in enumerate(issues, 1):
            priority_icon = priority_icons.get(issue.get("priority", 0), "⚪")
            state = _nested_name(issue.get("state"), "Unknown")
            assignee_name = _nested_name(issue.get("assignee"), "Unassigned")
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
        
        normalized_identifier = sanitize_issue_identifier(issue_identifier)
        if not normalized_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        result = get_issue_by_identifier(uid, normalized_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        # Format the issue details
        priority_map = {0: "No priority", 1: "🔴 Urgent", 2: "🟠 High", 3: "🟡 Medium", 4: "🔵 Low"}
        priority = priority_map.get(issue.get("priority", 0), "No priority")
        
        state = _nested_name(issue.get("state"), "Unknown")
        assignee_name = _nested_name(issue.get("assignee"), "Unassigned")
        creator_name = _nested_name(issue.get("creator"), "Unknown")
        team_data = issue.get("team") or {}
        team = team_data.get("name", "") if isinstance(team_data, dict) else ""
        project_name = _nested_name(issue.get("project"), "No project")

        labels_data = issue.get("labels") or {}
        label_nodes = labels_data.get("nodes") if isinstance(labels_data, dict) else []
        label_nodes = label_nodes if isinstance(label_nodes, list) else []
        labels = [label["name"] for label in label_nodes if isinstance(label, dict) and label.get("name")]
        labels_str = ", ".join(labels) if labels else "None"
        
        description = issue.get("description", "")
        if description and len(description) > 300:
            description = description[:300] + "..."
        
        identifier = issue.get("identifier", normalized_identifier)
        title = issue.get("title", "Untitled issue")
        details = [
            f"📋 **{identifier}**: {title}",
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
        
        if issue.get("url"):
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
        
        normalized_identifier = sanitize_issue_identifier(issue_identifier)
        if not normalized_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        if not isinstance(comment_body, str) or not comment_body.strip():
            return ChatToolResponse(error="Comment text is required")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        result = get_issue_by_identifier(uid, normalized_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        issue_id = issue.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            return ChatToolResponse(error=f"Issue {issue.get('identifier', normalized_identifier)} has no Linear ID; comment cannot be added.")
        
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
                "issueId": issue_id,
                "body": comment_body
            }
        })
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to add comment: {result['error']}")
        
        comment_data = result.get("commentCreate", {})
        if not comment_data.get("success"):
            return ChatToolResponse(error="Failed to add comment")
        
        return ChatToolResponse(
            result=f"💬 Added comment to **{issue.get('identifier', normalized_identifier)}**:\n\n"
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
                        },
                        "team": {
                            "type": "string",
                            "description": "Optional team key, name, or Linear team UUID. Required when multiple teams exist without a saved default."
                        },
                        "status": {
                            "type": "string",
                            "description": "Optional workflow state name or alias (for example, 'In Progress' or 'Done'); 'state' is accepted as an alias."
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

