# Omi Semantic Scholar App

A standalone no-auth Omi integration app that provides chat tools for discovering academic papers from Semantic Scholar.

## Tools

- `search_semantic_scholar_papers`: Search papers by keyword.
- `get_semantic_scholar_paper`: Fetch paper details by Semantic Scholar paper ID or DOI.
- `get_semantic_scholar_author_papers`: Get recent papers by author ID.

## Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

## Manifest

The Omi tools manifest is served at:

- `/.well-known/omi-tools.json`
