"""GitHub public no-auth chat tools app for Omi."""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import (
    ChatToolResponse,
    GetLatestReleaseRequest,
    GetRepositoryRequest,
    ListIssuesRequest,
    SearchRepositoriesRequest,
)

API_BASE = "https://api.github.com"
TIMEOUT = 20
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "omi-github-public-app",
    "X-GitHub-Api-Version": "2022-11-28",
}

app = FastAPI(
    title="GitHub Public Omi Integration",
    description="No-auth public GitHub chat tools for Omi",
    version="1.0.0",
)


def safe_path(value: str) -> str:
    return quote(value.strip(), safe="")


def short_text(value: str | None, limit: int = 280) -> str:
    if not value:
        return ""
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_topics(topics: List[str]) -> str:
    return ", ".join(topics[:8]) if topics else "None"


async def github_get(path: str, params: Dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


@app.get("/.well-known/omi-tools.json")
async def manifest() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "search_github_repositories",
                "description": "Search public GitHub repositories by keyword.",
                "endpoint": "/tools/search_github_repositories",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Repository search keywords"},
                        "language": {"type": "string", "description": "Optional programming language filter"},
                        "sort": {
                            "type": "string",
                            "description": "Sort by best_match, stars, forks, or updated",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max results (1-10, default 5)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_github_repository",
                "description": "Get a public GitHub repository summary.",
                "endpoint": "/tools/get_github_repository",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                    },
                    "required": ["owner", "repo"],
                },
            },
            {
                "name": "list_github_issues",
                "description": "List recent public GitHub issues for a repository, excluding pull requests.",
                "endpoint": "/tools/list_github_issues",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "state": {"type": "string", "description": "open, closed, or all"},
                        "labels": {"type": "string", "description": "Optional comma-separated labels"},
                        "max_results": {
                            "type": "integer",
                            "description": "Max results (1-10, default 5)",
                        },
                    },
                    "required": ["owner", "repo"],
                },
            },
            {
                "name": "get_latest_github_release",
                "description": "Get the latest public release for a GitHub repository.",
                "endpoint": "/tools/get_latest_github_release",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                    },
                    "required": ["owner", "repo"],
                },
            },
        ]
    }


@app.post("/tools/search_github_repositories", response_model=ChatToolResponse)
async def search_repositories(req: SearchRepositoriesRequest) -> ChatToolResponse:
    search_terms = [req.query.strip()]
    if req.language:
        search_terms.append(f"language:{req.language.strip()}")

    params: Dict[str, Any] = {
        "q": " ".join(search_terms),
        "per_page": req.max_results,
    }
    if req.sort != "best_match":
        params["sort"] = req.sort

    try:
        data = await github_get("/search/repositories", params)
        items = data.get("items", [])
        if not items:
            return ChatToolResponse(result="No repositories found.")

        lines = []
        for i, repo in enumerate(items, start=1):
            full_name = repo.get("full_name") or "unknown"
            description = short_text(repo.get("description"), 180) or "No description."
            language = repo.get("language") or "Unknown"
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            updated = repo.get("updated_at") or "Unknown"
            url = repo.get("html_url") or ""
            lines.append(
                f"{i}. {full_name}\n"
                f"   {description}\n"
                f"   Language: {language} | Stars: {stars} | Forks: {forks} | Updated: {updated}\n"
                f"   URL: {url}"
            )
        return ChatToolResponse(result="\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"GitHub API error: {exc.response.status_code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.post("/tools/get_github_repository", response_model=ChatToolResponse)
async def get_repository(req: GetRepositoryRequest) -> ChatToolResponse:
    try:
        owner = safe_path(req.owner)
        repo_name = safe_path(req.repo)
        repo = await github_get(f"/repos/{owner}/{repo_name}")

        license_info = repo.get("license") or {}
        topics = repo.get("topics") or []
        result = (
            f"Repository: {repo.get('full_name', f'{req.owner}/{req.repo}')}\n"
            f"Description: {short_text(repo.get('description'), 300) or 'No description.'}\n"
            f"Language: {repo.get('language') or 'Unknown'}\n"
            f"Stars: {repo.get('stargazers_count', 0)} | Forks: {repo.get('forks_count', 0)} | Open issues: {repo.get('open_issues_count', 0)}\n"
            f"License: {license_info.get('spdx_id') or 'Unknown'}\n"
            f"Topics: {format_topics(topics)}\n"
            f"Default branch: {repo.get('default_branch') or 'Unknown'}\n"
            f"Updated: {repo.get('updated_at') or 'Unknown'}\n"
            f"URL: {repo.get('html_url') or ''}"
        )
        return ChatToolResponse(result=result)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            return ChatToolResponse(error="Repository not found or not public.")
        return ChatToolResponse(error=f"GitHub API error: {code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.post("/tools/list_github_issues", response_model=ChatToolResponse)
async def list_issues(req: ListIssuesRequest) -> ChatToolResponse:
    params: Dict[str, Any] = {
        "state": req.state,
        "per_page": min(req.max_results * 2, 20),
        "sort": "updated",
        "direction": "desc",
    }
    if req.labels:
        params["labels"] = req.labels

    try:
        owner = safe_path(req.owner)
        repo_name = safe_path(req.repo)
        data = await github_get(f"/repos/{owner}/{repo_name}/issues", params)
        issues = [item for item in data if "pull_request" not in item][: req.max_results]
        if not issues:
            return ChatToolResponse(result="No matching issues found.")

        lines = []
        for issue in issues:
            labels = ", ".join(label.get("name", "") for label in issue.get("labels", []) if label.get("name"))
            body = short_text(issue.get("body"), 220)
            lines.append(
                f"#{issue.get('number')} {issue.get('title')}\n"
                f"   State: {issue.get('state')} | Updated: {issue.get('updated_at')}\n"
                f"   Labels: {labels or 'None'}\n"
                + (f"   Summary: {body}\n" if body else "")
                + f"   URL: {issue.get('html_url')}"
            )
        return ChatToolResponse(result="\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            return ChatToolResponse(error="Repository not found or issues are unavailable.")
        return ChatToolResponse(error=f"GitHub API error: {code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.post("/tools/get_latest_github_release", response_model=ChatToolResponse)
async def get_latest_release(req: GetLatestReleaseRequest) -> ChatToolResponse:
    try:
        owner = safe_path(req.owner)
        repo_name = safe_path(req.repo)
        release = await github_get(f"/repos/{owner}/{repo_name}/releases/latest")
        body = short_text(release.get("body"), 500)
        result = (
            f"Latest release: {release.get('name') or release.get('tag_name') or 'Unnamed release'}\n"
            f"Tag: {release.get('tag_name') or 'Unknown'}\n"
            f"Published: {release.get('published_at') or 'Unknown'}\n"
            f"Draft: {release.get('draft')} | Prerelease: {release.get('prerelease')}\n"
            + (f"Notes: {body}\n" if body else "")
            + f"URL: {release.get('html_url') or ''}"
        )
        return ChatToolResponse(result=result)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            return ChatToolResponse(error="No public latest release found for this repository.")
        return ChatToolResponse(error=f"GitHub API error: {code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "GitHub Public Omi integration is running."}
