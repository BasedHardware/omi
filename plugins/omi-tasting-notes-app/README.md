# Omi Tasting Notes App

Stay in the moment at tastings — no phone, no notebook. Omi captures the
conversation; this app turns it into structured tasting cards.

## What it does

Two capture paths:

1. **Chat tools (explicit)** — ask Omi to "log this tasting" and dictate or
   confirm the structured fields: beverage, name, producer, vintage, region,
   varietal, nose / palate / finish notes, 0–100 score, buy / skip / cellar verdict.
2. **Ambient webhook (implicit)** — Omi posts the finished `Conversation` to
   `/webhook/tasting-candidate` (it appends `?uid=<user-id>` itself). The app scores the transcript
   against a weighted tasting vocabulary (wine, coffee, whiskey, beer),
   extracts a normalized score ("94 points", "4.5 stars", "9/10") and a
   buy/skip verdict from explicit purchase language, and stores strong matches
   as candidates flagged `needs_review`. List them with `list_candidates` and
   confirm them with the `confirm_candidate` chat tool.

Scores are normalized to a 100-point scale. Storage is per-user JSON files —
no external database or API keys required.

## Tools

| Tool | Description |
|---|---|
| `log_tasting` | Record a structured tasting from chat |
| `list_tastings` | List recent tastings, newest first, filterable by beverage |
| `list_candidates` | List ambient-detected candidates awaiting review |
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

Run tests (stdlib-only, no pytest needed):

```bash
python3 test_main.py
```

Data is stored under `./data` (override with `TASTING_DATA_DIR`).

## Deploy

Runs on any container host — `Dockerfile` included; Railway via
`railway.toml` + `Procfile`. Health check: `/health`.

**Persistence:** tastings live in JSON files under `TASTING_DATA_DIR`.
Hosts with ephemeral disks (Fly.io machines, Railway without a volume) wipe
them on every deploy/restart, so mount a persistent volume and point
`TASTING_DATA_DIR` at it. On Fly.io, volumes are per-machine — run a single
machine so one user's data never splits across disks.

**Security:** there is no authentication. Anyone who knows a uid can read and
write that user's tastings. Tasting notes are low-sensitivity data, but treat
uids as bearer tokens and don't share them.

## Wiring the ambient webhook

Point Omi's conversation webhook at the bare URL
`https://<your-host>/webhook/tasting-candidate` — Omi appends
`?uid=<omi-user-id>` itself, so don't add it.
Omi posts the standard `Conversation` payload (`transcript_segments`,
`structured`, …); the uid arrives as a query parameter, following the same
convention as the other `omi-*-app` webhook endpoints. Only conversations
that clear the tasting-signal threshold are stored; everything else is
ignored.
