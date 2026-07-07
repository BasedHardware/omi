# Omi Crossref App

A no-auth Crossref integration app for Omi chat tools.

## Tools
- `search_crossref_works`: search scholarly works by query
- `get_crossref_work`: fetch work details by DOI
- `get_crossref_works_by_author`: list recent works by author name

## Run locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

## Deploy
Deploy this folder on Railway/Heroku-style hosts using the included `Procfile`/`railway.toml`.
