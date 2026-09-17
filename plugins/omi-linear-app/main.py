"""
Linear Integration App for Omi

This app provides Linear integration through OAuth authentication
and chat tools for managing issues, projects, and workflows.
"""
import os
import re
import base64
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


LINEAR_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9]+-\d+$')
UUID_PATTERN = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def sanitize_issue_identifier(raw: Any) -> Optional[str]:
    """Clean and sanitize a caller-supplied issue identifier.

    Handles dirty types (int, float, None), leading '#', full Linear URLs,
    and surrounding whitespace. Returns an uppercase identifier or UUID string,
    or None if input cannot be resolved to a valid identifier.
    """
    if raw is None or isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        val = str(int(raw) if isinstance(raw, float) and raw.is_integer() else raw).strip()
    elif isinstance(raw, str):
        val = raw.strip()
    else:
        return None

    if not val:
        return None

    # URL extraction (e.g. https://linear.app/team/issue/ENG-123/title-slug?comment=1)
    if "linear.app" in val.lower() or val.startswith(("http://", "https://")):
        try:
            parsed_path = urllib.parse.urlparse(val).path
        except Exception:
            return None
        url_match = re.search(r'/issue/([a-zA-Z0-9]+-\d+)', parsed_path, re.IGNORECASE)
        if url_match:
            return url_match.group(1).upper()
        parts = parsed_path.rstrip('/').split('/')
        for part in reversed(parts):
            p = part.strip()
            if LINEAR_IDENTIFIER_PATTERN.match(p) or UUID_PATTERN.match(p):
                return p.upper()
        return None

    # Strip composite leading prefixes like 'issue: #ENG-123'
    val = re.sub(r'^(?:#+\s*|issue:\s*)+', '', val, flags=re.IGNORECASE).strip()
    val_upper = val.upper()
    if LINEAR_IDENTIFIER_PATTERN.match(val_upper) or UUID_PATTERN.match(val_upper):
        return val_upper
    return None


def get_issue_by_identifier(uid: str, issue_identifier: Any) -> Dict[str, Any]:
    """Resolve an exact shorthand identifier, never a ranked search result."""
    clean_id = sanitize_issue_identifier(issue_identifier)
    if not clean_id:
        return {"issue": None}

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
    return linear_graphql_request(uid, query, {"id": clean_id})


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
    for team in ((result.get("teams") or {}).get("nodes") or []):
        if not isinstance(team, dict) or not team.get("id") or not team.get("key") or not team.get("name"):
            continue
        teams.append(LinearTeam(
            id=team["id"],
            name=team["name"],
            key=team["key"],
            description=team.get("description") or ""
        ))
    return teams


def resolve_team(
    uid: str, team_target: Optional[Any] = None
) -> Tuple[Optional[LinearTeam], List[LinearTeam], Optional[str]]:
    """Resolve a team by ID, key, or name with tiered disambiguation.

    Returns (resolved_team, candidate_teams, error_message).
    - If team_target is omitted or empty (including whitespace-only):
      - Uses default team if configured.
      - If no default team: if exactly one team exists, auto-selects it.
      - If multiple teams exist, returns (None, teams, error_message) to prompt the user
        instead of silently creating issues in whichever team happens to be first.
    - If team_target is provided:
      - Tier 1: Exact ID match (UUID).
      - Tier 2: Exact key or name match (cross-type overlap is checked for ambiguity).
      - Tier 3: Unambiguous substring/prefix match on name or key.
      - If multiple teams match at a tier, returns (None, matches, error_message) to refuse ambiguity.
    """
    teams = get_user_teams(uid)
    if not teams:
        return None, [], "No teams found in your Linear workspace."

    clean_target = str(team_target).strip() if team_target is not None else ""

    # Case 1: No team target provided
    if not clean_target:
        default = get_default_team(uid)
        if default:
            default_id = default.get("id")
            for t in teams:
                if t.id == default_id:
                    return t, [t], None

        if len(teams) == 1:
            return teams[0], teams, None

        team_list = ", ".join(f"'{t.name}' ({t.key})" for t in teams)
        return None, teams, f"Multiple teams found: {team_list}. Please specify which team to create the issue in."

    target_lower = clean_target.lower()

    # Tier 1: Exact ID match
    for t in teams:
        if t.id.lower() == target_lower:
            return t, [t], None

    # Tier 2: Exact match against Key and Name simultaneously (guards against cross-team key/name shadowing)
    key_matches = [t for t in teams if t.key.lower() == target_lower]
    name_matches = [t for t in teams if t.name.lower() == target_lower]
    exact_candidates = list({t.id: t for t in (key_matches + name_matches)}.values())

    if len(exact_candidates) == 1:
        return exact_candidates[0], exact_candidates, None
    if len(exact_candidates) > 1:
        team_list = ", ".join(f"'{t.name}' ({t.key})" for t in exact_candidates)
        return None, exact_candidates, f"'{clean_target}' matches multiple teams: {team_list}. Please specify the full team name."

    # Tier 3: Substring/prefix match on name or key
    partial_matches = [
        t for t in teams if target_lower in t.name.lower() or target_lower in t.key.lower()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0], partial_matches, None
    if len(partial_matches) > 1:
        team_list = ", ".join(f"'{t.name}' ({t.key})" for t in partial_matches)
        return None, partial_matches, f"'{clean_target}' is ambiguous between teams: {team_list}. Please specify the full team name."

    all_teams_str = ", ".join(f"'{t.name}' ({t.key})" for t in teams)
    return None, [], f"Could not find team '{clean_target}'. Available teams: {all_teams_str}"


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
    for state in (((result.get("team") or {}).get("states") or {}).get("nodes") or []):
        if not isinstance(state, dict) or not state.get("id") or not state.get("name") or not state.get("type"):
            continue
        states.append(WorkflowState(
            id=state["id"],
            name=state["name"],
            type=state["type"],
            color=state.get("color", "#888") or "#888",
            position=float(state.get("position", 0) or 0)
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
    clean_name = str(state_name).strip() if state_name is not None else ""
    if not clean_name:
        return None, []

    states = get_team_states(uid, team_id)
    state_name_lower = clean_name.lower()

    exact = [s for s in states if s.name.lower() == state_name_lower]
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

    partial = [s for s in states if state_name_lower in s.name.lower()]
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
    Chat tool for Omi - creates issues with title, description, priority, and optional state.
    """
    try:
        body = await request.json()
        uid = body.get("uid")
        title = body.get("title")
        description = body.get("description", "")
        priority = body.get("priority")  # 0 = No priority, 1 = Urgent, 2 = High, 3 = Medium, 4 = Low
        team_id = body.get("team_id") or body.get("team")
        status = body.get("status") or body.get("state")
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not title or not str(title).strip():
            return ChatToolResponse(error="Issue title is required and cannot be empty")
        title = str(title).strip()
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        # Resolve team with tiered matching and ambiguity defense
        team, candidates, err_msg = resolve_team(uid, team_id)
        if not team:
            return ChatToolResponse(error=err_msg or "Failed to resolve team.")
        
        # Map priority text or numeric to valid integer
        priority_map = {
            "urgent": 1,
            "high": 2,
            "medium": 3,
            "normal": 3,
            "low": 4,
            "none": 0,
        }
        if isinstance(priority, str):
            p_clean = priority.strip()
            if p_clean.isdigit():
                try:
                    priority = int(p_clean)
                    if priority < 0 or priority > 4:
                        priority = 0
                except (ValueError, OverflowError):
                    priority = 0
            else:
                priority = priority_map.get(p_clean.lower(), 0)
        elif isinstance(priority, (int, float)):
            try:
                priority = int(priority)
                if priority < 0 or priority > 4:
                    priority = 0
            except (ValueError, TypeError, OverflowError):
                priority = 0
        else:
            priority = 0
        
        # Optional workflow state resolution
        state_id = None
        if status:
            target_state, state_candidates = find_state_by_name(uid, team.id, str(status))
            if target_state:
                state_id = target_state.id
            elif state_candidates:
                names = ", ".join(f"'{s.name}'" for s in state_candidates)
                return ChatToolResponse(
                    error=f"Status '{status}' matches multiple workflow states: {names}. Please specify the full status name."
                )
            else:
                states = get_team_states(uid, team.id)
                names = ", ".join(f"'{s.name}'" for s in states)
                return ChatToolResponse(
                    error=f"Could not find status '{status}' for team '{team.name}'. Available states: {names}"
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
                "teamId": team.id,
                "title": title,
            }
        }
        
        if description:
            variables["input"]["description"] = description
        if priority:
            variables["input"]["priority"] = priority
        if state_id:
            variables["input"]["stateId"] = state_id
        
        result = linear_graphql_request(uid, mutation, variables)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to create issue: {result['error']}")
        
        issue_data = result.get("issueCreate", {})
        if not issue_data.get("success"):
            return ChatToolResponse(error="Failed to create issue")
        
        issue = issue_data.get("issue", {})
        identifier = issue.get("identifier", "")
        url = issue.get("url", "")
        state_name = (issue.get("state") or {}).get("name", "Unknown")
        
        return ChatToolResponse(
            result=f"✅ Created issue **{identifier}**: {title}\n\n"
                   f"Team: {team.name}\n"
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
        raw_identifier = body.get("issue_identifier")
        issue_identifier = sanitize_issue_identifier(raw_identifier)
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
        
        result = get_issue_by_identifier(uid, issue_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        team = issue.get("team")
        if not team or not isinstance(team, dict) or not team.get("id"):
            return ChatToolResponse(error=f"Could not determine team for issue '{issue_identifier}'.")
        team_id = team["id"]
        issue_id = issue.get("id")
        if not issue_id:
            return ChatToolResponse(error=f"Invalid issue data for '{issue_identifier}'.")
        
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
        new_state = (updated_issue.get("state") or {}).get("name", target_state.name)
        identifier = issue.get("identifier") or issue_identifier
        title = issue.get("title") or ""
        
        return ChatToolResponse(
            result=f"✅ Updated **{identifier}** to **{new_state}**\n\n"
                   f"{title}"
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
        raw_identifier = body.get("issue_identifier")
        issue_identifier = sanitize_issue_identifier(raw_identifier)
        
        if not uid:
            return ChatToolResponse(error="User ID is required")
        
        if not issue_identifier:
            return ChatToolResponse(error="Issue identifier is required (e.g., ENG-123)")
        
        # Check authentication
        if not get_linear_tokens(uid):
            return ChatToolResponse(error="Please connect your Linear account first in the app settings.")
        
        result = get_issue_by_identifier(uid, issue_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to get issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue:
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
        # Format the issue details
        priority_map = {0: "No priority", 1: "🔴 Urgent", 2: "🟠 High", 3: "🟡 Medium", 4: "🔵 Low"}
        priority = priority_map.get(issue.get("priority", 0), "No priority")
        
        state = (issue.get("state") or {}).get("name", "Unknown")
        assignee = issue.get("assignee")
        assignee_name = assignee.get("name", "Unassigned") if isinstance(assignee, dict) and assignee.get("name") else "Unassigned"
        creator = issue.get("creator")
        creator_name = creator.get("name", "Unknown") if isinstance(creator, dict) and creator.get("name") else "Unknown"
        team = (issue.get("team") or {}).get("name", "")
        project = issue.get("project")
        project_name = project.get("name", "No project") if isinstance(project, dict) and project.get("name") else "No project"
        
        labels = [
            l.get("name")
            for l in (issue.get("labels") or {}).get("nodes", [])
            if isinstance(l, dict) and l.get("name")
        ]
        labels_str = ", ".join(labels) if labels else "None"
        
        description = issue.get("description", "")
        if description and len(description) > 300:
            description = description[:300] + "..."
        
        identifier = issue.get("identifier") or issue_identifier
        title = issue.get("title") or "Untitled"
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
        
        url = issue.get("url")
        if url:
            details.append(f"\n🔗 {url}")
        
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
        raw_identifier = body.get("issue_identifier")
        issue_identifier = sanitize_issue_identifier(raw_identifier)
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
        
        result = get_issue_by_identifier(uid, issue_identifier)
        
        if "error" in result:
            return ChatToolResponse(error=f"Failed to find issue: {result['error']}")
        
        issue = result.get("issue")
        if not issue or not isinstance(issue, dict) or not issue.get("id"):
            return ChatToolResponse(error=f"Could not find issue: {issue_identifier}")
        
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
        
        identifier = issue.get("identifier") or issue_identifier
        return ChatToolResponse(
            result=f"💬 Added comment to **{identifier}**:\n\n"
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
                            "description": "Optional team name, key (e.g. 'ENG'), or ID to create the issue under"
                        },
                        "status": {
                            "type": "string",
                            "description": "Optional workflow status/state name (e.g. 'Todo', 'In Progress')"
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

