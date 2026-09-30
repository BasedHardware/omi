# Omi Tasting Notes App

Stay in the moment at tastings — no phone, no notebook. Omi captures the
conversation; this app turns it into structured tasting cards.

## What it does

Two capture paths:

1. **Chat tools (explicit)** — ask Omi to "log this tasting" and dictate or
   confirm the structured fields: beverage, name, producer, vintage, region,
   varietal, nose / palate / finish notes, 0–100 score, buy / skip / cellar verdict.
2. **Ambient webhook (implicit)** — POST a conversation transcript to
   `/webhook/tasting-candidate`. The app scores it against a weighted
   tasting vocabulary (wine, coffee, whiskey, beer), extracts a normalized
   score ("94 points", "4.5 stars", "9/10") and a buy/skip verdict from
   explicit purchase language, and stores strong matches as candidates flagged
   `needs_review`. Confirm them later with the `confirm_candidate` chat tool.

Scores are normalized to a 100-point scale. Storage is per-user JSON files —
no external database or API keys required.

## Tools

| Tool | Description |
|---|---|
| `log_tasting` | Record a structured tasting from chat |
| `list_tastings` | List recent tastings, newest first, filterable by beverage |
| `get_tasting` | Fetch one tasting by id |
| `tasting_stats` | Counts, average scores, buy-rate per beverage |
| `confirm_candidate` | Confirm an ambient candidate, applying corrections |

Tool manifest: `/.well-known/omi-tools.json`

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Run tests:

```bash
pytest test_main.py -v
```

Data is stored under `./data` (override with `TASTING_DATA_DIR`).

## Deploy

Railway-ready (`railway.toml` + `Procfile`), or any host that runs
`uvicorn main:app`. Health check: `/health`.

## Wiring the ambient webhook

Point Omi's `memory_created` / conversation webhook at
`https://<your-host>/webhook/tasting-candidate` with a JSON body of
`{"uid": "<omi-user-id>", "text": "<transcript>", "conversation_id": "..."}`.
Only conversations that clear the tasting-signal threshold are stored;
everything else is ignored.
