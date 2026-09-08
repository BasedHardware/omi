# Omi PubMed App

PubMed chat tools integration for Omi. This app uses the public NCBI E-utilities API (no OAuth/API key required).

## Tools
- `search_pubmed`: Search PubMed by query and return top matches.
- `get_pubmed_article`: Fetch article details for a PubMed ID.
- `get_related_pubmed`: Get related articles from a PubMed ID.

## Run locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

## Omi manifest URL
`/.well-known/omi-tools.json`

## Health check
`/health`
