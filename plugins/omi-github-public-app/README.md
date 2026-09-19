# Omi GitHub Public App

A standalone no-auth Omi integration app that provides chat tools for public GitHub repositories.

The app uses GitHub's public REST API and does not require OAuth, tokens, accounts, or secret configuration. Unauthenticated GitHub API rate limits apply.

## Tools

- `search_github_repositories`: Search public repositories by keyword, optional language, and sort.
- `get_github_repository`: Fetch public repository summary, stars, forks, topics, license, and URLs.
- `list_github_issues`: List recent public issues for a repository, excluding pull requests.
- `get_latest_github_release`: Fetch the latest public release for a repository.

## Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

## Manifest

The Omi tools manifest is served at:

- `/.well-known/omi-tools.json`

## Example Requests

```bash
curl -s http://localhost:8080/tools/search_github_repositories \
  -H 'content-type: application/json' \
  -d '{"query":"wearable ai", "language":"Python", "max_results":3}'
```
