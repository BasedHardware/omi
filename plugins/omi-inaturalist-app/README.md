# iNaturalist Wildlife Lookup for Omi

A standalone Omi chat-tool service for public taxonomy and regional observation
summaries. Example questions: “What is the scientific name of a monarch?” and
“Which birds have people reported in Michigan in September?” No iNaturalist
account, API key, or Omi device is required to run the service.

## Tools

| Tool | Required parameters | Optional parameters |
|---|---|---|
| `search_inaturalist_taxa` | `query` | `limit` (1–10, default 5) |
| `get_inaturalist_taxon` | `taxon_id` | None |
| `search_inaturalist_places` | `query` | `limit` (1–10, default 5) |
| `get_inaturalist_observed_taxa` | `place_id` | `taxon_id`, `month` (1–12), `limit` |

Search first and select the intended taxon or full place name. A common name can
match several ranks and species; the service does not silently choose one.
Observation summaries include only research-grade community reports. Counts are
reports, not animal abundance, a complete species inventory, or current presence.
A month filter covers that calendar month across all years. Empty results do not
establish absence. Taxon ranks are shown because observation “species counts” can
include other ranks. This service does not perform image identification or make
edibility claims.

## Run locally

Use Python 3.11+ from this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080 --workers 1 --no-access-log
```

On Windows, use the corresponding `.venv\Scripts\python` and
`.venv\Scripts\uvicorn` executables. Requests are POSTs with a JSON object:

```bash
curl -sS http://127.0.0.1:8080/tools/search_inaturalist_taxa \
  -H 'Content-Type: application/json' -d '{"query":"Danaus plexippus"}'
curl -sS http://127.0.0.1:8080/tools/get_inaturalist_taxon \
  -H 'Content-Type: application/json' -d '{"taxon_id":48662}'
curl -sS http://127.0.0.1:8080/tools/search_inaturalist_places \
  -H 'Content-Type: application/json' -d '{"query":"Michigan"}'
curl -sS http://127.0.0.1:8080/tools/get_inaturalist_observed_taxa \
  -H 'Content-Type: application/json' -d '{"place_id":29,"taxon_id":3,"month":9}'
```

Responses contain exactly one of `{"result":"..."}` or `{"error":"..."}`.
Tool validation and upstream errors use HTTP 200 with the `error` field. Omi can
send omitted optional arguments as `null`; both forms use the default limit of 5
and omit optional taxon/month filters. Required parameters cannot be null. Standard
Omi context fields (`uid`, `app_id`, `tool_name`, `geolocation`) are accepted but
ignored: they are never sent to iNaturalist or used in the cache. Only explicit
tool parameters are sent upstream. The service stores no credentials, individual
observation records, or user state. Access logging is disabled in launch commands;
configure any hosting proxy to avoid recording request bodies or user context.

## Hosting and Omi registration

The included Procfile and Railway descriptor target this directory as the service
root, with Python 3.11, port `$PORT` (8080 by default), and `/health` as health check.
Deployment is a separate operator action. Run **one worker and one replica** for
the shared outbound request budget. Horizontal scaling requires a shared limiter;
adding replicas or outbound IPs to work around provider limits is unsupported.

After hosting on HTTPS, set the Omi External Integration app's **App Home URL**
to the service origin, `https://YOUR-SERVICE`, and its **Chat Tools Manifest URL**
to `https://YOUR-SERVICE/.well-known/omi-tools.json`. Omi resolves the four relative
POST endpoints against App Home URL, so both settings are needed. The tools use
`auth_required: false`. This matches the
[Omi chat-tool contract](https://docs.omi.me/doc/developer/apps/ChatTools).

## API behavior and limits

- Uses only the fixed `https://api.inaturalist.org/v1` host, public GET endpoints,
  and an identifying `Omi-iNaturalist-Integration/1.0` User-Agent; redirects are
  refused. No photos or other media are downloaded.
- All tools share one request-start budget: at least one second apart and at
  most 10,000 requests in a rolling 24-hour period per running process. Ordinary
  back-to-back calls await pacing. Provider 429 cooldowns and the daily budget
  return explicit errors, with no automatic retries. Restarts reset local budgets.
- Cache: at most 64 successful responses, five-minute TTL, with the original
  fetch time included in the result. Cache hits do not consume provider requests.
- Upstream timeout: 15 seconds; response body: at most 1 MiB; output: at most
  10 selected records, with bounded text fields. No upstream error body is echoed.
- Follow iNaturalist's [API recommended practices](https://www.inaturalist.org/pages/api%2Brecommended%2Bpractices)
  and [API reference](https://api.inaturalist.org/v1/docs/). See also their
  [explanation of taxa counts](https://help.inaturalist.org/en/support/solutions/articles/151000194813-how-does-inaturalist-count-taxa-).

## Architecture and tests

`main.py` is the FastAPI adapter. `inaturalist.py` owns the manifest, validated
parameter contract, public transport, response formatting, cache, and request
budget. The same parameter definitions drive both the manifest and validation.

Run the hermetic component suite without installing dependencies:

```bash
python3 test_inaturalist.py -v
```

The suite executes production behavior through injected HTTP, clock and sleep
seams; it does not make network calls or sleep. It runs in both local and CI lanes
via `inaturalist-plugin-tests` in `.github/checks-manifest.yaml`. It covers the
normal search-to-detail flow, ambiguous ranks, place selection, observation
filters, invalid inputs, malformed/upstream errors, transport bounds, context
exclusion, caching, concurrent pacing, long cooldowns, and rolling daily limits.

Separately exercise the actual running service with the curl examples above;
these use the public network and belong outside CI. Before a contribution, run
`make preflight` and `scripts/pr-preflight` with the draft PR body from the
repository root. Running this service does not register or publish an Omi app.
