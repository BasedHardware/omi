"""
Cloud Run agent for running Claude Code sessions.

This module handles communication with the Cloud Run service that runs
aider/Claude Code sessions for modifying GitHub repositories.
"""

import os
import requests
from typing import Dict, Any


def start_coding_session(
    repo_url: str, feature: str, github_token: str, anthropic_key: str, owner: str, repo: str
) -> Dict[str, Any]:
    """
    Start a coding session on Cloud Run.

    Args:
        repo_url: Full GitHub repository URL (e.g., https://github.com/owner/repo)
        feature: Description of feature to implement
        github_token: GitHub access token for cloning and creating PRs
        anthropic_key: User's Anthropic API key (they pay for usage)
        owner: Repository owner
        repo: Repository name

    Returns:
        Dict containing:
        - pr_url: URL of created pull request
        - pr_number: PR number
        - tests_passed: Whether tests passed
        - error: Error message if failed
    """
    # Get Cloud Run service URL from environment
    cloud_run_url = os.getenv('CODING_AGENT_CLOUD_RUN_URL')

    if not cloud_run_url:
        return {
            'error': 'Cloud Run coding agent not configured. Please set CODING_AGENT_CLOUD_RUN_URL environment variable.'
        }

    try:
        # Call Cloud Run service
        response = requests.post(
            f"{cloud_run_url}/code",
            json={
                'repo_url': repo_url,
                'feature': feature,
                'github_token': github_token,
                'anthropic_key': anthropic_key,
                'owner': owner,
                'repo': repo,
            },
            timeout=600,  # 10 minute timeout for coding sessions
        )

        if response.status_code != 200:
            return {'error': f"Cloud Run service error: {response.status_code} - {response.text}"}

        return response.json()
    except requests.exceptions.Timeout:
        return {
            'error': 'Coding session timed out (10 minutes). The task may have been too complex. Try breaking it into smaller parts.'
        }
    except requests.exceptions.RequestException as e:
        return {'error': f"Network error communicating with Cloud Run service: {str(e)}"}
    except Exception as e:
        return {'error': f"Unexpected error: {str(e)}"}
