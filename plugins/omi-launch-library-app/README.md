# Launch Library 2 Omi App

Check upcoming rocket launches, search launch records, and inspect launch
details from Omi conversations.

This is a standalone no-auth app backed by the public Launch Library 2 API from
The Space Devs. It requires no account, OAuth connection, API key, or
environment variable.

## Tools

- `get_upcoming_launches`: list launches scheduled in the next 1-365 days,
  optionally filtered by launch service provider or rocket.
- `search_launches`: search public launch records by text, provider, rocket, or
  UTC date range.
- `get_launch`: retrieve a concise launch summary by its Launch Library UUID or
  API URL.

## Attribution and limits

Launch data is provided by [The Space Devs Launch Library
2](https://thespacedevs.com/llapi). Tool responses include a source link, and
the API currently documents a free allowance of 15 requests per hour.

The app performs one upstream request per tool call, treats upstream `429`
responses as a safe user-facing rate-limit message, does not send Omi user
identifiers, caps responses at 5 MiB, and uses bounded request timeouts.

## Example requests

```bash
curl -X POST http://localhost:8080/tools/get_upcoming_launches \
  -H "Content-Type: application/json" \
  -d '{"days":30,"provider":"SpaceX","limit":3}'
```

```bash
curl -X POST http://localhost:8080/tools/search_launches \
  -H "Content-Type: application/json" \
  -d '{"query":"Starlink","start_date":"2026-09-01","end_date":"2026-10-31"}'
```

```bash
curl -X POST http://localhost:8080/tools/get_launch \
  -H "Content-Type: application/json" \
  -d '{"launch_id":"5af31461-bce5-4cfb-a0ee-b527cf285d90"}'
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Run the hermetic tests:

```bash
python test_main.py
```

Health check: `GET /health`

Tool manifest: `GET /.well-known/omi-tools.json`
