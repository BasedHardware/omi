"""
Claude Code integration - AI-powered coding using Anthropic API.
Uses GitHub API directly (no git binary required).
"""
import os
import re
import tempfile
from typing import Optional, Dict, Any, List, Tuple
from anthropic import Anthropic
import requests
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_code_with_claude(feature_description: str, repo_context: str, anthropic_key: str) -> str:
    """
    Generate code using Claude API.

    Args:
        feature_description: What the user wants to implement
        repo_context: Context about the repository (structure, files, etc.)
        anthropic_key: User's Anthropic API key

    Returns:
        Generated code/changes as a string
    """
    client = Anthropic(api_key=anthropic_key)

    prompt = f"""You are an expert software engineer. Generate code to implement the following feature:

Feature Request: {feature_description}

Repository Context:
{repo_context}

Please provide the complete code changes needed. Format your response as:

FILE: path/to/file.py
```python
# complete file contents here
```

FILE: path/to/another/file.js
```javascript
// complete file contents here
```

EXPLANATION:
What this does and why

Be specific about which files to create or modify. Include the full file contents for each file.
If the feature is very simple (like adding a test file), just create that one file without overthinking it.
"""

    logger.info(f"Generating code with Claude for: {feature_description}")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


def parse_code_changes(changes: str) -> List[Tuple[str, str]]:
    """
    Parse Claude's response to extract file paths and their contents.

    Args:
        changes: Raw text from Claude with FILE: markers and code blocks

    Returns:
        List of (file_path, file_content) tuples
    """
    files = []

    # Pattern to match: FILE: path/to/file.ext followed by ```lang\ncode\n```
    pattern = r'FILE:\s*([^\n]+)\s*```(?:\w+)?\s*\n(.*?)```'

    matches = re.finditer(pattern, changes, re.DOTALL)

    for match in matches:
        file_path = match.group(1).strip()
        file_content = match.group(2)
        files.append((file_path, file_content))
        logger.info(f"Parsed file: {file_path} ({len(file_content)} chars)")

    # If no structured format found, create a simple change file
    if not files:
        logger.warning("No structured file changes found, creating CLAUDE_CHANGES.md")
        files.append(('CLAUDE_CHANGES.md', f"# Changes by Claude AI\n\n{changes}"))

    return files


def get_default_branch(owner: str, repo: str, github_token: str) -> str:
    """
    Get the default branch of a GitHub repository.

    Args:
        owner: Repository owner
        repo: Repository name
        github_token: GitHub access token

    Returns:
        Default branch name (e.g., 'main', 'master', 'flutterflow')
    """
    url = f'https://api.github.com/repos/{owner}/{repo}'
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            default_branch = response.json().get('default_branch', 'main')
            logger.info(f"Default branch for {owner}/{repo}: {default_branch}")
            return default_branch
    except Exception as e:
        logger.error(f"Failed to get default branch: {e}")

    # Fallback to 'main'
    return 'main'


def get_repo_context_via_api(owner: str, repo: str, github_token: str, path: str = "") -> str:
    """
    Get repository context via GitHub API (no git clone needed).

    Args:
        owner: Repository owner
        repo: Repository name
        github_token: GitHub access token
        path: Path within repo to explore (default: root)

    Returns:
        String describing the repo structure
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}'
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json()

            context = ["Repository Structure:"]

            # List directories and files
            for item in items[:20]:  # Limit to 20 items
                if item['type'] == 'dir':
                    context.append(f"  📁 {item['name']}/")
                else:
                    context.append(f"  📄 {item['name']}")

            if len(items) > 20:
                context.append(f"  ... and {len(items) - 20} more items")

            return '\n'.join(context)
    except Exception as e:
        logger.error(f"Failed to get repo context: {e}")

    return "Repository: Unable to fetch structure"


def create_or_update_files_via_api(
    owner: str,
    repo: str,
    branch_name: str,
    files: List[Tuple[str, str]],
    commit_message: str,
    github_token: str,
    base_branch: str
) -> Dict[str, Any]:
    """
    Create a new branch and commit files using GitHub API.

    Args:
        owner: Repository owner
        repo: Repository name
        branch_name: New branch name
        files: List of (file_path, content) tuples
        commit_message: Commit message
        github_token: GitHub access token
        base_branch: Base branch to branch from

    Returns:
        Dict with success status and branch name
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        # Step 1: Get the base branch reference
        logger.info(f"Getting reference for base branch: {base_branch}")
        ref_url = f'https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{base_branch}'
        response = requests.get(ref_url, headers=headers)

        if response.status_code != 200:
            return {
                'success': False,
                'message': f'Failed to get base branch: {response.text}'
            }

        base_sha = response.json()['object']['sha']
        logger.info(f"Base branch SHA: {base_sha}")

        # Step 2: Get the base tree
        logger.info(f"Getting base tree...")
        commit_url = f'https://api.github.com/repos/{owner}/{repo}/git/commits/{base_sha}'
        response = requests.get(commit_url, headers=headers)

        if response.status_code != 200:
            return {
                'success': False,
                'message': f'Failed to get base commit: {response.text}'
            }

        base_tree_sha = response.json()['tree']['sha']
        logger.info(f"Base tree SHA: {base_tree_sha}")

        # Step 3: Create blobs for each file
        logger.info(f"Creating blobs for {len(files)} files...")
        tree_items = []

        for file_path, content in files:
            # Create blob
            blob_url = f'https://api.github.com/repos/{owner}/{repo}/git/blobs'
            blob_data = {
                'content': content,
                'encoding': 'utf-8'
            }

            response = requests.post(blob_url, headers=headers, json=blob_data)

            if response.status_code != 201:
                logger.error(f"Failed to create blob for {file_path}: {response.text}")
                continue

            blob_sha = response.json()['sha']
            logger.info(f"Created blob for {file_path}: {blob_sha}")

            tree_items.append({
                'path': file_path,
                'mode': '100644',  # Regular file
                'type': 'blob',
                'sha': blob_sha
            })

        if not tree_items:
            return {
                'success': False,
                'message': 'No files were successfully processed'
            }

        # Step 4: Create a new tree
        logger.info(f"Creating new tree with {len(tree_items)} items...")
        tree_url = f'https://api.github.com/repos/{owner}/{repo}/git/trees'
        tree_data = {
            'base_tree': base_tree_sha,
            'tree': tree_items
        }

        response = requests.post(tree_url, headers=headers, json=tree_data)

        if response.status_code != 201:
            return {
                'success': False,
                'message': f'Failed to create tree: {response.text}'
            }

        new_tree_sha = response.json()['sha']
        logger.info(f"New tree SHA: {new_tree_sha}")

        # Step 5: Create a commit
        logger.info(f"Creating commit...")
        commit_url = f'https://api.github.com/repos/{owner}/{repo}/git/commits'
        commit_data = {
            'message': commit_message,
            'tree': new_tree_sha,
            'parents': [base_sha]
        }

        response = requests.post(commit_url, headers=headers, json=commit_data)

        if response.status_code != 201:
            return {
                'success': False,
                'message': f'Failed to create commit: {response.text}'
            }

        new_commit_sha = response.json()['sha']
        logger.info(f"New commit SHA: {new_commit_sha}")

        # Step 6: Create/update the branch reference
        logger.info(f"Creating branch: {branch_name}")
        ref_url = f'https://api.github.com/repos/{owner}/{repo}/git/refs'
        ref_data = {
            'ref': f'refs/heads/{branch_name}',
            'sha': new_commit_sha
        }

        response = requests.post(ref_url, headers=headers, json=ref_data)

        if response.status_code not in [201, 422]:  # 422 means already exists
            return {
                'success': False,
                'message': f'Failed to create branch: {response.text}'
            }

        logger.info(f"Branch {branch_name} created successfully!")

        return {
            'success': True,
            'branch': branch_name,
            'default_branch': base_branch,
            'message': f'Created branch {branch_name} with {len(tree_items)} files'
        }

    except Exception as e:
        logger.error(f"Error creating branch via API: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Failed to create branch: {str(e)}'
        }


def create_pr_with_github_api(
    owner: str,
    repo: str,
    branch: str,
    title: str,
    body: str,
    github_token: str,
    base_branch: str = 'main'
) -> Optional[Dict[str, Any]]:
    """
    Create a pull request using GitHub API.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch with changes
        title: PR title
        body: PR description
        github_token: GitHub access token
        base_branch: Base branch to merge into (default: 'main')

    Returns:
        Dict with pr_url and pr_number if successful, None otherwise
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/pulls'
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        'title': title,
        'body': body,
        'head': branch,
        'base': base_branch
    }

    logger.info(f"Creating PR: {branch} -> {base_branch}")

    try:
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 201:
            pr_data = response.json()
            pr_url = pr_data.get('html_url')
            pr_number = pr_data.get('number')
            logger.info(f"PR created successfully: {pr_url}")
            return {
                'pr_url': pr_url,
                'pr_number': pr_number
            }
        else:
            error_msg = f"Failed to create PR: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return None
    except Exception as e:
        logger.error(f"Exception creating PR: {e}", exc_info=True)
        return None


def merge_pr_with_github_api(
    owner: str,
    repo: str,
    pr_number: int,
    github_token: str,
    merge_method: str = 'merge'
) -> bool:
    """
    Merge a pull request using GitHub API.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_number: PR number to merge
        github_token: GitHub access token
        merge_method: Merge method ('merge', 'squash', or 'rebase')

    Returns:
        True if merged successfully, False otherwise
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge'
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        'merge_method': merge_method
    }

    logger.info(f"Merging PR #{pr_number} using {merge_method} method")

    try:
        response = requests.put(url, headers=headers, json=data)

        if response.status_code == 200:
            logger.info(f"PR #{pr_number} merged successfully")
            return True
        else:
            error_msg = f"Failed to merge PR: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return False
    except Exception as e:
        logger.error(f"Exception merging PR: {e}", exc_info=True)
        return False
