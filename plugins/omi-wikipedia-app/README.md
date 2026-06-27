# Wikipedia Omi App

Search and read Wikipedia from Omi chat tools. This app is useful for quick background research, definitions, people/place lookups, and random topic discovery without leaving a conversation.

## Features

- Search Wikipedia articles by keyword
- Fetch concise article summaries by title
- Discover a random article
- Optional language-code support, defaulting to English
- No OAuth, accounts, or API keys required

## Chat Tools

### `search_articles`

Searches Wikipedia using the MediaWiki API.

Parameters:

- `query` (required): topic, person, place, event, or concept to search
- `language` (optional): Wikipedia language code, defaults to `en`
- `limit` (optional): maximum results, defaults to 5 and caps at 10

### `get_article_summary`

Fetches a concise summary for a Wikipedia page using the REST summary endpoint.

Parameters:

- `title` (required): exact or near-exact article title
- `language` (optional): Wikipedia language code, defaults to `en`

### `get_random_article`

Returns a random article summary.

Parameters:

- `language` (optional): Wikipedia language code, defaults to `en`

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Open:

- `http://localhost:8080/health`
- `http://localhost:8080/.well-known/omi-tools.json`

## Deployment

Deploy this folder as a standalone FastAPI service. The app does not require environment variables.

Railway can use the included `Procfile`:

```bash
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Notes

Wikimedia asks API clients to send an identifying user agent. This app sets a static Omi integration user agent for all outbound requests.
