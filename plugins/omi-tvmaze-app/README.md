# TVmaze Omi App

Search TV shows, find next-episode air dates, and see tonight's TV schedule from Omi conversations.

This is a standalone no-auth Omi app backed by the public TVmaze API. It does not require environment variables, OAuth, or API keys.

## Tools

- `search_shows`: search shows by name and see channel, status, rating, and genres.
- `get_next_episode`: next episode air date for a show, plus the latest episode for context.
- `get_tonights_schedule`: tonight's broadcast/streaming schedule for a two-letter country code (default `US`).

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

Example show search:

```bash
curl -X POST http://localhost:8080/tools/search_shows \
  -H "Content-Type: application/json" \
  -d '{"query":"severance"}'
```

Example next-episode request:

```bash
curl -X POST http://localhost:8080/tools/get_next_episode \
  -H "Content-Type: application/json" \
  -d '{"show":"the bear"}'
```

Example schedule request:

```bash
curl -X POST http://localhost:8080/tools/get_tonights_schedule \
  -H "Content-Type: application/json" \
  -d '{"country":"US"}'
```

## Deployment

Deploy this folder as a standalone FastAPI service. Railway can use `railway.toml`; Heroku-style platforms can use the `Procfile`.

## Notes

- Show resolution uses TVmaze's `/search/shows` endpoint and takes the best match.
- Ended shows report their final aired episode instead of a next-episode date.
- Schedule output is capped at 15 items so chat responses stay readable.
