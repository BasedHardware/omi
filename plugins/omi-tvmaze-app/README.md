# TVMaze × Omi

Ask Omi “When does the next episode air?” after identifying the correct show.
This standalone, read-only integration searches TVMaze and retrieves a show's
status, channel and next announced episode. It does not stream video, access
watching history, create reminders, or need a TVMaze account/API key.

## Run

Use Python 3.10 or newer, from this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

For hosting, set this directory as the service root, install `requirements.txt`,
and use the included `Procfile` (default port 8080, or the host's `PORT`). The
service needs outbound HTTPS to `api.tvmaze.com`. Hosting is not provisioned by
this contribution. Use a normal HTTPS endpoint when registering the app in Omi.

In Omi, open **Apps → Create App** (or edit an existing app), select the
**External Integration** capability, and enter the deployed
`/.well-known/omi-tools.json` URL in **Chat Tools Manifest URL**. Chat tools
are a feature of external integrations, not a separate capability. No
authentication is required. `/health` checks the service process only; it
does not contact TVMaze.

## Tools

| Tool | Input | Result |
| --- | --- | --- |
| `search_tv_shows` | `query` (1–100 characters), optional `limit` (1–10, default 5) | Distinct show IDs, premiere dates and channels; ask the user to choose if the name is ambiguous. |
| `get_tv_show` | positive integer `show_id` from search | Show status/channel and next announced episode, if TVMaze lists one. |

Each tool accepts a JSON object POST body and returns exactly one of `result`
or `error`. Malformed JSON and non-object bodies use FastAPI's standard HTTP
422 validation response. Missing next-episode data is a successful “not
currently listed” result, not a cancellation claim. Unknown IDs, provider
timeouts, rate limits, truncated/oversized responses, and invalid provider JSON are
explicit tool errors.

```bash
curl -sS http://127.0.0.1:8080/tools/search_tv_shows \
  -H 'Content-Type: application/json' -d '{"query":"Severance","limit":3}'
curl -sS http://127.0.0.1:8080/tools/get_tv_show \
  -H 'Content-Type: application/json' -d '{"show_id":1}'
```

Airtime strings retain the provider's explicit UTC offset. They are not
converted to the user's timezone. When only a date is supplied, the tool does
not invent a time or timezone. TVMaze caches most API output for up to one
hour, and schedules may change. HTTP 429 returns a temporary error so callers
can retry later instead of repeatedly sending requests.

## Verification

Hermetic tests exercise the production handlers and urllib request boundary,
including same-name shows, absent episodes, offset preservation, invalid
inputs and provider failures. They do not call any network service:

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

The same tests are registered for local and CI execution in
`.github/checks-manifest.yaml`; run `make preflight` from the repository root.
The curl examples above are optional live checks and are not run in CI.

## Data and privacy

Requests send only a show-name query or show ID to TVMaze. The service does not
store queries, handle Omi user data, or require credentials. Its provider host
is fixed, responses are limited to 1 MiB and connections use a 10-second timeout.
Search results are capped at ten shows.

The implementation is covered by the repository license. TVMaze data is
separately licensed under [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).
Every successful result includes TVMaze attribution and show results link back
to the provider. Preserve this attribution and applicable ShareAlike terms if
redistributing adapted data. [Official API documentation](https://www.tvmaze.com/api).
