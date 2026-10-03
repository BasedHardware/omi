# openFDA Omi App

Search FDA drug recalls, drug label information, and food recalls from Omi conversations.

This is a standalone no-auth Omi app backed by the public openFDA API. It does not require environment variables, OAuth, or API keys (openFDA's free tier covers casual use without a key).

## Tools

- `search_drug_recalls`: FDA drug recall (enforcement) reports by product name or keyword — product, recalling firm, classification, reason, and initiation date.
- `get_drug_info`: FDA drug label summary — brand/generic names, manufacturer, purpose, warnings, and drug interactions.
- `search_food_recalls`: FDA food recall reports by food name, allergen, or keyword.

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

Example drug-recall search:

```bash
curl -X POST http://localhost:8080/tools/search_drug_recalls \
  -H "Content-Type: application/json" \
  -d '{"query":"metformin"}'
```

Example drug-info request:

```bash
curl -X POST http://localhost:8080/tools/get_drug_info \
  -H "Content-Type: application/json" \
  -d '{"drug":"tylenol"}'
```

Example food-recall search:

```bash
curl -X POST http://localhost:8080/tools/search_food_recalls \
  -H "Content-Type: application/json" \
  -d '{"query":"peanut"}'
```

## Deployment

Deploy this folder as a standalone FastAPI service. Railway can use `railway.toml`; Heroku-style platforms can use the `Procfile`.

## Notes

- openFDA returns most fields as one-element lists; helpers unwrap them safely.
- Results are capped at 5 items so chat responses stay readable.
- A 404 from openFDA means "no matches" — the app reports it as an empty result, not an error.
