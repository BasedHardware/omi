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

## Abstract text and regression checks
DOI lookup converts JATS/HTML abstracts to plain text before the 1,200-character
limit. Paragraphs remain separated; inline character data and escaped literal
angle brackets are preserved. This does not render mathematical layout.

Run the hermetic handler tests (standard library only):
```bash
python3 plugins/omi-crossref-app/test_main.py
```
Run this from the repository root. The tests import the production module with
temporary framework/model doubles and replace only the provider call; they do
not exercise HTTP routing or a deployed UI. The checks manifest runs them in
both local preflight and CI.
