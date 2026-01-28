"""
Tools for accessing GitHub data (PRs, issues, etc.).
"""

import contextvars
import requests
from datetime import datetime
from typing import Optional, List
import json

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

import database.users as users_db
from utils.retrieval.tools.integration_base import (
    ensure_capped,
    prepare_access,
    retry_on_auth,
)
from utils.llm.clients import llm_mini

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def refresh_github_token(uid: str, integration: Optional[dict] = None) -> Optional[str]:
    """
    Refresh GitHub access token using refresh token.

    Note: GitHub OAuth apps don't typically use refresh tokens in the same way.
    This is a placeholder for future implementation if needed.

    Args:
        uid: User ID
        integration: Optional integration dict. If not provided, will reload from database.

    Returns:
        New access token or None if refresh failed
    """
    # GitHub OAuth apps typically don't use refresh tokens
    # The token is long-lived or needs to be re-authorized
    # For now, return None to trigger re-authentication
    return None


def github_api_request(
    method: str,
    url: str,
    access_token: str,
    params: Optional[dict] = None,
    json_data: Optional[dict] = None,
) -> dict:
    """
    Make a request to GitHub API.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full GitHub API URL
        access_token: GitHub access token
        params: Optional query parameters
        json_data: Optional JSON body for POST/PATCH requests

    Returns:
        Response JSON data

    Raises:
        Exception: If request fails or returns non-2xx status
    """
    headers = {
        'Authorization': f'token {access_token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Omi-AI',
    }

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=10.0,
        )

        if response.status_code == 401:
            raise Exception("Authentication failed - token may be expired or invalid")
        elif response.status_code == 403:
            # Try to parse error message for more context
            try:
                error_data = response.json()
                error_message = error_data.get('message', 'Forbidden')
                if 'API rate limit' in error_message or 'rate limit' in error_message.lower():
                    raise Exception("GitHub API rate limit exceeded. Please try again later.")
                elif 'permission' in error_message.lower() or 'access' in error_message.lower():
                    raise Exception(
                        f"Permission denied: {error_message}. You may not have write access to this repository, or the repository may be private and your token doesn't have access."
                    )
                else:
                    raise Exception(
                        f"Forbidden: {error_message}. You may not have the required permissions for this repository."
                    )
            except (ValueError, KeyError):
                raise Exception(
                    "Forbidden - insufficient permissions. You may not have write access to this repository, or the repository may be private."
                )
        elif response.status_code == 404:
            raise Exception(
                "Repository not found. Please check that the repository owner and name are correct, and that you have access to it."
            )
        elif not response.ok:
            error_msg = response.text[:200] if response.text else "No error body"
            raise Exception(f"GitHub API error {response.status_code}: {error_msg}")

        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error: {str(e)}")


def get_github_user(access_token: str) -> dict:
    """
    Get authenticated GitHub user information.

    Args:
        access_token: GitHub access token

    Returns:
        User information dict
    """
    return github_api_request('GET', 'https://api.github.com/user', access_token)


def find_github_username(access_token: str, query: str, owner: Optional[str] = None) -> Optional[str]:
    """
    Find GitHub username using fuzzy matching.
    Searches GitHub users API and tries to match by username or name.

    Args:
        access_token: GitHub access token
        query: Username or name to search for (e.g., "mohsin", "Mohsin")
        owner: Optional repository owner to search within (for org members)

    Returns:
        Matched username or None if not found
    """
    query_lower = query.lower().strip()
    query_clean = query_lower.replace(' ', '').replace('-', '').replace('_', '')

    # Try exact match first
    try:
        url = f'https://api.github.com/users/{query}'
        user = github_api_request('GET', url, access_token)
        if user and user.get('login'):
            return user.get('login')
    except Exception:
        pass

    # If owner provided, try searching org members first (more likely to match)
    if owner:
        try:
            url = f'https://api.github.com/orgs/{owner}/members'
            params = {'per_page': 100}
            members = github_api_request('GET', url, access_token, params=params)

            if isinstance(members, list):
                best_match = None
                best_score = 0

                for member in members:
                    login = member.get('login', '')
                    login_lower = login.lower()
                    login_clean = login_lower.replace('-', '').replace('_', '')

                    # Exact match
                    if query_lower == login_lower:
                        return login

                    # Contains match (higher score)
                    if query_lower in login_lower:
                        score = len(query_lower) / len(login_lower)
                        if score > best_score:
                            best_score = score
                            best_match = login

                    # Clean match (removes numbers/special chars)
                    if query_clean in login_clean or login_clean in query_clean:
                        score = len(query_clean) / max(len(login_clean), 1)
                        if score > best_score:
                            best_score = score
                            best_match = login

                if best_match:
                    return best_match
        except Exception as e:
            print(f"Error searching org members for '{query}': {e}")

    # Search GitHub users API
    try:
        search_url = 'https://api.github.com/search/users'
        params = {
            'q': f'{query} in:login',
            'per_page': 20,
        }
        results = github_api_request('GET', search_url, access_token, params=params)

        if results and 'items' in results:
            items = results['items']
            if items:
                best_match = None
                best_score = 0

                for item in items:
                    login = item.get('login', '')
                    login_lower = login.lower()
                    login_clean = login_lower.replace('-', '').replace('_', '')

                    # Exact match
                    if query_lower == login_lower:
                        return login

                    # Contains match
                    if query_lower in login_lower:
                        score = len(query_lower) / len(login_lower)
                        if score > best_score:
                            best_score = score
                            best_match = login

                    # Clean match
                    if query_clean in login_clean or login_clean in query_clean:
                        score = len(query_clean) / max(len(login_clean), 1)
                        if score > best_score:
                            best_score = score
                            best_match = login

                # Return best match if score is reasonable (>0.3)
                if best_match and best_score > 0.3:
                    return best_match

                # Fallback to first result
                if items:
                    return items[0].get('login')
    except Exception as e:
        print(f"Error searching for GitHub user '{query}': {e}")

    return None


def get_github_labels(access_token: str, owner: str, repo: str) -> List[dict]:
    """
    Fetch available labels from a GitHub repository.

    Args:
        access_token: GitHub access token
        owner: Repository owner (username or org)
        repo: Repository name

    Returns:
        List of label dicts with 'name', 'color', 'description', etc.
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/labels'
    params = {
        'per_page': 100,
    }

    labels = github_api_request('GET', url, access_token, params=params)

    if isinstance(labels, list):
        return labels
    return []


class LabelSelection(BaseModel):
    """Model for LLM label selection response"""

    selected_labels: List[str] = Field(
        description="List of 1-2 label names selected from available labels. Must be exact matches from the available labels list."
    )


def select_labels_for_issue(title: str, body: Optional[str], available_labels: List[dict]) -> List[str]:
    """
    Use LLM to select 1-2 appropriate labels from available labels based on issue content.

    Args:
        title: Issue title
        body: Optional issue body
        available_labels: List of available label dicts with 'name', 'description', etc.

    Returns:
        List of selected label names (1-2 label names
    """
    if not available_labels:
        return []

    # Extract label names and descriptions
    labels_info = []
    for label in available_labels:
        label_name = label.get('name', '')
        label_desc = label.get('description', '')
        if label_name:
            label_str = f"- {label_name}"
            if label_desc:
                label_str += f": {label_desc}"
            labels_info.append(label_str)

    labels_list_str = '\n'.join(labels_info)
    label_names = [label.get('name', '') for label in available_labels if label.get('name')]

    issue_content = f"Title: {title}"
    if body:
        issue_content += f"\nBody: {body}"

    prompt = f"""
You are selecting labels for a GitHub issue. Your task is to choose 1-2 labels from the available labels that best match the issue content.

Available labels:
{labels_list_str}

Issue content:
{issue_content}

Instructions:
- Select 1-2 labels that best categorize this issue
- Only choose labels that exist in the available labels list (exact name matches)
- Consider the issue's title and body when selecting labels
- Prefer more specific labels over generic ones
- If the issue is clearly a bug, select a "bug" label if available
- If the issue is a feature request, select an "enhancement" or "feature" label if available
- If no labels are appropriate, return an empty list

Return ONLY the selected label names as a JSON array. Each label name must exactly match one from the available labels list.
"""

    try:
        with_parser = llm_mini.with_structured_output(LabelSelection)
        response: LabelSelection = with_parser.invoke(prompt)

        # Validate that selected labels exist in available labels
        valid_labels = []
        for selected_label in response.selected_labels:
            if selected_label in label_names:
                valid_labels.append(selected_label)
            else:
                # Try case-insensitive match
                for label_name in label_names:
                    if label_name.lower() == selected_label.lower():
                        valid_labels.append(label_name)
                        break

        # Limit to 2 labels max
        return valid_labels[:2]
    except Exception as e:
        print(f"Error selecting labels with LLM: {e}")
        # Fallback: return empty list if LLM fails
        return []


def get_github_pull_requests(
    access_token: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    author: Optional[str] = None,
    state: str = 'open',
    max_results: int = 10,
) -> List[dict]:
    """
    Fetch pull requests from GitHub.

    Args:
        access_token: GitHub access token
        owner: Repository owner (username or org). If None and repo provided, searches user's repos.
        repo: Repository name. If None and owner provided, searches across all repos.
        author: Filter by author username. If None, returns all PRs. Supports fuzzy matching.
        state: PR state ('open', 'closed', 'all'). Default: 'open'
        max_results: Maximum number of PRs to return

    Returns:
        List of pull request dicts
    """
    # Fuzzy match author username if provided
    final_author = author
    if author:
        matched_username = find_github_username(access_token, author, owner)
        if matched_username:
            final_author = matched_username
            if matched_username != author:
                print(f"Fuzzy matched '{author}' to GitHub username '{matched_username}'")
        else:
            # Try with author as-is, might still work
            final_author = author

    # Prefer searching within specific repo if owner/repo provided
    if owner and repo:
        # Specific repository
        url = f'https://api.github.com/repos/{owner}/{repo}/pulls'
        params = {
            'state': state,
            'per_page': min(max_results, 100),
        }
        if final_author:
            params['creator'] = final_author
    elif owner and not repo:
        # Owner provided but no repo - search within that user/org's repos
        query = f'is:pr author:{final_author} state:{state}' if final_author else f'is:pr state:{state}'
        query += f' user:{owner}'
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }
    elif final_author:
        # Search across all repos for a specific author (only if no owner/repo context)
        query = f'is:pr author:{final_author} state:{state}'
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }
    else:
        # Get authenticated user's PRs
        user = get_github_user(access_token)
        username = user.get('login')
        query = f'is:pr author:{username} state:{state}'
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }

    data = github_api_request('GET', url, access_token, params=params)

    # Handle search API response format
    if 'items' in data:
        return data['items'][:max_results]
    # Handle direct PRs API response format
    elif isinstance(data, list):
        return data[:max_results]
    else:
        return []


def get_github_issues(
    access_token: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    author: Optional[str] = None,
    assignee: Optional[str] = None,
    state: str = 'open',
    max_results: int = 10,
) -> List[dict]:
    """
    Fetch issues from GitHub.

    Args:
        access_token: GitHub access token
        owner: Repository owner (username or org). If None, searches user's repos.
        repo: Repository name. If None, searches across all repos.
        author: Filter by author username. If None, returns all issues. Supports fuzzy matching.
        assignee: Filter by assignee username. If None, returns all issues. Supports fuzzy matching.
        state: Issue state ('open', 'closed', 'all'). Default: 'open'
        max_results: Maximum number of issues to return

    Returns:
        List of issue dicts
    """
    # Fuzzy match author username if provided
    final_author = author
    if author:
        matched_username = find_github_username(access_token, author, owner)
        if matched_username:
            final_author = matched_username
            if matched_username != author:
                print(f"Fuzzy matched author '{author}' to GitHub username '{matched_username}'")
        else:
            final_author = author

    # Fuzzy match assignee username if provided
    final_assignee = assignee
    if assignee:
        matched_username = find_github_username(access_token, assignee, owner)
        if matched_username:
            final_assignee = matched_username
            if matched_username != assignee:
                print(f"Fuzzy matched assignee '{assignee}' to GitHub username '{matched_username}'")
        else:
            final_assignee = assignee

    if owner and repo:
        # Specific repository
        url = f'https://api.github.com/repos/{owner}/{repo}/issues'
        params = {
            'state': state,
            'per_page': min(max_results, 100),
        }
        if final_assignee:
            params['assignee'] = final_assignee
        if final_author:
            params['creator'] = final_author
    elif owner and not repo:
        # Owner provided but no repo - search within that user/org's repos
        query_parts = ['is:issue', f'state:{state}']
        if final_author:
            query_parts.append(f'author:{final_author}')
        if final_assignee:
            query_parts.append(f'assignee:{final_assignee}')
        query_parts.append(f'user:{owner}')
        query = ' '.join(query_parts)
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }
    elif final_author or final_assignee:
        # Search across all repos (only if no owner/repo context)
        query_parts = ['is:issue', f'state:{state}']
        if final_author:
            query_parts.append(f'author:{final_author}')
        if final_assignee:
            query_parts.append(f'assignee:{final_assignee}')
        query = ' '.join(query_parts)
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }
    else:
        # Get authenticated user's issues
        user = get_github_user(access_token)
        username = user.get('login')
        query = f'is:issue author:{username} state:{state}'
        url = 'https://api.github.com/search/issues'
        params = {
            'q': query,
            'per_page': min(max_results, 100),
        }

    data = github_api_request('GET', url, access_token, params=params)

    # Handle search API response format
    if 'items' in data:
        return data['items'][:max_results]
    # Handle direct issues API response format
    elif isinstance(data, list):
        # Filter out PRs (they appear in issues endpoint too)
        return [issue for issue in data if 'pull_request' not in issue][:max_results]
    else:
        return []


def create_github_issue(
    access_token: str,
    owner: str,
    repo: str,
    title: str,
    body: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
) -> dict:
    """
    Create a new GitHub issue.

    Args:
        access_token: GitHub access token
        owner: Repository owner (username or org)
        repo: Repository name
        title: Issue title
        body: Optional issue body/description
        labels: Optional list of label names
        assignees: Optional list of assignee usernames

    Returns:
        Created issue dict
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/issues'

    json_data = {
        'title': title,
    }

    if body:
        json_data['body'] = body
    if labels:
        json_data['labels'] = labels
    if assignees:
        json_data['assignees'] = assignees

    return github_api_request('POST', url, access_token, json_data=json_data)


def close_github_issue(
    access_token: str,
    owner: str,
    repo: str,
    issue_number: int,
) -> dict:
    """
    Close a GitHub issue.

    Note: GitHub API does not support deleting issues. This function closes the issue instead.
    To delete an issue, you need admin permissions and must use the GitHub web interface.

    Args:
        access_token: GitHub access token
        owner: Repository owner (username or org)
        repo: Repository name
        issue_number: Issue number to close

    Returns:
        Updated issue dict
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}'

    json_data = {
        'state': 'closed',
    }

    return github_api_request('PATCH', url, access_token, json_data=json_data)


@tool
def get_github_pull_requests_tool(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    author: Optional[str] = None,
    state: str = 'open',
    max_results: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve pull requests from GitHub.

    Use this tool when:
    - User asks about pull requests or PRs
    - User asks "show me my PRs" or "what PRs do I have?"
    - User asks about someone's PRs (e.g., "PRs by username")
    - User asks about PRs in a specific repository (e.g., "PRs in owner/repo")
    - User asks "show me open PRs" or "closed PRs"
    - **ALWAYS use this tool when the user asks about GitHub pull requests**

    Args:
        owner: Optional repository owner (username or org). If not provided, uses default repository from settings.
        repo: Optional repository name. If not provided, uses default repository from settings.
        author: Optional GitHub username to filter PRs by author. Supports fuzzy matching (e.g., "mohsin" matches "mdmohsin7").
        state: PR state filter ('open', 'closed', 'all'). Default: 'open'
        max_results: Maximum number of PRs to return (default: 10, max: 100)

    Returns:
        Formatted list of pull requests with their details.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'github',
        'GitHub',
        'GitHub is not connected. Please connect your GitHub account from settings to view pull requests.',
        'GitHub access token not found. Please reconnect your GitHub account from settings.',
        'Error checking GitHub connection',
    )
    if access_err:
        return access_err

    try:
        max_results = ensure_capped(
            max_results, 100, "⚠️ get_github_pull_requests_tool - max_results capped from {} to {}"
        )

        # Use default repository if owner/repo not specified
        final_owner = owner
        final_repo = repo
        if not final_owner or not final_repo:
            default_repo = integration.get('default_repo') if integration else None
            if default_repo and '/' in default_repo:
                parts = default_repo.split('/', 1)
                if not final_owner:
                    final_owner = parts[0].strip()
                if not final_repo:
                    final_repo = parts[1].strip()

        # Fetch PRs
        prs, err = retry_on_auth(
            get_github_pull_requests,
            {
                'access_token': access_token,
                'owner': final_owner,
                'repo': final_repo,
                'author': author,
                'state': state,
                'max_results': max_results,
            },
            refresh_github_token,
            uid,
            integration,
            "GitHub authentication expired. Please reconnect your GitHub account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
                "token may be expired or invalid",
            ),
        )
        if err:
            return err

        if not prs:
            repo_info = (
                f" in {final_owner}/{final_repo}" if (final_owner and final_repo) else f" by {author}" if author else ""
            )
            return f"No pull requests found{repo_info}."

        # Format PRs
        result = f"GitHub Pull Requests ({len(prs)} found):\n\n"

        for i, pr in enumerate(prs, 1):
            title = pr.get('title', 'Untitled')
            number = pr.get('number', 'N/A')
            state_pr = pr.get('state', 'unknown')
            user = pr.get('user', {})
            author_name = user.get('login', 'Unknown') if user else 'Unknown'
            created_at = pr.get('created_at', '')
            url = pr.get('html_url', '')
            body = pr.get('body', '')

            # Format timestamp
            try:
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                else:
                    time_str = "Unknown time"
            except Exception:
                time_str = created_at if created_at else "Unknown time"

            # Extract repo info
            repo_full_name = (
                pr.get('repository_url', '').replace('https://api.github.com/repos/', '')
                if pr.get('repository_url')
                else 'Unknown'
            )

            result += f"{i}. #{number}: {title}\n"
            result += f"   Repository: {repo_full_name}\n"
            result += f"   Author: {author_name}\n"
            result += f"   State: {state_pr}\n"
            result += f"   Created: {time_str}\n"
            if url:
                result += f"   URL: {url}\n"
            if body:
                body_preview = body[:150] + '...' if len(body) > 150 else body
                result += f"   Description: {body_preview}\n"
            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_github_pull_requests_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching GitHub pull requests: {str(e)}"


@tool
def get_github_issues_tool(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    author: Optional[str] = None,
    assignee: Optional[str] = None,
    state: str = 'open',
    max_results: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve issues from GitHub.

    Use this tool when:
    - User asks about issues or GitHub issues
    - User asks "show me my issues" or "what issues do I have?"
    - User asks about someone's issues (e.g., "issues by username")
    - User asks about issues assigned to someone (e.g., "issues assigned to username")
    - User asks about issues in a specific repository (e.g., "issues in owner/repo")
    - User asks "show me open issues" or "closed issues"
    - **ALWAYS use this tool when the user asks about GitHub issues**

    Args:
        owner: Optional repository owner (username or org). If not provided, uses default repository from settings.
        repo: Optional repository name. If not provided, uses default repository from settings.
        author: Optional GitHub username to filter issues by author. Supports fuzzy matching (e.g., "mohsin" matches "mdmohsin7").
        assignee: Optional GitHub username to filter issues by assignee. Supports fuzzy matching (e.g., "mohsin" matches "mdmohsin7").
        state: Issue state filter ('open', 'closed', 'all'). Default: 'open'
        max_results: Maximum number of issues to return (default: 10, max: 100)

    Returns:
        Formatted list of issues with their details.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'github',
        'GitHub',
        'GitHub is not connected. Please connect your GitHub account from settings to view issues.',
        'GitHub access token not found. Please reconnect your GitHub account from settings.',
        'Error checking GitHub connection',
    )
    if access_err:
        return access_err

    try:
        max_results = ensure_capped(max_results, 100, "⚠️ get_github_issues_tool - max_results capped from {} to {}")

        # Use default repository if owner/repo not specified
        final_owner = owner
        final_repo = repo
        if not final_owner or not final_repo:
            default_repo = integration.get('default_repo') if integration else None
            if default_repo and '/' in default_repo:
                parts = default_repo.split('/', 1)
                if not final_owner:
                    final_owner = parts[0].strip()
                if not final_repo:
                    final_repo = parts[1].strip()

        # Fetch issues
        issues, err = retry_on_auth(
            get_github_issues,
            {
                'access_token': access_token,
                'owner': final_owner,
                'repo': final_repo,
                'author': author,
                'assignee': assignee,
                'state': state,
                'max_results': max_results,
            },
            refresh_github_token,
            uid,
            integration,
            "GitHub authentication expired. Please reconnect your GitHub account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
                "token may be expired or invalid",
            ),
        )
        if err:
            return err

        if not issues:
            repo_info = (
                f" in {final_owner}/{final_repo}"
                if (final_owner and final_repo)
                else f" by {author}" if author else f" assigned to {assignee}" if assignee else ""
            )
            return f"No issues found{repo_info}."

        # Format issues
        result = f"GitHub Issues ({len(issues)} found):\n\n"

        for i, issue in enumerate(issues, 1):
            title = issue.get('title', 'Untitled')
            number = issue.get('number', 'N/A')
            state_issue = issue.get('state', 'unknown')
            user = issue.get('user', {})
            author_name = user.get('login', 'Unknown') if user else 'Unknown'
            created_at = issue.get('created_at', '')
            url = issue.get('html_url', '')
            body = issue.get('body', '')
            labels = issue.get('labels', [])
            assignees = issue.get('assignees', [])

            # Format timestamp
            try:
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                else:
                    time_str = "Unknown time"
            except Exception:
                time_str = created_at if created_at else "Unknown time"

            # Extract repo info
            repo_full_name = (
                issue.get('repository_url', '').replace('https://api.github.com/repos/', '')
                if issue.get('repository_url')
                else 'Unknown'
            )

            result += f"{i}. #{number}: {title}\n"
            result += f"   Repository: {repo_full_name}\n"
            result += f"   Author: {author_name}\n"
            result += f"   State: {state_issue}\n"
            result += f"   Created: {time_str}\n"
            if labels:
                label_names = [label.get('name', '') for label in labels if isinstance(label, dict)] or [
                    str(l) for l in labels if isinstance(l, str)
                ]
                if label_names:
                    result += f"   Labels: {', '.join(label_names)}\n"
            if assignees:
                assignee_names = [a.get('login', '') for a in assignees if isinstance(a, dict)] or [
                    str(a) for a in assignees if isinstance(a, str)
                ]
                if assignee_names:
                    result += f"   Assignees: {', '.join(assignee_names)}\n"
            if url:
                result += f"   URL: {url}\n"
            if body:
                body_preview = body[:150] + '...' if len(body) > 150 else body
                result += f"   Description: {body_preview}\n"
            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_github_issues_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching GitHub issues: {str(e)}"


@tool
def create_github_issue_tool(
    title: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    body: Optional[str] = None,
    labels: Optional[str] = None,
    assignees: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Create a new GitHub issue. ALWAYS use this tool immediately when the user asks to create an issue - do not ask for permission or confirmation.

    Use this tool when:
    - User asks to create an issue or open an issue
    - User says "create an issue" or "create an issue in owner/repo"
    - User wants to file a bug report or feature request
    - User asks "open an issue about X"
    - **ALWAYS use this tool immediately when the user wants to create a GitHub issue - never ask for confirmation**

    Args:
        title: Issue title (required)
        owner: Optional repository owner (username or org). If not provided, uses default repository from settings.
        repo: Optional repository name. If not provided, uses default repository from settings. If owner is provided, repo must also be provided.
        body: Optional issue body/description
        labels: Optional comma-separated list of label names (e.g., "bug,enhancement"). If not provided, will auto-select 1-2 labels.
        assignees: Optional comma-separated list of assignee usernames (e.g., "user1,user2")
        config: LangChain config (automatically provided)

    Returns:
        Success message with issue number and URL. The URL is always included and should be prominently displayed to the user.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'github',
        'GitHub',
        'GitHub is not connected. Please connect your GitHub account from settings to create issues.',
        'GitHub access token not found. Please reconnect your GitHub account from settings.',
        'Error checking GitHub connection',
    )
    if access_err:
        return access_err

    try:
        # Determine owner and repo
        final_owner = owner
        final_repo = repo

        # If owner or repo not provided, use default repository from settings
        if not final_owner or not final_repo:
            default_repo = integration.get('default_repo') if integration else None
            if not default_repo:
                return "❌ No repository specified. Please provide a repository (e.g., 'owner/repo') or set a default repository in GitHub settings."

            # Parse default_repo format: "owner/repo"
            if '/' in default_repo:
                parts = default_repo.split('/', 1)
                if not final_owner:
                    final_owner = parts[0].strip()
                if not final_repo:
                    final_repo = parts[1].strip()
            else:
                return f"❌ Invalid default repository format: {default_repo}. Expected format: 'owner/repo'. Please set a valid default repository in GitHub settings."

        if not final_owner or not final_repo:
            return "❌ Could not determine repository. Please provide both owner and repo, or set a default repository in GitHub settings."

        # Parse labels and assignees from comma-separated strings
        labels_list = None
        if labels:
            labels_list = [label.strip() for label in labels.split(',') if label.strip()]
        else:
            # Auto-select labels if not provided
            try:
                available_labels, err = retry_on_auth(
                    get_github_labels,
                    {
                        'access_token': access_token,
                        'owner': final_owner,
                        'repo': final_repo,
                    },
                    refresh_github_token,
                    uid,
                    integration,
                    "GitHub authentication expired. Please reconnect your GitHub account from settings.",
                    (
                        "Authentication failed",
                        "401",
                        "token may be expired",
                        "token may be expired or invalid",
                    ),
                )
                if not err and available_labels:
                    selected_labels = select_labels_for_issue(title, body, available_labels)
                    if selected_labels:
                        labels_list = selected_labels
                        print(f"Auto-selected labels: {selected_labels}")
            except Exception as e:
                print(f"Error auto-selecting labels: {e}")
                # Continue without labels if auto-selection fails
                pass

        assignees_list = None
        if assignees:
            assignees_list = [assignee.strip() for assignee in assignees.split(',') if assignee.strip()]

        # Create issue
        issue, err = retry_on_auth(
            create_github_issue,
            {
                'access_token': access_token,
                'owner': final_owner,
                'repo': final_repo,
                'title': title,
                'body': body,
                'labels': labels_list,
                'assignees': assignees_list,
            },
            refresh_github_token,
            uid,
            integration,
            "GitHub authentication expired. Please reconnect your GitHub account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
                "token may be expired or invalid",
            ),
        )
        if err:
            # Provide helpful context for permission errors
            if "Permission denied" in err or "Forbidden" in err or "not have write access" in err:
                return f"❌ Unable to create issue in {final_owner}/{final_repo}.\n\n{err}\n\n**Possible solutions:**\n- Make sure you have write access to the repository\n- If it's a private repository, ensure your GitHub account has been granted access\n- If it's an organization repository, you may need to request access from the repository owner\n- Try reconnecting your GitHub account from settings to refresh permissions"
            elif "not found" in err.lower():
                return f"❌ Repository {final_owner}/{final_repo} not found.\n\n{err}\n\n**Possible solutions:**\n- Check that the repository owner and name are spelled correctly\n- Ensure the repository exists and is accessible\n- If it's a private repository, make sure you have access to it"
            return f"❌ Error creating issue: {err}"

        # Format success message - always include URL prominently
        issue_number = issue.get('number', 'N/A')
        issue_url = issue.get('html_url', '')

        if not issue_url:
            # Fallback: construct URL if not provided in response
            issue_url = f"https://github.com/{final_owner}/{final_repo}/issues/{issue_number}"

        result = f"✅ Successfully created issue #{issue_number} in {final_owner}/{final_repo}\n\n"
        result += f"**Issue Link:** {issue_url}\n\n"
        result += f"Title: {title}\n"
        if labels_list:
            result += f"Labels: {', '.join(labels_list)}\n"

        return result
    except Exception as e:
        print(f"❌ Unexpected error in create_github_issue_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error creating GitHub issue: {str(e)}"


@tool
def close_github_issue_tool(
    owner: str,
    repo: str,
    issue_number: int,
    config: RunnableConfig = None,
) -> str:
    """
    Close a GitHub issue.

    Use this tool when:
    - User asks to close an issue or delete an issue
    - User says "close issue #123" or "delete issue #123"
    - User wants to remove or close a GitHub issue
    - **ALWAYS use this tool when the user wants to close or delete a GitHub issue**

    Note: GitHub API does not support deleting issues. This tool closes the issue instead.
    To permanently delete an issue, admin permissions are required and it must be done via GitHub web interface.

    Args:
        owner: Repository owner (username or org)
        repo: Repository name
        issue_number: Issue number to close
        config: LangChain config (automatically provided)

    Returns:
        Success message or error message.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'github',
        'GitHub',
        'GitHub is not connected. Please connect your GitHub account from settings to close issues.',
        'GitHub access token not found. Please reconnect your GitHub account from settings.',
        'Error checking GitHub connection',
    )
    if access_err:
        return access_err

    try:
        # Close issue
        issue, err = retry_on_auth(
            close_github_issue,
            {
                'access_token': access_token,
                'owner': owner,
                'repo': repo,
                'issue_number': issue_number,
            },
            refresh_github_token,
            uid,
            integration,
            "GitHub authentication expired. Please reconnect your GitHub account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
                "token may be expired or invalid",
            ),
        )
        if err:
            # Provide helpful context for permission errors
            if "Permission denied" in err or "Forbidden" in err or "not have write access" in err:
                return f"❌ Unable to close issue #{issue_number} in {owner}/{repo}.\n\n{err}\n\n**Possible solutions:**\n- Make sure you have write access to the repository\n- Ensure you have permission to close issues\n- If it's a private repository, ensure your GitHub account has been granted access\n- Try reconnecting your GitHub account from settings to refresh permissions"
            elif "not found" in err.lower():
                return f"❌ Issue #{issue_number} in {owner}/{repo} not found.\n\n{err}\n\n**Possible solutions:**\n- Check that the issue number is correct\n- Ensure the repository exists and is accessible\n- If it's a private repository, make sure you have access to it"
            return f"❌ Error closing issue: {err}"

        # Format success message
        issue_url = issue.get('html_url', '')
        issue_state = issue.get('state', 'closed')

        result = f"✅ Successfully closed issue #{issue_number} in {owner}/{repo}\n"
        if issue_url:
            result += f"   URL: {issue_url}\n"
        result += "\n**Note:** GitHub API does not support deleting issues. The issue has been closed instead. To permanently delete an issue, you need admin permissions and must use the GitHub web interface."

        return result
    except Exception as e:
        print(f"❌ Unexpected error in close_github_issue_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error closing GitHub issue: {str(e)}"


@tool
def code_with_claude_tool(
    owner: str,
    repo: str,
    feature_description: str,
    config: RunnableConfig = None,
) -> str:
    """
    Modify code in a GitHub repository using Claude AI (aider/Claude Code).

    Use this tool when:
    - User asks to "code" or "modify" or "implement" a feature in a repository
    - User says "add feature X to repo Y"
    - User wants to write code, fix bugs, or refactor
    - **ALWAYS use this tool when user wants Claude to write/modify code in a GitHub repo**

    This tool will:
    1. Clone the repository
    2. Use Claude AI (via aider) to implement the feature
    3. Run tests automatically
    4. Create a PR with the changes

    Note: User must have set their Anthropic API key in GitHub integration settings.
    They will be charged for Claude API usage via their own key.

    Args:
        owner: Repository owner (username or org)
        repo: Repository name
        feature_description: Detailed description of what to code/implement
        config: LangChain config (automatically provided)

    Returns:
        Success message with PR URL or error message
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'github',
        'GitHub',
        'GitHub is not connected. Please connect your GitHub account from settings.',
        'GitHub access token not found. Please reconnect your GitHub account from settings.',
        'Error checking GitHub connection',
    )
    if access_err:
        return access_err

    try:
        # Check if user has Anthropic API key set
        # Fetch Anthropic key from GitHub app
        import requests
        anthropic_key = None
        try:
            github_app_url = os.getenv('GITHUB_APP_URL', 'https://omi-github.up.railway.app')
            response = requests.get(f"{github_app_url}/get-anthropic-key?uid={uid}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                anthropic_key = data.get('key') if data.get('success') else None
        except Exception as e:
            print(f"Error fetching Anthropic key from GitHub app: {e}")

        if not anthropic_key:
            return "❌ Anthropic API key not set. Please add your Anthropic API key in GitHub settings to use Claude Code.\n\nVisit: https://omi-github.up.railway.app and add your key from: https://console.anthropic.com/settings/keys"

        # Import Cloud Run agent
        from utils.cloud_run_agent import start_coding_session

        # Start coding session on Cloud Run
        result = start_coding_session(
            repo_url=f"https://github.com/{owner}/{repo}",
            feature=feature_description,
            github_token=access_token,
            anthropic_key=anthropic_key,
            owner=owner,
            repo=repo,
        )

        if result.get('error'):
            return f"❌ Error during coding session: {result['error']}"

        pr_url = result.get('pr_url')
        pr_number = result.get('pr_number')
        tests_passed = result.get('tests_passed', False)

        response = f"✅ Successfully implemented feature in {owner}/{repo}\n\n"
        response += f"**Pull Request:** {pr_url}\n\n"
        if pr_number:
            response += f"PR #{pr_number}\n"
        if tests_passed:
            response += "✅ All tests passed!\n"
        else:
            response += "⚠️ Tests not run or failed - please review PR and run tests manually.\n"

        response += f"\n🤖 Code generated by Claude AI using your API key"

        return response
    except Exception as e:
        print(f"❌ Unexpected error in code_with_claude_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error during coding session: {str(e)}"
