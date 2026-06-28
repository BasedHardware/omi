# Open Library x Omi

Search books, fetch metadata, and browse subject recommendations from Omi conversations.

This is a standalone no-auth Omi app backed by the public Open Library APIs. It does not require environment variables, OAuth, or an Open Library API key.

## Tools

- `search_books`: search books by free-form query, optional author, and optional subject.
- `get_book_details`: fetch work metadata by Open Library work ID or edition metadata by ISBN.
- `search_subject`: browse notable books for a subject such as fantasy, economics, or machine learning.

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

Search books:

```bash
curl -X POST http://localhost:8080/tools/search_books \
  -H "Content-Type: application/json" \
  -d '{"query":"The Left Hand of Darkness", "limit":3}'
```

Fetch work details:

```bash
curl -X POST http://localhost:8080/tools/get_book_details \
  -H "Content-Type: application/json" \
  -d '{"work_id":"OL59895W"}'
```

Browse a subject:

```bash
curl -X POST http://localhost:8080/tools/search_subject \
  -H "Content-Type: application/json" \
  -d '{"subject":"science fiction", "limit":5}'
```

## Deployment

The app is ready for Railway or Heroku-style deployment:

- `Procfile` starts uvicorn on `$PORT`
- `railway.toml` defines the same start command and `/health` check
- `runtime.txt` pins Python 3.11

## Notes

Open Library is a public community catalog. Metadata completeness varies by work and edition, so some fields may be missing for less common books.
