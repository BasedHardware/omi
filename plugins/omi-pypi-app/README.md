# Omi PyPI lookup

Read public Python package metadata from Omi chat. Ask “What Python version does
httpx require?” or “What dependencies did requests 2.32.3 declare?”

This standalone FastAPI integration uses the [PyPI JSON API](https://docs.pypi.org/api/json/).
It needs no PyPI account or API key and never downloads or executes packages.

## Run

Use Python 3.11. From this directory:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080
```

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/tools/get_pypi_package \
  -H 'Content-Type: application/json' -d '{"package":"sampleproject"}'
curl -s http://127.0.0.1:8080/tools/get_pypi_release \
  -H 'Content-Type: application/json' -d '{"package":"sampleproject","version":"4.0.0"}'
```

## Omi registration

Deploy this directory as an independent Python web service with HTTPS, install
`requirements.txt`, and start `uvicorn main:app --host 0.0.0.0 --port $PORT`.
The host must permit outbound HTTPS to `pypi.org`. Hosting is not provisioned by
this contribution.

Register the two POST chat tools from `/.well-known/omi-tools.json` in the Omi
app's external integration configuration. Use your service's HTTPS origin plus
the manifest's endpoint for each URL. No authentication or OAuth flow is required
for these public lookups. The manifest supplies the parameter schemas and
required fields. `/health` reports only that this service is running, not PyPI's
availability.

| Tool | Required parameters | Result |
| --- | --- | --- |
| `get_pypi_package` | `package` | Metadata for PyPI's current version |
| `get_pypi_release` | `package`, `version` | Metadata for the requested version |

Responses use Omi's `result` / `error` text envelope. Missing, wrongly typed or overlong parameters return HTTP 422. Invalid
package/version syntax and unsuccessful upstream lookups return HTTP 200 with
a readable error envelope; inspect `error` before using `result`.
Use package names, not PyPI URLs. Hyphens, underscores and dots in names follow
PyPI normalization. Versions follow PEP 440.

## What the answer means

The response presents publisher-supplied metadata: version, Python requirement,
summary, license, project links, declared dependencies and yanked status.
Missing fields are reported as unavailable. Long fields and dependency lists are
bounded for chat; the PyPI project link provides the source for fuller details.
Dependencies are declarations, including environment markers and extras; this
service does not resolve them for the user's machine. A yanked release is not
recommended merely because it is retrievable.

Metadata is not a package audit, compatibility guarantee or safety endorsement.
Project links are displayed as source data and are never fetched. Only the
requested package name and optional version are sent to PyPI; Omi user IDs,
conversation history and account credentials are neither required nor stored.
Do not put secrets in query parameters. The standalone service is unauthenticated;
operators should apply their hosting platform's normal access/rate controls.

## Tests

The hermetic endpoint tests live at
`backend/tests/unit/test_pypi_plugin.py` so the backend unit CI discovers them.
From the repository root, after setting up the backend test environment:

```bash
backend/.venv/bin/python -m pytest backend/tests/unit/test_pypi_plugin.py -q
```

The tests execute the actual ASGI routes while replacing only outbound HTTP with
a deterministic transport. They require no PyPI access or Omi credentials. The
curl examples above are optional live smoke checks, separate from hermetic CI.
