"""Omi tools manifest — slice C owns this file.

Mirrors plugins/omi-linear-app/main.py:1135 shape. The Nooto backend fetches
this URL during app registration to learn each tool's name, parameters, and
status_message.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest() -> dict:
    """Omi Chat Tools Manifest.

    Returned to the Nooto backend at app registration time. Lists all 7
    Jira chat tools with their HTTP endpoint, parameter schema, and the
    user-facing `status_message` shown while the tool runs.
    """
    return {
        "tools": [
            {
                "name": "jira_create_issue",
                "description": (
                    "Create a new issue in Jira. Use this when the user wants to create a "
                    "Jira task, ticket, story, or bug."
                ),
                "endpoint": "/tools/create_issue",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Short summary / title of the Jira issue",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the Jira issue (optional)",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Jira project key (e.g. 'ENG', 'OPS'). Optional if a default project is configured.",
                        },
                        "issue_type": {
                            "type": "string",
                            "description": "Issue type: 'Task', 'Bug', 'Story', or 'Epic'. Defaults to 'Task'.",
                        },
                        "priority": {
                            "type": "string",
                            "description": "Priority: 'Highest', 'High', 'Medium', 'Low', 'Lowest' (optional).",
                        },
                    },
                    "required": ["summary"],
                },
                "auth_required": True,
                "write": True,
                "status_message": "Creating Jira issue...",
            },
            {
                "name": "jira_list_my_issues",
                "description": (
                    "List Jira issues assigned to the user. Use this when the user wants to see "
                    "their Jira tasks, tickets, or assigned work."
                ),
                "endpoint": "/tools/list_my_issues",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by Jira status name (e.g. 'To Do', 'In Progress', 'Done'). Optional.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of Jira issues to return (default: 10).",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Getting your Jira issues...",
            },
            {
                "name": "jira_search_issues",
                "description": (
                    "Search for Jira issues by keyword. Use this when the user wants to find "
                    "a Jira issue by its title, description, or text content."
                ),
                "endpoint": "/tools/search_issues",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-text search query.",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional Jira project key to scope the search (e.g. 'ENG').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of Jira issues to return (default: 10).",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": True,
                "status_message": "Searching Jira...",
            },
            {
                "name": "jira_get_issue",
                "description": (
                    "Get detailed information about a specific Jira issue. Use this when the "
                    "user asks about a particular Jira issue and wants its details."
                ),
                "endpoint": "/tools/get_issue",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Jira issue key (e.g. 'ENG-123', 'OPS-42').",
                        },
                    },
                    "required": ["issue_key"],
                },
                "auth_required": True,
                "status_message": "Getting Jira issue details...",
            },
            {
                "name": "jira_update_issue_status",
                "description": (
                    "Move a Jira issue to a new status (workflow transition). Use this when the "
                    "user wants to change an issue's state, e.g. 'In Progress' or 'Done'."
                ),
                "endpoint": "/tools/update_issue_status",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Jira issue key (e.g. 'ENG-123').",
                        },
                        "new_status": {
                            "type": "string",
                            "description": "Target status name (e.g. 'In Progress', 'Done', 'To Do').",
                        },
                    },
                    "required": ["issue_key", "new_status"],
                },
                "auth_required": True,
                "write": True,
                "status_message": "Updating Jira issue status...",
            },
            {
                "name": "jira_add_comment",
                "description": (
                    "Add a comment to an existing Jira issue. Use this when the user wants to "
                    "comment on, note, or add information to a Jira issue."
                ),
                "endpoint": "/tools/add_comment",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "issue_key": {
                            "type": "string",
                            "description": "Jira issue key (e.g. 'ENG-123').",
                        },
                        "comment": {
                            "type": "string",
                            "description": "Comment body text.",
                        },
                    },
                    "required": ["issue_key", "comment"],
                },
                "auth_required": True,
                "write": True,
                "status_message": "Adding comment to Jira issue...",
            },
            {
                "name": "jira_list_projects",
                "description": (
                    "List Jira projects the user has access to. Use this when the user wants "
                    "to see available projects or pick one to file an issue against."
                ),
                "endpoint": "/tools/list_projects",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional substring to filter projects by name or key.",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Listing Jira projects...",
            },
            {
                "name": "jira_list_releases",
                "description": (
                    "List upcoming Jira releases (versions) the user is targeting. Each "
                    "release becomes a Goal in the user's Plan view; the LLM can also "
                    "use this to summarise what's shipping next. Defaults to unreleased "
                    "versions across every project the user can see."
                ),
                "endpoint": "/tools/list_releases",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "project_key": {
                            "type": "string",
                            "description": "Optional ProjectKey (e.g. 'WPNG') to scope the listing.",
                        },
                        "include_released": {
                            "type": "boolean",
                            "description": "When true, also include already-released versions. Default false.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of releases to return (1–100). Default 50.",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Listing Jira releases...",
            },
        ]
    }
