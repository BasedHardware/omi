# Stack Overflow x Omi

Search Stack Overflow and read top answers from Omi conversations.

This is a standalone no-auth Omi app backed by the public Stack Exchange API. It does not require environment variables, OAuth, or a Stack Exchange API key.

## Tools

- `search_questions`: search Stack Overflow or another Stack Exchange site by query, optional tags, and accepted-answer status.
- `get_question`: fetch a specific question by ID with title, metadata, tags, link, and body excerpt.
- `get_top_answers`: fetch the highest-voted answers for a question.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

Tool manifest:

```bash
curl http://localhost:8080/.well-known/omi-tools.json
```

Search Stack Overflow:

```bash
curl -X POST http://localhost:8080/tools/search_questions \
  -H "Content-Type: application/json" \
  -d '{"query":"fastapi dependency injection", "tags":"python;fastapi", "limit":3}'
```

Fetch top answers:

```bash
curl -X POST http://localhost:8080/tools/get_top_answers \
  -H "Content-Type: application/json" \
  -d '{"question_id":11227809, "limit":2}'
```

## Deployment

The app is ready for Railway or Heroku-style deployment:

- `Procfile` starts uvicorn on `$PORT`
- `railway.toml` defines the same start command and `/health` check
- `runtime.txt` pins Python 3.11

## Notes

Unauthenticated Stack Exchange API calls are rate limited by Stack Exchange. The app keeps responses concise and caps result limits to reduce quota usage.
