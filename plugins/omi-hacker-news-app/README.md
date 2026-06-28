# Hacker News Omi Integration

Read Hacker News from Omi with chat tools. This app does not require user auth.

## Tools

- `get_front_page`: returns current front page stories.
- `search_stories`: searches Hacker News stories by keyword, sorted by relevance or date.
- `get_discussion`: fetches a story/item plus top-level comments.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080/.well-known/omi-tools.json` to inspect the Omi tools manifest.

## Deployment

Deploy this folder as a standalone FastAPI service. No environment variables are required.

## Example Requests

```bash
curl -X POST http://localhost:8080/tools/get_front_page \
  -H 'Content-Type: application/json' \
  -d '{"limit": 5}'
```

```bash
curl -X POST http://localhost:8080/tools/search_stories \
  -H 'Content-Type: application/json' \
  -d '{"query": "open source", "sort_by": "date", "limit": 5}'
```

```bash
curl -X POST http://localhost:8080/tools/get_discussion \
  -H 'Content-Type: application/json' \
  -d '{"item_id": 8863, "comment_limit": 3}'
```
