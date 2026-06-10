# arXiv x Omi

Search arXiv papers, inspect paper metadata, and find recent papers by author from Omi conversations.

This is a standalone no-auth Omi app backed by the public arXiv API. It does not require environment variables, OAuth, or API keys.

## Tools

- `search_papers`: search arXiv by topic, title, author, category, or free-form query.
- `get_paper_details`: fetch metadata for a specific arXiv paper ID.
- `search_author`: find recent arXiv papers from a named author.

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

Search papers:

```bash
curl -X POST http://localhost:8080/tools/search_papers \
  -H "Content-Type: application/json" \
  -d '{"query":"retrieval augmented generation", "limit":3}'
```

Fetch details:

```bash
curl -X POST http://localhost:8080/tools/get_paper_details \
  -H "Content-Type: application/json" \
  -d '{"paper_id":"2401.01234"}'
```

Search an author:

```bash
curl -X POST http://localhost:8080/tools/search_author \
  -H "Content-Type: application/json" \
  -d '{"author":"Yoshua Bengio", "limit":3}'
```

## Deployment

The app is ready for Railway or Heroku-style deployment:

- `Procfile` starts uvicorn on `$PORT`
- `railway.toml` defines the same start command and `/health` check
- `runtime.txt` pins Python 3.11

## Notes

arXiv metadata is returned from a public Atom feed. Result freshness, category labels, and abstracts depend on arXiv records.
