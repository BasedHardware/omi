# DuckDuckGo Instant Answers & Search Integration for Omi

Provides real-time instant factual summaries, definitions, and web entity disambiguation through DuckDuckGo's public Instant Answers API directly into Omi chat tools.

## Features

- **Instant Answers (`/tools/instant_answer`)**: Factual summaries, Wikipedia entity abstracts, math calculations, and source citations without browsing overhead.
- **Related Topics & Disambiguation (`/tools/search_topics`)**: Topic exploration with snippet descriptions and direct URLs.
- **Dictionary Definitions (`/tools/define_term`)**: Quick word definitions and origin references.
- **Zero Authentication / Keys Required**: Free public API with no tokens or subscription limits.
- **100% Hermetic Tests**: Instant deterministic unit test suite in standard Python.

## Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/tools/instant_answer` | `POST` | Get instant abstract or direct calculation/fact for a query. |
| `/tools/search_topics` | `POST` | Retrieve related topics and disambiguation snippets. |
| `/tools/define_term` | `POST` | Look up dictionary definitions. |
| `/` | `GET` | HTML documentation and app dashboard. |
| `/manifest.json` | `GET` | Omi integration plugin manifest. |
| `/health` | `GET` | Service health status. |
| `/privacy` | `GET` | Privacy policy. |

## Running Locally

```bash
cd plugins/omi-duckduckgo-app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Running Tests

```bash
python3 plugins/omi-duckduckgo-app/test_main.py
```
