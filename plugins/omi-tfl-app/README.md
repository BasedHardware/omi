# London Transit for Omi

Check London's line disruptions, find a stop and look up its next arrivals from
an Omi conversation. The app uses Transport for London's public Unified API.
It requires no account, API key, OAuth or Omi hardware for local development.

## Tools

| Tool | Example | Result |
| --- | --- | --- |
| `get_line_status` | `{"line_ids":["victoria","central"]}` | Current status and disruption reasons. Omit IDs for Tube lines only. |
| `find_stops` | `{"query":"Oxford Circus","mode":"tube"}` | Stop names, modes and exact IDs; does not silently select an ambiguous match. |
| `get_arrivals` | `{"stop_id":"940GZZLUOXC","limit":5}` | Upcoming predictions ordered by absolute arrival time, including platform, destination and the provider's report time. |

All tools accept JSON POST bodies and return Omi's `result` or `error` string.
Omi's extra `uid`, `app_id` and `tool_name` fields are ignored and never sent to
TfL. Queries go to TfL; this app stores no conversation or user data.

Predictions are presented in UTC with explicit offsets; the chat assistant can
convert them to the user's timezone. Cached `timeToStation` countdowns are not
presented as current countdowns. Predictions marked deleted by TfL, past their
provider expiry time, or past their expected arrival are removed. No predictions
does **not** mean no service; missing line status is explicitly unknown.

## Run and connect

From this directory, with Python 3.11 or later:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080 --workers 1
```

Check `/health`, inspect `/.well-known/omi-tools.json`, or try:

```bash
curl -X POST http://127.0.0.1:8080/tools/find_stops \
  -H 'Content-Type: application/json' \
  -d '{"query":"Oxford Circus","mode":"tube"}'
```

For an Omi app, host this directory with its dependencies behind HTTPS, using
`uvicorn main:app --host 0.0.0.0 --port "$PORT" --workers 1`. Add the deployed
manifest URL using the [Omi chat tools guide](https://docs.omi.me/doc/developer/apps/ChatTools).
Select **External Integration** and fill in **Chat Tools Manifest URL**; set
**App Home URL** to the service root so relative tool URLs resolve correctly.
There is no account-connection flow. Hosting
and app-store registration are separate from running this example locally.

TfL [allows 50 anonymous requests per minute](https://api-portal.tfl.gov.uk/products).
The client caps itself at 40 per rolling minute, including concurrent requests,
with no automatic retries. This bound is **per process**: run one worker and one
replica, and account for other apps sharing your public IP. For larger deployments,
use a shared rate limiter and the appropriate TfL subscription. Upstream rate
limits and failures are returned explicitly, without exposing provider error bodies.

## Verification

From the repository root:

```bash
python3 plugins/omi-tfl-app/test_transit.py
make preflight
```

The hermetic tests exercise the production dispatch, output semantics and HTTP
transport through controlled seams, including expired predictions, missing data,
bad input, provider failures and quota recovery. They require only Python's
standard library and run in the existing local/CI check manifest. A live smoke
test uses the running server and sample requests above; it is separate from CI.

Powered by TfL Open Data. This is an independent integration, not an official
TfL app. Contains OS data © Crown copyright and database rights 2016. Geomni UK
Map data © and database rights [2019]. Preserve the attributions returned by
the tools and follow TfL's [transport data terms](https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service), including its registration requirements before public deployment.
Endpoint and response contracts: [TfL Unified API specification](https://api.tfl.gov.uk/swagger/docs/v1).
