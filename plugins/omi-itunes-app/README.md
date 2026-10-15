# iTunes Omi App

Search songs, podcasts, and artist top tracks from Omi conversations.

This is a standalone no-auth Omi app backed by Apple's public iTunes Search API. It does not require environment variables, OAuth, or API keys.

## Tools

- `search_songs`: search songs by title, artist, or album — track, artist, album, and duration.
- `search_podcasts`: search podcasts by name or topic — title, host, and genre.
- `get_artist_top_songs`: an artist's top songs on iTunes.

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

Example song search:

```bash
curl -X POST http://localhost:8080/tools/search_songs \
  -H "Content-Type: application/json" \
  -d '{"query":"daft punk get lucky"}'
```

Example podcast search:

```bash
curl -X POST http://localhost:8080/tools/search_podcasts \
  -H "Content-Type: application/json" \
  -d '{"query":"technology"}'
```

Example artist request:

```bash
curl -X POST http://localhost:8080/tools/get_artist_top_songs \
  -H "Content-Type: application/json" \
  -d '{"query":"radiohead"}'
```

## Deployment

Deploy this folder as a standalone FastAPI service. Railway can use `railway.toml`; Heroku-style platforms can use the `Procfile`.

## Notes

- Artist resolution uses the iTunes `musicArtist` entity search, then a `lookup` for that artist's songs sorted by popularity.
- Results are capped at 10 items so chat responses stay readable.
- The artist row in the lookup response is filtered out so only songs are listed.
