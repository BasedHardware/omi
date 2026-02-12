"""
Agent provider integrations for coding features.
Calls external agent APIs (Cursor Agent, Devin).
"""
from __future__ import annotations

import os
from typing import Dict, Any, Optional

import requests

DEFAULT_BASE_URLS: Dict[str, str] = {
    "cursor": "https://api.cursor.com",
    "devin": "https://api.devin.ai/v1",
}

PROVIDERS: Dict[str, Dict[str, str]] = {
    "cursor": {
        "label": "Cursor Agent",
        "env_url": "CURSOR_AGENT_API_URL",
        "env_key": "CURSOR_AGENT_API_KEY",
        "env_endpoint": "CURSOR_AGENT_API_ENDPOINT",
        "env_auth_header": "CURSOR_AGENT_API_AUTH_HEADER",
        "env_auth_prefix": "CURSOR_AGENT_API_AUTH_PREFIX",
    },
    "devin": {
        "label": "Devin",
        "env_url": "DEVIN_API_URL",
        "env_key": "DEVIN_API_KEY",
        "env_endpoint": "DEVIN_API_ENDPOINT",
        "env_auth_header": "DEVIN_API_AUTH_HEADER",
        "env_auth_prefix": "DEVIN_API_AUTH_PREFIX",
    },
}


def get_provider_config(provider: str) -> Dict[str, str]:
    provider_key = provider.lower().strip()
    if provider_key not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    return PROVIDERS[provider_key]


def get_provider_label(provider: str) -> str:
    return get_provider_config(provider)["label"]


def get_provider_base_url(provider: str) -> Optional[str]:
    config = get_provider_config(provider)
    env_url = os.getenv(config["env_url"])
    if env_url:
        return env_url
    return DEFAULT_BASE_URLS.get(provider.lower().strip())


def get_provider_default_key(provider: str) -> Optional[str]:
    config = get_provider_config(provider)
    return os.getenv(config["env_key"])


def _build_headers(provider: str, api_key: Optional[str]) -> Dict[str, str]:
    if not api_key:
        return {}

    config = get_provider_config(provider)
    header_name = os.getenv(config["env_auth_header"], "Authorization")
    prefix = os.getenv(config["env_auth_prefix"], "Bearer ")
    return {header_name: f"{prefix}{api_key}"}


def run_agent_provider(
    provider: str,
    repo_full_name: str,
    feature_description: str,
    branch_name: str,
    github_token: str,
    api_key: Optional[str],
    merge: bool = False,
    timeout_seconds: int = 300,
    base_url_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call an external agent provider to implement a feature.

    Returns:
        Dict with success, message, data (provider response JSON if available)
    """
    provider_key = provider.lower().strip()
    config = get_provider_config(provider_key)

    base_url = base_url_override or get_provider_base_url(provider_key)
    if not base_url:
        return {
            "success": False,
            "message": f"Missing {config['env_url']} for {config['label']} API URL"
        }

    if provider_key == "cursor":
        endpoint = os.getenv(config["env_endpoint"], "/v0/agents")
    elif provider_key == "devin":
        endpoint = os.getenv(config["env_endpoint"], "/sessions")
    else:
        endpoint = os.getenv(config["env_endpoint"], "/run")
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{repo_full_name}"

    if provider_key == "cursor":
        payload = {
            "prompt": {
                "text": feature_description
            },
            "source": {
                "repository": repo_url
            },
            "target": {
                "autoCreatePr": True,
                "branchName": branch_name,
                "openAsCursorGithubApp": False,
                "skipReviewerRequest": False
            }
        }
    elif provider_key == "devin":
        if api_key and api_key.startswith("cog_"):
            return {
                "success": False,
                "message": (
                    "Devin v3 service-user keys (cog_) are not supported by the v1 /sessions endpoint. "
                    "Generate a v1 personal/service key (apk_user_*/apk_*) or provide a v3 base URL."
                )
            }
        payload = {
            "prompt": f"{feature_description}\n\nRepo: {repo_url}",
            "title": f"Repo task: {feature_description[:60]}",
            "tags": [repo_full_name]
        }
    else:
        payload = {
            "provider": provider_key,
            "feature": feature_description,
            "branch": branch_name,
            "repo_full_name": repo_full_name,
            "owner": owner,
            "repo": repo,
            "repo_url": repo_url,
            "github_token": github_token,
            "merge": merge,
        }

    callback_url = os.getenv("AGENT_CALLBACK_URL")
    if callback_url:
        payload["callback_url"] = callback_url

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update(_build_headers(provider_key, api_key))

    try:
        if provider_key == "cursor":
            if not api_key:
                return {
                    "success": False,
                    "message": "Missing Cursor API key"
                }
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                auth=(api_key, ""),
                timeout=timeout_seconds
            )
        elif provider_key == "devin":
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds
            )
        else:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)

        if response.status_code in (401, 403) and provider_key == "devin":
            return {
                "success": False,
                "message": (
                    f"Devin API unauthorized ({response.status_code}). "
                    "Ensure you're using a v1 API key (apk_user_*/apk_*) and that it has access to the org. "
                    f"Response: {response.text}"
                )
            }
        if not response.ok:
            return {
                "success": False,
                "message": f"{config['label']} API error: {response.status_code} - {response.text}"
            }

        try:
            data = response.json()
        except ValueError:
            return {
                "success": False,
                "message": f"{config['label']} API returned non-JSON response"
            }

        return {
            "success": True,
            "message": data.get("message") if isinstance(data, dict) else None,
            "data": data,
        }

    except requests.RequestException as exc:
        return {
            "success": False,
            "message": f"{config['label']} API request failed: {str(exc)}"
        }
